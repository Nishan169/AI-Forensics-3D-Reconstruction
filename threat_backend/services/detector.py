"""
detector.py – Open-vocabulary threat detector powered by YOLO-World and COCO priors.

Accurately classifies forensic weapons (guns, knives, hammers) in crime scene imagery
without false overrides, eliminating false positives on footwear, furniture,
clothing, and household scene items.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default weapon categories (forensic crime scene threats)
# ---------------------------------------------------------------------------
DEFAULT_CLASSES: list[str] = [
    "gun",
    "knife",
    "hammer",
]

# Fine-grained detection prompts mapped to canonical forensic weapon classes
WEAPON_PROMPT_MAP: dict[str, list[str]] = {
    "gun": [
        "hand gun",
        "handgun",
        "pistol",
        "revolver",
        "firearm",
        "gun",
        "black revolver",
        "black handgun",
        "revolver gun",
    ],
    "knife": [
        "knife",
        "kitchen knife",
        "chef knife",
        "bloody knife",
        "large knife",
        "butcher knife",
        "hunting knife",
        "dagger",
        "blade",
        "pocket knife",
    ],
    "hammer": [
        "hammer",
        "claw hammer",
        "sledgehammer",
        "carpenter hammer",
    ],
}

# ---------------------------------------------------------------------------
# Negative distractor categories
# ---------------------------------------------------------------------------
DISTRACTOR_CLASSES: list[str] = [
    # Footwear
    "shoe",
    "sneaker",
    "boot",
    "sandal",
    "slipper",
    # Clothing & linens
    "clothing",
    "shirt",
    "pants",
    "jacket",
    "towel",
    "blanket",
    # Desk & office items
    "cell phone",
    "remote control",
    "pen",
    "pencil",
    "laptop",
    "keys",
    "watch",
    "wallet",
    "stapler",
    "hole punch",
    "paper",
    "book",
    # Kitchen / dining
    "cup",
    "mug",
    "bottle",
    "can",
    "plate",
    "bowl",
    # Furniture & architecture
    "chair",
    "armchair",
    "table",
    "desk",
    "bed",
    "sofa",
    "couch",
    "curtain",
    "floor",
    "wall",
    "door",
    "window",
    "chair leg",
    "metal chair leg",
    "table leg",
    "furniture leg",
    "metal tube",
    "pole",
    # Humans
    "person",
    "human body",
    "arm",
    "leg",
    "foot",
    "hand",
    # Forensic scene markers
    "yellow evidence marker",
    "evidence marker tent",
    "number cone",
]

# ---------------------------------------------------------------------------
# Model initialisation
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_WORLD_PATH = os.path.join(_BASE_DIR, "yolov8m-worldv2.pt")
if not os.path.exists(_WORLD_PATH):
    _WORLD_PATH = "yolov8m-worldv2.pt"

_COCO_PATH = os.path.join(_BASE_DIR, "yolov8m.pt")
if not os.path.exists(_COCO_PATH):
    _COCO_PATH = "yolov8m.pt"

logger.info("Loading YOLO models from %s and %s …", _WORLD_PATH, _COCO_PATH)
model: YOLO = YOLO(_WORLD_PATH)
coco_model: YOLO | None = None
try:
    coco_model = YOLO(_COCO_PATH)
except Exception as e:
    logger.warning("Could not load COCO auxiliary detector: %s", e)

logger.info("Threat detector models ready.")


def _compute_iou(box1: list[int], box2: list[int]) -> float:
    """Compute Intersection over Union between two [x1, y1, x2, y2] bounding boxes."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def _analyze_crop_solidity(image_np: np.ndarray, bbox: list[int]) -> tuple[float, float]:
    """Calculate aspect ratio and solidity of the main foreground contour in a crop."""
    x1, y1, x2, y2 = bbox
    H, W = image_np.shape[:2]
    crop = image_np[max(0, y1 - 3): min(H, y2 + 3), max(0, x1 - 3): min(W, x2 + 3)]
    if crop is None or crop.size == 0:
        return 1.0, 1.0

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return 1.0, 1.0

    c = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(c)
    hull_area = cv2.contourArea(cv2.convexHull(c))
    solidity = area / hull_area if hull_area > 0 else 1.0
    rect = cv2.minAreaRect(c)
    rw, rh = rect[1]
    aspect = max(rw, rh) / (min(rw, rh) + 1e-5)
    return aspect, solidity


# ---------------------------------------------------------------------------
# Public detection API
# ---------------------------------------------------------------------------

def detect_objects(
    image_np: np.ndarray,
    candidate_classes: list[str] | None = None,
    confidence_threshold: float = 0.10,
) -> list[dict[str, Any]]:
    """Run open-vocabulary forensic threat detection on a single image.

    Parameters
    ----------
    image_np:
        HxWxC NumPy array in **BGR** colour order.
    candidate_classes:
        List of text labels to detect. When *None* or empty, forensic
        threat categories (gun, knife, hammer) are detected with synonym expansion.
    confidence_threshold:
        Minimum confidence score required to keep a detection (default 0.10).

    Returns
    -------
    list[dict]
        Clean list of detected objects: [{"label": str, "confidence": float, "bbox": [x1, y1, x2, y2]}]
    """
    prompt_to_canon: dict[str, str] = {}

    if candidate_classes:
        target_weapons = [c.strip().lower() for c in candidate_classes if c.strip()]
        for c in target_weapons:
            prompt_to_canon[c] = c
            if c in WEAPON_PROMPT_MAP:
                for syn in WEAPON_PROMPT_MAP[c]:
                    prompt_to_canon[syn] = c
    else:
        for canon, syn_list in WEAPON_PROMPT_MAP.items():
            for syn in syn_list:
                prompt_to_canon[syn] = canon

    weapon_prompts = list(prompt_to_canon.keys())

    # Combine weapon categories with negative distractor categories to suppress false positives
    all_classes: list[str] = list(weapon_prompts)
    for dist in DISTRACTOR_CLASSES:
        if dist not in all_classes:
            all_classes.append(dist)

    model.set_classes(all_classes)

    candidates: list[dict[str, Any]] = []

    # ── 1. High-precision COCO prior for knives ──────────────────────────────
    if coco_model is not None and ("knife" in prompt_to_canon.values() or not candidate_classes):
        try:
            res_coco = coco_model.predict(source=image_np, conf=0.18, verbose=False)
            if res_coco and res_coco[0].boxes:
                for b in res_coco[0].boxes:
                    cls_name = coco_model.names[int(b.cls[0])]
                    conf = float(b.conf[0])
                    bbox = [int(v) for v in b.xyxy[0].tolist()]
                    if cls_name == "knife":
                        candidates.append(
                            {
                                "label": "knife",
                                "confidence": round(conf, 4),
                                "bbox": bbox,
                                "priority": 2,
                            }
                        )
        except Exception as exc:
            logger.warning("Error running COCO prior: %s", exc)

    # ── 2. Open-vocabulary YOLO-World detection ───────────────────────────────
    results = model.predict(
        source=image_np,
        conf=0.035,
        imgsz=640,
        verbose=False,
    )

    raw_weapons: list[dict[str, Any]] = []
    raw_distractors: list[dict[str, Any]] = []

    for result in results:
        if result.boxes is None:
            continue

        for box in result.boxes:
            conf = float(box.conf[0])
            cls_idx = int(box.cls[0])
            label = all_classes[cls_idx]
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            bbox = [int(x1), int(y1), int(x2), int(y2)]

            item = {
                "label": prompt_to_canon.get(label, label),
                "confidence": round(conf, 4),
                "bbox": bbox,
                "priority": 1,
            }

            if label in prompt_to_canon:
                raw_weapons.append(item)
            else:
                raw_distractors.append(item)

    # Distractor suppression: discard weapon detections that heavily overlap with distractors
    for w in raw_weapons:
        suppressed = False
        for d in raw_distractors:
            iou = _compute_iou(w["bbox"], d["bbox"])
            if iou > 0.40 and d["confidence"] >= w["confidence"]:
                suppressed = True
                break
        if not suppressed and w["confidence"] >= confidence_threshold:
            candidates.append(w)

    # ── 3. Deduplication & Morphological Shape Refinement ──────────────────────
    candidates.sort(key=lambda x: (x.get("priority", 1), x["confidence"]), reverse=True)
    deduped: list[dict[str, Any]] = []

    for c in candidates:
        # Check IoU overlap with already accepted higher-priority detections
        if any(_compute_iou(c["bbox"], kept["bbox"]) > 0.40 for kept in deduped):
            continue

        resolved_label = c["label"]

        # Morphological shape check for hammer vs knife
        # A hammer has a distinct T-shape crosshead on a slender handle (solidity < 0.58, aspect 1.8-4.2)
        aspect, solidity = _analyze_crop_solidity(image_np, c["bbox"])
        if resolved_label == "knife" and solidity < 0.58 and 1.8 <= aspect <= 4.2:
            resolved_label = "hammer"

        deduped.append(
            {
                "label": resolved_label,
                "confidence": c["confidence"],
                "bbox": c["bbox"],
            }
        )

    return deduped
