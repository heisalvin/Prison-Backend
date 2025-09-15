from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
import os

from app.routes import auth, inmates, recognize, logs, stats, activity, officers
from app.routes.auth import get_current_officer  # ✅ import from auth.py

# ─── LOAD ENVIRONMENT ──────────────────────────────────────────────────────────
env_loaded = load_dotenv(dotenv_path=Path(".env"))
SECRET_KEY = os.getenv("SECRET_KEY", "REPLACE_ME")  # fallback for dev/testing

# Load allowed emails from .env
ALLOWED_EMAILS = os.getenv("ALLOWED_EMAILS", "").split(",")

print("✅ ENV loaded:", env_loaded)
print("🔐 SECRET_KEY in use:", SECRET_KEY)
print("📧 ALLOWED_EMAILS:", ALLOWED_EMAILS)

if SECRET_KEY == "REPLACE_ME":
    raise RuntimeError("❌ SECRET_KEY not set! Check your .env file.")

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
origins = [
    "http://localhost:3000",   # React/Next dev server
    "http://localhost:5173",   # Vite dev server
    "https://prison-dashboard-1ovo.vercel.app",  # ✅ your deployed frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://prison-dashboard-1ovo.vercel.app"
    ],
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── ROUTES ────────────────────────────────────────────────────────────────────

# Public routes (no auth)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(recognize.router)

# Protected routes (JWT enforced in route)
app.include_router(inmates.router, prefix="/inmates", tags=["inmates"])
app.include_router(logs.router, prefix="/logs", tags=["logs"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(officers.router, prefix="/officers", tags=["officers"])

# Activity WebSocket
app.include_router(activity.router, prefix="/activity", tags=["activity"])

# ─── ROOT ──────────────────────────────────────────────────────────────────────
@app.get("/", tags=["root"])
async def root():
    return {"message": "Prison Face Verification API Running"}
