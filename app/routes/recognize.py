from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from datetime import datetime
from bson import ObjectId
import numpy as np
import traceback
from typing import Optional, Dict, Any, List
from io import BytesIO
import base64
from PIL import Image, ImageDraw
import time

from app.db.mongo import inmates_col, logs_col
from app.routes.auth import get_current_officer
from app.utils.face_tools import get_embedding, cosine_similarity, mtcnn
from app.routes.activity import broadcast_activity

# Try to import helpers from face_tools
try:
    from app.utils.face_tools import (
        euclidean_distance,
        distance_to_score,
        choose_match,
    )
    _HAS_FT_HELPERS = True
except Exception:
    _HAS_FT_HELPERS = False

    def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
        a_arr = np.asarray(a, dtype=np.float32)
        b_arr = np.asarray(b, dtype=np.float32)
        return float(np.linalg.norm(a_arr - b_arr))

    def distance_to_score(dist: float) -> float:
        return float(1.0 / (1.0 + float(dist)))

    def choose_match(best_cos: Dict[str, Any], best_euc: Dict[str, Any],
                     cos_threshold: float = 0.85, euc_threshold: float = 0.6):
        chosen = None
        method = "none"
        reported_score = 0.0

        if best_cos.get("inmate") and best_cos.get("score", 0.0) >= cos_threshold:
            chosen = best_cos["inmate"]
            method = "cosine"
            reported_score = float(best_cos["score"])
            return chosen, method, reported_score

        if best_euc.get("inmate") and best_euc.get("dist", float("inf")) <= euc_threshold:
            chosen = best_euc["inmate"]
            method = "euclidean"
            reported_score = float(distance_to_score(best_euc["dist"]))
            return chosen, method, reported_score

        if best_cos.get("score", 0.0) > 0:
            reported_score = float(best_cos["score"])
        elif best_euc.get("dist", float("inf")) != float("inf"):
            reported_score = float(distance_to_score(best_euc["dist"]))
        else:
            reported_score = 0.0

        return None, "none", float(reported_score)


router = APIRouter(prefix="/recognize", tags=["recognize"])

COSINE_THRESHOLD = 0.85
EUCLIDEAN_THRESHOLD = 0.6
RECOGNITION_COOLDOWN = 30  # seconds

# In-memory cache of last recognition times per inmate_id
last_recognized: Dict[str, float] = {}


@router.post("/", description="Identify the inmate in the uploaded image with bounding boxes")
async def recognize_face(
    image: UploadFile = File(...),
    officer=Depends(get_current_officer),
    debug: Optional[bool] = Query(False, description="If true, return extra debug info")
):
    try:
        # Read uploaded image
        content = await image.read()
        pil_img = Image.open(BytesIO(content)).convert("RGB")

        # Detect all faces and bounding boxes
        boxes, _ = mtcnn.detect(pil_img)

        if boxes is None or len(boxes) == 0:
            raise HTTPException(400, "No face detected")

        # Use first face for recognition
        try:
            query_vec = get_embedding(content)
            query_vec = np.asarray(query_vec, dtype=np.float32)
        except ValueError as e:
            raise HTTPException(400, str(e))

        best_cos = {"score": 0.0, "inmate": None}
        best_euc = {"dist": float("inf"), "inmate": None}

        # Compare against stored inmates
        for doc in inmates_col.find({}):
            for emb in doc.get("embeddings", []):
                if "vector" not in emb or not emb["vector"]:
                    continue
                try:
                    stored_vec = np.asarray(emb["vector"], dtype=np.float32)
                except Exception:
                    continue

                # cosine
                try:
                    cos_score = float(cosine_similarity(query_vec, stored_vec))
                    if cos_score > best_cos["score"]:
                        best_cos = {"score": cos_score, "inmate": doc}
                except Exception:
                    pass

                # euclidean
                try:
                    dist = euclidean_distance(query_vec, stored_vec)
                    if dist < best_euc["dist"]:
                        best_euc = {"dist": dist, "inmate": doc}
                except Exception:
                    pass

        chosen_doc, method, reported_score = choose_match(
            best_cos, best_euc,
            cos_threshold=COSINE_THRESHOLD,
            euc_threshold=EUCLIDEAN_THRESHOLD
        )

        # Officer ID
        officer_id = None
        if isinstance(officer, dict):
            officer_id = officer.get("id") or officer.get("_id")
        else:
            officer_id = getattr(officer, "id", None) or getattr(officer, "_id", None)

        if not officer_id:
            raise HTTPException(500, "Could not determine officer ID")

        recognized_by = officer_id if isinstance(officer_id, ObjectId) else ObjectId(str(officer_id))

        if chosen_doc:
            inmate_id = chosen_doc["inmate_id"]
            now = time.time()
            last_seen = last_recognized.get(inmate_id, 0)

            if now - last_seen >= RECOGNITION_COOLDOWN:
                last_recognized[inmate_id] = now

                # Log recognition
                log_doc = {
                    "inmate_id": inmate_id,
                    "inmate_name": chosen_doc.get("name"),
                    "prison_name": chosen_doc.get("prison_name"),
                    "score": float(reported_score),
                    "image": image.filename,
                    "recognized_by": recognized_by,
                    "recognized_at": datetime.utcnow(),
                }
                logs_col.insert_one(log_doc)

                # Broadcast event
                try:
                    payload = {
                        "inmate_id": inmate_id,
                        "inmate_name": chosen_doc.get("name"),
                        "prison_name": chosen_doc.get("prison_name"),
                        "officer_name": officer.get("name") if isinstance(officer, dict) else getattr(officer, "name", None),
                        "score": float(reported_score),
                        "method": method,
                        "recognized_at": log_doc["recognized_at"].isoformat()
                    }
                    await broadcast_activity(payload)
                except Exception:
                    pass
            else:
                print(f"Skipped logging {inmate_id} (recognized too recently)")

        # Build boxes array for frontend
        boxes_list: List[Dict[str, Any]] = []
        if boxes is not None:
            for box in boxes:
                x1, y1, x2, y2 = [float(v) for v in box]
                w = x2 - x1
                h = y2 - y1
                boxes_list.append({
                    "x": x1,
                    "y": y1,
                    "width": w,
                    "height": h,
                    "recognized": chosen_doc is not None,
                    "name": chosen_doc.get("name") if chosen_doc else None,
                    "score": float(reported_score)
                })

        # Also return base64 debug image (optional for debugging)
        buf = BytesIO()
        draw = ImageDraw.Draw(pil_img)
        for box in boxes:
            x1, y1, x2, y2 = [int(v) for v in box]
            draw.rectangle([x1, y1, x2, y2], outline="green" if chosen_doc else "red", width=3)
        pil_img.save(buf, format="JPEG")
        boxed_img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        # Final response
        return JSONResponse({
            "inmate_id": chosen_doc["inmate_id"] if chosen_doc else None,
            "name": chosen_doc.get("name") if chosen_doc else None,
            "prison_name": chosen_doc.get("prison_name") if chosen_doc else None,
            "score": float(reported_score),
            "method": method,
            "boxes": boxes_list,         # <-- for frontend overlay
            "image_base64": boxed_img_b64  # <-- optional, can be shown for debug
        })

    except HTTPException:
        raise
    except Exception as e:
        print("Recognition error:", e)
        traceback.print_exc()
        raise HTTPException(500, "An unexpected error occurred during recognition")
