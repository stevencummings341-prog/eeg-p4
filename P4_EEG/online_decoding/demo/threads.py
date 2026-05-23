"""
threads.py — LSL 采集线程 + 摄像头采集线程

所有采集线程输出带 perf_counter_ns 时间戳的数据，确保跨源对齐。
"""

import time
import queue
import logging
import threading

import numpy as np

import config

log = logging.getLogger("threads")

# ============================================================
# 时间戳数据封装
# ============================================================

class Sample:
    """LSL 数据块 + 本机到达时间"""
    __slots__ = ("data", "lsl_ts", "arrival_ns")

    def __init__(self, data: np.ndarray, lsl_ts: list, arrival_ns: int):
        self.data = data              # (n_channels, n_samples)
        self.lsl_ts = lsl_ts          # LSL 硬件时间戳
        self.arrival_ns = arrival_ns  # time.perf_counter_ns()


class Frame:
    """摄像头帧 + 采集时间"""
    __slots__ = ("image", "capture_ns")

    def __init__(self, image: np.ndarray, capture_ns: int):
        self.image = image            # BGR H×W×3
        self.capture_ns = capture_ns  # time.perf_counter_ns()


# ============================================================
# LSL 读取线程
# ============================================================

class LSLReader:
    """发现 iRe 流 → pull_chunk → 写入队列"""

    def __init__(self, data_queue: queue.Queue, target_name: str = ""):
        self.data_queue = data_queue
        self.target_name = target_name
        self.running = False
        self.inlet = None
        self.fs = config.DEFAULT_SFREQ
        self._connected = threading.Event()
        self._thread = threading.Thread(target=self._run, name="LSL", daemon=True)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def start(self):
        self.running = True
        self._thread.start()

    def stop(self):
        self.running = False

    def _run(self):
        from pylsl import StreamInlet, resolve_streams

        log.info("搜索 LSL 流...")
        streams = resolve_streams(config.LSL_TIMEOUT)
        for s in streams:
            if s.type() == "EEG" and self.target_name in s.name():
                self.inlet = StreamInlet(s)
                log.info("LSL 连接: %s", s.name())
                break

        if self.inlet is None and streams:
            self.inlet = StreamInlet(streams[0])
            log.info("LSL 兜底: %s", streams[0].name())

        if self.inlet is None:
            log.warning("未找到 LSL 流 (timeout=%.0fs)，进入离线模式。", config.LSL_TIMEOUT)
            return

        self.fs = int(self.inlet.info().nominal_srate())
        self._connected.set()
        log.info("采样率: %d Hz", self.fs)

        while self.running:
            try:
                chunk, lsl_ts = self.inlet.pull_chunk(timeout=1.0)
                if lsl_ts:
                    self.data_queue.put(Sample(
                        data=np.array(chunk),
                        lsl_ts=lsl_ts,
                        arrival_ns=time.perf_counter_ns(),
                    ))
                else:
                    time.sleep(0.001)
            except Exception:
                log.exception("LSL 读取异常")
                break

        self.inlet.close_stream()
        self._connected.clear()
        log.info("LSL 已关闭。")


# ============================================================
# 摄像头采集线程
# ============================================================

class CameraCapture:
    """OpenCV 摄像头 -> 锁保护的最新帧 + 时间戳

    支持两种定位方式（优先级从高到低）：
    1. camera_name: Windows dshow 设备名，如 "HD USB Camera"
    2. camera_index: 整数索引，0=内置, 1=外接 USB
    """

    def __init__(self, camera_index: int = 0, camera_name: str = "",
                 backend: str = "dshow",
                 fps: float = 30.0, width: int = 640, height: int = 480):
        self.camera_index = camera_index
        self.camera_name = camera_name
        self.backend = backend
        self.target_fps = fps
        self.width = width
        self.height = height
        self.running = False
        self.cap = None
        self.actual_fps = 0.0

        self._lock = threading.Lock()
        self._latest_image: np.ndarray | None = None
        self._latest_ns: int = 0

        self._thread = threading.Thread(target=self._run, name="Camera", daemon=True)
        self._connected = threading.Event()

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def snapshot(self) -> tuple[np.ndarray | None, int]:
        """线程安全地获取最新帧和采集时间"""
        with self._lock:
            return self._latest_image, self._latest_ns

    def start(self):
        self.running = True
        self._thread.start()

    def stop(self):
        self.running = False

    def _run(self):
        import cv2

        backends = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}
        api = backends.get(self.backend, cv2.CAP_ANY)

        if self.camera_name:
            uri = f"video={self.camera_name}" if self.backend == "dshow" else self.camera_name
            log.info("Opening camera (name=%s, backend=%s)", self.camera_name, self.backend or "auto")
            self.cap = cv2.VideoCapture(uri, api)
        else:
            log.info("Opening camera (index=%d, backend=%s)", self.camera_index, self.backend or "auto")
            self.cap = cv2.VideoCapture(self.camera_index, api)

        if not self.cap.isOpened():
            log.warning("Camera not available (index=%d, name=%s), offline mode.",
                        self.camera_index, self.camera_name or "-")
            return

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)

        self.actual_fps = self.cap.get(cv2.CAP_PROP_FPS) or self.target_fps
        self._connected.set()
        ident = self.camera_name or str(self.camera_index)
        log.info("Camera opened (%s, %dx%d, fps~%.1f)", ident, self.width, self.height, self.actual_fps)

        interval = 1.0 / self.target_fps

        while self.running:
            t0 = time.perf_counter()
            ret, frame = self.cap.read()
            ns = time.perf_counter_ns()

            if ret:
                with self._lock:
                    self._latest_image = frame
                    self._latest_ns = ns
            else:
                time.sleep(0.05)

            dt = time.perf_counter() - t0
            if dt < interval:
                time.sleep(interval - dt)

        self.cap.release()
        self._connected.clear()
        log.info("摄像头已释放。")
