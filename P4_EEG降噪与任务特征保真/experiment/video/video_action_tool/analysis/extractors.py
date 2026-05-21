"""Per-frame extractors: YOLOv8-Pose + MediaPipe Face Landmarker.

Both extractors are lazy-initialized so import is cheap.

YOLO weights (``yolov8n-pose.pt``) are auto-downloaded by ultralytics on first use.

MediaPipe Face Landmarker uses the Tasks API (the legacy ``mp.solutions.face_mesh``
is missing on this install). The model ``face_landmarker.task`` is expected at
``analysis/models/face_landmarker.task`` and is loaded via ``model_asset_buffer``
to dodge Windows non-ASCII path bugs in MediaPipe's C++ layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


DEFAULT_FACE_LANDMARKER_MODEL = (
    Path(__file__).resolve().parent / "models" / "face_landmarker.task"
)

# Blendshapes from FaceLandmarker we care about (subset of the 52 outputs).
RELEVANT_BLENDSHAPES = (
    "eyeBlinkLeft",
    "eyeBlinkRight",
    "eyeLookDownLeft",
    "eyeLookDownRight",
    "eyeLookInLeft",
    "eyeLookInRight",
    "eyeLookOutLeft",
    "eyeLookOutRight",
    "eyeLookUpLeft",
    "eyeLookUpRight",
    "eyeSquintLeft",
    "eyeSquintRight",
    "jawOpen",
    "jawLeft",
    "jawRight",
    "mouthClose",
    "mouthPucker",
    "mouthFunnel",
    "browDownLeft",
    "browDownRight",
    "browInnerUp",
)


COCO_KEYPOINT_NAMES = [
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
]


@dataclass
class FrameResult:
    """Container for one frame's extraction results."""

    frame_index: int
    pose_bbox: Optional[np.ndarray] = None  # (x1, y1, x2, y2, conf)
    pose_keypoints: Optional[np.ndarray] = None  # (17, 3) -> x, y, conf
    face_landmarks: Optional[np.ndarray] = None  # (468, 3) -> x, y, z (normalized)
    face_detected: bool = False
    image_size: tuple[int, int] = (0, 0)  # (height, width)
    extras: dict = field(default_factory=dict)


class PoseExtractor:
    """Wrapper around YOLOv8-Pose returning keypoints for the highest-confidence person."""

    def __init__(
        self,
        model_name: str = "yolov8n-pose.pt",
        conf: float = 0.35,
        iou: float = 0.5,
        device: str = "cpu",
        imgsz: int = 640,
        verbose: bool = False,
    ) -> None:
        from ultralytics import YOLO

        self.model = YOLO(model_name)
        self.conf = conf
        self.iou = iou
        self.device = device
        self.imgsz = imgsz
        self.verbose = verbose

    def infer(self, frame_bgr: np.ndarray) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Run YOLO on one BGR frame.

        Returns
        -------
        bbox : Optional[np.ndarray]
            Shape (5,) with (x1, y1, x2, y2, conf) for the best person, or None.
        keypoints : Optional[np.ndarray]
            Shape (17, 3) with (x, y, conf) in pixel coordinates, or None.
        """
        results = self.model.predict(
            frame_bgr,
            conf=self.conf,
            iou=self.iou,
            device=self.device,
            imgsz=self.imgsz,
            verbose=self.verbose,
        )
        if not results:
            return None, None

        result = results[0]
        if result.boxes is None or len(result.boxes) == 0:
            return None, None

        confs = result.boxes.conf.cpu().numpy()
        best = int(np.argmax(confs))

        bbox_xyxy = result.boxes.xyxy.cpu().numpy()[best]
        bbox = np.concatenate([bbox_xyxy, [float(confs[best])]]).astype(np.float32)

        if result.keypoints is None or result.keypoints.data is None:
            return bbox, None

        kpt_data = result.keypoints.data.cpu().numpy()
        if kpt_data.ndim != 3 or kpt_data.shape[0] <= best:
            return bbox, None

        keypoints = kpt_data[best].astype(np.float32)  # (17, 3): x, y, conf
        return bbox, keypoints


@dataclass
class FaceMeshResult:
    """Per-frame Face Landmarker output."""

    landmarks: Optional[np.ndarray] = None   # (478, 3) normalized x, y, z
    blendshapes: dict = field(default_factory=dict)  # {blendshape_name: float}


class FaceMeshExtractor:
    """Wrapper around MediaPipe Face Landmarker (Tasks API).

    Operates in VIDEO running mode, so callers must provide a monotonically
    increasing timestamp in milliseconds via :meth:`infer`.
    """

    def __init__(
        self,
        model_path: Path | str | None = None,
        num_faces: int = 1,
        min_face_detection_confidence: float = 0.5,
        min_face_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        output_blendshapes: bool = True,
    ) -> None:
        from mediapipe.tasks.python.core.base_options import BaseOptions
        from mediapipe.tasks.python.vision.face_landmarker import (
            FaceLandmarker,
            FaceLandmarkerOptions,
        )
        from mediapipe.tasks.python.vision.core.vision_task_running_mode import (
            VisionTaskRunningMode,
        )

        path = Path(model_path) if model_path is not None else DEFAULT_FACE_LANDMARKER_MODEL
        if not path.exists():
            raise FileNotFoundError(
                f"face_landmarker.task not found at {path}. Run "
                "`python analysis/_download_model.py` first."
            )

        # Load via in-memory buffer to dodge MediaPipe's non-ASCII Windows path bug.
        model_bytes = path.read_bytes()

        opts = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=model_bytes),
            running_mode=VisionTaskRunningMode.VIDEO,
            num_faces=num_faces,
            min_face_detection_confidence=min_face_detection_confidence,
            min_face_presence_confidence=min_face_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_face_blendshapes=output_blendshapes,
            output_facial_transformation_matrixes=False,
        )
        self._landmarker = FaceLandmarker.create_from_options(opts)
        self._mp_image_cls = None
        self._mp_image_format = None

    def _make_mp_image(self, rgb_array: np.ndarray):
        if self._mp_image_cls is None:
            import mediapipe as mp

            self._mp_image_cls = mp.Image
            self._mp_image_format = mp.ImageFormat.SRGB
        return self._mp_image_cls(image_format=self._mp_image_format, data=rgb_array)

    def infer(self, frame_bgr: np.ndarray, timestamp_ms: int) -> FaceMeshResult:
        """Run Face Landmarker on one BGR frame.

        Parameters
        ----------
        frame_bgr : np.ndarray
            BGR-format frame as returned by cv2.VideoCapture.read().
        timestamp_ms : int
            Monotonically increasing frame timestamp in milliseconds (relative
            to the start of the video).
        """
        import cv2

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = self._make_mp_image(rgb)
        result = self._landmarker.detect_for_video(mp_image, int(timestamp_ms))

        out = FaceMeshResult()
        if not result.face_landmarks:
            return out

        lm = result.face_landmarks[0]
        out.landmarks = np.array(
            [(p.x, p.y, getattr(p, "z", 0.0)) for p in lm],
            dtype=np.float32,
        )
        if getattr(result, "face_blendshapes", None):
            bs = result.face_blendshapes[0]
            out.blendshapes = {
                b.category_name: float(b.score)
                for b in bs
                if b.category_name in RELEVANT_BLENDSHAPES
            }
        return out

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "FaceMeshExtractor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
