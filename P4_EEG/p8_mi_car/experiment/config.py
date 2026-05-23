"""
P8 离线运动想象实验配置模块。

提供：
- MIExperimentConfig 配置数据类
- tkinter 图形化启动器
- argparse 命令行入口
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MIExperimentConfig:
    """单次离线 MI 采集的完整配置。"""

    subject_id: str = "Sub_01"
    session: str = "4A"

    port_name: str = "COM5"
    baud_rate: int = 115200
    no_hardware: bool = False

    screen_id: int = 0
    full_screen: bool = False
    screen_width: int = 1280
    screen_height: int = 720
    background_color: str = "#000000"

    data_dir: str = ""

    baseline_duration: float = 2.0
    cue_duration: float = 1.0
    imagery_duration: float = 4.0
    rest_duration: float = 2.0

    demo_trials_per_class: int = 5
    practice_trials_per_class: int = 5
    formal_trials_per_class: int = 40
    formal_blocks: int = 4

    random_seed: int = 42
    exp_timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def make_filename(self, suffix: str = "") -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"P8_{self.session}_{self.subject_id}_{stamp}"
        if suffix:
            base = f"{base}_{suffix}"
        return base

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("被试 ID 不能为空")
        if self.screen_width <= 0 or self.screen_height <= 0:
            raise ValueError("屏幕分辨率必须为正数")
        if self.baseline_duration <= 0 or self.cue_duration <= 0 or self.imagery_duration <= 0 or self.rest_duration <= 0:
            raise ValueError("所有时长参数都必须大于 0")
        if self.demo_trials_per_class <= 0 or self.practice_trials_per_class <= 0 or self.formal_trials_per_class <= 0:
            raise ValueError("每类 trial 数必须大于 0")
        if self.formal_blocks <= 0:
            raise ValueError("正式采集 blocks 数必须大于 0")
        if self.formal_trials_per_class < self.formal_blocks:
            raise ValueError("正式采集每类 trial 数不能小于 block 数")
        if not self.data_dir.strip():
            raise ValueError("数据保存目录不能为空")


MARKER_TABLE = {
    "DEMO_LEFT": 11,
    "DEMO_RIGHT": 12,
    "PRACTICE_LEFT": 21,
    "PRACTICE_RIGHT": 22,
    "FORMAL_LEFT_CUE": 31,
    "FORMAL_RIGHT_CUE": 32,
    "FORMAL_LEFT_MI": 41,
    "FORMAL_RIGHT_MI": 42,
    "REST_START": 50,
    "BLOCK_START": 90,
    "BLOCK_END": 91,
}


class ExperimentLauncher:
    """图形化离线 MI 启动配置窗口。"""

    def __init__(self):
        self.config: Optional[MIExperimentConfig] = None
        self.cancelled = True

    def run(self) -> Optional[MIExperimentConfig]:
        self.root = tk.Tk()
        self.root.title("P8 离线运动想象采集 — 启动配置")
        self.root.geometry("760x820")
        self.root.resizable(False, False)

        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()
        self.root.mainloop()

        if self.cancelled:
            return None
        return self.config

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="▌ 被试信息", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        row1 = ttk.Frame(main)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="被试 ID:", width=16).pack(side=tk.LEFT)
        self.var_subject = tk.StringVar(value="Sub_01")
        ttk.Entry(row1, textvariable=self.var_subject, width=30).pack(side=tk.LEFT, padx=5)

        ttk.Label(main, text="▌ Trigger 串口", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))
        row2 = ttk.Frame(main)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="串口号:", width=16).pack(side=tk.LEFT)
        self.var_port = tk.StringVar(value="COM5")
        ttk.Entry(row2, textvariable=self.var_port, width=15).pack(side=tk.LEFT, padx=5)
        self.var_no_hardware = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="无硬件模式 (不发送 Trigger)", variable=self.var_no_hardware).pack(side=tk.LEFT, padx=10)

        row2b = ttk.Frame(main)
        row2b.pack(fill=tk.X, pady=2)
        ttk.Label(row2b, text="波特率:", width=16).pack(side=tk.LEFT)
        self.var_baud = tk.StringVar(value="115200")
        ttk.Combobox(row2b, textvariable=self.var_baud, values=["115200"], width=10, state="readonly").pack(side=tk.LEFT, padx=5)

        ttk.Label(main, text="▌ 屏幕设置", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))
        row3 = ttk.Frame(main)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="屏幕 ID:", width=16).pack(side=tk.LEFT)
        self.var_screen = tk.StringVar(value="0")
        ttk.Combobox(row3, textvariable=self.var_screen, values=["0", "1"], width=5, state="readonly").pack(side=tk.LEFT, padx=5)
        self.var_fullscreen = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="全屏", variable=self.var_fullscreen).pack(side=tk.LEFT, padx=10)

        row3b = ttk.Frame(main)
        row3b.pack(fill=tk.X, pady=2)
        ttk.Label(row3b, text="分辨率:", width=16).pack(side=tk.LEFT)
        self.var_width = tk.StringVar(value="1280")
        self.var_height = tk.StringVar(value="720")
        ttk.Entry(row3b, textvariable=self.var_width, width=8).pack(side=tk.LEFT)
        ttk.Label(row3b, text="×").pack(side=tk.LEFT)
        ttk.Entry(row3b, textvariable=self.var_height, width=8).pack(side=tk.LEFT)

        ttk.Label(main, text="▌ 数据保存", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))
        row4 = ttk.Frame(main)
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="保存目录:", width=16).pack(side=tk.LEFT)
        self.var_data_dir = tk.StringVar(value=os.path.join(os.getcwd(), "data"))
        ttk.Entry(row4, textvariable=self.var_data_dir, width=42).pack(side=tk.LEFT, padx=5)
        ttk.Button(row4, text="浏览...", command=self._browse_data_dir, width=8).pack(side=tk.LEFT)

        ttk.Label(main, text="▌ Trial 时长 (秒)", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))
        row5 = ttk.Frame(main)
        row5.pack(fill=tk.X, pady=2)
        self.var_baseline = tk.StringVar(value="2.0")
        self.var_cue = tk.StringVar(value="1.0")
        self.var_imagery = tk.StringVar(value="4.0")
        self.var_rest = tk.StringVar(value="2.0")
        for label, var in [("基线", self.var_baseline), ("Cue", self.var_cue), ("想象", self.var_imagery), ("休息", self.var_rest)]:
            ttk.Label(row5, text=f"{label}:").pack(side=tk.LEFT, padx=(0, 4))
            ttk.Entry(row5, textvariable=var, width=6).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(main, text="▌ Trial 数量", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))
        row6 = ttk.Frame(main)
        row6.pack(fill=tk.X, pady=2)
        self.var_demo_trials = tk.StringVar(value="5")
        self.var_practice_trials = tk.StringVar(value="5")
        self.var_formal_trials = tk.StringVar(value="40")
        self.var_blocks = tk.StringVar(value="4")
        for label, var in [("真实动作/类", self.var_demo_trials), ("练习/类", self.var_practice_trials), ("正式/类", self.var_formal_trials), ("正式 blocks", self.var_blocks)]:
            ttk.Label(row6, text=f"{label}:").pack(side=tk.LEFT, padx=(0, 4))
            ttk.Entry(row6, textvariable=var, width=6).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(main, text="▌ 提示", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))
        hint = (
            "标准流程已内置：讲解 → 真实动作示范 → 纯想象练习 → 准备度确认 → 正式采集。\n"
            "左手 / 右手都统一采用“握拳—松开”的动作感觉想象。"
        )
        ttk.Label(main, text=hint, justify=tk.LEFT, wraplength=700).pack(anchor=tk.W)

        btn_row = ttk.Frame(main)
        btn_row.pack(pady=20)
        ttk.Button(btn_row, text="✓ 开始实验", command=self._on_confirm, width=16).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_row, text="✗ 取消", command=self._on_cancel, width=12).pack(side=tk.LEFT, padx=10)

    def _browse_data_dir(self):
        path = filedialog.askdirectory(title="选择数据保存目录")
        if path:
            self.var_data_dir.set(path)

    def _on_confirm(self):
        try:
            cfg = MIExperimentConfig()
            cfg.subject_id = self.var_subject.get().strip()
            cfg.port_name = self.var_port.get().strip() or cfg.port_name
            cfg.baud_rate = int(self.var_baud.get())
            cfg.no_hardware = self.var_no_hardware.get()

            cfg.screen_id = int(self.var_screen.get())
            cfg.full_screen = True if cfg.screen_id == 1 else self.var_fullscreen.get()
            cfg.screen_width = int(self.var_width.get())
            cfg.screen_height = int(self.var_height.get())
            cfg.data_dir = self.var_data_dir.get().strip()

            cfg.baseline_duration = float(self.var_baseline.get())
            cfg.cue_duration = float(self.var_cue.get())
            cfg.imagery_duration = float(self.var_imagery.get())
            cfg.rest_duration = float(self.var_rest.get())

            cfg.demo_trials_per_class = int(self.var_demo_trials.get())
            cfg.practice_trials_per_class = int(self.var_practice_trials.get())
            cfg.formal_trials_per_class = int(self.var_formal_trials.get())
            cfg.formal_blocks = int(self.var_blocks.get())

            cfg.validate()
            self.config = cfg
            self.cancelled = False
            self.root.quit()
            self.root.destroy()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))

    def _on_cancel(self):
        self.cancelled = True
        self.root.quit()
        self.root.destroy()


def config_from_args() -> MIExperimentConfig:
    import argparse

    parser = argparse.ArgumentParser(description="P8 离线双手运动想象采集")
    parser.add_argument("--subject", default="Sub_01", help="被试 ID")
    parser.add_argument("--port", default="COM5", help="Trigger 串口号")
    parser.add_argument("--no-hardware", action="store_true", help="无硬件模式")
    parser.add_argument("--screen", type=int, default=0, help="屏幕 ID")
    parser.add_argument("--windowed", action="store_true", help="窗口模式")
    parser.add_argument("--data-dir", default="data", help="数据保存目录")
    parser.add_argument("--baseline-duration", type=float, default=2.0, help="基线时长")
    parser.add_argument("--cue-duration", type=float, default=1.0, help="cue 时长")
    parser.add_argument("--imagery-duration", type=float, default=4.0, help="运动想象时长")
    parser.add_argument("--rest-duration", type=float, default=2.0, help="休息时长")
    parser.add_argument("--demo-trials-per-class", type=int, default=5, help="真实动作示范每类 trial 数")
    parser.add_argument("--practice-trials-per-class", type=int, default=5, help="纯想象练习每类 trial 数")
    parser.add_argument("--formal-trials-per-class", type=int, default=40, help="正式采集每类 trial 数")
    parser.add_argument("--formal-blocks", type=int, default=4, help="正式采集 block 数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")

    args = parser.parse_args()

    cfg = MIExperimentConfig()
    cfg.subject_id = args.subject
    cfg.port_name = args.port
    cfg.no_hardware = args.no_hardware
    cfg.screen_id = args.screen
    cfg.full_screen = False if args.windowed else (cfg.screen_id == 1)
    cfg.data_dir = args.data_dir
    cfg.baseline_duration = args.baseline_duration
    cfg.cue_duration = args.cue_duration
    cfg.imagery_duration = args.imagery_duration
    cfg.rest_duration = args.rest_duration
    cfg.demo_trials_per_class = args.demo_trials_per_class
    cfg.practice_trials_per_class = args.practice_trials_per_class
    cfg.formal_trials_per_class = args.formal_trials_per_class
    cfg.formal_blocks = args.formal_blocks
    cfg.random_seed = args.seed
    cfg.validate()
    return cfg
