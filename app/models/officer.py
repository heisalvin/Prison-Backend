from pydantic import BaseModel, EmailStr, Field
from typing import Optional


# Request model for creating an officer (now requires prison_name)
class OfficerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    prison_name: str = Field(..., min_length=1, max_length=100)


# Request model for updating an officer (prison_name optional)
class OfficerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    email: Optional[EmailStr]
    password: Optional[str] = Field(None, min_length=8)
    prison_name: Optional[str] = Field(None, min_length=1, max_length=100)


# Response model (what we return to clients)
class OfficerOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    # Make prison_name optional so missing values won't raise validation errors
    prison_name: Optional[str] = None
    # recognitions_today can be absent; default to 0
    recognitions_today: Optional[int] = 0

    class Config:
        from_attributes = True


# Internal DB model (if you ever use it)
class OfficerInDB(BaseModel):
    id: str
    name: str
    email: EmailStr
    password: str  # storing plain password per your request (not secure for prod)
    prison_name: str
    recognitions_today: int = 0

    class Config:
        from_attributes = True
