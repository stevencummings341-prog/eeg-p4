"""Check whether the video action tool environment is ready."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def check_import(name: str, import_name: str | None = None) -> bool:
    import_name = import_name or name
    try:
        mod = importlib.import_module(import_name)
        version = getattr(mod, "__version__", "unknown")
        print(f"[OK] {name}: {version}")
        return True
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False


def main() -> int:
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version}")
    ok = True
    ok &= check_import("numpy")
    ok &= check_import("pandas")
    ok &= check_import("cv2", "cv2")
    ok &= check_import("torch")
    ok &= check_import("ultralytics")
    ok &= check_import("mediapipe")
    ok &= check_import("pyarrow")
    ok &= check_import("tqdm")

    face_model = ROOT / "analysis" / "models" / "face_landmarker.task"
    yolo_weight = ROOT / "yolov8n-pose.pt"
    print(f"[{'OK' if face_model.exists() else 'FAIL'}] Face model: {face_model}")
    print(f"[{'OK' if yolo_weight.exists() else 'FAIL'}] YOLO weight: {yolo_weight}")
    ok &= face_model.exists()
    ok &= yolo_weight.exists()

    try:
        import analysis.gui  # noqa: F401
        import analysis.pipeline  # noqa: F401
        print("[OK] analysis package imports")
    except Exception as exc:
        print(f"[FAIL] analysis package imports: {exc}")
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
