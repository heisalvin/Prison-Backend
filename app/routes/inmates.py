from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Path, Form
from typing import List, Optional
from datetime import datetime

from app.db.mongo import inmates_col
from app.routes.auth import get_current_officer
from app.utils.face_tools import get_embedding, ALLOWED_EXT
from app.models.inmate import InmateOut

router = APIRouter(tags=["inmates"])
MAX_IMAGES = 5


def format_inmate(doc: dict) -> dict:
    """
    Formats a MongoDB inmate document for JSON output.
    """
    return {
        "id": str(doc["_id"]),
        "inmate_id": doc["inmate_id"],
        "name": doc["name"],
        "images": doc.get("embeddings", []),
        "extra_info": doc.get("extra_info", {}),
        "created_at": doc["created_at"].isoformat(),
        "registered_by": doc.get("registered_by")
    }


@router.post("/", response_model=InmateOut, status_code=201)
async def create_inmate(
    inmate_id: str = Form(..., description="Unique inmate identifier"),
    name: str = Form(..., description="Inmate name"),
    cell: Optional[str] = Form(None),
    crime: Optional[str] = Form(None),
    sentence: Optional[str] = Form(None),
    age: Optional[int] = Form(None),
    legal_status: Optional[str] = Form(None),
    facility_name: Optional[str] = Form(None),
    sex: Optional[str] = Form(None, description="Sex of inmate (male or female)"),
    images: List[UploadFile] = File(..., description="1–5 face images"),
    officer=Depends(get_current_officer),
):
    """
    Create a new inmate with optional extra_info and face embeddings.
    """
    # Check for duplicate inmate_id
    if inmates_col.find_one({"inmate_id": inmate_id}):
        raise HTTPException(status_code=400, detail="Inmate ID already exists")

    # Validate age
    if age is not None:
        try:
            age = int(age)
        except ValueError:
            raise HTTPException(400, "Age must be an integer")

    extra_info = {
        "cell": cell,
        "crime": crime,
        "sentence": sentence,
        "age": age,
        "legal_status": legal_status,
        "facility_name": facility_name,
        "sex": sex
    }

    # Validate number of images
    if not (1 <= len(images) <= MAX_IMAGES):
        raise HTTPException(400, "Upload between 1 and 5 images")

    embeddings = []
    for img in images:
        ext = img.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"Invalid image type: .{ext}")
        content = await img.read()
        vec = get_embedding(content)
        embeddings.append({
            "vector": vec.tolist(),
            "filename": img.filename,
            "uploaded_at": datetime.utcnow()
        })

    registered_by = str(officer.get("_id") or officer.get("id"))
    if not registered_by:
        raise HTTPException(400, "Could not determine officer ID")

    doc = {
        "inmate_id": inmate_id,
        "name": name,
        "extra_info": extra_info,
        "embeddings": embeddings,
        "registered_by": registered_by,
        "created_at": datetime.utcnow()
    }

    res = inmates_col.insert_one(doc)
    created = inmates_col.find_one({"_id": res.inserted_id})
    return format_inmate(created)


@router.get("/", response_model=List[InmateOut])
def list_inmates(officer=Depends(get_current_officer)):
    """
    List all inmates.
    """
    return [format_inmate(doc) for doc in inmates_col.find({})]


@router.get("/{inmate_id}", response_model=InmateOut)
def get_inmate(inmate_id: str = Path(...), officer=Depends(get_current_officer)):
    """
    Get a single inmate by inmate_id.
    """
    doc = inmates_col.find_one({"inmate_id": inmate_id})
    if not doc:
        raise HTTPException(404, "Inmate not found")
    return format_inmate(doc)


@router.patch("/{inmate_id}", response_model=InmateOut)
async def update_inmate(
    inmate_id: str,
    name: Optional[str] = Form(None),
    cell: Optional[str] = Form(None),
    crime: Optional[str] = Form(None),
    sentence: Optional[str] = Form(None),
    age: Optional[int] = Form(None),
    legal_status: Optional[str] = Form(None),
    facility_name: Optional[str] = Form(None),
    sex: Optional[str] = Form(None, description="Sex of inmate (male or female)"),
    officer=Depends(get_current_officer)
):
    """
    Update inmate fields. Supports partial updates for name and extra_info.
    """
    update_data = {}

    if name is not None:
        update_data["name"] = name

    # Dot notation for extra_info
    if cell is not None:
        update_data["extra_info.cell"] = cell
    if crime is not None:
        update_data["extra_info.crime"] = crime
    if sentence is not None:
        update_data["extra_info.sentence"] = sentence
    if age is not None:
        try:
            update_data["extra_info.age"] = int(age)
        except ValueError:
            raise HTTPException(400, "Age must be an integer")
    if legal_status is not None:
        update_data["extra_info.legal_status"] = legal_status
    if facility_name is not None:
        update_data["extra_info.facility_name"] = facility_name
    if sex is not None:
        update_data["extra_info.sex"] = sex

    if not update_data:
        raise HTTPException(400, "No fields provided for update")

    result = inmates_col.update_one({"inmate_id": inmate_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(404, "Inmate not found")

    updated = inmates_col.find_one({"inmate_id": inmate_id})
    return format_inmate(updated)


@router.delete("/{inmate_id}", status_code=204)
async def delete_inmate(
    inmate_id: str,
    officer=Depends(get_current_officer),
):
    """
    Delete an inmate by inmate_id.
    """
    res = inmates_col.delete_one({"inmate_id": inmate_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Inmate not found")
    return {"message": "Inmate deleted successfully"}
