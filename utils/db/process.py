'''
This file contains code to load the data and put in blob storage
'''

from fastapi import UploadFile
import uuid
from azure.storage.blob import BlobServiceClient
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient #type: ignore
from pymongo.server_api import ServerApi #type: ignore
from datetime import datetime
from fastapi import HTTPException
from bson import ObjectId
import json
import redis.asyncio as aioredis
import pandas as pd
import io
import requests


load_dotenv()   


async def get_container_client()->BlobServiceClient:
    '''
    This function returns a container client, and can be used in any downstream function where a container client is needed
    Returns:
        ContainerClient
    '''
    os.environ["BLOB_STORAGE_ACCOUNT_KEY"]=os.getenv("BLOB_STORAGE_ACCOUNT_KEY")
    #Get the service client
    blob_service_client = BlobServiceClient.from_connection_string(os.getenv("BLOB_STORAGE_ACCOUNT_KEY"))
    #Get the container client
    container_client = blob_service_client.get_container_client("images-analysis")
    return container_client


async def get_blob_client(container_client: BlobServiceClient, unique_file_name: str) -> BlobServiceClient:
    '''
    This function returns a blob client for a specific file
    Args:
        container_client: The container client
        unique_file_name: The unique name of the file
    Returns:
        BlobClient
    '''
    return container_client.get_blob_client(unique_file_name)


async def get_client_redis():
    redis_client = aioredis.from_url("redis://localhost:6379", decode_responses=True)
    return redis_client

async def enqueue_task(task_data, redis_client):
    task_data["status"] = "queued"
    # Push the task as JSON string to the end of the list
    await redis_client.rpush("task_queue", json.dumps(task_data))

async def dequeue_task(redis_client):
    # Pop a task from the left (start) of the list → FIFO
    task_json = await redis_client.lpop("task_queue")
    if task_json:
        task_data = json.loads(task_json)
        return task_data
    return None  # No tasks left

async def get_client_mongo():   
    uri = os.getenv('uri')
    try:
        if not uri:
            print("Error: MongoDB URI not found in environment variables")
            return
        
        client = AsyncIOMotorClient(uri, server_api=ServerApi('1'))
        return client
    except Exception as e:
        print(f"Failed to connect to MongoDB: {str(e)}")
        return None

async def load_data_to_blob_storage(file:UploadFile, blob_client=None, mongo_client=None, redis_client=None)->dict:
    '''
    Args:
        file:UploadFile
        blob_client:BlobServiceClient(To upload the file to blob storage)
        mongo_client:AsyncIOMotorClient(To save the file metadata to mongo db)
        redis_client:Redis client for task queue management

    Returns:
        A dictionary with the following keys:
            {file_name:str, file_url:str, created_at:datetime, updated_at:datetime, status:str}

    NOTE: In the route we can define the blob_client and mongo_client as a dependency and pass it to this function
    '''
    try:
        # Create a unique file name
        unique_file_name = str(uuid.uuid4())
        
        # Read file content
        file_content = await file.read()
        
        # Upload the file to blob storage
        blob_client.upload_blob(file_content, overwrite=True)
        
        #Get the storage account name from connection string
        storage_account = os.getenv("BLOB_STORAGE_ACCOUNT_KEY").split(";")[1].split("=")[1]
        
        current_time = datetime.now()
        
        data_dict = {
            "file_name": unique_file_name,
            "file_url": f"https://{storage_account}.blob.core.windows.net/images-analysis/{unique_file_name}",
            "created_at": current_time,
            "updated_at": current_time,
            "status": "File uploaded successfully"
        }
        
        db = mongo_client["Python-Data-Analyst"]
        collection = db["file_uploads-db"]
        result = await collection.insert_one(data_dict)

        # Convert datetime to ISO format string for Redis
        redis_dict = {
            "file_name": unique_file_name,
            "created_at": current_time.isoformat(),
            "updated_at": current_time.isoformat(),
            "status": "Task queued successfully",
            "file_url": f"https://{storage_account}.blob.core.windows.net/images-analysis/{unique_file_name}" #This is important since using the url can load the file and do anything you want to do with it
        }

        #Post upload we need to push the task to the queue
        await enqueue_task(redis_dict, redis_client)

        #Need to update the mongo db with the status task queued successfully
        await collection.update_one({"_id": result.inserted_id}, {"$set": {"status": "Task queued successfully"}})
        
        # Convert ObjectId to string in the response
        data_dict["_id"] = str(result.inserted_id)
        return data_dict
    
    except Exception as e:
        print(f"Error uploading file to blob storage: {str(e)}")
        error_dict = {
            "file_name": unique_file_name,
            "file_url": f"https://{storage_account}.blob.core.windows.net/images-analysis/{unique_file_name}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "status": f"Error uploading file: {str(e)}",
            "class": "error"
        }
        raise HTTPException(status_code=500, detail=error_dict)

async def read_file_from_blob_to_df(blob_url: str) -> pd.DataFrame:
    '''
    Reads a file from blob storage and converts it to a pandas DataFrame
    
    Args:
        blob_url (str): The URL of the blob storage file
        
    Returns:
        pd.DataFrame: The data loaded into a pandas DataFrame
        
    Raises:
        HTTPException: If there's an error reading the file
    '''
    try:
        # Download the file content
        response = requests.get(blob_url)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Get the file extension from the URL
        file_extension = blob_url.split('.')[-1].lower()
        
        # Read the content into a pandas DataFrame based on file type
        if file_extension in ['csv']:
            df = pd.read_csv(io.StringIO(response.text))
        elif file_extension in ['xlsx', 'xls']:
            df = pd.read_excel(io.BytesIO(response.content))
        elif file_extension in ['json']:
            df = pd.read_json(io.StringIO(response.text))
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_extension}. Supported types are: csv, xlsx, xls, json"
            )
            
        return df
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error downloading file from blob storage: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading file into DataFrame: {str(e)}"
        )




