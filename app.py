'''
This is the main file for the Deep Analysis API.

NOTE:
1. This is a little longer task, so for v1 is still fast but later it can more deep,
   so we need a basic implementation of background tasks so that api call doesn't timeout.
'''
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from utils.file_processor import process_uploaded_file, get_task_status_from_db
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from database.get_client import get_client
import uvicorn
from utils.db.process import get_blob_client, load_data_to_blob_storage, get_client_mongo, get_container_client, get_client_redis, get_task_status_for_dashboard
from utils.db.filters import get_filters
from azure.storage.blob import BlobServiceClient
from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore
from fastapi import Depends
import uuid
import redis.asyncio as aioredis
from utils.db.bgprocess import get_dashboard_title
from bson import ObjectId

# Initialize FastAPI app
app = FastAPI(
    title="Data Analysis Platform",
    description="API for generating data analysis reports and dashboards",
    version="1.0.0"
)

# Create routers for different sections
deep_analysis_router = APIRouter(
    prefix="/deep-analysis",
    tags=["Deep Analysis"],
    responses={404: {"description": "Not found"}},
)

dashboard_router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    responses={404: {"description": "Not found"}},
)

# Add CORS middleware to allow cross-origin requests from the React app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return HTMLResponse(content=open("templates/index.html").read())


@app.get("/health")
def health_check():
    """Health check endpoint to verify the API is running"""
    return {"status": "healthy"}

# Deep Analysis Endpoints
@deep_analysis_router.post("/analyze/")
async def analyze_data(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Upload a CSV file and start the analysis process in the background
    """
    return await process_uploaded_file(file, background_tasks)

@deep_analysis_router.get("/task/{task_id}")
async def get_task_status_endpoint(task_id: str):
    """
    Get the status of an analysis task primarily from MongoDB,
    with Redis used only for queue management.
    """
    # Always get task status from MongoDB for consistent data
    mongo_task = await get_task_status_from_db(task_id)

    # If task not found in MongoDB, check Redis queue status
    if not mongo_task:
        # Import the Redis function just for queue status
        from utils.redis_tasks import get_task_status
        redis_task = await get_task_status(task_id)
        if redis_task:
            return {
                "task_id": redis_task.get("task_id"),
                "status": redis_task.get("status", "pending"),
                "progress": redis_task.get("progress", 0),
                "message": redis_task.get("message", "Waiting in queue")
            }
        raise HTTPException(status_code=404, detail="Task not found")

    return mongo_task

# Dashboard Endpoints
@dashboard_router.post("/upload-file/")
async def upload_db_file(
    file: UploadFile = File(...),
    container_client: BlobServiceClient = Depends(get_container_client),
    db_client: AsyncIOMotorClient = Depends(get_client_mongo),
    redis_client: aioredis.Redis = Depends(get_client_redis)
):
    """
    Upload a file to the blob storage for dashboard generation
    
    Args:
        file: UploadFile - The file to upload to the blob storage

    Returns:
        Dictionary with file metadata and status
    """
    try:
        # Simply pass container_client directly, skipping the get_blob_client step
        response_dict = await load_data_to_blob_storage(file, container_client, db_client, redis_client)

        return response_dict
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@dashboard_router.get("/task")
async def get_db_task_status_endpoint(file_url: str, mongo_client: AsyncIOMotorClient = Depends(get_client_mongo)):
    """
    Get the status of an analysis task primarily from MongoDB,
    with Redis used only for queue management.
    """
    return await get_task_status_for_dashboard(file_url, mongo_client)

@dashboard_router.get("/get_all_filters")
async def get_all_filters(file_url: str, mongo_client: AsyncIOMotorClient = Depends(get_client_mongo)):
    """
    Get all filters for a dashboard
    """
    try:
        filters=await get_filters(file_url,mongo_client)
        if filters:
            return filters
        else:
            raise HTTPException(status_code=404, detail="No filters found") # 404 is not found
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) # 500 is internal server error

@app.on_event("startup")
async def startup_event():
    # Get database connection
    client = await get_client()
    db = client["Python-Data-Analyst"]
    tasks_collection = db["analysis_tasks"]

    # Find all tasks that were left in "processing" state
    interrupted_tasks = await tasks_collection.find(
        {"status": "processing"}
    ).to_list(length=None)

    # Update their status to indicate server restart
    for task in interrupted_tasks:
        await tasks_collection.update_one(
            {"task_id": task["task_id"]},
            {"$set": {
                "status": "failed",
                "message": "Analysis was interrupted due to server resource constraints. Please try again later in 5 minutes.",
                "updated_at": datetime.now()
            }}
        )

    print(f"Updated {len(interrupted_tasks)} interrupted tasks due to server restart")

# Include routers in the main app
app.include_router(deep_analysis_router)
app.include_router(dashboard_router)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)