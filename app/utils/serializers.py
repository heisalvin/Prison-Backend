from bson import ObjectId

def serialize_doc(doc):
    """Convert MongoDB ObjectId and datetime into JSON-safe formats"""
    if not doc:
        return doc

    serialized = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            serialized[key] = str(value)
        elif hasattr(value, "isoformat"):  # datetime
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized

def serialize_list(docs):
    return [serialize_doc(doc) for doc in docs]
