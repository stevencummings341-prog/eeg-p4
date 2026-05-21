"""Feature derivation from Face Mesh landmarks.

Computes:
- EAR (Eye Aspect Ratio) for left and right eyes (Soukupova & Cech, 2016)
- MAR (Mouth Aspect Ratio) for jaw clench / mouth open detection
- Head pose (yaw, pitch, roll) via OpenCV solvePnP using a canonical 6-point face model

All inputs use MediaPipe Face Mesh's 468-landmark layout (normalized [0,1] coords).
For numerical stability we work in pixel coordinates derived from image_size.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


# MediaPipe Face Mesh landmark indices.
# Eye corners follow the conventional 6-point EAR layout adapted to Face Mesh.
# Subject-perspective: "LEFT_EYE" = the eye on subject's left = appears on viewer's right.
LEFT_EYE_EAR_INDICES = [33, 160, 158, 133, 153, 144]   # p1..p6
RIGHT_EYE_EAR_INDICES = [362, 385, 387, 263, 373, 380]  # p1..p6

# Mouth: upper inner lip, lower inner lip, left mouth corner, right mouth corner.
MOUTH_TOP = 13
MOUTH_BOTTOM = 14
MOUTH_LEFT = 78
MOUTH_RIGHT = 308

# 6-point head pose model (subset used widely for PnP).
HEAD_POSE_INDICES = {
    "nose_tip": 1,
    "chin": 152,
    "left_eye_outer": 33,
    "right_eye_outer": 263,
    "left_mouth_corner": 61,
    "right_mouth_corner": 291,
}

# Canonical 3D face model (millimeters). Coordinates loosely follow standard
# reference values used in OpenCV head-pose tutorials.
HEAD_POSE_MODEL_3D = np.array(
    [
        [0.0, 0.0, 0.0],            # nose_tip
        [0.0, -63.6, -12.5],        # chin
        [-43.3, 32.7, -26.0],       # left_eye_outer (subject's left)
        [43.3, 32.7, -26.0],        # right_eye_outer
        [-28.9, -28.9, -24.1],      # left_mouth_corner
        [28.9, -28.9, -24.1],       # right_mouth_corner
    ],
    dtype=np.float64,
)


@dataclass
class FaceFeatures:
    ear_left: float = float("nan")
    ear_right: float = float("nan")
    ear_mean: float = float("nan")
    mar: float = float("nan")
    yaw_deg: float = float("nan")
    pitch_deg: float = float("nan")
    roll_deg: float = float("nan")
    pose_solved: bool = False


def _ear_from_points(p1, p2, p3, p4, p5, p6) -> float:
    """Eye Aspect Ratio = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)."""
    num = np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)
    den = 2.0 * np.linalg.norm(p1 - p4)
    if den < 1e-6:
        return float("nan")
    return float(num / den)


def _to_pixels(landmarks: np.ndarray, image_hw: tuple[int, int]) -> np.ndarray:
    h, w = image_hw
    pts = landmarks[:, :2].copy()
    pts[:, 0] *= w
    pts[:, 1] *= h
    return pts


def _solve_head_pose(
    image_points: np.ndarray, image_hw: tuple[int, int]
) -> tuple[bool, float, float, float]:
    """Estimate yaw/pitch/roll (degrees) using OpenCV solvePnP."""
    import cv2

    h, w = image_hw
    focal_length = float(w)
    center = (w / 2.0, h / 2.0)
    camera_matrix = np.array(
        [
            [focal_length, 0.0, center[0]],
            [0.0, focal_length, center[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    ok, rvec, _tvec = cv2.solvePnP(
        HEAD_POSE_MODEL_3D,
        image_points.astype(np.float64),
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        return False, float("nan"), float("nan"), float("nan")

    rot_mat, _ = cv2.Rodrigues(rvec)
    sy = float(np.sqrt(rot_mat[0, 0] ** 2 + rot_mat[1, 0] ** 2))
    singular = sy < 1e-6
    if not singular:
        pitch = np.degrees(np.arctan2(rot_mat[2, 1], rot_mat[2, 2]))
        yaw = np.degrees(np.arctan2(-rot_mat[2, 0], sy))
        roll = np.degrees(np.arctan2(rot_mat[1, 0], rot_mat[0, 0]))
    else:
        pitch = np.degrees(np.arctan2(-rot_mat[1, 2], rot_mat[1, 1]))
        yaw = np.degrees(np.arctan2(-rot_mat[2, 0], sy))
        roll = 0.0

    # Normalize pitch around 0 by subtracting 180 wrap if subject is upright.
    if pitch > 90:
        pitch -= 180
    elif pitch < -90:
        pitch += 180
    return True, float(yaw), float(pitch), float(roll)


def compute_face_features(
    landmarks: Optional[np.ndarray],
    image_hw: tuple[int, int],
) -> FaceFeatures:
    """Compute all face features from one frame's mesh.

    Parameters
    ----------
    landmarks : (N, 3) array or None
        Normalized Face Mesh landmarks. None ⇒ NaN features.
    image_hw : (height, width)
        Frame size used to denormalize landmark pixel coordinates.
    """
    feat = FaceFeatures()
    if landmarks is None or len(landmarks) < 478 - 10:  # accept 468 or 478
        return feat

    pts = _to_pixels(landmarks, image_hw)

    left_pts = pts[LEFT_EYE_EAR_INDICES]
    right_pts = pts[RIGHT_EYE_EAR_INDICES]
    feat.ear_left = _ear_from_points(*left_pts)
    feat.ear_right = _ear_from_points(*right_pts)
    if not (np.isnan(feat.ear_left) or np.isnan(feat.ear_right)):
        feat.ear_mean = 0.5 * (feat.ear_left + feat.ear_right)

    top = pts[MOUTH_TOP]
    bot = pts[MOUTH_BOTTOM]
    left = pts[MOUTH_LEFT]
    right = pts[MOUTH_RIGHT]
    horizontal = float(np.linalg.norm(left - right))
    if horizontal > 1e-6:
        feat.mar = float(np.linalg.norm(top - bot) / horizontal)

    pose_pts = np.stack(
        [pts[HEAD_POSE_INDICES[name]] for name in [
            "nose_tip",
            "chin",
            "left_eye_outer",
            "right_eye_outer",
            "left_mouth_corner",
            "right_mouth_corner",
        ]],
        axis=0,
    )
    ok, yaw, pitch, roll = _solve_head_pose(pose_pts, image_hw)
    feat.pose_solved = ok
    feat.yaw_deg = yaw
    feat.pitch_deg = pitch
    feat.roll_deg = roll
    return feat
