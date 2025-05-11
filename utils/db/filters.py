'''
Author: Aditya Bhatt 10:17 AM 09-05-2025

NOTE:    

BUG(Not a bug but a note):
1.df=await read_file_from_blob_to_df(file_url)
This operation is little tricky because "df" is a pandas dataframe and we need to load it in the memory to process it.(All this can not be done in the api server)
So this is will all this needs to be done in a worker node.Before working on filters we need to fix this
(Fixed)

'''
from motor.motor_asyncio import AsyncIOMotorClient #type: ignore
from fastapi import HTTPException

async def get_filters(file_url:str,mongo_client:AsyncIOMotorClient):
    try:
        db=mongo_client["Python-Data-Analyst"]
        collection=db["file_uploads-db"]
        task=await collection.find_one({"file_url":file_url})
        if task:
            return task["all_filters"]
        else:
            return None
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    











