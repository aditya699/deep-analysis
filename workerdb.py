'''
Implementing a worker node that will be used to process the tasks in the quque (for our dashboard generation)
'''
import asyncio
import json
import redis.asyncio as aioredis
from utils.db.process import dequeue_task, get_client_mongo, get_client_redis,get_blob_client,get_container_client
import os
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient #type: ignore


load_dotenv()

async def worker_process():
    print("Starting worker process...")
    
    # Get clients
    redis_client = await get_client_redis()
    mongo_client = await get_client_mongo()
    container_client = await get_container_client()
    
    # Get MongoDB collection for updating task status
    db = mongo_client["Python-Data-Analyst"]
    collection = db["file_uploads-db"]
    
    try:
        # Continuous loop to keep checking for new tasks
        while True:
            print("Waiting for new tasks...")
            
            # Try to get a task from the queue
            task = await dequeue_task(redis_client)
            
            if task:
                print(f"Processing task: {task['file_name']}")
                
                # Update task status in MongoDB to "processing"
                await collection.update_one(
                    {"file_name": task['file_name']}, 
                    {"$set": {"status": "processing", "updated_at": datetime.now().isoformat()}}
                )
                
                # Process the task (we'll implement this in the next step)
                # For now just add a placeholder
                print(f"Task data: {task}")
                
                # Sleep a bit to avoid tight loops
                await asyncio.sleep(1)
            else:
                # No tasks in the queue, wait a bit before checking again
                await asyncio.sleep(5)
                
    except KeyboardInterrupt:
        print("Worker stopped by user")
    except Exception as e:
        print(f"Worker error: {str(e)}")
    finally:
        # Close connections
        await redis_client.close()
        mongo_client.close()

if __name__ == "__main__":
    asyncio.run(worker_process())


