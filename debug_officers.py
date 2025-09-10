from app.db.mongo import officers_col

for o in officers_col.find({}, {"_id": 1, "name": 1}):
    print(o)
