'''
Author: Aditya Bhatt 10:17 AM 09-05-2025

NOTE:    

BUG(Not a bug but a note):
1.df=await read_file_from_blob_to_df(file_url)
This operation is little tricky because "df" is a pandas dataframe and we need to load it in the memory to process it.(All this can not be done in the api server)
So this is will all this needs to be done in a worker node.Before working on filters we need to fix this


'''
from motor.motor_asyncio import AsyncIOMotorClient #type: ignore
from utils.db.bgprocess import read_file_from_blob_to_df


async def get_filters(file_url:str,mongo_client:AsyncIOMotorClient):
    df=await read_file_from_blob_to_df(file_url)
    columns_datatypes=df.dtypes.to_dict()
    output_dict={}
    for column,datatype in columns_datatypes.items():
        # Convert numpy dtype to string to avoid serialization issues
        output_dict[column]={"type":str(datatype)}

    # Fo iteration 1 we will remove all columns 
    return output_dict










