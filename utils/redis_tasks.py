import json
from redis.asyncio import Redis
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
load_dotenv()


# Redis connection parameters
HOST = os.getenv("REDIS_HOST")
PORT = 6380
PASSWORD = os.getenv("REDIS_PASSWORD")

# Add these for additional queues(processing queue)
PROCESSING_QUEUE = "analysis_tasks_processing"  # Queue for tasks being processed
VISIBILITY_TIMEOUT = 25 * 60  # 25 minutes in seconds

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
         #add it to a TASK_QUEUE
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
    print("I am being called")
    try:
        task_data = await redis_client.get(f"task:{task_id}")
        print(f"Task data: {task_data}")
        if task_data:
            return json.loads(task_data)
        return None
    except Exception as e:
        print(f"Error getting task status: {e}")
        return None

async def dequeue_task():
    """
    Get the next task from the queue for processing.
    Uses BRPOPLPUSH to atomically move the task from waiting queue to processing queue.
    
    Returns:
        dict: Task data or None if no task available
    """
    try:
        # BRPOPLPUSH atomically moves an item from TASK_QUEUE to PROCESSING_QUEUE
        task_id = await redis_client.brpoplpush(TASK_QUEUE, PROCESSING_QUEUE, timeout=1)
        
        if not task_id:
            return None
            
        # Get the full task data
        task_data_str = await redis_client.get(f"task:{task_id}")
        if task_data_str:
            task_data = json.loads(task_data_str)
            
            # Set lease expiration time (25 minutes from now)
            lease_expires = (datetime.now() + timedelta(seconds=VISIBILITY_TIMEOUT)).isoformat()
            
            # Update the task status to "processing" and add lease info
            task_data["status"] = "processing"
            task_data["updated_at"] = datetime.now().isoformat()
            task_data["message"] = "Task processing started"
            task_data["lease_expires"] = lease_expires
            
            # Save the updated task data
            await redis_client.set(f"task:{task_id}", json.dumps(task_data))
            
            return task_data
        
        return None
        
    except Exception as e:
        print(f"Error dequeuing task: {e}")
        return None
    
async def ack_task(task_id: str):
    """
    Acknowledge task completion - remove it from the processing queue.
    Called when a task completes successfully.
    
    Args:
        task_id: The task identifier
    
    Returns:
        bool: True if acknowledged successfully, False otherwise
    """
    try:
        # Remove the task from the processing queue
        await redis_client.lrem(PROCESSING_QUEUE, 0, task_id)
        return True
    except Exception as e:
        print(f"Error acknowledging task: {e}")
        return False
    

async def requeue_stale_tasks():
    """
    Check for tasks with expired leases and move them back to the main queue.
    This should be run periodically to rescue tasks from crashed workers.
    
    Returns:
        int: Number of stale tasks that were requeued
    """
    try:
        now = datetime.now()
        stale_tasks = []
        
        # Get all tasks in the processing queue
        processing_tasks = await redis_client.lrange(PROCESSING_QUEUE, 0, -1)
        
        for task_id in processing_tasks:
            # Get the task data
            task_data_str = await redis_client.get(f"task:{task_id}")
            if not task_data_str:
                continue
                
            task_data = json.loads(task_data_str)
            
            # Check if lease has expired
            if "lease_expires" in task_data:
                lease_expires = datetime.fromisoformat(task_data["lease_expires"])
                
                if now > lease_expires:
                    # Lease expired - task was abandoned
                    stale_tasks.append(task_id)
                    
                    # Update the task data
                    task_data["status"] = "pending"
                    task_data["message"] = "Task requeued after worker timeout"
                    task_data["updated_at"] = now.isoformat()
                    if "lease_expires" in task_data:
                        del task_data["lease_expires"]
                    
                    # Save the updated task data
                    await redis_client.set(f"task:{task_id}", json.dumps(task_data))
        
        # Move all stale tasks back to the main queue
        for task_id in stale_tasks:
            # Remove from processing queue
            await redis_client.lrem(PROCESSING_QUEUE, 0, task_id)
            # Add back to main queue
            await redis_client.lpush(TASK_QUEUE, task_id)
            
            print(f"Requeued stale task: {task_id}")
            
        return len(stale_tasks)
        
    except Exception as e:
        print(f"Error requeuing stale tasks: {e}")
        return 0
    
