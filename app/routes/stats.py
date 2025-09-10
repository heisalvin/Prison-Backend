# app/routes/stats.py
from fastapi import APIRouter, Depends, Query, HTTPException, WebSocket, WebSocketDisconnect
from datetime import datetime, timedelta, time
from app.db.mongo import logs_col, inmates_col, officers_col
from app.routes.auth import get_current_officer
from bson import ObjectId
import traceback
from typing import Dict, Any, List

router = APIRouter(tags=["stats"])

# ------------------------------
# Recognitions today (for current authenticated officer)
# ------------------------------
@router.get("/recognitions-today-by-officer")
async def recognitions_today_by_officer(current=Depends(get_current_officer)) -> Dict[str, Any]:
    """
    Returns count of recognition logs for the authenticated officer during the current UTC day.
    Response: { "count": <int> }
    """
    try:
        # Resolve officer id: current may be a dict or a DB document
        officer_id_str = None
        if isinstance(current, dict):
            officer_id_str = current.get("id") or current.get("_id")
        else:
            # attempt to read common attributes
            officer_id_str = getattr(current, "id", None) or getattr(current, "_id", None)

        if not officer_id_str:
            raise HTTPException(status_code=500, detail="Could not determine officer id")

        # If it's an ObjectId instance, convert to ObjectId; if string, convert to ObjectId
        if isinstance(officer_id_str, ObjectId):
            officer_oid = officer_id_str
        else:
            try:
                officer_oid = ObjectId(str(officer_id_str))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid officer id")

        # UTC day range
        now = datetime.utcnow()
        start_of_day = datetime.combine(now.date(), time.min)
        start_of_next_day = start_of_day + timedelta(days=1)

        count = logs_col.count_documents({
            "recognized_by": officer_oid,
            "recognized_at": {"$gte": start_of_day, "$lt": start_of_next_day}
        })

        return {"count": int(count)}
    except HTTPException:
        raise
    except Exception as e:
        print("Error in /recognitions-today-by-officer:", e)
        traceback.print_exc()
        raise HTTPException(500, "Could not retrieve today's recognitions")

# ------------------------------
# Daily recognition counts (from logs)
# ------------------------------
@router.get("/recognitions-daily")
async def daily_counts(
    days: int = Query(7, ge=1),
    officer=Depends(get_current_officer)
):
    try:
        start = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {"$match": {"recognized_at": {"$gte": start}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$recognized_at"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        data = list(logs_col.aggregate(pipeline))
        return {"daily": data}
    except Exception as e:
        print("Error in /recognitions-daily:", e)
        traceback.print_exc()
        raise HTTPException(500, "Could not retrieve daily recognition stats")

# ------------------------------
# Top recognized inmates (from logs)
# ------------------------------
@router.get("/top-inmates")
async def top_inmates(
    days: int = Query(30, ge=1),
    officer=Depends(get_current_officer)
):
    try:
        start = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {"$match": {"recognized_at": {"$gte": start}}},
            {"$group": {"_id": "$inmate_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        data = []
        for entry in logs_col.aggregate(pipeline):
            inmate = inmates_col.find_one({"inmate_id": entry["_id"]}, {"name": 1})
            name = (inmate or {}).get("name") or "Unknown"
            data.append({"inmate": name, "count": entry["count"]})
        return {"top_inmates": data}
    except Exception as e:
        print("Error in /top-inmates:", e)
        traceback.print_exc()
        raise HTTPException(500, "Could not retrieve top inmates")

# ------------------------------
# Recognitions by officer (robust join on officer id)
# ------------------------------
@router.get("/recognitions-by-officer")
async def by_officer(
    officer=Depends(get_current_officer)
):
    try:
        # Normalize recognized_by to string for grouping, then join to officers by toString(_id)
        pipeline = [
            {"$addFields": {
                "officer_id": {
                    "$cond": [
                        {"$eq": [{"$type": "$recognized_by"}, "objectId"]},
                        {"$toString": "$recognized_by"},
                        "$recognized_by"  # assume already string or null
                    ]
                }
            }},
            {"$group": {"_id": "$officer_id", "count": {"$sum": 1}}},
            {"$lookup": {
                "from": "officers",
                "let": {"oid": "$_id"},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": [{"$toString": "$_id"}, "$$oid"]}}},  # matches even if logs stored string
                    {"$project": {"name": 1}}
                ],
                "as": "officer"
            }},
            {"$project": {
                "_id": 0,
                "officer": {"$ifNull": [{"$arrayElemAt": ["$officer.name", 0]}, "Unknown"]},
                "count": 1
            }},
            {"$sort": {"count": -1}}
        ]
        result = list(logs_col.aggregate(pipeline))
        return {"by_officer": result}
    except Exception as e:
        print("Error in /recognitions-by-officer:", e)
        traceback.print_exc()
        raise HTTPException(500, "Could not retrieve officer recognition stats")

# ------------------------------
# Recent verifications (names default to 'Unknown' if missing)
# ------------------------------
@router.get("/recent-verifications")
async def recent_verifications(
    limit: int = Query(5, ge=1, le=20),
    officer=Depends(get_current_officer)
):
    try:
        pipeline = [
            {"$sort": {"recognized_at": -1}},
            {"$limit": limit},
            {"$lookup": {
                "from": "inmates",
                "localField": "inmate_id",
                "foreignField": "inmate_id",
                "as": "inmate"
            }},
            {"$lookup": {
                "from": "officers",
                "localField": "recognized_by",
                "foreignField": "_id",
                "as": "officer"
            }},
            {"$project": {
                "_id": 0,
                "inmate_id": 1,
                "inmate_name": {"$ifNull": [{"$arrayElemAt": ["$inmate.name", 0]}, "Unknown"]},
                "officer_name": {"$ifNull": [{"$arrayElemAt": ["$officer.name", 0]}, "Unknown"]},
                "score": 1,
                "recognized_at": 1
            }}
        ]
        data = list(logs_col.aggregate(pipeline))
        return {"recent": data}
    except Exception as e:
        print("Error in /recent-verifications:", e)
        traceback.print_exc()
        raise HTTPException(500, "Could not retrieve recent verifications")

# ------------------------------
# Age Distribution (from inmates)
# ------------------------------
@router.get("/age-distribution")
async def age_distribution(
    officer=Depends(get_current_officer)
):
    try:
        pipeline = [
            # Only count inmates that actually have a numeric age
            {"$match": {"extra_info.age": {"$type": "number"}}},
            {"$project": {"age": "$extra_info.age"}},
            {"$addFields": {
                "age_range": {
                    "$switch": {
                        "branches": [
                            {"case": {"$lte": ["$age", 20]}, "then": "0-20"},
                            {"case": {"$and": [{"$gt": ["$age", 20]}, {"$lte": ["$age", 40]}]}, "then": "21-40"},
                            {"case": {"$and": [{"$gt": ["$age", 40]}, {"$lte": ["$age", 60]}]}, "then": "41-60"},
                        ],
                        "default": "61+"
                    }
                }
            }},
            {"$group": {"_id": "$age_range", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        data = list(inmates_col.aggregate(pipeline))
        return {"age_distribution": data}
    except Exception as e:
        print("Error in /age-distribution:", e)
        traceback.print_exc()
        raise HTTPException(500, "Could not retrieve age distribution stats")

# ------------------------------
# Sex Distribution (from inmates)
# ------------------------------
@router.get("/sex-distribution")
async def sex_distribution(
    officer=Depends(get_current_officer)
):
    try:
        # Normalize various case inputs to lower-case and bucket into Male/Female/Unknown
        pipeline = [
            {"$project": {
                "sex": {
                    "$switch": {
                        "branches": [
                            {"case": {"$eq": [{ "$toLower": "$extra_info.sex" }, "male"]}, "then": "Male"},
                            {"case": {"$eq": [{ "$toLower": "$extra_info.sex" }, "female"]}, "then": "Female"},
                        ],
                        "default": "Unknown"
                    }
                }
            }},
            {"$group": {"_id": "$sex", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        data = list(inmates_col.aggregate(pipeline))
        return {"sex_distribution": data}
    except Exception as e:
        print("Error in /sex-distribution:", e)
        traceback.print_exc()
        raise HTTPException(500, "Could not retrieve sex distribution stats")

# ------------------------------
# Legal Status Distribution (from inmates)
# ------------------------------
@router.get("/legal-status-distribution")
async def legal_status_distribution(
    officer=Depends(get_current_officer)
):
    try:
        pipeline = [
            {"$project": {
                "legal_status": {"$ifNull": ["$extra_info.legal_status", "Unknown"]}
            }},
            {"$group": {"_id": "$legal_status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        data = list(inmates_col.aggregate(pipeline))
        return {"legal_status_distribution": data}
    except Exception as e:
        print("Error in /legal-status-distribution:", e)
        traceback.print_exc()
        raise HTTPException(500, "Could not retrieve legal status distribution stats")

# ------------------------------
# Facility Distribution (from inmates)
# ------------------------------
@router.get("/facility-distribution")
async def facility_distribution(
    officer=Depends(get_current_officer)
):
    try:
        pipeline = [
            {"$project": {
                "facility": {"$ifNull": ["$extra_info.facility_name", "Unknown"]}
            }},
            {"$group": {"_id": "$facility", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        data = list(inmates_col.aggregate(pipeline))
        return {"facility_distribution": data}
    except Exception as e:
        print("Error in /facility-distribution:", e)
        traceback.print_exc()
        raise HTTPException(500, "Could not retrieve facility distribution stats")

# ------------------------------
# Live Activity WebSocket
# ------------------------------
active_connections: List[WebSocket] = []

@router.websocket("/ws/activity")
async def websocket_activity(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # keep-alive; you can also implement ping/pong if you like
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)

# ------------------------------
# Function to broadcast events
# ------------------------------
async def broadcast_activity(event: dict):
    to_remove = []
    for connection in list(active_connections):
        try:
            await connection.send_json(event)
        except Exception:
            to_remove.append(connection)
    for conn in to_remove:
        if conn in active_connections:
            active_connections.remove(conn)
