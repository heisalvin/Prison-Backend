import torch
import numpy as np
from facenet_pytorch import MTCNN, InceptionResnetV1
from io import BytesIO
from PIL import Image, ImageDraw
from typing import Optional, Tuple, Dict, List

ALLOWED_EXT = {"jpeg", "jpg", "png"}

# Use GPU if available, otherwise CPU
_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Initialize once at startup (keep on chosen device)
mtcnn = MTCNN(image_size=160, margin=14, keep_all=False, device=_DEVICE)
resnet = InceptionResnetV1(pretrained="vggface2").eval().to(_DEVICE)


def get_embedding(image_bytes: bytes) -> np.ndarray:
    """
    Detects the largest face in the image and returns its 512-D embedding (np.float32).
    Raises ValueError if no face is detected.
    """
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    face_tensor = mtcnn(img)
    if face_tensor is None:
        raise ValueError("No face detected")
    with torch.no_grad():
        face_tensor = face_tensor.to(_DEVICE)
        emb = resnet(face_tensor.unsqueeze(0))  # shape [1,512]
    return emb[0].cpu().numpy().astype(np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Computes cosine similarity between two 1-D numpy vectors.
    Returns value in [-1, 1]. Handles zero-length vectors gracefully (returns 0.0).
    """
    a_arr = np.asarray(a, dtype=np.float32)
    b_arr = np.asarray(b, dtype=np.float32)

    a_norm = np.linalg.norm(a_arr)
    b_norm = np.linalg.norm(b_arr)
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (a_norm * b_norm))


# --- New helpers for hybrid recognition ---


def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    """
    L2 (Euclidean) distance between two vectors.
    Returns a non-negative float. Accepts array-like inputs.
    """
    a_arr = np.asarray(a, dtype=np.float32)
    b_arr = np.asarray(b, dtype=np.float32)
    return float(np.linalg.norm(a_arr - b_arr))


def distance_to_score(dist: float) -> float:
    """
    Convert Euclidean distance to a UI-friendly 0..1 score.
    This mapping is monotonic and meant only for display (not a rigorous probability).
    Using 1/(1+dist) is simple and works well for showing relative confidence.
    """
    return float(1.0 / (1.0 + float(dist)))


def choose_match(
    best_cos: Dict,
    best_euc: Dict,
    *,
    cos_threshold: float = 0.85,
    euc_threshold: float = 0.6
) -> Tuple[Optional[dict], str, float]:
    """
    Decide which match (if any) to accept given the best cosine and euclidean candidates.
    """
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
        reported_score = distance_to_score(best_euc["dist"])
        return chosen, method, float(reported_score)

    if best_cos.get("score", 0.0) > 0:
        reported_score = float(best_cos["score"])
    elif best_euc.get("dist", float("inf")) != float("inf"):
        reported_score = distance_to_score(best_euc["dist"])
    else:
        reported_score = 0.0

    return None, "none", float(reported_score)


# --- New: face detection + annotation (draw green boxes) ---

def detect_and_annotate(image_bytes: bytes) -> Tuple[bytes, List[List[int]]]:
    """
    Detect faces in the image, draw green boxes, and return:
      - annotated image bytes (JPEG)
      - list of bounding boxes [x1, y1, x2, y2]
    """
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    boxes, probs = mtcnn.detect(img)

    if boxes is None:
        return image_bytes, []

    draw = ImageDraw.Draw(img)
    annotated_boxes = []
    for box in boxes:
        x1, y1, x2, y2 = [int(v) for v in box]
        draw.rectangle([x1, y1, x2, y2], outline="green", width=3)
        annotated_boxes.append([x1, y1, x2, y2])

    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue(), annotated_boxes
