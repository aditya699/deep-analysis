import redis
import os
from dotenv import load_dotenv

load_dotenv()

# Replace these with your actual values:
HOST = os.getenv("REDIS_HOST")
PORT = 6380
PASSWORD = os.getenv("REDIS_PASSWORD")

# Connect with SSL (required for Azure Redis)
r = redis.Redis(
    host=HOST,
    port=PORT,
    password=PASSWORD,
    ssl=True
)

# Set a value
r.set("testkey", "hello redis!")

# Get the value
value = r.get("testkey")

# Print result
print("Redis returned:", value.decode('utf-8'))
