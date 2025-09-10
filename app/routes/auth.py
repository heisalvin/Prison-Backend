from fastapi import APIRouter, HTTPException, Depends, Form, status
from fastapi.security import OAuth2PasswordBearer
from app.models.officer import OfficerIn, OfficerOut
from app.db.mongo import officers_col
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from bson import ObjectId
import os
from dotenv import load_dotenv

# ─── LOAD ENVIRONMENT ──────────────────────────────────────────────────────────
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "REPLACE_ME")  # fallback for dev
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ─── SECURITY UTILS ────────────────────────────────────────────────────────────
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

router = APIRouter(tags=["auth"])

# ─── LOAD ALLOWED EMAILS ───────────────────────────────────────────────────────
ALLOWED_EMAILS = os.getenv(
    "ALLOWED_EMAILS",
    "admin@prison.com,manager@prison.com"
).split(",")

# ─── HELPER FUNCTIONS ──────────────────────────────────────────────────────────
def hash_pwd(password: str):
    return pwd_ctx.hash(password)

def verify_pwd(plain: str, hashed: str):
    return pwd_ctx.verify(plain, hashed)

def create_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ─── DEPENDENCIES ──────────────────────────────────────────────────────────────
async def get_current_officer(token: str = Depends(oauth2_scheme)):
    """Validate JWT for normal API requests"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        officer_id: str = payload.get("sub")
        if officer_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    officer = officers_col.find_one({"_id": ObjectId(officer_id)})
    if officer is None:
        raise credentials_exception
    return officer

async def get_ws_current_officer(token: str):
    """Validate JWT for WebSocket connections (uses query param)"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        officer_id: str = payload.get("sub")
        if officer_id is None:
            return None
    except JWTError:
        return None

    officer = officers_col.find_one({"_id": ObjectId(officer_id)})
    return officer

# ─── ROUTES ────────────────────────────────────────────────────────────────────
@router.post("/register", response_model=OfficerOut, status_code=201)
async def register_officer(officer: OfficerIn):
    """Register a new officer account"""
    if officer.email not in ALLOWED_EMAILS:
        raise HTTPException(status_code=400, detail="This email is not allowed to register")

    if officers_col.find_one({"email": officer.email}):
        raise HTTPException(400, detail="Email already registered")

    hashed = hash_pwd(officer.password)
    doc = {**officer.dict(), "password": hashed, "created_at": datetime.utcnow()}
    res = officers_col.insert_one(doc)

    return OfficerOut(id=str(res.inserted_id), name=officer.name, email=officer.email)

@router.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    """Authenticate and return a JWT token"""
    if username not in ALLOWED_EMAILS:
        raise HTTPException(status_code=400, detail="This email is not allowed to log in")

    doc = officers_col.find_one({"email": username})
    if not doc or not verify_pwd(password, doc["password"]):
        raise HTTPException(status_code=401, detail="Wrong email or password")

    token = create_token(
        {"sub": str(doc["_id"])},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(doc["_id"]),
            "name": doc["name"],
            "email": doc["email"]
        }
    }

@router.get("/me", response_model=OfficerOut)
async def get_me(officer=Depends(get_current_officer)):
    """Get the currently authenticated officer"""
    return OfficerOut(
        id=str(officer["_id"]),
        name=officer["name"],
        email=officer["email"]
    )
