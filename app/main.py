from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from bson import ObjectId
import os
from dotenv import load_dotenv
from pathlib import Path

from app.routes import auth, inmates, recognize, logs, stats, activity, officers
from app.db.mongo import officers_col

# ─── LOAD ENVIRONMENT ──────────────────────────────────────────────────────────
env_loaded = load_dotenv(dotenv_path=Path(".env"))
SECRET_KEY = os.getenv("SECRET_KEY", "REPLACE_ME")  # fallback for dev/testing

# Load allowed emails from .env
ALLOWED_EMAILS = os.getenv("ALLOWED_EMAILS", "").split(",")  # load allowed emails from .env

print("✅ ENV loaded:", env_loaded)
print("🔐 SECRET_KEY in use:", SECRET_KEY)
print("📧 ALLOWED_EMAILS:", ALLOWED_EMAILS)  # Log it to confirm it's loaded

if SECRET_KEY == "REPLACE_ME":
    raise RuntimeError("❌ SECRET_KEY not set! Check your .env file.")

ALGORITHM = "HS256"

# ─── JWT AUTH DEPENDENCY ───────────────────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=True)

async def get_current_officer(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    token = creds.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        officer_id: str = payload.get("sub")
        if not officer_id:
            raise ValueError("Missing officer ID in token")
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    doc = officers_col.find_one({"_id": ObjectId(officer_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Officer not found")

    return {"id": str(doc["_id"]), "name": doc["name"], "email": doc["email"]}

# ─── FASTAPI APP CONFIG ────────────────────────────────────────────────────────
app = FastAPI(
    title="Prison Face Verification API",
    description="Facial recognition system for inmate verification and monitoring.",
    version="1.0.0",
    openapi_tags=[
        {"name": "auth", "description": "Login & Registration"},
        {"name": "inmates", "description": "Register, list, and manage inmates"},
        {"name": "recognize", "description": "Facial recognition endpoints"},
        {"name": "logs", "description": "Attendance and activity logs"},
        {"name": "stats", "description": "System usage and inmate stats"},
        {"name": "officers", "description": "Officer management"},
        {"name": "activity", "description": "Real-time activity WebSocket"},
    ],
)

# ─── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # your front-end dev server
        # add more if you deploy elsewhere (e.g. "https://myapp.com")
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── ROUTES ────────────────────────────────────────────────────────────────────

# Public (no auth)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(recognize.router)

# Protected (need valid JWT)
app.include_router(
    inmates.router,
    prefix="/inmates",
    tags=["inmates"],
    dependencies=[Depends(get_current_officer)],
)
app.include_router(
    logs.router,
    prefix="/logs",
    tags=["logs"],
    dependencies=[Depends(get_current_officer)],
)
app.include_router(
    stats.router,
    prefix="/stats",
    tags=["stats"],
    dependencies=[Depends(get_current_officer)],
)
app.include_router(
    officers.router,
    prefix="/officers",
    tags=["officers"],
    dependencies=[Depends(get_current_officer)],
)

# Activity WebSocket
app.include_router(activity.router, prefix="/activity", tags=["activity"])

# ─── ROOT ──────────────────────────────────────────────────────────────────────
@app.get("/", tags=["root"])
async def root():
    return {"message": "Prison Face Verification API Running"}
