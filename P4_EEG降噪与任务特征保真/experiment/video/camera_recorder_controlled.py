"""Start and stop FFmpeg camera recording from Python code."""

from __future__ import annotations

import csv
import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = (SCRIPT_DIR / ".." / "data" / "video_records").resolve()


@dataclass
class FFmpegCameraRecorder:
    device_name: str = "FF-Camera"
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    output_dir: Path = DEFAULT_OUTPUT_DIR
    prefix: str = "camera"
    input_codec: str = "mjpeg"

    process: subprocess.Popen | None = field(default=None, init=False)
    video_path: Path | None = field(default=None, init=False)
    timestamp_path: Path | None = field(default=None, init=False)
    metadata_path: Path | None = field(default=None, init=False)
    log_path: Path | None = field(default=None, init=False)
    log_file: object | None = field(default=None, init=False)
    start_unix_ns: int | None = field(default=None, init=False)
    start_perf_ns: int | None = field(default=None, init=False)

    def start(self) -> tuple[Path, Path, Path]:
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError("Recording is already running.")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.video_path = self.output_dir / f"{self.prefix}_{stamp}.mp4"
        self.timestamp_path = self.output_dir / f"{self.prefix}_{stamp}_timestamps.csv"
        self.metadata_path = self.output_dir / f"{self.prefix}_{stamp}_metadata.json"
        self.log_path = self.output_dir / f"{self.prefix}_{stamp}_ffmpeg.log"

        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-f",
            "dshow",
            "-rtbufsize",
            "256M",
            "-video_size",
            f"{self.width}x{self.height}",
            "-framerate",
            str(self.fps),
            "-vcodec",
            self.input_codec,
            "-i",
            f"video={self.device_name}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(self.video_path),
        ]

        self.start_unix_ns = time.time_ns()
        self.start_perf_ns = time.perf_counter_ns()
        self.log_file = self.log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=self.log_file,
            text=True,
        )

        self._write_metadata(
            {
                "device_name": self.device_name,
                "width": self.width,
                "height": self.height,
                "fps": self.fps,
                "input_codec": self.input_codec,
                "video_path": str(self.video_path.resolve()),
                "timestamp_path": str(self.timestamp_path.resolve()),
                "log_path": str(self.log_path.resolve()),
                "start_unix_time_ns": self.start_unix_ns,
                "start_local_time_iso": datetime.fromtimestamp(self.start_unix_ns / 1_000_000_000).astimezone().isoformat(timespec="microseconds"),
                "start_utc_time_iso": datetime.fromtimestamp(self.start_unix_ns / 1_000_000_000, tz=timezone.utc).isoformat(timespec="microseconds"),
                "timestamp_definition": "Frame timestamps are estimated as recording_start_time + frame_index / fps after FFmpeg finalizes the video.",
            }
        )

        time.sleep(0.5)
        if self.process.poll() is not None:
            self._close_log_file()
            raise RuntimeError(f"FFmpeg failed to start. Check log: {self.log_path}")

        return self.video_path, self.timestamp_path, self.metadata_path

    def stop(self, timeout: float = 5.0) -> dict:
        if self.process is None:
            raise RuntimeError("Recording has not been started.")

        if self.process.poll() is None:
            try:
                if self.process.stdin:
                    self.process.stdin.write("q\n")
                    self.process.stdin.flush()
                self.process.wait(timeout=timeout)
            except Exception:
                self.process.terminate()
                try:
                    self.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=timeout)

        self._close_log_file()
        elapsed_seconds = (time.perf_counter_ns() - self.start_perf_ns) / 1_000_000_000
        frame_count, video_fps = self._read_video_info()
        if frame_count <= 0:
            video_fps = self.fps
            frame_count = max(0, int(round(elapsed_seconds * self.fps)))

        self._write_timestamp_csv(frame_count, video_fps)

        result = {
            "video_path": str(self.video_path.resolve()),
            "timestamp_path": str(self.timestamp_path.resolve()),
            "metadata_path": str(self.metadata_path.resolve()),
            "log_path": str(self.log_path.resolve()),
            "return_code": self.process.returncode,
            "elapsed_seconds": elapsed_seconds,
            "frame_count": frame_count,
            "video_fps": video_fps,
            "estimated_video_duration_seconds": frame_count / video_fps if video_fps else None,
        }
        self._write_metadata(result, merge=True)
        return result

    def _read_video_info(self) -> tuple[int, float]:
        try:
            import cv2
        except ImportError:
            return 0, self.fps

        cap = cv2.VideoCapture(str(self.video_path))
        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            video_fps = float(cap.get(cv2.CAP_PROP_FPS)) or self.fps
        finally:
            cap.release()
        return frame_count, video_fps

    def _write_timestamp_csv(self, frame_count: int, video_fps: float) -> None:
        if self.start_unix_ns is None:
            raise RuntimeError("Missing recording start time.")

        with self.timestamp_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "video_frame_index",
                    "unix_time_ns",
                    "unix_time_seconds",
                    "local_time_iso",
                    "utc_time_iso",
                    "elapsed_seconds",
                ]
            )
            for frame_index in range(frame_count):
                elapsed = frame_index / video_fps
                unix_time_ns = self.start_unix_ns + int(round(elapsed * 1_000_000_000))
                unix_seconds = unix_time_ns / 1_000_000_000
                writer.writerow(
                    [
                        frame_index,
                        unix_time_ns,
                        f"{unix_seconds:.9f}",
                        datetime.fromtimestamp(unix_seconds).astimezone().isoformat(timespec="microseconds"),
                        datetime.fromtimestamp(unix_seconds, tz=timezone.utc).isoformat(timespec="microseconds"),
                        f"{elapsed:.9f}",
                    ]
                )

    def _write_metadata(self, data: dict, merge: bool = False) -> None:
        if merge and self.metadata_path.exists():
            old_data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            old_data.update(data)
            data = old_data
        self.metadata_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _close_log_file(self) -> None:
        if self.log_file:
            self.log_file.close()
            self.log_file = None

    def __enter__(self) -> FFmpegCameraRecorder:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()


if __name__ == "__main__":
    recorder = FFmpegCameraRecorder()
    video_path, timestamp_path, metadata_path = recorder.start()
    print(f"Recording started: {video_path}")
    input("Press Enter to stop recording...")
    result = recorder.stop()
    print("Recording stopped.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
