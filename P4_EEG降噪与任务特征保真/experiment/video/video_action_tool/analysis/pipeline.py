"""End-to-end pipeline: video -> per-frame features + events.

Outputs (in ``output_dir``):
- ``per_frame.parquet``     : compact per-frame table (kpts + EAR/MAR/head pose)
- ``per_frame.csv``         : same content as csv (optional, for quick inspection)
- ``events.csv``            : detected events table
- ``meta.json``             : processing parameters + alignment info
- ``preview_overlay.mp4``   : optional, drawn overlay (toggle via flag)

Designed for the P4 EEG experiment camera (1280x720@30fps from FFmpegCameraRecorder).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd
from tqdm import tqdm

from .events import EventConfig, detect_events
from .extractors import (
    COCO_KEYPOINT_NAMES,
    RELEVANT_BLENDSHAPES,
    FaceMeshExtractor,
    PoseExtractor,
)
from .features import compute_face_features


@dataclass
class PipelineConfig:
    video_path: Path
    output_dir: Path
    start_seconds: float = 0.0
    duration_seconds: Optional[float] = None
    yolo_model: str = "yolov8n-pose.pt"
    yolo_conf: float = 0.35
    yolo_imgsz: int = 640
    device: str = "cpu"
    save_preview: bool = False
    preview_max_seconds: float = 60.0
    save_csv: bool = True
    skip_face_mesh: bool = False
    skip_yolo: bool = False
    progress: bool = True
    progress_callback: Optional[Callable[[int, int], None]] = field(default=None, repr=False, compare=False)

    def to_serializable(self) -> dict:
        d = asdict(self)
        d["video_path"] = str(self.video_path)
        d["output_dir"] = str(self.output_dir)
        d.pop("progress_callback", None)
        return d


_PER_FRAME_FIXED_COLS = [
    "frame_index",
    "unix_time_ns",
    "unix_time_seconds",
    "elapsed_seconds",
    "yolo_detected",
    "yolo_bbox_x1",
    "yolo_bbox_y1",
    "yolo_bbox_x2",
    "yolo_bbox_y2",
    "yolo_bbox_conf",
    "face_detected",
    "ear_left",
    "ear_right",
    "ear_mean",
    "mar",
    "yaw_deg",
    "pitch_deg",
    "roll_deg",
    "pose_solved",
]


def _kpt_col_names() -> list[str]:
    cols = []
    for name in COCO_KEYPOINT_NAMES:
        cols += [f"kpt_{name}_x", f"kpt_{name}_y", f"kpt_{name}_conf"]
    return cols


def _blendshape_col_names() -> list[str]:
    return [f"bs_{name}" for name in RELEVANT_BLENDSHAPES]


def _resolve_timestamps_csv(video_path: Path) -> Optional[Path]:
    candidate = video_path.with_name(video_path.stem + "_timestamps.csv")
    return candidate if candidate.exists() else None


def _load_timestamps(video_path: Path) -> Optional[pd.DataFrame]:
    ts_path = _resolve_timestamps_csv(video_path)
    if ts_path is None:
        return None
    try:
        ts = pd.read_csv(ts_path)
    except Exception:
        return None
    if "video_frame_index" not in ts.columns:
        return None
    ts = ts.rename(columns={"video_frame_index": "frame_index"})
    keep_cols = [c for c in ["frame_index", "unix_time_ns", "unix_time_seconds", "elapsed_seconds"] if c in ts.columns]
    return ts[keep_cols]


def _draw_overlay(frame_bgr, frame_row: dict, face_landmarks: Optional[np.ndarray]):
    import cv2

    img = frame_bgr.copy()
    if frame_row.get("yolo_detected"):
        x1 = int(frame_row["yolo_bbox_x1"])
        y1 = int(frame_row["yolo_bbox_y1"])
        x2 = int(frame_row["yolo_bbox_x2"])
        y2 = int(frame_row["yolo_bbox_y2"])
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)

    for name in COCO_KEYPOINT_NAMES:
        cx = frame_row.get(f"kpt_{name}_x")
        cy = frame_row.get(f"kpt_{name}_y")
        cf = frame_row.get(f"kpt_{name}_conf", 0.0)
        if cx is None or cy is None or np.isnan(cx) or np.isnan(cy):
            continue
        if cf > 0.3:
            cv2.circle(img, (int(cx), int(cy)), 3, (255, 0, 255), -1)

    if face_landmarks is not None:
        h, w = img.shape[:2]
        for idx in [33, 133, 362, 263, 1, 152, 13, 14, 78, 308]:
            if idx >= len(face_landmarks):
                continue
            x = int(face_landmarks[idx, 0] * w)
            y = int(face_landmarks[idx, 1] * h)
            cv2.circle(img, (x, y), 2, (0, 200, 255), -1)

    ear = frame_row.get("ear_mean")
    yaw = frame_row.get("yaw_deg")
    pitch = frame_row.get("pitch_deg")

    def _fmt(v):
        return "nan" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.2f}"

    txt = f"EAR={_fmt(ear)}  yaw={_fmt(yaw)}  pitch={_fmt(pitch)}"
    cv2.putText(img, txt, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def run_pipeline(cfg: PipelineConfig) -> dict:
    import cv2

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = cfg.output_dir / "per_frame.parquet"
    csv_path = cfg.output_dir / "per_frame.csv"
    events_path = cfg.output_dir / "events.csv"
    meta_path = cfg.output_dir / "meta.json"
    preview_path = cfg.output_dir / "preview_overlay.mp4"

    cap = cv2.VideoCapture(str(cfg.video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {cfg.video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    start_frame = int(round(cfg.start_seconds * src_fps))
    if cfg.duration_seconds is None:
        end_frame = src_total_frames
    else:
        end_frame = min(start_frame + int(round(cfg.duration_seconds * src_fps)), src_total_frames)
    expected_frames = max(0, end_frame - start_frame)

    if start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    pose_extractor = None if cfg.skip_yolo else PoseExtractor(
        model_name=cfg.yolo_model,
        conf=cfg.yolo_conf,
        device=cfg.device,
        imgsz=cfg.yolo_imgsz,
    )
    face_extractor_cm = (
        FaceMeshExtractor() if not cfg.skip_face_mesh else None
    )

    timestamps_df = _load_timestamps(cfg.video_path)

    writer = None
    if cfg.save_preview:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(preview_path), fourcc, src_fps, (src_w, src_h))

    kpt_cols = _kpt_col_names()
    blendshape_cols = _blendshape_col_names()
    all_cols = _PER_FRAME_FIXED_COLS + kpt_cols + blendshape_cols
    rows: list[dict] = []

    try:
        iterator = range(start_frame, end_frame)
        if cfg.progress:
            iterator = tqdm(iterator, desc="extract", total=expected_frames, mininterval=1.0)
        for frame_index in iterator:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            row = {col: float("nan") for col in all_cols}
            row["frame_index"] = frame_index
            row["face_detected"] = False
            row["yolo_detected"] = False
            row["pose_solved"] = False

            if pose_extractor is not None:
                bbox, keypoints = pose_extractor.infer(frame)
                if bbox is not None:
                    row["yolo_detected"] = True
                    row["yolo_bbox_x1"] = float(bbox[0])
                    row["yolo_bbox_y1"] = float(bbox[1])
                    row["yolo_bbox_x2"] = float(bbox[2])
                    row["yolo_bbox_y2"] = float(bbox[3])
                    row["yolo_bbox_conf"] = float(bbox[4])
                if keypoints is not None:
                    for i, name in enumerate(COCO_KEYPOINT_NAMES):
                        row[f"kpt_{name}_x"] = float(keypoints[i, 0])
                        row[f"kpt_{name}_y"] = float(keypoints[i, 1])
                        row[f"kpt_{name}_conf"] = float(keypoints[i, 2])

            face_landmarks = None
            if face_extractor_cm is not None:
                timestamp_ms = int(round((frame_index - start_frame) * 1000.0 / max(src_fps, 1e-6)))
                fm_result = face_extractor_cm.infer(frame, timestamp_ms=timestamp_ms)
                face_landmarks = fm_result.landmarks
                if face_landmarks is not None:
                    row["face_detected"] = True
                    feats = compute_face_features(face_landmarks, image_hw=(src_h, src_w))
                    row["ear_left"] = feats.ear_left
                    row["ear_right"] = feats.ear_right
                    row["ear_mean"] = feats.ear_mean
                    row["mar"] = feats.mar
                    row["yaw_deg"] = feats.yaw_deg
                    row["pitch_deg"] = feats.pitch_deg
                    row["roll_deg"] = feats.roll_deg
                    row["pose_solved"] = feats.pose_solved
                for name in RELEVANT_BLENDSHAPES:
                    if name in fm_result.blendshapes:
                        row[f"bs_{name}"] = fm_result.blendshapes[name]

            rows.append(row)

            if writer is not None:
                elapsed_s = (frame_index - start_frame) / max(src_fps, 1e-6)
                if elapsed_s <= cfg.preview_max_seconds:
                    overlay = _draw_overlay(frame, row, face_landmarks)
                    writer.write(overlay)

            if cfg.progress_callback is not None:
                processed = frame_index - start_frame + 1
                if processed == 1 or processed == expected_frames or processed % 10 == 0:
                    cfg.progress_callback(processed, expected_frames)
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        if face_extractor_cm is not None:
            face_extractor_cm.close()

    df = pd.DataFrame(rows, columns=all_cols)

    if timestamps_df is not None:
        df = df.merge(timestamps_df, on="frame_index", how="left", suffixes=("", "_ts"))
        for col in ["unix_time_ns", "unix_time_seconds", "elapsed_seconds"]:
            ts_col = col + "_ts"
            if ts_col in df.columns:
                df[col] = df[ts_col]
                df = df.drop(columns=[ts_col])

    final_cols = _PER_FRAME_FIXED_COLS + kpt_cols + blendshape_cols
    df = df[[c for c in final_cols if c in df.columns]]

    df.to_parquet(parquet_path, index=False)
    if cfg.save_csv:
        df.to_csv(csv_path, index=False)

    events_cfg = EventConfig(fps=float(src_fps))
    events_df = detect_events(df, cfg=events_cfg)
    events_df.to_csv(events_path, index=False)

    meta = {
        "config": cfg.to_serializable(),
        "source_video": {
            "path": str(cfg.video_path),
            "fps": src_fps,
            "total_frames": src_total_frames,
            "width": src_w,
            "height": src_h,
        },
        "processed": {
            "start_frame": start_frame,
            "end_frame": end_frame,
            "frames_written": int(len(df)),
            "face_detection_rate": float(df["face_detected"].mean()) if len(df) else 0.0,
            "yolo_detection_rate": float(df["yolo_detected"].mean()) if len(df) else 0.0,
            "events_count": int(len(events_df)),
            "events_breakdown": events_df["event_type"].value_counts().to_dict() if len(events_df) else {},
        },
        "outputs": {
            "per_frame_parquet": str(parquet_path),
            "per_frame_csv": str(csv_path) if cfg.save_csv else None,
            "events_csv": str(events_path),
            "preview_overlay": str(preview_path) if cfg.save_preview else None,
        },
        "event_config": asdict(events_cfg),
        "generated_at_iso": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
