import json
from redis.asyncio import Redis
from datetime import datetime
from dotenv import load_dotenv
import os
load_dotenv()

# Redis connection parameters
HOST = os.getenv("REDIS_HOST")
PORT = 6380
PASSWORD = os.getenv("REDIS_PASSWORD")

# Create async Redis client
redis_client = Redis(
    host=HOST,
    port=PORT,
    password=PASSWORD,
    ssl=True,
    decode_responses=True  # Automatically decode responses to strings
)

# Task queue name
TASK_QUEUE = "analysis_tasks"

async def enqueue_task(task_id:str,file_url:str):
    """
    Add a task to the analysis queue.

    Args:
        task_id: Unique identifier for the task
        file_url: URL of the file to be analyzed
    Returns:
        bool:True if task is added successfully, False otherwise
    """
    try:
        task_data={
            "task_id":task_id,
            "file_url":file_url,
            "status":"pending",
            "progress":0,
            "message":"Task queued,waiting for processing",
            "created_at":datetime.now().isoformat(),
            "updated_at":datetime.now().isoformat()
        }
         
         #store task data with task_id as the key
        await redis_client.set(f"task:{task_id}", json.dumps(task_data))
         #add it to a processing queue
        await redis_client.lpush(TASK_QUEUE,task_id) #we are using lpush so worker should rpop.
        return True
    except Exception as e:
        print(f"Error enqueuing task: {e}")
        return False
    

async def get_task_status(task_id: str):
    """
    Get the current status and data for a task
    
    Args:
        task_id: The task identifier
    
    Returns:
        dict: Task data or None if not found
    """
    try:
        task_data = await redis_client.get(f"task:{task_id}")
        if task_data:
            return json.loads(task_data)
        return None
    except Exception as e:
        print(f"Error getting task status: {e}")
        return None

async def dequeue_task():
    """
    Get the next task from the queue for processing.
    Uses BRPOP which blocks until a task is available.
    
    Returns:
        dict: Task data or None if no task available
    """
    try:
        # Get the next task from the queue with a timeout of 1 second
        # BRPOP is a blocking right pop - waits for a task and removes it from the queue
        result = await redis_client.brpop(TASK_QUEUE, timeout=1)
        
        if not result:
            return None
            
        # Extract the task_id from the result (format is [queue_name, task_id])
        _, task_id = result
        
        # Get the full task data
        task_data = await get_task_status(task_id)
        
        if task_data:
            # Update the task status to "processing"
            task_data["status"] = "processing"
            task_data["updated_at"] = datetime.now().isoformat()
            task_data["message"] = "Task processing started"
            
            # Save the updated task data
            await redis_client.set(f"task:{task_id}", json.dumps(task_data))
            
        return task_data
        
    except Exception as e:
        print(f"Error dequeuing task: {e}")
        return None