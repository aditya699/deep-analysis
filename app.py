'''
This is the main file for the Deep Analysis API.

NOTE:
1. This is a little longer task, so for v1 is still fast but later it can more deep,
   so we need a basic implementation of background tasks so that api call doesn't timeout.
'''
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from utils.file_processor import process_uploaded_file, get_task_status_from_db
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from database.get_client import get_client
import uvicorn

# Initialize FastAPI app
app = FastAPI(
    title="Deep Analysis API",
    description="API for generating data analysis reports",
    version="1.0.0"
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

@app.post("/analyze/")
async def analyze_data(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Upload a CSV file and start the analysis process in the background
    """
    return await process_uploaded_file(file, background_tasks)
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
                "message": "Analysis was interrupted due to server resource constraints. Please try again later in 5 minutes.",
                "updated_at": datetime.now()
            }}
        )
    
    print(f"Updated {len(interrupted_tasks)} interrupted tasks due to server restart")

@app.get("/task/{task_id}")
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

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)