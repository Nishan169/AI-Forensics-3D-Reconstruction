"""
blood_analyzer.py – Forensic bloodstain segmentation.

Accurately segments true liquid/pooling blood and impact spatter patterns
while rejecting false positives on wood floors, shadows, furniture, and standing personnel.

Public API
----------
segment_blood(image_np) -> (mask, centroids, polygons)
"""

from __future__ import annotations

import logging
import os
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Detector for excluding standing investigators and large furniture
_COCO_DETECTOR = None
try:
    from ultralytics import YOLO
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _COCO_PATH = os.path.join(_BASE_DIR, "yolov8m.pt")
    if not os.path.exists(_COCO_PATH):
        _COCO_PATH = "yolov8m.pt"
    _COCO_DETECTOR = YOLO(_COCO_PATH)
except Exception as e:
    logger.warning("Could not load COCO detector for scene context: %s", e)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MORPH_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
_OPEN_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

_MIN_AREA_PX = 150
_MAX_AREA_PX = 100000
_POOL_THRESHOLD_PX = 2500


def segment_blood(
    image_np: np.ndarray,
) -> tuple[np.ndarray, list[dict], list[np.ndarray]]:
    """Detect bloodstains in a BGR image using strict chromatic filtering.

    Parameters
    ----------
    image_np:
        BGR uint8 NumPy array (H × W × 3).

    Returns
    -------
    mask : np.ndarray
        Binary (uint8, 0/255) blood mask.
    centroids : list[dict]
        One dict per valid stain with keys: cx, cy, area, type.
    polygons : list[np.ndarray]
        Contour polygons (kept empty or simplified).
    """
    H, W = image_np.shape[:2]

    hsv = cv2.cvtColor(image_np, cv2.COLOR_BGR2HSV)
    b, g, r = cv2.split(image_np.astype(np.float32))

    # ── 1. Fresh / liquid blood (deep crimson red) ──
    # True blood has sharp red dominance over green and blue, and high saturation.
    fresh_hue = (hsv[:, :, 0] <= 8) | (hsv[:, :, 0] >= 172)
    fresh = (
        fresh_hue
        & (hsv[:, :, 1] >= 80)
        & (hsv[:, :, 2] >= 35)
        & (hsv[:, :, 2] <= 210)
        & ((r - g) >= 35)
        & ((r - b) >= 35)
        & (r >= 90)
    )

    # ── 2. Dried brownish blood pool (dark, high red-to-blue contrast) ──
    # Must have low brightness (V <= 85) to prevent misclassifying normal wood floors or tan tiles.
    dried_hue = (hsv[:, :, 0] <= 12) | (hsv[:, :, 0] >= 168)
    dried = (
        dried_hue
        & (hsv[:, :, 1] >= 65)
        & (hsv[:, :, 2] >= 20)
        & (hsv[:, :, 2] <= 85)
        & ((r - b) >= 30)
        & ((r - g) >= 20)
        & (r <= 130)
    )

    combined = ((fresh | dried).astype(np.uint8) * 255)

    # ── 3. Furniture and Standing Investigator Suppression ──
    if _COCO_DETECTOR is not None:
        try:
            results = _COCO_DETECTOR.predict(source=image_np, conf=0.25, verbose=False)
            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                name = _COCO_DETECTOR.names[cls_id]
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                area = (x2 - x1) * (y2 - y1)

                # Mask out furniture pieces (chairs, couches, beds, potted plants, etc.)
                if name in ["chair", "couch", "bed", "potted plant", "dining table"] and area > 5000:
                    cv2.rectangle(combined, (x1, y1), (x2, y2), 0, -1)

                # Mask out standing upright investigators in clean PPE
                elif name == "person":
                    bh = y2 - y1
                    bw = x2 - x1
                    if bh > bw * 1.35 and y1 < H * 0.35 and bh > H * 0.35:
                        cv2.rectangle(
                            combined,
                            (max(0, x1 - 10), max(0, y1 - 10)),
                            (min(W, x2 + 10), min(H, y2 + 45)),
                            0,
                            -1,
                        )
        except Exception as e:
            logger.warning("Error running context detector: %s", e)

    # ── 4. Morphological clean-up ──
    closed = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, _MORPH_KERNEL)
    cleaned = cv2.morphologyEx(closed, cv2.MORPH_OPEN, _OPEN_KERNEL)

    # ── 5. Contour extraction & geometric filtering ──
    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    centroids: list[dict] = []
    polygons: list[np.ndarray] = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < _MIN_AREA_PX or area > _MAX_AREA_PX:
            continue

        _bx, _by, bw, bh = cv2.boundingRect(cnt)
        aspect = bh / max(bw, 1)
        if aspect > 4.0 or (bw / max(bh, 1)) > 7.5:
            continue

        hull_area = cv2.contourArea(cv2.convexHull(cnt))
        if hull_area > 0 and (area / hull_area) < 0.10:
            continue

        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        # Filter out extreme edge artifacts (wall/ceiling borders)
        if cy < 25 or cy > (H - 8) or cx < 8 or cx > (W - 8):
            continue

        stain_type = "pool" if area > _POOL_THRESHOLD_PX else "spatter"
        centroids.append({"cx": cx, "cy": cy, "area": float(area), "type": stain_type})
        # Leave polygons empty to prevent drawing / highlighting blood polygons on the output image
        polygons.append(np.empty((0, 2), dtype=np.int32))

    return cleaned, centroids, polygons
