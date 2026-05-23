# main.py — Closed-loop AAD System (8s Block Design)
import sys
import os
import time
import queue
import math
import random

import config
config.bootstrap()  # 必须在所有 GUI import 前调用

import numpy as np
import soundfile as sf

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QGroupBox, QFrame, QProgressBar,
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import pyqtgraph as pg

from threads import LSLReader
from widgets import MneTopoCanvas
from utils import band_power, decide_target_speaker

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")

SEPARATED_DIR = r"E:\python_workspace\LSL_0130\0130\separated_results"

STATE_IDLE = 0
STATE_LISTEN = 1
STATE_FEEDBACK = 2


class AADSystemMain(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Closed-loop AAD System (8s Block Design)")
        self.resize(1600, 950)
        self.setStyleSheet("background-color: white; color: black; font-family: Segoe UI;")

        self.block_duration = 8.0
        self.eeg_channels = len(config.CHANNEL_NAMES)
        self.plot_len = 500
        self.eeg_buffer = np.zeros((self.eeg_channels, self.plot_len))
        self.fs_eeg = config.DEFAULT_SFREQ

        self.dec_buffer = np.zeros(200) + 0.5

        self.current_state = STATE_IDLE
        self.block_start_time = 0.0
        self.accumulated_scores = []
        self.final_decision = None

        self.current_demo_target = 1.0
        self.trial_frame_counter = 0

        idx = {name: i for i, name in enumerate(config.CHANNEL_NAMES)}
        self.idx_t7 = idx.get("T7", 0)
        self.idx_t8 = idx.get("T8", 1)

        # 使用 config 中的预定义脑区索引
        self.left_temporal_cluster = config.LEFT_TEMPORAL
        self.right_temporal_cluster = config.RIGHT_TEMPORAL
        self.occipital_cluster = config.OCCIPITAL
        self.frontal_cluster = config.FRONTAL

        self.lsl_queue: queue.Queue = queue.Queue()
        self.lsl_thread = None

        self.init_audio_system()
        self.init_ui()

        if config.ENABLE_LSL:
            self.start_lsl()

        self.timer_fast = QTimer(self)
        self.timer_fast.timeout.connect(self.update_fast_loop)
        self.timer_fast.start(40)

        self.timer_slow = QTimer(self)
        self.timer_slow.timeout.connect(self.update_slow_loop)
        self.timer_slow.start(300)

    # ==================== 音频 ====================

    def init_audio_system(self):
        self.audio_data = None
        self.source1_data = None
        self.source2_data = None
        self.sr_mix = self.sr_s1 = self.sr_s2 = 0
        self.has_separated_files = False

        self.player_s1 = QMediaPlayer(self)
        self.out_s1 = QAudioOutput(self)
        self.player_s1.setAudioOutput(self.out_s1)
        self.out_s1.setVolume(1.0)

        self.player_s2 = QMediaPlayer(self)
        self.out_s2 = QAudioOutput(self)
        self.player_s2.setAudioOutput(self.out_s2)
        self.out_s2.setVolume(1.0)

    # ==================== LSL ====================

    def start_lsl(self):
        self.lsl_thread = LSLReader(self.lsl_queue, target_name=config.LSL_STREAM_NAME)
        self.lsl_thread.start()
        time.sleep(1)
        if self.lsl_thread.connected:
            self.fs_eeg = self.lsl_thread.fs

    # ==================== UI ====================

    def init_ui(self):
        layout = QHBoxLayout(self)

        # -- 左侧 --
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)

        gb = QGroupBox("Real-time Topomap")
        lt = QVBoxLayout(gb)
        self.mne_canvas = MneTopoCanvas(self, width=4, height=4)
        lt.addWidget(self.mne_canvas)
        left_layout.addWidget(gb, stretch=2)

        gb = QGroupBox("Power Analysis")
        lp = QVBoxLayout(gb)
        self.plot_psd = pg.PlotWidget()
        self.plot_psd.setLabel("left", "Power", units="V^2/Hz")
        self.plot_psd.setLogMode(x=False, y=True)
        self.plot_psd.setXRange(1, 40)
        self.curve_t7 = self.plot_psd.plot(pen=pg.mkPen("b", width=2), name="T7 (Left)")
        self.curve_t8 = self.plot_psd.plot(pen=pg.mkPen("r", width=2), name="T8 (Right)")
        self.plot_psd.addLegend()
        lp.addWidget(self.plot_psd)
        left_layout.addWidget(gb, stretch=1)

        layout.addWidget(left_panel, stretch=3)

        # -- 右侧 --
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)

        ctrl_layout = QHBoxLayout()
        btn = QPushButton("Load Audio")
        btn.clicked.connect(self.open_audio)
        ctrl_layout.addWidget(btn)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet(
            "font-size: 20pt; font-weight: bold; color: gray; "
            "background-color: #f0f0f0; border-radius: 5px; padding: 10px;"
        )
        ctrl_layout.addWidget(self.lbl_status, stretch=1)
        right_layout.addLayout(ctrl_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        right_layout.addWidget(self.progress_bar)

        gb = QGroupBox("Audio Stream")
        la = QHBoxLayout(gb)
        la.setContentsMargins(5, 15, 5, 5)
        self.plot_mix = pg.PlotWidget(
            title="<span style='font-size: 28pt;'><b>Input:</b> 多说话人音频</span>"
        )
        self.plot_mix.hideAxis("left"); self.plot_mix.hideAxis("bottom")
        self.curve_mix = self.plot_mix.plot(pen=pg.mkPen("#3498db", width=1))
        la.addWidget(self.plot_mix, stretch=4)
        arrow = QLabel(">")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        la.addWidget(arrow, stretch=1)
        self.plot_target = pg.PlotWidget(
            title="<span style='font-size: 28pt;'><b>Output:</b> 目标说话人音频</span>"
        )
        self.plot_target.hideAxis("left"); self.plot_target.hideAxis("bottom")
        self.curve_target = self.plot_target.plot(pen=pg.mkPen("#27ae60", width=1))
        la.addWidget(self.plot_target, stretch=4)
        right_layout.addWidget(gb, stretch=2)

        self.plot_eeg = pg.PlotWidget(title="EEG Signals")
        self.plot_eeg.hideAxis("bottom")
        self.eeg_curves = [
            self.plot_eeg.plot(pen=pg.mkPen((50, 50, 50), width=1))
            for _ in range(self.eeg_channels)
        ]
        right_layout.addWidget(self.plot_eeg, stretch=3)

        self.plot_dec = pg.PlotWidget(
            title="<span style='font-size: 28pt; font-weight: bold;'>实时解码概率</span>"
        )
        self.plot_dec.setYRange(-0.2, 1.2)
        self.plot_dec.getAxis("left").setTicks([[(1.0, "Speaker A"), (0.0, "Speaker B")]])
        self.plot_dec.addLine(y=0.5, pen=pg.mkPen("k", style=Qt.DashLine))
        self.curve_decoding = self.plot_dec.plot(pen=pg.mkPen("r", width=3), name="Target")

        right_layout.addWidget(self.plot_dec, stretch=2)
        layout.addWidget(right_panel, stretch=7)

    # ==================== 主循环 ====================

    def update_fast_loop(self):
        if config.ENABLE_LSL:
            self.fetch_lsl_data()
        else:
            self.generate_demo_data()

        for i, c in enumerate(self.eeg_curves):
            data = self.eeg_buffer[i, :] - np.mean(self.eeg_buffer[i, :])
            c.setData(data + i * 10)

        if not self.has_separated_files or self.current_state == STATE_IDLE:
            return

        current_pos = self.player_s1.position() / 1000.0
        elapsed = current_pos - self.block_start_time

        if self.current_state == STATE_LISTEN and not config.ENABLE_LSL:
            if self.will_switch_this_block and not self.has_switched_in_this_block:
                if elapsed > self.switch_time_threshold:
                    print(f"Mid-trial switch! ({elapsed:.1f}s)")
                    self.current_demo_target = 1.0 - self.current_demo_target
                    self.has_switched_in_this_block = True
                    self.trial_frame_counter = 0

        if elapsed >= self.block_duration:
            self.switch_phase()
        else:
            self.progress_bar.setValue(int((elapsed / self.block_duration) * 100))

        self.update_audio_viz()

        if self.current_state == STATE_LISTEN:
            if not config.ENABLE_LSL:
                self.update_demo_decoding()
            self.curve_decoding.setData(self.dec_buffer)
            self.accumulated_scores.append(self.dec_buffer[-1])

    def switch_phase(self):
        if self.current_state == STATE_LISTEN:
            recent = self.accumulated_scores[-50:]
            avg_score = np.mean(recent) if recent else 0.5
            self.final_decision = 1 if avg_score > 0.5 else 0

            target_name = "Speaker A" if self.final_decision == 1 else "Speaker B"
            self.lbl_status.setText(f"Replaying: {target_name}")
            self.lbl_status.setStyleSheet(
                "font-size: 24pt; font-weight: bold; color: white; "
                "background-color: #27ae60; padding: 10px; border-radius: 5px;"
            )

            if self.final_decision == 1:
                self.out_s1.setVolume(1.0); self.out_s2.setVolume(0.0)
            else:
                self.out_s1.setVolume(0.0); self.out_s2.setVolume(1.0)

            seek_pos = int(self.block_start_time * 1000)
            self.player_s1.setPosition(seek_pos)
            self.player_s2.setPosition(seek_pos)
            self.current_state = STATE_FEEDBACK
            self.accumulated_scores = []

        elif self.current_state == STATE_FEEDBACK:
            self.block_start_time += self.block_duration
            total_duration = self.player_s1.duration() / 1000.0
            if self.block_start_time >= total_duration:
                self.stop_experiment()
                return

            self.lbl_status.setText(f"Listening (Next {int(self.block_duration)}s)...")
            self.lbl_status.setStyleSheet(
                "font-size: 24pt; font-weight: bold; color: white; "
                "background-color: #3498db; padding: 10px; border-radius: 5px;"
            )

            self.out_s1.setVolume(1.0); self.out_s2.setVolume(1.0)
            seek_pos = int(self.block_start_time * 1000)
            self.player_s1.setPosition(seek_pos)
            self.player_s2.setPosition(seek_pos)

            self.current_state = STATE_LISTEN
            self.trial_frame_counter = 0
            self.current_demo_target = 1.0 - self.current_demo_target
            self.has_switched_in_this_block = False
            self.switch_time_threshold = random.uniform(3.0, 5.0)
            self.will_switch_this_block = (random.random() < 0.4)

    def start_experiment(self):
        if not self.has_separated_files:
            return

        self.current_state = STATE_LISTEN
        self.block_start_time = 0.0
        self.accumulated_scores = []
        self.current_demo_target = 1.0
        self.trial_frame_counter = 0
        self.has_switched_in_this_block = False
        self.switch_time_threshold = random.uniform(3.0, 5.0)
        self.will_switch_this_block = (random.random() < 0.4)

        self.out_s1.setVolume(1.0); self.out_s2.setVolume(1.0)
        self.player_s1.setPosition(0); self.player_s2.setPosition(0)
        self.player_s1.play(); self.player_s2.play()

        self.lbl_status.setText("Listening...")
        self.lbl_status.setStyleSheet(
            "font-size: 24pt; font-weight: bold; color: white; "
            "background-color: #3498db; padding: 10px; border-radius: 5px;"
        )

    def stop_experiment(self):
        self.current_state = STATE_IDLE
        self.player_s1.stop(); self.player_s2.stop()
        self.lbl_status.setText("Finished")
        self.lbl_status.setStyleSheet(
            "font-size: 24pt; font-weight: bold; color: gray; "
            "background-color: #f0f0f0; padding: 10px;"
        )

    # ==================== 慢循环 ====================

    def update_slow_loop(self):
        n_points = min(self.plot_len, self.fs_eeg)
        if self.eeg_buffer.shape[1] < n_points:
            return
        recent = self.eeg_buffer[:, -n_points:]

        raw_t7 = recent[self.idx_t7] - np.mean(recent[self.idx_t7])
        raw_t8 = recent[self.idx_t8] - np.mean(recent[self.idx_t8])

        from scipy.signal import welch as _w
        f, pxx7 = _w(raw_t7, fs=self.fs_eeg, nperseg=n_points // 2)
        _, pxx8 = _w(raw_t8, fs=self.fs_eeg, nperseg=n_points // 2)
        self.curve_t7.setData(f, pxx7)
        self.curve_t8.setData(f, pxx8)

        self.mne_canvas.update_topo(np.std(recent, axis=1))

        if config.ENABLE_LSL:
            p_t7 = band_power(raw_t7, self.fs_eeg)
            p_t8 = band_power(raw_t8, self.fs_eeg)
            _, target_val = decide_target_speaker(p_t7, p_t8)
            self.dec_buffer = np.roll(self.dec_buffer, -1)
            self.dec_buffer[-1] = target_val

    # ==================== 数据 ====================

    def generate_demo_data(self):
        n_new = 8
        noise = np.random.normal(0, 1.0, (self.eeg_channels, n_new))
        t = time.time()

        noise += np.sin(t * 20 * np.pi) * 0.5

        for idx in self.occipital_cluster:
            noise[idx] += np.sin(t * 20 * np.pi + 1.0) * 1.5
            noise[idx] += np.random.normal(0, 0.3, n_new)
        for idx in self.frontal_cluster:
            noise[idx] += np.sin(t * 2 * np.pi) * 2.0
            noise[idx] += np.random.normal(0, 0.5, n_new)

        target = self.current_demo_target
        if target > 0.5:
            left_gain, right_gain = 1.4, 0.8
        else:
            left_gain, right_gain = 0.8, 1.4

        for idx in self.left_temporal_cluster:
            noise[idx] *= left_gain
            if idx == self.idx_t7:
                noise[idx] *= 1.1
        for idx in self.right_temporal_cluster:
            noise[idx] *= right_gain
            if idx == self.idx_t8:
                noise[idx] *= 1.1

        self.eeg_buffer = np.roll(self.eeg_buffer, -n_new, axis=1)
        self.eeg_buffer[:, -n_new:] = noise

    def update_demo_decoding(self):
        self.trial_frame_counter += 1
        conf = min(1.0, self.trial_frame_counter / 50.0)
        base_val = self.current_demo_target * conf + 0.5 * (1.0 - conf)
        final_val = np.clip(base_val + random.uniform(-0.05, 0.05), 0, 1)
        self.dec_buffer = np.roll(self.dec_buffer, -1)
        self.dec_buffer[-1] = final_val

    def update_audio_viz(self):
        if self.audio_data is None:
            return
        pos = self.player_s1.position() / 1000.0
        win_sec = 3.0
        half = int(win_sec / 2 * self.sr_mix)
        start, end = int(pos * self.sr_mix) - half, int(pos * self.sr_mix) + half

        viz = self._get_slice(self.audio_data, start, end)
        step = max(1, len(viz) // 800)
        self.curve_mix.setData(viz[::step])

        if self.current_state == STATE_LISTEN:
            self.curve_target.setData(viz[::step], pen=pg.mkPen((200, 200, 200), width=1))
        elif self.current_state == STATE_FEEDBACK:
            t_data = self.source1_data if self.final_decision == 1 else self.source2_data
            t_sr = self.sr_s1 if self.final_decision == 1 else self.sr_s2
            color = "#27ae60" if self.final_decision == 1 else "#e67e22"
            c = int(pos * t_sr)
            h = int(win_sec / 2 * t_sr)
            vt = self._get_slice(t_data, c - h, c + h)
            self.curve_target.setData(vt[::step], pen=pg.mkPen(color, width=2))

    @staticmethod
    def _get_slice(data, start, end):
        length = end - start
        viz = np.zeros(length)
        ds = max(0, start)
        de = min(len(data), end)
        if de > ds:
            viz[ds - start:ds - start + (de - ds)] = data[ds:de]
        return viz

    def fetch_lsl_data(self):
        """从队列取 Sample 对象 → 写入 eeg_buffer"""
        try:
            while not self.lsl_queue.empty():
                s = self.lsl_queue.get_nowait()
                data = s.data.T          # (n_channels, n_samples)
                ns = data.shape[1]
                if ns > self.plot_len:
                    data = data[:, -self.plot_len:]
                    ns = self.plot_len
                nc = min(data.shape[0], self.eeg_channels)
                self.eeg_buffer[:nc] = np.roll(self.eeg_buffer[:nc], -ns, axis=1)
                self.eeg_buffer[:nc, -ns:] = data[:nc]
        except Exception:
            pass

    # ==================== 音频加载 ====================

    def open_audio(self):
        p, _ = QFileDialog.getOpenFileName(self, "Audio", "", "*.wav *.mp3")
        if not p:
            return
        d, sr = sf.read(p)
        if d.ndim > 1:
            d = d.mean(axis=1)
        self.audio_data = d
        self.sr_mix = sr

        basename = os.path.splitext(os.path.basename(p))[0]
        p1 = os.path.join(SEPARATED_DIR, f"{basename}_1.wav")
        p2 = os.path.join(SEPARATED_DIR, f"{basename}_2.wav")

        if os.path.exists(p1) and os.path.exists(p2):
            self.has_separated_files = True
            d1, sr1 = sf.read(p1)
            if d1.ndim > 1:
                d1 = d1.mean(axis=1)
            self.source1_data = d1; self.sr_s1 = sr1
            d2, sr2 = sf.read(p2)
            if d2.ndim > 1:
                d2 = d2.mean(axis=1)
            self.source2_data = d2; self.sr_s2 = sr2

            self.player_s1.setSource(QUrl.fromLocalFile(p1))
            self.player_s2.setSource(QUrl.fromLocalFile(p2))
            self.start_experiment()
        else:
            self.has_separated_files = False
            print("Missing separated files")

    def closeEvent(self, e):
        if self.lsl_thread:
            self.lsl_thread.stop()
        e.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = AADSystemMain()
    w.show()
    sys.exit(app.exec())
