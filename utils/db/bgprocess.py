'''
This file will be used to implement functions that will be doing the heavy lifting of the background tasks

'''

import pandas as pd
import io
import requests
from fastapi import HTTPException

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
        response = requests.get(blob_url)
        response.raise_for_status()
        return pd.read_csv(io.StringIO(response.text))
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading CSV: {str(e)}")

async def process_file_background(blob_url: str) -> pd.DataFrame:
    '''
    Background task to process files from blob storage.
    This function will be called by the background worker.
    
    Args:
        blob_url (str): The URL of the blob storage file
        
    Returns:
        pd.DataFrame: The data loaded into a pandas DataFrame
        
    Raises:
        HTTPException: If there's an error processing the file
    '''
    try:
        df = await read_file_from_blob_to_df(blob_url)
        return df
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))