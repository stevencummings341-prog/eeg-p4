"""Video action / pose extraction for P4 EEG experiment.

Combines YOLOv8-Pose (body keypoints, head coarse pose) with MediaPipe Face Mesh
(EAR/MAR for blink and mouth state, fine head pose via solvePnP).

Designed to align with experiment camera timestamps so that detected events
can be mapped to EEG markers later on.
"""

from .extractors import PoseExtractor, FaceMeshExtractor, FrameResult
from .features import compute_face_features, FaceFeatures
from .events import detect_events, EventConfig

__all__ = [
    "PoseExtractor",
    "FaceMeshExtractor",
    "FrameResult",
    "compute_face_features",
    "FaceFeatures",
    "detect_events",
    "EventConfig",
]
