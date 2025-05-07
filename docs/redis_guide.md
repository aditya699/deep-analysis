# Redis Task Queue Implementation

## Overview
Redis is an in-memory data structure store that can be used as a database, cache, and message broker. In our application, we use Redis as a task queue to manage asynchronous processing.

## Key Concepts
- **Redis as a Queue**: Redis lists provide an efficient way to implement FIFO (First In, First Out) queues
- **Task Serialization**: Tasks are serialized to JSON before being stored in Redis
- **Asynchronous Processing**: Redis operations are performed asynchronously using redis.asyncio

## Task Enqueuing
The following function adds a new task to our Redis queue:

```python
async def enqueue_task(task_data):
    task_data["status"] = "queued"
    # Push the task as JSON string to the end of the list
    await redis_client.rpush("task_queue", json.dumps(task_data))
```

# LRANGE helps you view all the list items in the queue
127.0.0.1:6379> LRANGE task_queue 0 -1
1) "{\"file_name\": \"51b1ec9d-d627-436e-a1b9-b42a61b130d6\", \"created_at\": \"2025-05-07T16:55:43.382828\", \"updated_at\": \"2025-05-07T16:55:43.382828\", \"status\": \"queued\"}"
