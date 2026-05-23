"""CLI entry point for the video action extraction pipeline.

Example
-------
Run a quick 60s sanity check on a recording::

    cd P4_EEG/experiment/video/video_action_tool
    python -m analysis.run_analysis \\
        --video ../../data/video_records/camera_20260518_193936.mp4 \\
        --duration 60 \\
        --save-preview

Outputs land in ``experiment/video/analysis_outputs/<video_stem>/``
(unless overridden via ``--output-dir``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# experiment/video/analysis_outputs/<stem>/  — analysis outputs live next to the
# tool code (under experiment/video/), not inside the raw data tree.
_VIDEO_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_OUTPUT_PARENT = _VIDEO_DIR / "analysis_outputs"


def _default_output_dir(video_path: Path) -> Path:
    return _DEFAULT_OUTPUT_PARENT / video_path.stem


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", required=True, type=Path, help="Path to mp4 input video.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write outputs. Defaults to <video_dir>/analysis_outputs/<video_stem>/",
    )
    parser.add_argument("--start", type=float, default=0.0, help="Start time in seconds.")
    parser.add_argument("--duration", type=float, default=None, help="Duration to process in seconds. None = full video.")
    parser.add_argument("--device", type=str, default="cpu", help="YOLO device, e.g. cpu, 0, 0,1.")
    parser.add_argument("--yolo-model", type=str, default="yolov8n-pose.pt", help="Ultralytics YOLO model name/path.")
    parser.add_argument("--yolo-conf", type=float, default=0.35, help="YOLO detection confidence threshold.")
    parser.add_argument("--yolo-imgsz", type=int, default=640, help="YOLO inference image size.")
    parser.add_argument("--skip-face-mesh", action="store_true", help="Disable MediaPipe Face Mesh stage.")
    parser.add_argument("--skip-yolo", action="store_true", help="Disable YOLO stage.")
    parser.add_argument("--save-preview", action="store_true", help="Write an overlay preview mp4 (first preview-max-seconds).")
    parser.add_argument("--preview-max-seconds", type=float, default=60.0, help="Cap preview overlay length.")
    parser.add_argument("--no-csv", action="store_true", help="Skip per_frame.csv (parquet is always written).")
    parser.add_argument("--no-progress", action="store_true", help="Disable tqdm progress bar.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.video.exists():
        print(f"[error] video not found: {args.video}", file=sys.stderr)
        return 2

    out_dir = args.output_dir or _default_output_dir(args.video)

    from .pipeline import PipelineConfig, run_pipeline

    cfg = PipelineConfig(
        video_path=args.video,
        output_dir=out_dir,
        start_seconds=args.start,
        duration_seconds=args.duration,
        yolo_model=args.yolo_model,
        yolo_conf=args.yolo_conf,
        yolo_imgsz=args.yolo_imgsz,
        device=args.device,
        save_preview=args.save_preview,
        preview_max_seconds=args.preview_max_seconds,
        save_csv=not args.no_csv,
        skip_face_mesh=args.skip_face_mesh,
        skip_yolo=args.skip_yolo,
        progress=not args.no_progress,
    )

    meta = run_pipeline(cfg)
    print(json.dumps(meta["processed"], ensure_ascii=False, indent=2))
    print(f"[done] outputs in: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
