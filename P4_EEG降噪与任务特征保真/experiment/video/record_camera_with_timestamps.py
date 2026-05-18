"""Record webcam video and per-frame absolute timestamps."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "scratch" / "video_records"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record a camera video and save one absolute timestamp per frame."
    )
    parser.add_argument("--camera", type=int, default=0, help="Camera index. Camera 1 auto-uses FFmpeg DirectShow on Windows.")
    parser.add_argument("--list-cameras", action="store_true", help="List available OpenCV camera indexes and exit.")
    parser.add_argument("--duration", type=float, default=60.0, help="Recording duration in seconds. Use 0 to record until Q/Ctrl+C.")
    parser.add_argument("--fps", type=float, default=30.0, help="Output video FPS.")
    parser.add_argument("--backend", choices=["auto", "opencv-dshow", "opencv-msmf", "opencv-any", "ffmpeg-dshow", "ffmpeg-file"], default="auto", help="Camera capture backend on Windows.")
    parser.add_argument("--device-name", default="Logi C310 HD WebCam", help="DirectShow device name for --backend ffmpeg-dshow.")
    parser.add_argument("--input-format", choices=["MJPG", "YUY2", "auto"], default="MJPG", help="Camera input format. MJPG is usually required for USB 720p/30fps.")
    parser.add_argument("--auto-exposure", choices=["auto", "manual", "leave"], default="manual", help="Exposure mode for OpenCV backends. Manual avoids Logitech low-light FPS drops.")
    parser.add_argument("--exposure", type=float, default=-6.0, help="Manual exposure value for OpenCV DirectShow; try -4 to -8 if the image is too dark/bright.")
    parser.add_argument("--gain", type=float, default=None, help="Optional camera gain for OpenCV backends.")
    parser.add_argument("--no-realtime-video", action="store_true", help="Write one video frame per captured camera frame instead of padding to real time.")
    parser.add_argument("--width", type=int, default=1280, help="Requested capture width.")
    parser.add_argument("--height", type=int, default=720, help="Requested capture height.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for mp4/csv/json outputs.")
    parser.add_argument("--prefix", default="camera", help="Output filename prefix.")
    parser.add_argument("--no-preview", action="store_true", help="Disable preview window.")
    parser.add_argument("--warmup-frames", type=int, default=10, help="Discard initial frames before recording.")
    parser.add_argument("--max-index", type=int, default=6, help="Highest camera index to probe with --list-cameras.")
    return parser.parse_args()


def resolve_backend(args: argparse.Namespace) -> str:
    if args.backend != "auto":
        return args.backend
    if platform.system() == "Windows" and args.camera == 1:
        return "ffmpeg-file"
    if platform.system() == "Windows":
        return "opencv-dshow"
    return "opencv-any"


def opencv_backend_id(name: str) -> int:
    if platform.system() != "Windows":
        return cv2.CAP_ANY
    return {
        "opencv-dshow": cv2.CAP_DSHOW,
        "opencv-msmf": cv2.CAP_MSMF,
        "opencv-any": cv2.CAP_ANY,
    }[name]


def fourcc_text(value: float) -> str:
    code = int(value)
    return "".join(chr((code >> 8 * i) & 255) for i in range(4)).strip("\x00")


def ffmpeg_input_codec(input_format: str) -> str:
    return {
        "MJPG": "mjpeg",
        "YUY2": "yuyv422",
        "auto": "mjpeg",
    }[input_format]


def open_opencv_camera(camera_index: int, backend: str) -> cv2.VideoCapture:
    return cv2.VideoCapture(camera_index, opencv_backend_id(backend))


def open_ffmpeg_pipe(args: argparse.Namespace) -> subprocess.Popen:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "dshow",
        "-rtbufsize",
        "256M",
        "-video_size",
        f"{args.width}x{args.height}",
        "-framerate",
        str(args.fps),
        "-vcodec",
        ffmpeg_input_codec(args.input_format),
        "-i",
        f"video={args.device_name}",
        "-an",
        "-pix_fmt",
        "bgr24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=args.width * args.height * 3 * 4,
    )


def read_ffmpeg_frame(process: subprocess.Popen, width: int, height: int) -> tuple[bool, np.ndarray | None]:
    frame_size = width * height * 3
    data = process.stdout.read(frame_size) if process.stdout else b""
    if len(data) != frame_size:
        return False, None
    return True, np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3))


def close_ffmpeg_pipe(process: subprocess.Popen | None) -> str:
    if process is None:
        return ""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    if not process.stderr:
        return ""
    return process.stderr.read().decode("utf-8", errors="replace").strip()


def list_cameras(max_index: int) -> None:
    print("Available OpenCV camera indexes:")
    found = False
    for camera_index in range(max_index + 1):
        cap = open_opencv_camera(camera_index, "opencv-dshow" if platform.system() == "Windows" else "opencv-any")
        ok = cap.isOpened()
        if ok:
            ret, _ = cap.read()
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            fmt = fourcc_text(cap.get(cv2.CAP_PROP_FOURCC))
            status = "readable" if ret else "opened but no frame returned"
            print(f"  {camera_index}: {status}, {width}x{height}, fps={fps:.2f}, format={fmt or 'unknown'}")
            found = True
        cap.release()
    if not found:
        print("  No available camera found. Check the USB camera connection and close apps using the camera.")


def make_output_paths(output_dir: Path, prefix: str) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = output_dir / f"{prefix}_{stamp}.mp4"
    timestamp_path = output_dir / f"{prefix}_{stamp}_timestamps.csv"
    metadata_path = output_dir / f"{prefix}_{stamp}_metadata.json"
    return video_path, timestamp_path, metadata_path


def seconds_from_ffmpeg_time(value: str) -> float | None:
    match = re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", value)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def iso_local_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def prepare_capture(args: argparse.Namespace, backend: str):
    if backend == "ffmpeg-dshow":
        process = open_ffmpeg_pipe(args)
        for _ in range(max(0, args.warmup_frames)):
            ret, _ = read_ffmpeg_frame(process, args.width, args.height)
            if not ret:
                error_text = close_ffmpeg_pipe(process)
                raise RuntimeError(f"Cannot read FFmpeg camera stream. {error_text}")
        return {
            "kind": "ffmpeg",
            "process": process,
            "cap": None,
            "actual_width": args.width,
            "actual_height": args.height,
            "camera_reported_fps": args.fps,
            "camera_format": ffmpeg_input_codec(args.input_format),
            "auto_exposure": None,
            "exposure": None,
            "gain": None,
        }

    cap = open_opencv_camera(args.camera, backend)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {args.camera}. Run --list-cameras first if unsure.")

    if args.input_format != "auto":
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.input_format))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    if args.auto_exposure == "manual":
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        cap.set(cv2.CAP_PROP_EXPOSURE, args.exposure)
    elif args.auto_exposure == "auto":
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
    if args.gain is not None:
        cap.set(cv2.CAP_PROP_GAIN, args.gain)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    for _ in range(max(0, args.warmup_frames)):
        cap.read()

    return {
        "kind": "opencv",
        "process": None,
        "cap": cap,
        "actual_width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "actual_height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "camera_reported_fps": float(cap.get(cv2.CAP_PROP_FPS)),
        "camera_format": fourcc_text(cap.get(cv2.CAP_PROP_FOURCC)),
        "auto_exposure": float(cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)),
        "exposure": float(cap.get(cv2.CAP_PROP_EXPOSURE)),
        "gain": float(cap.get(cv2.CAP_PROP_GAIN)),
    }


def read_capture_frame(capture: dict) -> tuple[bool, np.ndarray | None]:
    if capture["kind"] == "ffmpeg":
        return read_ffmpeg_frame(capture["process"], capture["actual_width"], capture["actual_height"])
    return capture["cap"].read()


def close_capture(capture: dict | None) -> str:
    if capture is None:
        return ""
    if capture["cap"] is not None:
        capture["cap"].release()
    return close_ffmpeg_pipe(capture["process"])


def record_ffmpeg_file(args: argparse.Namespace) -> None:
    if args.duration <= 0:
        raise RuntimeError("--backend ffmpeg-file requires --duration > 0. Use a fixed duration, e.g. --duration 600.")

    video_path, timestamp_path, metadata_path = make_output_paths(args.output_dir, args.prefix)
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "info",
        "-f",
        "dshow",
        "-rtbufsize",
        "256M",
        "-video_size",
        f"{args.width}x{args.height}",
        "-framerate",
        str(args.fps),
        "-vcodec",
        ffmpeg_input_codec(args.input_format),
        "-i",
        f"video={args.device_name}",
        "-t",
        str(args.duration),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        str(video_path),
    ]

    start_unix_ns = time.time_ns()
    start_perf_ns = time.perf_counter_ns()
    metadata = {
        "camera_index": args.camera,
        "device_name": args.device_name,
        "backend": "ffmpeg-file",
        "requested_input_format": args.input_format,
        "actual_input_format": ffmpeg_input_codec(args.input_format),
        "requested_width": args.width,
        "requested_height": args.height,
        "actual_width": args.width,
        "actual_height": args.height,
        "requested_fps": args.fps,
        "duration_seconds": args.duration,
        "video_path": str(video_path.resolve()),
        "timestamp_path": str(timestamp_path.resolve()),
        "start_unix_time_ns": start_unix_ns,
        "start_local_time_iso": iso_local_now(),
        "start_utc_time_iso": iso_utc_now(),
        "timestamp_definition": "Timestamps are estimated from FFmpeg CFR frame index and recording start time.",
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Start FFmpeg recording device {args.device_name}")
    print(f"Video:     {video_path.resolve()}")
    print(f"Timestamp: {timestamp_path.resolve()}")
    print(f"Metadata:  {metadata_path.resolve()}")
    print(f"Capture:   backend=ffmpeg-file; format={ffmpeg_input_codec(args.input_format)}")
    print(f"Frame:     {args.width}x{args.height}; FPS: {args.fps}; duration={args.duration:.1f}s")

    process = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
    stderr_lines: list[str] = []
    last_video_time = 0.0

    try:
        if process.stderr:
            for line in process.stderr:
                stderr_lines.append(line.rstrip())
                parsed_time = seconds_from_ffmpeg_time(line)
                if parsed_time is not None:
                    last_video_time = max(last_video_time, parsed_time)
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        return_code = process.returncode
        print("Ctrl+C received; FFmpeg recording stopped.")

    elapsed_total_seconds = (time.perf_counter_ns() - start_perf_ns) / 1_000_000_000
    video_duration_seconds = last_video_time if last_video_time > 0 else min(args.duration, elapsed_total_seconds)
    frame_count = int(round(video_duration_seconds * args.fps))

    with timestamp_path.open("w", newline="", encoding="utf-8") as f:
        csv_writer = csv.writer(f)
        csv_writer.writerow(
            [
                "video_frame_index",
                "capture_frame_index",
                "is_padding_frame",
                "unix_time_ns",
                "unix_time_seconds",
                "local_time_iso",
                "utc_time_iso",
                "elapsed_monotonic_seconds",
                "read_duration_ms",
            ]
        )
        for frame_index in range(frame_count):
            elapsed = frame_index / args.fps
            unix_time_ns = start_unix_ns + int(round(elapsed * 1_000_000_000))
            unix_seconds = unix_time_ns / 1_000_000_000
            csv_writer.writerow(
                [
                    frame_index,
                    frame_index,
                    False,
                    unix_time_ns,
                    f"{unix_seconds:.9f}",
                    datetime.fromtimestamp(unix_seconds).astimezone().isoformat(timespec="microseconds"),
                    datetime.fromtimestamp(unix_seconds, tz=timezone.utc).isoformat(timespec="microseconds"),
                    f"{elapsed:.9f}",
                    "",
                ]
            )

    metadata.update(
        {
            "end_local_time_iso": iso_local_now(),
            "end_utc_time_iso": iso_utc_now(),
            "return_code": return_code,
            "captured_camera_frames": frame_count,
            "written_video_frames": frame_count,
            "elapsed_total_seconds": elapsed_total_seconds,
            "estimated_video_duration_seconds": video_duration_seconds,
            "measured_capture_fps": frame_count / video_duration_seconds if video_duration_seconds else 0.0,
            "ffmpeg_stderr_tail": stderr_lines[-30:],
        }
    )
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    if return_code != 0:
        print("FFmpeg failed. Last messages:")
        for line in stderr_lines[-10:]:
            print(line)
        raise RuntimeError(f"FFmpeg exited with code {return_code}")

    print(f"Done. Wrote {frame_count} frames.")
    print(f"Estimated playback duration: {video_duration_seconds:.3f} seconds.")


def record(args: argparse.Namespace) -> None:
    backend = resolve_backend(args)
    if backend == "ffmpeg-file":
        record_ffmpeg_file(args)
        return

    capture = prepare_capture(args, backend)

    actual_width = capture["actual_width"]
    actual_height = capture["actual_height"]
    camera_reported_fps = capture["camera_reported_fps"]
    camera_format = capture["camera_format"]
    camera_auto_exposure = capture["auto_exposure"]
    camera_exposure = capture["exposure"]
    camera_gain = capture["gain"]

    video_path, timestamp_path, metadata_path = make_output_paths(args.output_dir, args.prefix)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, args.fps, (actual_width, actual_height))
    if not writer.isOpened():
        close_capture(capture)
        raise RuntimeError(f"Cannot create video file: {video_path}")

    capture_label = args.device_name if backend == "ffmpeg-dshow" else str(args.camera)
    metadata = {
        "camera_index": args.camera,
        "device_name": args.device_name if backend == "ffmpeg-dshow" else None,
        "backend": backend,
        "requested_input_format": args.input_format,
        "actual_input_format": camera_format,
        "requested_auto_exposure": args.auto_exposure,
        "requested_exposure": args.exposure,
        "actual_auto_exposure": camera_auto_exposure,
        "actual_exposure": camera_exposure,
        "actual_gain": camera_gain,
        "requested_width": args.width,
        "requested_height": args.height,
        "actual_width": actual_width,
        "actual_height": actual_height,
        "requested_fps": args.fps,
        "camera_reported_fps": camera_reported_fps,
        "duration_seconds": args.duration,
        "video_path": str(video_path.resolve()),
        "timestamp_path": str(timestamp_path.resolve()),
        "start_local_time_iso": iso_local_now(),
        "start_utc_time_iso": iso_utc_now(),
        "timestamp_definition": "unix_time_ns is recorded immediately after a camera frame is received.",
        "realtime_video_padding": not args.no_realtime_video,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Start recording camera {capture_label}")
    print(f"Video:     {video_path.resolve()}")
    print(f"Timestamp: {timestamp_path.resolve()}")
    print(f"Metadata:  {metadata_path.resolve()}")
    print(f"Capture:   backend={backend}; requested format={args.input_format}; actual format={camera_format or 'unknown'}")
    if camera_auto_exposure is not None:
        print(f"Exposure:  mode={camera_auto_exposure:.3f}; exposure={camera_exposure:.3f}; gain={camera_gain:.3f}")
    print(f"Frame:     {actual_width}x{actual_height}; writer FPS: {args.fps}; camera FPS: {camera_reported_fps:.2f}")
    if args.duration > 0:
        print(f"Duration:  {args.duration:.1f} seconds")
    else:
        print("Duration:  until Q or Ctrl+C")

    capture_frame_index = 0
    video_frame_index = 0
    skipped_capture_frames = 0
    start_perf_ns = time.perf_counter_ns()
    ffmpeg_error_text = ""

    try:
        with timestamp_path.open("w", newline="", encoding="utf-8") as f:
            csv_writer = csv.writer(f)
            csv_writer.writerow(
                [
                    "video_frame_index",
                    "capture_frame_index",
                    "is_padding_frame",
                    "unix_time_ns",
                    "unix_time_seconds",
                    "local_time_iso",
                    "utc_time_iso",
                    "elapsed_monotonic_seconds",
                    "read_duration_ms",
                ]
            )

            while True:
                read_start_perf_ns = time.perf_counter_ns()
                ret, frame = read_capture_frame(capture)
                unix_time_ns = time.time_ns()
                read_end_perf_ns = time.perf_counter_ns()

                if not ret or frame is None:
                    print("Camera read failed; recording stopped.")
                    break

                elapsed_seconds = (read_end_perf_ns - start_perf_ns) / 1_000_000_000
                read_duration_ms = (read_end_perf_ns - read_start_perf_ns) / 1_000_000
                local_time = iso_local_now()
                utc_time = iso_utc_now()

                if args.no_realtime_video:
                    frames_to_write = 1
                else:
                    target_video_frame_count = max(1, int(round(elapsed_seconds * args.fps)))
                    frames_to_write = target_video_frame_count - video_frame_index

                if frames_to_write <= 0:
                    skipped_capture_frames += 1
                else:
                    for padding_index in range(frames_to_write):
                        writer.write(frame)
                        csv_writer.writerow(
                            [
                                video_frame_index,
                                capture_frame_index,
                                padding_index > 0,
                                unix_time_ns,
                                f"{unix_time_ns / 1_000_000_000:.9f}",
                                local_time,
                                utc_time,
                                f"{elapsed_seconds:.9f}",
                                f"{read_duration_ms:.3f}",
                            ]
                        )
                        video_frame_index += 1

                capture_frame_index += 1

                if not args.no_preview:
                    cv2.imshow("Recording - press Q to stop", frame)
                    if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                        print("Q pressed; recording stopped.")
                        break

                if args.duration > 0 and elapsed_seconds >= args.duration:
                    print("Target duration reached; recording stopped.")
                    break

    except KeyboardInterrupt:
        print("Ctrl+C received; recording stopped.")
    finally:
        writer.release()
        ffmpeg_error_text = close_capture(capture)
        cv2.destroyAllWindows()

    elapsed_total_seconds = (time.perf_counter_ns() - start_perf_ns) / 1_000_000_000
    measured_capture_fps = capture_frame_index / elapsed_total_seconds if elapsed_total_seconds else 0.0
    metadata.update(
        {
            "end_local_time_iso": iso_local_now(),
            "end_utc_time_iso": iso_utc_now(),
            "captured_camera_frames": capture_frame_index,
            "written_video_frames": video_frame_index,
            "skipped_capture_frames": skipped_capture_frames,
            "elapsed_total_seconds": elapsed_total_seconds,
            "measured_capture_fps": measured_capture_fps,
            "estimated_video_duration_seconds": video_frame_index / args.fps if args.fps else None,
            "ffmpeg_stderr": ffmpeg_error_text,
        }
    )
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Done. Captured {capture_frame_index} camera frames; wrote {video_frame_index} video frames.")
    print(f"Measured capture FPS: {measured_capture_fps:.2f}")
    if args.fps:
        print(f"Estimated playback duration: {video_frame_index / args.fps:.3f} seconds.")


def main() -> int:
    args = parse_args()
    if args.list_cameras:
        list_cameras(args.max_index)
        return 0
    record(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
