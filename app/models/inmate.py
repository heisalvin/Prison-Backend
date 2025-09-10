from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

# ─── Embedding Model ──────────────────────────────────────────────────────────
class Embedding(BaseModel):
    vector: List[float]
    filename: str
    uploaded_at: datetime

# ─── Extra Info Models ─────────────────────────────────────────────────────────
class InmateExtraInfo(BaseModel):
    cell: Optional[str] = None
    crime: Optional[str] = None
    sentence: Optional[str] = None
    age: Optional[int] = None
    legal_status: Optional[str] = None
    facility_name: Optional[str] = None
    sex: Optional[str] = Field(default=None, description="Sex of the inmate: male or female")

# ─── Base Model ───────────────────────────────────────────────────────────────
class InmateBase(BaseModel):
    inmate_id: str = Field(..., description="Unique inmate identifier")
    name: str
    extra_info: Optional[InmateExtraInfo] = Field(default_factory=InmateExtraInfo)

# ─── Create & Update Models ────────────────────────────────────────────────────
class InmateCreate(InmateBase):
    pass  # same fields as InmateBase

class InmateUpdate(BaseModel):
    name: Optional[str] = None
    extra_info: Optional[InmateExtraInfo] = None

# ─── Output Model ──────────────────────────────────────────────────────────────
class InmateOut(BaseModel):
    id: str
    inmate_id: str
    name: str
    images: List[Dict[str, Any]]  # could be List[Embedding] if you want typed embeddings
    extra_info: InmateExtraInfo
    created_at: datetime
