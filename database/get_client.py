import asyncio
from motor.motor_asyncio import AsyncIOMotorClient #type: ignore
from pymongo.server_api import ServerApi #type: ignore
import os
from dotenv import load_dotenv

load_dotenv()

async def get_client():
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

