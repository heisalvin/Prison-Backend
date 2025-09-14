from fastapi import APIRouter, Depends, Query
from app.db.mongo import logs_col
from app.routes.auth import get_current_officer
from app.utils.serializers import serialize_list
from datetime import datetime
from collections import defaultdict

router = APIRouter(prefix="/logs", tags=["logs"])

# ─── GET ALL LOGS ──────────────────────────────────────────────
@router.get("/")
async def get_logs(officer=Depends(get_current_officer)):
    logs = list(logs_col.find({}))
    return {"logs": serialize_list(logs)}

# ─── GET RECENT LOGS ──────────────────────────────────────────
@router.get("/recent")
async def get_recent_logs(
    limit: int = Query(10, ge=1, le=100, description="Number of recent logs to fetch"),
    officer=Depends(get_current_officer)
):
    """
    Get the most recent logs, sorted by timestamp descending.
    `limit` query parameter specifies how many logs to return.
    """
    logs = list(
        logs_col.find({})
        .sort("timestamp", -1)
        .limit(limit)
    )
    return {"logs": serialize_list(logs)}

# ─── GET DAILY LOGS COUNT ─────────────────────────────────────
@router.get("/daily")
async def get_daily_logs(officer=Depends(get_current_officer)):
    """
    Return counts of logs per day.
    """
    logs = list(logs_col.find({}))
    daily = defaultdict(int)

    for log in logs:
        ts = log.get("timestamp")
        if isinstance(ts, datetime):
            day = ts.strftime("%Y-%m-%d")
            daily[day] += 1

    return {"daily_logs": dict(daily)}

# ─── GET LOGS GROUPED BY OFFICER ──────────────────────────────
@router.get("/by_officer")
async def get_logs_by_officer(officer=Depends(get_current_officer)):
    """
    Return logs grouped by officer name.
    """
    logs = list(logs_col.find({}))
    grouped = defaultdict(list)

    for log in serialize_list(logs):  # ensure JSON-safe logs
        officer_name = log.get("officer", "Unknown")
        grouped[officer_name].append(log)

    return {"logs_by_officer": dict(grouped)}
