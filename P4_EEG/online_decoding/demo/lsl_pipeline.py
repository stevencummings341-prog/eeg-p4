"""
lsl_pipeline.py — iRe 脑电 LSL 实时传输 + 摄像头同步可视化

架构：双采集线程 (LSL / Camera) + 双刷新定时器 (Render / Analysis)
所有时间戳统一用 time.perf_counter_ns() 确保跨源对齐。

用法:
    python lsl_pipeline.py                  # 完整模式
    python lsl_pipeline.py --no-camera      # 仅 EEG
    python lsl_pipeline.py --no-lsl         # 仅摄像头
"""

from __future__ import annotations

import sys
import time
import queue
import logging
import argparse

import config
config.bootstrap()  # 必须在所有 GUI import 前调用

import numpy as np

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGroupBox, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QImage

import pyqtgraph as pg
import matplotlib
import matplotlib.pyplot as _plt
import mne
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import cv2

from threads import LSLReader, CameraCapture
from utils import RingBuffer, band_power

# ============================================================
# 日志
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)
log = logging.getLogger("pipeline")

# ============================================================
# MNE Topomap
# ============================================================

class TopoCanvas(FigureCanvas):
    """MNE 头皮地形图 — 低频刷新，复用 MNE info 对象"""

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig, self.ax = _plt.subplots(figsize=(width, height), dpi=dpi)
        self.fig.patch.set_facecolor("white")
        self.ax.axis("off")
        super().__init__(self.fig)
        self.setParent(parent)
        self.fig.tight_layout(pad=0)

        montage = mne.channels.make_standard_montage("standard_1020")
        self.info = mne.create_info(
            ch_names=config.CHANNEL_NAMES,
            sfreq=config.DEFAULT_SFREQ,
            ch_types="eeg",
        )
        self.info.set_montage(montage)

    def update_topo(self, data: np.ndarray):
        if len(data) != len(config.CHANNEL_NAMES):
            return
        self.ax.clear()
        mne.viz.plot_topomap(
            data, self.info, axes=self.ax,
            show=False, cmap="RdBu_r", contours=4,
            sensors=True, sphere="auto",
        )
        self.draw()


# ============================================================
# 同步指示灯
# ============================================================

class SyncIndicator(QFrame):
    """颜色圆点：绿(<50ms) / 橙(<150ms) / 红(>150ms) / 灰(离线)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self._set("gray")

    def set_offset(self, abs_delta_ms: float):
        if abs_delta_ms < 50:
            self._set("#27ae60")
        elif abs_delta_ms < 150:
            self._set("#f39c12")
        else:
            self._set("#e74c3c")

    def set_offline(self):
        self._set("gray")

    def _set(self, color: str):
        self.setStyleSheet(
            f"background-color: {color}; border-radius: 9px;"
        )


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QWidget):

    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self._args = args
        self._setup_data()
        self._setup_acquisition()
        self._init_ui()
        self._setup_timers()

        self.setWindowTitle("iRe EEG + Camera — Real-Time Viewer")
        self.resize(1920, 960)

    # ==================== 数据 ====================

    def _setup_data(self):
        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")

        self.fs = config.DEFAULT_SFREQ
        n_ch = len(config.CHANNEL_NAMES)
        cap = int(self.fs * config.PLOT_WINDOW_SEC)

        self.buffer = RingBuffer(n_ch, cap)
        self._n_psd_new = 0               # 上次 PSD 后新样本数

        # 通道索引
        idx = {n: i for i, n in enumerate(config.CHANNEL_NAMES)}
        self.idx_t7 = idx.get("T7", 0)
        self.idx_t8 = idx.get("T8", 1)

        # 偏侧化历史
        hist_len = int(config.LATERAL_HISTORY_SEC / config.ANALYSIS_INTERVAL)
        self._lat_history = np.full(hist_len, 0.5)
        self._lat_pos = 0

        # 同步
        self._lsl_arrival_ns = 0
        self._cam_capture_ns = 0

    # ==================== 采集 ====================

    def _setup_acquisition(self):
        self.lsl_queue: queue.Queue[object] = queue.Queue()
        self.lsl_reader = LSLReader(self.lsl_queue, target_name=config.LSL_STREAM_NAME)
        self.camera = CameraCapture(
            camera_index=config.CAMERA_INDEX,
            camera_name=config.CAMERA_NAME,
            backend=config.CAMERA_BACKEND,
            fps=config.CAMERA_FPS,
            width=config.CAMERA_WIDTH,
            height=config.CAMERA_HEIGHT,
        )

        if not self._args.no_lsl:
            self.lsl_reader.start()
        if not self._args.no_camera:
            self.camera.start()

        # 异步等待连接（不阻塞 UI）
        QTimer.singleShot(1500, self._on_connected)

    def _on_connected(self):
        if self.lsl_reader.connected:
            self.fs = self.lsl_reader.fs
        if not self.lsl_reader.connected and not self.camera.connected:
            log.warning("LSL 和摄像头均未连接，仅显示空白面板。")

    # ==================== UI ====================

    def _init_ui(self):
        top = QHBoxLayout(self)
        top.setSpacing(8)

        # -- 左侧 --
        left = QVBoxLayout()

        gb = QGroupBox("Real-time Topomap (std dev)")
        lt = QVBoxLayout(gb)
        self.topo = TopoCanvas(self, width=4, height=4)
        lt.addWidget(self.topo)
        left.addWidget(gb, stretch=3)

        gb = QGroupBox("T7 / T8 Power Spectrum")
        lp = QVBoxLayout(gb)
        self.plt_psd = pg.PlotWidget()
        self.plt_psd.setLabel("left", "Power", units="V²/Hz")
        self.plt_psd.setLogMode(x=False, y=True)
        self.plt_psd.setXRange(1, 40)
        self.curve_t7 = self.plt_psd.plot(pen=pg.mkPen("#2980b9", width=2), name="T7 (L)")
        self.curve_t8 = self.plt_psd.plot(pen=pg.mkPen("#e74c3c", width=2), name="T8 (R)")
        self.plt_psd.addLegend()
        lp.addWidget(self.plt_psd)
        left.addWidget(gb, stretch=2)

        top.addLayout(left, stretch=4)

        # -- 中间 --
        mid = QVBoxLayout()

        n_ch = len(config.CHANNEL_NAMES)
        gb = QGroupBox(f"EEG ({n_ch} ch)")
        le = QVBoxLayout(gb)
        self.plt_eeg = pg.PlotWidget()
        self.plt_eeg.hideAxis("bottom")
        self._eeg_curves = [
            self.plt_eeg.plot(pen=pg.mkPen((60, 60, 60), width=1))
            for _ in range(n_ch)
        ]
        le.addWidget(self.plt_eeg)
        mid.addWidget(gb, stretch=4)

        gb = QGroupBox("Hemispheric Lateralization (T7 vs T8)")
        ld = QVBoxLayout(gb)
        self.plt_lat = pg.PlotWidget()
        self.plt_lat.setYRange(-0.1, 1.1)
        self.plt_lat.getAxis("left").setTicks([[(1.0, "Left > Right"), (0.0, "Right > Left")]])
        self.curve_lat = self.plt_lat.plot(pen=pg.mkPen("#e74c3c", width=3))
        self._lat_line = self.plt_lat.addLine(y=0.5, pen=pg.mkPen("k", style=Qt.DashLine))
        ld.addWidget(self.plt_lat)
        mid.addWidget(gb, stretch=1)

        top.addLayout(mid, stretch=6)

        # -- 右侧 --
        right = QVBoxLayout()

        gb = QGroupBox(f"Camera (index={config.CAMERA_INDEX})")
        lc = QVBoxLayout(gb)
        self.lbl_cam = QLabel()
        self.lbl_cam.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cam.setMinimumSize(320, 240)
        self.lbl_cam.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_cam.setStyleSheet("background-color: #1a1a1a; border-radius: 4px;")
        lc.addWidget(self.lbl_cam)
        right.addWidget(gb, stretch=3)

        gb = QGroupBox("Timestamp Sync")
        ls = QVBoxLayout(gb)
        ls.setSpacing(4)

        self.lbl_lsl = QLabel("LSL: --")
        self.lbl_lsl.setStyleSheet("font: 13pt Consolas; color: #2980b9;")
        ls.addWidget(self.lbl_lsl)

        self.lbl_cam_ts = QLabel("Camera: --")
        self.lbl_cam_ts.setStyleSheet("font: 13pt Consolas; color: #e67e22;")
        ls.addWidget(self.lbl_cam_ts)

        self.lbl_delta = QLabel("Δ (EEG − Cam): -- ms")
        self.lbl_delta.setStyleSheet("font: bold 14pt Consolas; color: #27ae60;")
        ls.addWidget(self.lbl_delta)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("同步:"))
        self.sync_dot = SyncIndicator(self)
        hdr.addWidget(self.sync_dot)
        hdr.addStretch()
        ls.addLayout(hdr)

        right.addWidget(gb, stretch=1)
        top.addLayout(right, stretch=5)

    # ==================== 定时器 ====================

    def _setup_timers(self):
        # 渲染定时器：LSL 拉取 + 波形 + 摄像头帧 + 同步面板
        self._tmr_render = QTimer(self)
        self._tmr_render.timeout.connect(self._render)
        self._tmr_render.start(33)  # ~30 Hz

        # 分析定时器：PSD + Topomap + Lateralization
        self._tmr_analysis = QTimer(self)
        self._tmr_analysis.timeout.connect(self._analyze)
        self._tmr_analysis.start(int(config.ANALYSIS_INTERVAL * 1000))

    # ==================== 渲染循环 (~30 Hz) ====================

    def _render(self):
        self._fetch_lsl()
        self._draw_waveforms()
        self._draw_camera()
        self._draw_sync()

    def _fetch_lsl(self):
        """LSL 队列 → RingBuffer"""
        try:
            while True:
                s = self.lsl_queue.get_nowait()
                data = s.data.T          # (n_ch, n_samples)
                self.buffer.push(data)
                self._n_psd_new += data.shape[1]
                self._lsl_arrival_ns = s.arrival_ns
        except queue.Empty:
            pass

    def _draw_waveforms(self):
        recent = self.buffer.get_recent()
        if recent.shape[1] == 0:
            return
        n_ch = len(self._eeg_curves)
        for i in range(min(n_ch, recent.shape[0])):
            trace = recent[i] - recent[i].mean()
            self._eeg_curves[i].setData(trace + i * 10)

    def _draw_camera(self):
        img, ns = self.camera.snapshot()
        if ns:
            self._cam_capture_ns = ns
        if img is None:
            return
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pm = QPixmap.fromImage(qimg).scaled(
            self.lbl_cam.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lbl_cam.setPixmap(pm)

    def _draw_sync(self):
        now = time.perf_counter_ns()

        if self._lsl_arrival_ns:
            d = (now - self._lsl_arrival_ns) / 1e6
            self.lbl_lsl.setText(f"LSL: 延迟 {d:.1f} ms")
        else:
            self.lbl_lsl.setText("LSL: --")

        if self._cam_capture_ns:
            d = (now - self._cam_capture_ns) / 1e6
            self.lbl_cam_ts.setText(f"Camera: 延迟 {d:.1f} ms")
        else:
            self.lbl_cam_ts.setText("Camera: --")

        if self._lsl_arrival_ns and self._cam_capture_ns:
            delta = (self._lsl_arrival_ns - self._cam_capture_ns) / 1e6
            s = "+" if delta >= 0 else ""
            if abs(delta) < 50:
                color = "#27ae60"
            elif abs(delta) < 150:
                color = "#f39c12"
            else:
                color = "#e74c3c"
            self.lbl_delta.setText(f"Δ (EEG − Cam): {s}{delta:.1f} ms")
            self.lbl_delta.setStyleSheet(f"font: bold 14pt Consolas; color: {color};")
            self.sync_dot.set_offset(abs(delta))
        else:
            self.lbl_delta.setText("Δ (EEG − Cam): -- ms")
            self.sync_dot.set_offline()

    # ==================== 分析循环 (~3 Hz) ====================

    def _analyze(self):
        recent = self.buffer.get_recent()
        if recent.shape[1] < int(self.fs * 0.5):
            return          # 至少 0.5s 数据

        # PSD
        t7 = recent[self.idx_t7]
        t8 = recent[self.idx_t8]
        t7 = t7 - t7.mean()
        t8 = t8 - t8.mean()

        nperseg = min(len(t7), int(self.fs))
        f, pxx7 = _welch(t7, self.fs, nperseg)
        _, pxx8 = _welch(t8, self.fs, nperseg)
        self.curve_t7.setData(f, pxx7)
        self.curve_t8.setData(f, pxx8)

        # Topomap
        self.topo.update_topo(np.std(recent, axis=1))

        # Lateralization
        p_t7 = band_power(t7, self.fs, 8, 30)
        p_t8 = band_power(t8, self.fs, 8, 30)
        self._lat_history[self._lat_pos] = p_t7 / (p_t7 + p_t8 + 1e-9)
        self._lat_pos = (self._lat_pos + 1) % len(self._lat_history)
        # 滚动显示
        ordered = np.roll(self._lat_history, -self._lat_pos)
        self.curve_lat.setData(ordered)

    # ==================== 清理 ====================

    def closeEvent(self, event):
        self.lsl_reader.stop()
        self.camera.stop()
        event.accept()


# ============================================================
# 轻量 welch 封装（复用 nperseg）
# ============================================================

def _welch(data, fs, nperseg):
    from scipy.signal import welch as _w
    return _w(data, fs=fs, nperseg=nperseg)


# ============================================================
# 入口
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="iRe EEG + Camera real-time viewer")
    ap.add_argument("--no-camera", action="store_true", help="禁用摄像头")
    ap.add_argument("--no-lsl", action="store_true", help="禁用 LSL")
    ap.add_argument("--camera-index", type=int, default=config.CAMERA_INDEX)
    args = ap.parse_args()

    if args.camera_index != config.CAMERA_INDEX:
        config.CAMERA_INDEX = args.camera_index

    app = QApplication(sys.argv)
    win = MainWindow(args)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
