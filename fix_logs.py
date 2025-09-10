# fix_logs.py
from bson import ObjectId
from app.db.mongo import logs_col

count = 0
for log in logs_col.find():
    if isinstance(log.get("recognized_by"), str):
        try:
            logs_col.update_one(
                {"_id": log["_id"]},
                {"$set": {"recognized_by": ObjectId(log["recognized_by"])}}
            )
            count += 1
        except Exception as e:
            print(f"Failed to update log {log['_id']}: {e}")

print(f"✅ Fixed {count} log entries.")
