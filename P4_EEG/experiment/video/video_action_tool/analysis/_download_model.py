"""Download MediaPipe face_landmarker.task model with progress + integrity check."""

import hashlib
import sys
import urllib.request
from pathlib import Path

URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"


def main() -> int:
    dest = Path(__file__).resolve().parent / "models" / "face_landmarker.task"
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"downloading: {URL}")
    print(f"  -> {dest}")

    chunk = 64 * 1024
    bytes_done = 0
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        h = hashlib.sha256()
        with open(dest, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                h.update(buf)
                bytes_done += len(buf)
                if total:
                    pct = 100 * bytes_done / total
                    print(f"  {bytes_done/1024:.0f} KB / {total/1024:.0f} KB ({pct:.0f}%)", flush=True)
                else:
                    print(f"  {bytes_done/1024:.0f} KB", flush=True)
    print(f"done. final size = {dest.stat().st_size} bytes")
    print(f"sha256 = {h.hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
