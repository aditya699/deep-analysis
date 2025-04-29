"""
Worker script to process tasks from the Redis queue with parallel processing
"""
import asyncio
import os
import sys
import multiprocessing
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Load environment variables
load_dotenv()

from utils.redis_tasks import dequeue_task
from utils.file_processor import run_analysis
from database.get_client import get_client

# Maximum concurrent tasks per worker process
MAX_CONCURRENT_TASKS = 2

async def process_tasks_loop():
    """
    Asyncio worker loop that processes multiple tasks concurrently
    """
    print(f"Starting worker process (PID: {os.getpid()}) with {MAX_CONCURRENT_TASKS} concurrent tasks...")
    
    # Set to keep track of running tasks
    running_tasks = set()
    
    while True:
        try:
            # Clean up completed tasks
            done_tasks = {task for task in running_tasks if task.done()}
            for task in done_tasks:
                # Check for exceptions
                if task.exception():
                    print(f"Task failed with error: {task.exception()}")
                running_tasks.remove(task)
            
            # If we can process more tasks
            if len(running_tasks) < MAX_CONCURRENT_TASKS:
                # Get a new task from the queue
                task = await dequeue_task()
                
                if task:
                    task_id = task["task_id"]
                    file_url = task["file_url"]
                    
                    print(f"Starting task {task_id} (concurrent tasks: {len(running_tasks)+1})")
                    
                    # Create a MongoDB client for this task
                    client = await get_client()
                    
                    # Create a new asyncio task and add it to our set
                    analysis_task = asyncio.create_task(
                        run_analysis(task_id, file_url, client)
                    )
                    running_tasks.add(analysis_task)
                else:
                    # No tasks available, wait a bit
                    await asyncio.sleep(1)
            else:
                # At maximum concurrent tasks, wait for some to complete
                await asyncio.sleep(0.5)
                
        except Exception as e:
            print(f"Error in worker loop: {e}")
            await asyncio.sleep(5)

def start_worker_process():
    """
    Start an asyncio event loop in a separate process
    """
    asyncio.run(process_tasks_loop())

if __name__ == "__main__":
    # Number of worker processes to spawn (usually = number of CPU cores)
    NUM_PROCESSES = max(1, multiprocessing.cpu_count() - 1)
    
    print(f"Starting {NUM_PROCESSES} worker processes...")
    
    # Create and start the worker processes
    processes = []
    for i in range(NUM_PROCESSES):
        p = multiprocessing.Process(target=start_worker_process)
        p.start()
        processes.append(p)
        print(f"Started worker process {i+1} (PID: {p.pid})")
    
    # Wait for all processes to finish (they won't normally finish)
    for p in processes:
        p.join()