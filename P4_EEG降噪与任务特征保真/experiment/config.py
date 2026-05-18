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

    # Session 选择
    session: str = "1"  # "1" / "2" / "3" / "4"

    # Session 3/4 任务选择
    run_oddball: bool = True
    run_ssvep: bool = True

    # 串口 (Trigger / Marker 发送)
    port_name: str = "COM3"
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
    data_dir: str = ""

    # Session 4 特有 — 自然态模式
    natural_mode: bool = False
    forced_blink_ratio: float = 0.3
    ssvep_grid_debug: bool = False

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

    # Session 4 — 自然态 (<128)
    "S4_ODDBALL_STD":      81,
    "S4_ODDBALL_TARGET":   82,
    "S4_SSVEP_6HZ":        91,
    "S4_SSVEP_8_57HZ":     92,
    "S4_SSVEP_10HZ":       93,
    "S4_SSVEP_15HZ":       94,
}


def get_marker(name: str, natural_mode: bool = False):
    """根据任务名和模式返回 Marker 值。"""
    if name == "ODDBALL_STD":
        return MARKER_TABLE["S4_ODDBALL_STD"] if natural_mode else MARKER_TABLE["S3_ODDBALL_STD"]
    if name == "ODDBALL_TARGET":
        return MARKER_TABLE["S4_ODDBALL_TARGET"] if natural_mode else MARKER_TABLE["S3_ODDBALL_TARGET"]
    if name == "SSVEP_6HZ":
        return MARKER_TABLE["S4_SSVEP_6HZ"] if natural_mode else MARKER_TABLE["S3_SSVEP_6HZ"]
    if name == "SSVEP_8_57HZ":
        return MARKER_TABLE["S4_SSVEP_8_57HZ"] if natural_mode else MARKER_TABLE["S3_SSVEP_8_57HZ"]
    if name == "SSVEP_10HZ":
        return MARKER_TABLE["S4_SSVEP_10HZ"] if natural_mode else MARKER_TABLE["S3_SSVEP_10HZ"]
    if name == "SSVEP_15HZ":
        return MARKER_TABLE["S4_SSVEP_15HZ"] if natural_mode else MARKER_TABLE["S3_SSVEP_15HZ"]
    return MARKER_TABLE.get(name, 0)


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
        self.root.geometry("580x650")
        self.root.resizable(False, False)

        # 居中
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()
        self.root.mainloop()

        if self.cancelled:
            return None
        return self.config

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ---- 被试信息 ----
        ttk.Label(main_frame, text="▌ 被试信息", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))

        row1 = ttk.Frame(main_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="被试 ID:", width=12).pack(side=tk.LEFT)
        self.var_subject = tk.StringVar(value="Sub_01")
        ttk.Entry(row1, textvariable=self.var_subject, width=30).pack(side=tk.LEFT, padx=5)

        # ---- Session 选择 ----
        ttk.Label(main_frame, text="▌ Session 选择", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

        row2 = ttk.Frame(main_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Session:", width=12).pack(side=tk.LEFT)
        self.var_session = tk.StringVar(value="1")
        session_frame = ttk.Frame(row2)
        session_frame.pack(side=tk.LEFT, padx=5)
        for s, label in [("1", "S1 静息态"), ("2", "S2 伪迹模板"), ("3", "S3 银标准"), ("4", "S4 自然态"), ("all", "全流程 S1-S4")]:
            ttk.Radiobutton(session_frame, text=label, variable=self.var_session,
                           value=s).pack(side=tk.LEFT, padx=3)

        # Session 3/4 任务选择
        row2b = ttk.Frame(main_frame)
        row2b.pack(fill=tk.X, pady=2)
        ttk.Label(row2b, text="任务选择:", width=12).pack(side=tk.LEFT)
        self.var_oddball = tk.BooleanVar(value=True)
        self.var_ssvep = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2b, text="Oddball (P300)", variable=self.var_oddball).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(row2b, text="SSVEP", variable=self.var_ssvep).pack(side=tk.LEFT, padx=5)

        # ---- 串口设置 ----
        ttk.Label(main_frame, text="▌ Trigger 串口", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

        row3 = ttk.Frame(main_frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="串口号:", width=12).pack(side=tk.LEFT)
        self.var_port = tk.StringVar(value="COM3")
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

        # ---- Session 4 选项 ----
        ttk.Label(main_frame, text="▌ Session 4 选项", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

        row6 = ttk.Frame(main_frame)
        row6.pack(fill=tk.X, pady=2)
        self.var_forced_blink = tk.StringVar(value="0.3")
        ttk.Label(row6, text="强制眨眼比例:", width=16).pack(side=tk.LEFT)
        ttk.Entry(row6, textvariable=self.var_forced_blink, width=6).pack(side=tk.LEFT, padx=5)
        ttk.Label(row6, text="(0=不强制, 0.3=30%靶刺激强制眨眼)").pack(side=tk.LEFT)

        # ---- 被试间顺序平衡 ----
        row7 = ttk.Frame(main_frame)
        row7.pack(fill=tk.X, pady=2)
        ttk.Label(row7, text="Session 顺序:", width=16).pack(side=tk.LEFT)
        self.var_order = tk.StringVar(value="3_then_4")
        ttk.Combobox(row7, textvariable=self.var_order,
                    values=["3_then_4", "4_then_3"],
                    width=12, state="readonly").pack(side=tk.LEFT, padx=5)

        # ---- 按钮 ----
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="✓  开始实验", command=self._on_confirm, width=15).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="✗  取消", command=self._on_cancel, width=10).pack(side=tk.LEFT, padx=10)

    def _browse_data_dir(self):
        path = filedialog.askdirectory(title="选择数据保存目录")
        if path:
            self.var_data_dir.set(path)

    def _on_confirm(self):
        """验证参数并构建 Config"""
        try:
            cfg = ExperimentConfig()
            cfg.subject_id = self.var_subject.get().strip()
            if not cfg.subject_id:
                raise ValueError("被试 ID 不能为空")

            cfg.session = self.var_session.get()
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
            cfg.natural_mode = (cfg.session == "4")
            cfg.forced_blink_ratio = float(self.var_forced_blink.get())
            cfg.session_order = self.var_order.get()

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
    parser.add_argument("--subject", default="Sub_01", help="被试 ID")
    parser.add_argument("--session", default="1", choices=["1", "2", "3", "4", "all"])
    parser.add_argument("--no-oddball", action="store_true", help="跳过 Oddball")
    parser.add_argument("--no-ssvep", action="store_true", help="跳过 SSVEP")
    parser.add_argument("--port", default="COM3", help="串口号")
    parser.add_argument("--no-hardware", action="store_true", help="无硬件模式")
    parser.add_argument("--screen", type=int, default=1)
    parser.add_argument("--windowed", action="store_true", help="窗口模式")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--forced-blink", type=float, default=0.3)
    parser.add_argument("--ssvep-grid-debug", action="store_true", help="SSVEP 四宫格持续闪烁调试模式")

    args = parser.parse_args()

    cfg = ExperimentConfig()
    cfg.subject_id = args.subject
    cfg.session = args.session
    cfg.run_oddball = not args.no_oddball
    cfg.run_ssvep = not args.no_ssvep
    cfg.port_name = args.port
    cfg.no_hardware = args.no_hardware
    cfg.screen_id = args.screen
    cfg.full_screen = True if cfg.screen_id == 1 else (not args.windowed)
    cfg.data_dir = args.data_dir
    cfg.natural_mode = (cfg.session == "4")
    cfg.forced_blink_ratio = args.forced_blink
    cfg.ssvep_grid_debug = args.ssvep_grid_debug

    return cfg
