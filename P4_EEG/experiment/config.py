"""
实验配置模块 — 图形化启动对话框 + 配置数据类
依赖: Python 3.9+, tkinter (内置)
输入: 主试通过 GUI 填写的参数
输出: ExperimentConfig 对象
"""

import os
import sys
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List


# ============================================================
# 配置数据类
# ============================================================

@dataclass
class ExperimentConfig:
    """单次实验运行的完整配置"""
    # 被试信息
    subject_id: str = "Sub_01"

    # 实验方案：S1-S3 完全一致；S4 根据 scheme 切换
    #   "motor_imagery"       — Session 4 = 离线双手运动想象（默认）
    #   "emotion"             — Session 4 = 情绪识别（音视频刺激）
    #   "auditory_attention"  — Session 4 = 听觉注意力（HRTF 空间化双说话人 AAD）
    scheme: str = "motor_imagery"

    # Session 选择
    # 支持以下取值：
    #   "1" / "2" / "3" / "4"      — 单 Session
    #   "all"                       — 全流程 S1+S2+S3+S4
    #   "1,3" / "3,4" / "2,3,4"    — 任意多 Session 串联（逗号分隔）
    # 由 parse_sessions(cfg) 统一解析为有序 list[str]，被 launcher 调度。
    session: str = "1"

    # Session 3/4 任务选择
    run_oddball: bool = True
    run_ssvep: bool = True

    # 串口 (Trigger / Marker 发送)
    port_name: str = "COM5"
    baud_rate: int = 115200
    no_hardware: bool = False

    # 屏幕参数
    screen_id: int = 1         # 1 = 外接拓展屏，0 = 主屏幕
    full_screen: bool = True
    screen_width: int = 1920
    screen_height: int = 1080
    refresh_rate: float = 60.0  # Hz
    background_color: str = "#000000"  # 黑色

    # 音频参数 (Session 2 滴声)
    beep_frequency: float = 1000.0  # Hz
    beep_duration: float = 0.1      # 秒

    # 数据保存路径
    # 真正的落点是 <data_dir>/<scheme>/{eeg-bdf,eeg-npz,video_records}
    # 由 utils.save_data / launcher.get_*_dir 自动按 scheme 分流。
    data_dir: str = ""
    experiment_log_dir: str = ""

    # 相机录制
    camera_enabled: bool = True
    camera_device_name: str = "FF-Camera"
    camera_output_dir: str = ""
    camera_width: int = 1920
    camera_height: int = 1080
    camera_fps: float = 30.0

    # Session 4 — 离线双手运动想象 (scheme="motor_imagery")
    mi_baseline_duration: float = 2.0
    mi_cue_duration: float = 1.0
    mi_imagery_duration: float = 4.0
    mi_rest_duration: float = 2.0
    mi_demo_trials_per_class: int = 5
    mi_practice_trials_per_class: int = 5
    mi_formal_trials_per_class: int = 40
    mi_formal_blocks: int = 4
    mi_random_seed: int = 42
    ssvep_grid_debug: bool = False

    # Session 4 — 情绪识别 (scheme="emotion")
    emotion_fixation_duration: float = 2.0
    emotion_rest_duration: float = 2.0
    emotion_random_seed: int = 42

    # Session 4 — 听觉注意力 AAD (scheme="auditory_attention")
    aad_audio_dir: str = ""                # 空间化音频目录，默认 experiment/spatialized_90/
    aad_difficulty: float = 0.0            # 难度调整: 0=正常, 0.5=简单(干扰减半), -0.5=困难(干扰增强)
    aad_speed_multiplier: int = 1          # 倍速模式: 1=正常, 更大值=飞速测试
    aad_trials: int = 32                   # 每轮 trial 数
    aad_random_seed: int = 42              # 随机化种子
    aad_fixation_duration: float = 2.0     # 刺激前注视十字时长 (秒)
    aad_rest_duration: float = 2.0         # 刺激后休息时长 (秒)

    # Session 3 — 自然态 / 强制眨眼比例
    # 历史遗留：Session 4 曾经是"自然态 Oddball+SSVEP"，现在已改为 MI。
    # 这里保留 natural_mode/forced_blink_ratio 是为了让 session3_oddball.py
    # 与 session3_ssvep.py 的旧分支不再 crash；默认 False / 0.0 时行为与
    # 原始银标准 Session 3 完全一致。
    natural_mode: bool = False
    forced_blink_ratio: float = 0.0

    # 全流程冒烟测试开关：True 时所有 Session 用极短时长 / 极少 trial,
    # 用来在不耗费一两个小时的情况下验证整套 GUI / Marker / 保存流程是否还能跑通。
    quick_test: bool = False

    # 被试间顺序平衡 (Session 3 vs 4 顺序)
    session_order: str = "3_then_4"  # "3_then_4" / "4_then_3"

    # 实验时间戳 (自动填充)
    exp_timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # 生成的保存文件名
    def make_filename(self, suffix: str = "") -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"P4_S{self.session}_{self.subject_id}_{ts}"
        if suffix:
            base = f"{base}_{suffix}"
        return base


# ============================================================
# Marker 编码表
# ============================================================

MARKER_TABLE = {
    # Session 1 — 静息态
    "S1_EO_START":   11,
    "S1_EO_END":     12,
    "S1_EC_START":   21,
    "S1_EC_END":     22,

    # Session 2 — 伪迹模板
    "S2_KEYPRESS":      30,
    "S2_ARTIFACT_ON":   31,
    "S2_BLINK_SINGLE":  41,
    "S2_BLINK_MULTI":   42,
    "S2_SACCADE":       43,
    "S2_JAW_CLENCH":    44,
    "S2_SWALLOW":       45,
    "S2_HEAD_LEFT":     46,
    "S2_HEAD_RIGHT":    47,
    "S2_HEAD_NOD":      48,

    # Session 3 — 银标准任务态 (<128)
    "S3_ODDBALL_STD":      61,
    "S3_ODDBALL_TARGET":   62,
    "S3_REST_BASELINE":    63,
    "S3_SSVEP_6HZ":        71,
    "S3_SSVEP_8_57HZ":     72,
    "S3_SSVEP_10HZ":       73,
    "S3_SSVEP_15HZ":       74,

    # Session 4 (scheme="motor_imagery") — 离线双手运动想象 (<128)
    "S4_MI_DEMO_LEFT":        81,
    "S4_MI_DEMO_RIGHT":       82,
    "S4_MI_FORMAL_LEFT_CUE":  83,
    "S4_MI_FORMAL_RIGHT_CUE": 84,
    "S4_MI_FORMAL_LEFT":      85,
    "S4_MI_FORMAL_RIGHT":     86,
    "S4_MI_REST":             87,
    "S4_MI_BLOCK_START":      88,
    "S4_MI_BLOCK_END":        89,

    # Session 4 (scheme="emotion") — 情绪识别 (音视频刺激, <128)
    "S4_EMOTION_START":      100,
    "S4_EMOTION_NEGATIVE":   101,
    "S4_EMOTION_NEUTRAL":    102,
    "S4_EMOTION_POSITIVE":   103,
    "S4_EMOTION_END":        104,
    "S4_EMOTION_BASELINE":   105,
    "S4_EMOTION_REST":       106,

    # Session 4 (scheme="auditory_attention") — 听觉注意力 AAD (<128)
    "S4_AAD_START":       110,
    "S4_AAD_BASELINE":    111,
    "S4_AAD_AUDIO_LEFT":  112,
    "S4_AAD_AUDIO_RIGHT": 113,
    "S4_AAD_QUESTION":    114,
    "S4_AAD_REST":        115,
    "S4_AAD_END":         116,
}


VALID_SESSION_IDS = ("1", "2", "3", "4")


def parse_sessions(cfg: "ExperimentConfig") -> List[str]:
    """根据 cfg.session 字符串和 cfg.session_order，返回有序的 session 编号列表。

    支持：
      "1" / "2" / "3" / "4"      → 单元素列表
      "all"                       → S1 + S2 + 按 session_order 编排 S3/S4
      "1,3" / "3,4" / "2,3,4"    → 多 session 串联（保持用户给出的顺序，
                                    若同时含 3 和 4 则改按 cfg.session_order 排）

    任何无效 token 会抛 ValueError。空列表也视为错误。
    """
    raw = (cfg.session or "").strip().lower()
    if not raw:
        raise ValueError("Session 不能为空")

    if raw == "all":
        tokens = list(VALID_SESSION_IDS)
    else:
        tokens = [t.strip() for t in raw.split(",") if t.strip()]

    seen: List[str] = []
    for t in tokens:
        if t not in VALID_SESSION_IDS:
            raise ValueError(f"无效的 Session: {t!r} (合法值: {VALID_SESSION_IDS} / 'all' / 逗号列表)")
        if t not in seen:
            seen.append(t)

    if not seen:
        raise ValueError("至少要选择一个 Session")

    # 若同时包含 3 和 4，按 cfg.session_order 重排。
    # 不含 3 或不含 4 时不动用户给的顺序。
    if "3" in seen and "4" in seen:
        order = getattr(cfg, "session_order", "3_then_4") or "3_then_4"
        pair = ("3", "4") if order == "3_then_4" else ("4", "3")
        # 把不属于 {3,4} 的保留原顺序，再追加调整后的 (3,4) 对
        others = [s for s in seen if s not in ("3", "4")]
        seen = others + list(pair)

    return seen


def get_marker(name: str, natural_mode: bool = False):
    """根据任务名和模式返回 Marker 值。

    历史背景：S4 曾经是"自然态 Oddball + SSVEP"，会复用 S3 任务但用一套独立的 Marker。
    现在 S4 已经改为运动想象 (MI)，原本的 S4_ODDBALL_* / S4_SSVEP_* Marker 已经从
    MARKER_TABLE 中删除，因此 natural_mode 参数实际上不再有任何效果——仅保留参数
    签名以兼容历史调用者。
    """
    mapping = {
        "ODDBALL_STD":   "S3_ODDBALL_STD",
        "ODDBALL_TARGET": "S3_ODDBALL_TARGET",
        "SSVEP_6HZ":      "S3_SSVEP_6HZ",
        "SSVEP_8_57HZ":   "S3_SSVEP_8_57HZ",
        "SSVEP_10HZ":     "S3_SSVEP_10HZ",
        "SSVEP_15HZ":     "S3_SSVEP_15HZ",
    }
    key = mapping.get(name, name)
    return MARKER_TABLE.get(key, 0)


# ============================================================
# 图形化启动对话框 (模仿 MATLAB inputdlg)
# ============================================================

class ExperimentLauncher:
    """基于 tkinter 的实验启动配置对话框"""

    def __init__(self):
        self.config: Optional[ExperimentConfig] = None
        self.cancelled = True

    def run(self) -> Optional[ExperimentConfig]:
        """显示 GUI 并等待用户完成配置。返回 Config 或 None (取消)"""
        self.root = tk.Tk()
        self.root.title("P4 EEG 降噪实验 — 启动配置")

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        window_w = min(760, max(620, screen_w - 260))
        window_h = min(720, max(580, screen_h - 180))
        x = max(40, (screen_w - window_w) // 2)
        y = max(30, (screen_h - window_h) // 2)

        self.root.geometry(f"{window_w}x{window_h}+{x}+{y}")
        self.root.minsize(620, 580)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.root.bind("<Return>", lambda _event: self._on_confirm())
        self.root.bind("<Escape>", lambda _event: self._on_cancel())

        self._build_ui()
        self.root.mainloop()

        if self.cancelled:
            return None
        return self.config

    def _build_ui(self):
        outer_frame = ttk.Frame(self.root, padding=12)
        outer_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(outer_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        content_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=content_frame, anchor="nw")

        content_frame.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        main_frame = ttk.Frame(content_frame, padding=8)
        main_frame.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main_frame, padding=(8, 8, 8, 12))
        header.pack(fill=tk.X)
        ttk.Label(header, text="P4 EEG 启动配置", font=("Microsoft YaHei", 14, "bold")).pack(anchor=tk.W)
        ttk.Label(
            header,
            text="窗口已缩小；如果内容没显示全，请滚动到最下方点击“开始实验”。",
            foreground="#555555"
        ).pack(anchor=tk.W, pady=(4, 0))

        # ---- 实验方案 ----
        ttk.Label(main_frame, text="▌ 实验方案 (Scheme)", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))

        row_scheme = ttk.Frame(main_frame)
        row_scheme.pack(fill=tk.X, pady=2)
        ttk.Label(row_scheme, text="S4 类型:", width=12).pack(side=tk.LEFT)
        self.var_scheme = tk.StringVar(value="motor_imagery")
        scheme_frame = ttk.Frame(row_scheme)
        scheme_frame.pack(side=tk.LEFT, padx=5)
        for s, label in [("motor_imagery", "● 运动想象 (MI)"),
                         ("emotion", "● 情绪识别 (Emotion)"),
                         ("auditory_attention", "● 听觉注意 (AAD)")]:
            ttk.Radiobutton(scheme_frame, text=label, variable=self.var_scheme,
                           value=s, command=self._on_scheme_change).pack(side=tk.LEFT, padx=6)
        self.scheme_status_label = ttk.Label(row_scheme, text="", foreground="#0066AA",
                                             font=("Microsoft YaHei", 10, "bold"))
        self.scheme_status_label.pack(side=tk.LEFT, padx=15)

        # ---- 被试信息 ----
        ttk.Label(main_frame, text="▌ 被试信息", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(10, 5))

        row1 = ttk.Frame(main_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="被试 ID:", width=12).pack(side=tk.LEFT)
        self.var_subject = tk.StringVar(value="Sub_01")
        ttk.Entry(row1, textvariable=self.var_subject, width=30).pack(side=tk.LEFT, padx=5)

        # ---- Session 选择（可勾选多个） ----
        ttk.Label(main_frame, text="▌ Session 选择 (可勾选多个，按序串联)",
                 font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

        row2 = ttk.Frame(main_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Sessions:", width=12).pack(side=tk.LEFT)
        session_frame = ttk.Frame(row2)
        session_frame.pack(side=tk.LEFT, padx=5)

        self.var_s1 = tk.BooleanVar(value=True)
        self.var_s2 = tk.BooleanVar(value=True)
        self.var_s3 = tk.BooleanVar(value=True)
        self.var_s4 = tk.BooleanVar(value=True)
        self.session_chk_s1 = ttk.Checkbutton(session_frame, text="S1 静息态", variable=self.var_s1)
        self.session_chk_s2 = ttk.Checkbutton(session_frame, text="S2 伪迹模板", variable=self.var_s2)
        self.session_chk_s3 = ttk.Checkbutton(session_frame, text="S3 银标准", variable=self.var_s3)
        self.session_chk_s4 = ttk.Checkbutton(session_frame, text="S4", variable=self.var_s4)
        for w in (self.session_chk_s1, self.session_chk_s2, self.session_chk_s3, self.session_chk_s4):
            w.pack(side=tk.LEFT, padx=3)

        row2_btn = ttk.Frame(main_frame)
        row2_btn.pack(fill=tk.X, pady=2)
        ttk.Label(row2_btn, text="", width=12).pack(side=tk.LEFT)
        ttk.Button(row2_btn, text="全选", width=6,
                  command=lambda: self._set_sessions(True, True, True, True)).pack(side=tk.LEFT, padx=3)
        ttk.Button(row2_btn, text="全清", width=6,
                  command=lambda: self._set_sessions(False, False, False, False)).pack(side=tk.LEFT, padx=3)
        ttk.Button(row2_btn, text="只 S3+S4", width=10,
                  command=lambda: self._set_sessions(False, False, True, True)).pack(side=tk.LEFT, padx=3)
        ttk.Button(row2_btn, text="只 S4", width=6,
                  command=lambda: self._set_sessions(False, False, False, True)).pack(side=tk.LEFT, padx=3)

        row2b = ttk.Frame(main_frame)
        row2b.pack(fill=tk.X, pady=2)
        ttk.Label(row2b, text="S3 任务:", width=12).pack(side=tk.LEFT)
        self.var_oddball = tk.BooleanVar(value=True)
        self.var_ssvep = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2b, text="Oddball (P300)", variable=self.var_oddball).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(row2b, text="SSVEP", variable=self.var_ssvep).pack(side=tk.LEFT, padx=5)

        # ---- 串口设置 ----
        ttk.Label(main_frame, text="▌ Trigger 串口", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

        row3 = ttk.Frame(main_frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="串口号:", width=12).pack(side=tk.LEFT)
        self.var_port = tk.StringVar(value="COM5")
        ttk.Entry(row3, textvariable=self.var_port, width=15).pack(side=tk.LEFT, padx=5)
        self.var_no_hw = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="无硬件模式 (不发送 Trigger)",
                       variable=self.var_no_hw).pack(side=tk.LEFT, padx=10)

        row3b = ttk.Frame(main_frame)
        row3b.pack(fill=tk.X, pady=2)
        ttk.Label(row3b, text="波特率:", width=12).pack(side=tk.LEFT)
        self.var_baud = tk.StringVar(value="115200")
        ttk.Combobox(row3b, textvariable=self.var_baud, values=["115200"],
                    width=10, state="readonly").pack(side=tk.LEFT, padx=5)

        # ---- 屏幕设置 ----
        ttk.Label(main_frame, text="▌ 屏幕设置", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

        row4 = ttk.Frame(main_frame)
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="屏幕 ID:", width=12).pack(side=tk.LEFT)
        self.var_screen = tk.StringVar(value="1")
        ttk.Combobox(row4, textvariable=self.var_screen, values=["0", "1"],
                    width=5, state="readonly").pack(side=tk.LEFT, padx=5)
        self.var_fullscreen = tk.BooleanVar(value=True)
        ttk.Checkbutton(row4, text="全屏", variable=self.var_fullscreen).pack(side=tk.LEFT, padx=10)

        row4b = ttk.Frame(main_frame)
        row4b.pack(fill=tk.X, pady=2)
        ttk.Label(row4b, text="分辨率:", width=12).pack(side=tk.LEFT)
        self.var_width = tk.StringVar(value="1920")
        ttk.Entry(row4b, textvariable=self.var_width, width=6).pack(side=tk.LEFT)
        ttk.Label(row4b, text="×").pack(side=tk.LEFT)
        self.var_height = tk.StringVar(value="1080")
        ttk.Entry(row4b, textvariable=self.var_height, width=6).pack(side=tk.LEFT)

        # ---- 数据保存 ----
        ttk.Label(main_frame, text="▌ 数据保存", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

        row5 = ttk.Frame(main_frame)
        row5.pack(fill=tk.X, pady=2)
        ttk.Label(row5, text="保存目录:", width=12).pack(side=tk.LEFT)
        self.var_data_dir = tk.StringVar(value=os.path.join(os.getcwd(), "data"))
        ttk.Entry(row5, textvariable=self.var_data_dir, width=35).pack(side=tk.LEFT, padx=5)
        ttk.Button(row5, text="浏览...", command=self._browse_data_dir, width=6).pack(side=tk.LEFT)

        # ---- 相机录制 ----
        ttk.Label(main_frame, text="▌ 相机录制", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

        row5b = ttk.Frame(main_frame)
        row5b.pack(fill=tk.X, pady=2)
        self.var_camera_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(row5b, text="启用相机自动录制", variable=self.var_camera_enabled).pack(side=tk.LEFT)

        row5c = ttk.Frame(main_frame)
        row5c.pack(fill=tk.X, pady=2)
        ttk.Label(row5c, text="设备名:", width=12).pack(side=tk.LEFT)
        self.var_camera_device = tk.StringVar(value="FF-Camera")
        ttk.Entry(row5c, textvariable=self.var_camera_device, width=35).pack(side=tk.LEFT, padx=5)

        row5d = ttk.Frame(main_frame)
        row5d.pack(fill=tk.X, pady=2)
        ttk.Label(row5d, text="视频保存:", width=12).pack(side=tk.LEFT)
        ttk.Label(row5d, text="默认保存到 <保存目录>/video_records").pack(side=tk.LEFT)

        # ---- Session 4 (MI) 选项 ----
        self.mi_frame = ttk.LabelFrame(main_frame, text="Session 4 选项 — 运动想象 (MI)", padding=8)
        self.mi_frame.pack(fill=tk.X, pady=(15, 5))

        row6 = ttk.Frame(self.mi_frame)
        row6.pack(fill=tk.X, pady=2)
        self.var_mi_baseline = tk.StringVar(value="2.0")
        self.var_mi_cue = tk.StringVar(value="1.0")
        self.var_mi_imagery = tk.StringVar(value="4.0")
        self.var_mi_rest = tk.StringVar(value="2.0")
        for label, var in [("基线", self.var_mi_baseline), ("Cue", self.var_mi_cue), ("想象", self.var_mi_imagery), ("休息", self.var_mi_rest)]:
            ttk.Label(row6, text=f"{label}:").pack(side=tk.LEFT, padx=(0, 4))
            ttk.Entry(row6, textvariable=var, width=6).pack(side=tk.LEFT, padx=(0, 10))

        row6b = ttk.Frame(self.mi_frame)
        row6b.pack(fill=tk.X, pady=2)
        self.var_mi_demo = tk.StringVar(value="5")
        self.var_mi_practice = tk.StringVar(value="5")
        self.var_mi_formal = tk.StringVar(value="40")
        self.var_mi_blocks = tk.StringVar(value="4")
        for label, var in [("示范/类", self.var_mi_demo), ("练习/类", self.var_mi_practice), ("正式/类", self.var_mi_formal), ("正式 blocks", self.var_mi_blocks)]:
            ttk.Label(row6b, text=f"{label}:").pack(side=tk.LEFT, padx=(0, 4))
            ttk.Entry(row6b, textvariable=var, width=6).pack(side=tk.LEFT, padx=(0, 10))

        # ---- Session 4 (Emotion) 选项 ----
        self.emotion_frame = ttk.LabelFrame(main_frame, text="Session 4 选项 — 情绪识别 (Emotion)", padding=8)
        self.emotion_frame.pack(fill=tk.X, pady=(5, 5))

        row_e1 = ttk.Frame(self.emotion_frame)
        row_e1.pack(fill=tk.X, pady=2)
        ttk.Label(row_e1, text="刺激类别:").pack(side=tk.LEFT)
        ttk.Label(row_e1, text="负性(6) / 中性(6) / 正性(6) = 18 trials").pack(side=tk.LEFT, padx=5)

        row_e2 = ttk.Frame(self.emotion_frame)
        row_e2.pack(fill=tk.X, pady=2)
        self.var_emotion_fixation = tk.StringVar(value="2.0")
        self.var_emotion_rest = tk.StringVar(value="2.0")
        ttk.Label(row_e2, text="注视:").pack(side=tk.LEFT)
        ttk.Entry(row_e2, textvariable=self.var_emotion_fixation, width=6).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(row_e2, text="s   休息:").pack(side=tk.LEFT)
        ttk.Entry(row_e2, textvariable=self.var_emotion_rest, width=6).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(row_e2, text="s   随机种子:").pack(side=tk.LEFT)
        self.var_emotion_seed = tk.StringVar(value="42")
        ttk.Entry(row_e2, textvariable=self.var_emotion_seed, width=8).pack(side=tk.LEFT, padx=(0, 6))

        # ---- Session 4 (Auditory Attention) 选项 ----
        self.aad_frame = ttk.LabelFrame(main_frame, text="Session 4 选项 — 听觉注意力 (AAD)", padding=8)
        self.aad_frame.pack(fill=tk.X, pady=(5, 5))

        row_a1 = ttk.Frame(self.aad_frame)
        row_a1.pack(fill=tk.X, pady=2)
        ttk.Label(row_a1, text="音频目录:").pack(side=tk.LEFT)
        self.var_aad_audio_dir = tk.StringVar(value="spatialized_90")
        ttk.Entry(row_a1, textvariable=self.var_aad_audio_dir, width=30).pack(side=tk.LEFT, padx=5)

        row_a2 = ttk.Frame(self.aad_frame)
        row_a2.pack(fill=tk.X, pady=2)
        self.var_aad_difficulty = tk.StringVar(value="0.0")
        self.var_aad_speed = tk.StringVar(value="1")
        self.var_aad_trials = tk.StringVar(value="32")
        self.var_aad_seed = tk.StringVar(value="42")
        ttk.Label(row_a2, text="难度:").pack(side=tk.LEFT)
        ttk.Entry(row_a2, textvariable=self.var_aad_difficulty, width=6).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(row_a2, text="倍速:").pack(side=tk.LEFT)
        ttk.Entry(row_a2, textvariable=self.var_aad_speed, width=4).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(row_a2, text="Trial数:").pack(side=tk.LEFT)
        ttk.Entry(row_a2, textvariable=self.var_aad_trials, width=5).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(row_a2, text="种子:").pack(side=tk.LEFT)
        ttk.Entry(row_a2, textvariable=self.var_aad_seed, width=6).pack(side=tk.LEFT, padx=(0, 6))

        row_a3 = ttk.Frame(self.aad_frame)
        row_a3.pack(fill=tk.X, pady=2)
        self.var_aad_fixation = tk.StringVar(value="2.0")
        self.var_aad_rest = tk.StringVar(value="2.0")
        ttk.Label(row_a3, text="注视:").pack(side=tk.LEFT)
        ttk.Entry(row_a3, textvariable=self.var_aad_fixation, width=6).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(row_a3, text="s   休息:").pack(side=tk.LEFT)
        ttk.Entry(row_a3, textvariable=self.var_aad_rest, width=6).pack(side=tk.LEFT, padx=(0, 6))

        # ---- 通用：被试间顺序平衡 / quick-test ----
        row7 = ttk.Frame(main_frame)
        row7.pack(fill=tk.X, pady=(10, 2))
        ttk.Label(row7, text="Session 顺序:", width=16).pack(side=tk.LEFT)
        self.var_order = tk.StringVar(value="3_then_4")
        ttk.Combobox(row7, textvariable=self.var_order,
                    values=["3_then_4", "4_then_3"],
                    width=12, state="readonly").pack(side=tk.LEFT, padx=5)
        self.var_quick_test = tk.BooleanVar(value=False)
        ttk.Checkbutton(row7, text="quick-test (冒烟测试)", variable=self.var_quick_test).pack(side=tk.LEFT, padx=10)

        button_bar = ttk.Frame(self.root, padding=(12, 6, 12, 12))
        button_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Separator(button_bar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 10))

        button_row = ttk.Frame(button_bar)
        button_row.pack(fill=tk.X)
        ttk.Label(button_row, text="向下滚动可查看全部选项。", foreground="#666666").pack(side=tk.LEFT)
        ttk.Button(button_row, text="开始实验", command=self._on_confirm, width=18).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(button_row, text="取消", command=self._on_cancel, width=10).pack(side=tk.RIGHT)

        self.root.after(50, lambda: self.canvas.yview_moveto(0.0))

        # 初始按方案刷新 S4 区域显示状态
        self._on_scheme_change()

    def _on_scheme_change(self):
        scheme = self.var_scheme.get()

        # 1. 更新 S4 checkbox 文案
        if hasattr(self, "session_chk_s4"):
            label_map = {
                "motor_imagery": "S4 双手 MI",
                "emotion": "S4 情绪识别",
                "auditory_attention": "S4 听觉 AAD",
            }
            self.session_chk_s4.configure(text=label_map.get(scheme, "S4"))

        # 2. 顶部状态横幅
        if hasattr(self, "scheme_status_label"):
            label_map2 = {
                "motor_imagery": "运动想象 (MI)",
                "emotion": "情绪识别 (Emotion)",
                "auditory_attention": "听觉注意力 (AAD)",
            }
            self.scheme_status_label.configure(
                text=f"→ S4 将执行：{label_map2.get(scheme, scheme)}"
            )

        # 3. 禁用/启用对应的 S4 参数框
        frames = {}
        if hasattr(self, "mi_frame"):
            frames["motor_imagery"] = self.mi_frame
        if hasattr(self, "emotion_frame"):
            frames["emotion"] = self.emotion_frame
        if hasattr(self, "aad_frame"):
            frames["auditory_attention"] = self.aad_frame

        for key, frame in frames.items():
            is_active = key == scheme
            try:
                base = frame.cget("text").split(" — ")[0]
                suffix = " — ✓ 当前方案" if is_active else " — (本次不使用)"
                frame.configure(text=base + suffix)
            except Exception:
                pass
            self._set_frame_state(frame, "normal" if is_active else "disabled")

    @staticmethod
    def _set_frame_state(frame, state: str):
        for child in frame.winfo_children():
            try:
                child.configure(state=state)
            except Exception:
                # 部分 Frame 自身没有 state 属性，递归子节点
                pass
            if child.winfo_children():
                ExperimentLauncher._set_frame_state(child, state)


    def _set_sessions(self, s1: bool, s2: bool, s3: bool, s4: bool):
        self.var_s1.set(s1)
        self.var_s2.set(s2)
        self.var_s3.set(s3)
        self.var_s4.set(s4)

    def _on_content_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        if not hasattr(self, "canvas") or not self.canvas.winfo_exists():
            return
        delta = 0
        if event.delta:
            delta = -1 * int(event.delta / 120)
        elif getattr(event, "num", None) == 5:
            delta = 1
        elif getattr(event, "num", None) == 4:
            delta = -1
        if delta:
            self.canvas.yview_scroll(delta, "units")

    def _browse_data_dir(self):
        path = filedialog.askdirectory(title="选择数据保存目录")
        if path:
            self.var_data_dir.set(path)

    def _on_confirm(self):
        """验证参数并构建 Config"""
        try:
            cfg = ExperimentConfig()
            cfg.scheme = self.var_scheme.get()
            if cfg.scheme not in ("motor_imagery", "emotion", "auditory_attention"):
                raise ValueError(f"未知实验方案: {cfg.scheme}")
            cfg.subject_id = self.var_subject.get().strip()
            if not cfg.subject_id:
                raise ValueError("被试 ID 不能为空")

            selected = [s for s, v in [
                ("1", self.var_s1.get()),
                ("2", self.var_s2.get()),
                ("3", self.var_s3.get()),
                ("4", self.var_s4.get()),
            ] if v]
            if not selected:
                raise ValueError("至少要勾选一个 Session")
            cfg.session = ",".join(selected) if len(selected) < 4 else "all"
            cfg.run_oddball = self.var_oddball.get()
            cfg.run_ssvep = self.var_ssvep.get()

            cfg.port_name = self.var_port.get().strip()
            cfg.baud_rate = int(self.var_baud.get())
            cfg.no_hardware = self.var_no_hw.get()

            cfg.screen_id = int(self.var_screen.get())
            cfg.full_screen = True if cfg.screen_id == 1 else self.var_fullscreen.get()
            cfg.screen_width = int(self.var_width.get())
            cfg.screen_height = int(self.var_height.get())

            cfg.data_dir = self.var_data_dir.get().strip()
            cfg.camera_enabled = self.var_camera_enabled.get()
            cfg.camera_device_name = self.var_camera_device.get().strip() or cfg.camera_device_name
            cfg.mi_baseline_duration = float(self.var_mi_baseline.get())
            cfg.mi_cue_duration = float(self.var_mi_cue.get())
            cfg.mi_imagery_duration = float(self.var_mi_imagery.get())
            cfg.mi_rest_duration = float(self.var_mi_rest.get())
            cfg.mi_demo_trials_per_class = int(self.var_mi_demo.get())
            cfg.mi_practice_trials_per_class = int(self.var_mi_practice.get())
            cfg.mi_formal_trials_per_class = int(self.var_mi_formal.get())
            cfg.mi_formal_blocks = int(self.var_mi_blocks.get())
            cfg.emotion_fixation_duration = float(self.var_emotion_fixation.get())
            cfg.emotion_rest_duration = float(self.var_emotion_rest.get())
            cfg.emotion_random_seed = int(self.var_emotion_seed.get())
            cfg.aad_audio_dir = self.var_aad_audio_dir.get().strip()
            cfg.aad_difficulty = float(self.var_aad_difficulty.get())
            cfg.aad_speed_multiplier = int(self.var_aad_speed.get())
            cfg.aad_trials = int(self.var_aad_trials.get())
            cfg.aad_random_seed = int(self.var_aad_seed.get())
            cfg.aad_fixation_duration = float(self.var_aad_fixation.get())
            cfg.aad_rest_duration = float(self.var_aad_rest.get())
            cfg.session_order = self.var_order.get()
            cfg.quick_test = self.var_quick_test.get()

            self.config = cfg
            self.cancelled = False
            self.root.quit()
            self.root.destroy()

        except ValueError as e:
            messagebox.showerror("参数错误", str(e))

    def _on_cancel(self):
        self.cancelled = True
        self.root.quit()
        self.root.destroy()


# ============================================================
# 命令行快速入口 (无 GUI 模式)
# ============================================================

def config_from_args() -> ExperimentConfig:
    """从命令行参数构建配置 (用于调试和快速启动)"""
    import argparse

    parser = argparse.ArgumentParser(description="P4 EEG 降噪实验")
    parser.add_argument("--scheme", default="motor_imagery",
                       choices=["motor_imagery", "emotion", "auditory_attention"],
                       help="S4 实验方案：motor_imagery=运动想象 / emotion=情绪识别 / auditory_attention=听觉注意力")
    parser.add_argument("--subject", default="Sub_01", help="被试 ID")
    parser.add_argument("--session", default="1",
                       help="Session 选择：单值 (1/2/3/4)、'all'、或逗号列表 (例如 3,4 / 1,3,4)")
    parser.add_argument("--no-oddball", action="store_true", help="跳过 Oddball")
    parser.add_argument("--no-ssvep", action="store_true", help="跳过 SSVEP")
    parser.add_argument("--port", default="COM5", help="串口号")
    parser.add_argument("--no-hardware", action="store_true", help="无硬件模式")
    parser.add_argument("--screen", type=int, default=1)
    parser.add_argument("--windowed", action="store_true", help="窗口模式")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--no-camera", action="store_true", help="禁用相机自动录制")
    parser.add_argument("--camera-device", default="FF-Camera", help="FFmpeg / dshow 相机设备名")
    parser.add_argument("--camera-output-dir", default="", help="相机录制保存目录，默认使用 <data_dir>/video_records")
    parser.add_argument("--mi-baseline-duration", type=float, default=2.0)
    parser.add_argument("--mi-cue-duration", type=float, default=1.0)
    parser.add_argument("--mi-imagery-duration", type=float, default=4.0)
    parser.add_argument("--mi-rest-duration", type=float, default=2.0)
    parser.add_argument("--mi-demo-trials-per-class", type=int, default=5)
    parser.add_argument("--mi-practice-trials-per-class", type=int, default=5)
    parser.add_argument("--mi-formal-trials-per-class", type=int, default=40)
    parser.add_argument("--mi-formal-blocks", type=int, default=4)
    parser.add_argument("--mi-seed", type=int, default=42)
    parser.add_argument("--emotion-fixation-duration", type=float, default=2.0,
                       help="Session 4 情绪方案：刺激前注视十字时长 (秒)")
    parser.add_argument("--emotion-rest-duration", type=float, default=2.0,
                       help="Session 4 情绪方案：刺激后休息时长 (秒)")
    parser.add_argument("--emotion-seed", type=int, default=42,
                       help="Session 4 情绪方案：视频随机化种子")
    parser.add_argument("--aad-audio-dir", default="",
                       help="Session 4 听觉注意力方案：空间化音频目录 (默认 experiment/spatialized_90/)")
    parser.add_argument("--aad-difficulty", type=float, default=0.0,
                       help="Session 4 听觉注意力方案：难度 (-1=困难, 0=正常, 1=简单)")
    parser.add_argument("--aad-speed-multiplier", type=int, default=1,
                       help="Session 4 听觉注意力方案：倍速 (1=正常, 更大=飞速测试)")
    parser.add_argument("--aad-trials", type=int, default=32,
                       help="Session 4 听觉注意力方案：每轮 trial 数")
    parser.add_argument("--aad-seed", type=int, default=42,
                       help="Session 4 听觉注意力方案：随机化种子")
    parser.add_argument("--aad-fixation-duration", type=float, default=2.0,
                       help="Session 4 听觉注意力方案：刺激前注视十字时长 (秒)")
    parser.add_argument("--aad-rest-duration", type=float, default=2.0,
                       help="Session 4 听觉注意力方案：刺激后休息时长 (秒)")
    parser.add_argument("--ssvep-grid-debug", action="store_true", help="SSVEP 四宫格持续闪烁调试模式")
    parser.add_argument("--natural-mode", action="store_true",
                       help="Session 3 自然态 (历史遗留，对当前 Marker 表无影响)")
    parser.add_argument("--forced-blink-ratio", type=float, default=0.0,
                       help="Session 3 Oddball 自然态下的强制眨眼比例 (默认 0)")
    parser.add_argument("--quick-test", action="store_true",
                       help="全流程冒烟测试：所有 Session 用极短时长 / 极少 trial 快速过完")

    args = parser.parse_args()

    cfg = ExperimentConfig()
    cfg.scheme = args.scheme
    cfg.subject_id = args.subject
    cfg.session = args.session
    cfg.run_oddball = not args.no_oddball
    cfg.run_ssvep = not args.no_ssvep
    cfg.port_name = args.port
    cfg.no_hardware = args.no_hardware
    cfg.screen_id = args.screen
    cfg.full_screen = True if cfg.screen_id == 1 else (not args.windowed)
    cfg.data_dir = args.data_dir
    cfg.camera_enabled = not args.no_camera
    cfg.camera_device_name = args.camera_device
    cfg.camera_output_dir = args.camera_output_dir
    cfg.mi_baseline_duration = args.mi_baseline_duration
    cfg.mi_cue_duration = args.mi_cue_duration
    cfg.mi_imagery_duration = args.mi_imagery_duration
    cfg.mi_rest_duration = args.mi_rest_duration
    cfg.mi_demo_trials_per_class = args.mi_demo_trials_per_class
    cfg.mi_practice_trials_per_class = args.mi_practice_trials_per_class
    cfg.mi_formal_trials_per_class = args.mi_formal_trials_per_class
    cfg.mi_formal_blocks = args.mi_formal_blocks
    cfg.mi_random_seed = args.mi_seed
    cfg.emotion_fixation_duration = args.emotion_fixation_duration
    cfg.emotion_rest_duration = args.emotion_rest_duration
    cfg.emotion_random_seed = args.emotion_seed
    cfg.aad_audio_dir = args.aad_audio_dir
    cfg.aad_difficulty = args.aad_difficulty
    cfg.aad_speed_multiplier = args.aad_speed_multiplier
    cfg.aad_trials = args.aad_trials
    cfg.aad_random_seed = args.aad_seed
    cfg.aad_fixation_duration = args.aad_fixation_duration
    cfg.aad_rest_duration = args.aad_rest_duration
    cfg.ssvep_grid_debug = args.ssvep_grid_debug
    cfg.natural_mode = args.natural_mode
    cfg.forced_blink_ratio = args.forced_blink_ratio
    cfg.quick_test = args.quick_test

    # 在这里就报错，比把无效 session 带到 launcher 里再炸要友好
    parse_sessions(cfg)

    return cfg
