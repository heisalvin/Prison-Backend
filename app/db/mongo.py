from dotenv import load_dotenv
import os
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
# Load .env from project root
load_dotenv()

# Now os.getenv will see your MONGO_URI
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
client = MongoClient(MONGO_URI)
db = client["prison_fvs"]

officers_col = db["officers"]
inmates_col  = db.get_collection("inmates")
logs_col     = db["logs"]

inmates_col.create_index("inmate_id", unique=True)