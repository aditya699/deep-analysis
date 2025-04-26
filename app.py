'''
This is the main file for the Deep Analysis API.

NOTE:
1. This is a little longer task, so for v1 is still fast but later it can more deep,
   so we need a basic implementation of background tasks so that api call doesn't timeout.
'''
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from utils.file_processor import process_uploaded_file, get_task_status_from_db
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
    """Root endpoint that returns a welcome message"""
    return {"message": "Welcome to the Deep Analysis API"}

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

@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """
    Get the status of an analysis task
    """
    return await get_task_status_from_db(task_id)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)