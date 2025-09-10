from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from bson import ObjectId

from app.db.mongo import officers_col
from app.routes.auth import get_current_officer

router = APIRouter()  # main.py mounts with prefix="/officers"

# ---------- Pydantic schemas ----------
class OfficerIn(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)
    prison_name: str = Field(..., min_length=1)


class OfficerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)
    prison_name: Optional[str] = None


class OfficerOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    prison_name: str
    recognitions_today: int = 0


# ---------- helper ----------
def officer_helper(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "prison_name": doc.get("prison_name", ""),
        "recognitions_today": doc.get("recognitions_today", 0),
    }


# ---------- Endpoints ----------
@router.get("/", response_model=List[OfficerOut])
async def list_officers(current=Depends(get_current_officer)):
    docs = list(officers_col.find())
    return [officer_helper(d) for d in docs]


@router.get("/count", response_model=int)
async def count_officers(current=Depends(get_current_officer)):
    """
    Returns the total number of registered officers.
    """
    return officers_col.count_documents({})


@router.get("/recognitions/today", response_model=int)
async def total_recognitions_today(current=Depends(get_current_officer)):
    """
    Returns the sum of recognitions_today across all officers.
    """
    pipeline = [
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$recognitions_today", 0]}}}}
    ]
    result = list(officers_col.aggregate(pipeline))
    return result[0]["total"] if result else 0


@router.get("/{id}", response_model=OfficerOut)
async def get_officer(id: str, current=Depends(get_current_officer)):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid officer id")
    doc = officers_col.find_one({"_id": ObjectId(id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Officer not found")
    return officer_helper(doc)


@router.post("/", response_model=OfficerOut, status_code=status.HTTP_201_CREATED)
async def create_officer(payload: OfficerIn, current=Depends(get_current_officer)):
    # prevent email duplicates
    if officers_col.find_one({"email": payload.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    doc = {
        "name": payload.name,
        "email": payload.email,
        "password": payload.password,  # plain (⚠️ hash in prod!)
        "prison_name": payload.prison_name,
        "recognitions_today": 0,
    }
    result = officers_col.insert_one(doc)
    return officer_helper(officers_col.find_one({"_id": result.inserted_id}))


@router.put("/{id}", response_model=OfficerOut)
async def update_officer(id: str, payload: OfficerUpdate, current=Depends(get_current_officer)):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid officer id")
    doc = officers_col.find_one({"_id": ObjectId(id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Officer not found")

    update = {}
    if payload.name is not None:
        update["name"] = payload.name
    if payload.email is not None:
        existing = officers_col.find_one({"email": payload.email, "_id": {"$ne": ObjectId(id)}})
        if existing:
            raise HTTPException(status_code=400, detail="Email already used by another officer")
        update["email"] = payload.email
    if payload.password is not None:
        update["password"] = payload.password
    if payload.prison_name is not None:
        update["prison_name"] = payload.prison_name

    if update:
        officers_col.update_one({"_id": ObjectId(id)}, {"$set": update})

    return officer_helper(officers_col.find_one({"_id": ObjectId(id)}))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_officer(id: str, current=Depends(get_current_officer)):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid officer id")
    res = officers_col.delete_one({"_id": ObjectId(id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Officer not found")
    return {}
