'''
This file will be used to implement functions that will be doing the heavy lifting of the background tasks

'''
import pandas as pd
import io
import requests
from fastapi import HTTPException
from utils.db.process import get_client_mongo
from azure.storage.blob import BlobServiceClient, ContainerClient
from datetime import datetime
from utils.db.process import get_blob_client, get_container_client

async def read_file_from_blob_to_df(blob_url: str) -> pd.DataFrame:
    '''
    Reads a file from blob storage and converts it to a pandas DataFrame.
    This function is designed to run in the background and process files asynchronously.
    
    Args:
        blob_url (str): The URL of the blob storage file
        
    Returns:
        pd.DataFrame: The data loaded into a pandas DataFrame
        
    Raises:
        HTTPException: If there's an error reading the file
    '''
    try:
        # Download the file content using requests instead of trying to access blob directly
        # This is more reliable when working with URLs
        response = requests.get(blob_url)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Convert to DataFrame
        df = pd.read_csv(io.BytesIO(response.content))
        
        # Update the process in mongo db
        mongo_client = await get_client_mongo()
        db = mongo_client["Python-Data-Analyst"]
        collection = db["file_uploads-db"]
        await collection.update_one(
            {"file_url": blob_url},
            {"$set": {
                "status": "Data Loaded in DataFrame",
                "updated_at": datetime.now().isoformat()
            }}
        )
        return df
    except Exception as e:
        # Update MongoDB with error status
        mongo_client = await get_client_mongo()
        db = mongo_client["Python-Data-Analyst"]
        collection = db["file_uploads-db"]
        await collection.update_one(
            {"file_url": blob_url},
            {"$set": {
                "status": "error",
                "error_message": str(e),
                "updated_at": datetime.now().isoformat()
            }}
        )
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

async def process_file_background(blob_url: str) -> str:
    '''
    Background task to process files from blob storage.
    This function will be called by the background worker.
    
    Args:
        blob_url (str): The URL of the blob storage file
        
    Returns:
        str: A message indicating the processing result
        
    Raises:
        HTTPException: If there's an error processing the file
    '''
    try:
        # Update MongoDB with processing status
        mongo_client = await get_client_mongo()
        db = mongo_client["Python-Data-Analyst"]
        collection = db["file_uploads-db"]
        
        try:
            df = await read_file_from_blob_to_df(blob_url)
            columns = df.columns.tolist()
            
            # Update MongoDB with success status
            await collection.update_one(
                {"file_url": blob_url},
                {"$set": {
                    "status": "completed",
                    "columns": columns,
                    "updated_at": datetime.now().isoformat()
                }}
            )
            
            return f"Processing completed. Columns: {columns}"
        except Exception as e:
            # Update MongoDB with error status
            await collection.update_one(
                {"file_url": blob_url},
                {"$set": {
                    "status": "failed",
                    "error_message": str(e),
                    "updated_at": datetime.now().isoformat()
                }}
            )
            raise e
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))