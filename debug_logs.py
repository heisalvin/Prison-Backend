# debug_logs.py
from app.db.mongo import logs_col

for log in logs_col.find({}, {"_id": 0, "recognized_by": 1}):
    print(log)
