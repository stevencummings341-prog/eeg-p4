"""
config.py — 全局配置 + 环境初始化（PySide6 / MPL / Qt plugin 路径）

在 import 任何 PySide6 / matplotlib 之前调用 bootstrap()。
"""

import os as _os


def bootstrap():
    """在任何 GUI 库 import 之前设置环境变量。可被多次安全调用（幂等）。

    用强制赋值（而非 setdefault），因为 conda 环境激活脚本可能已把
    MPLBACKEND / PYQTGRAPH_QT_LIB 设为空字符串，setdefault 不会覆盖空值。
    """
    _os.environ["MPLBACKEND"] = "QtAgg"
    _os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

    if not _os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"):
        import importlib.util as _util
        _spec = _util.find_spec("PySide6")
        if _spec and _spec.origin:
            _dir = _os.path.join(_os.path.dirname(_spec.origin), "plugins", "platforms")
            if _os.path.isdir(_dir):
                _os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _dir


# ============================================================
# LSL
# ============================================================

ENABLE_LSL = True
LSL_STREAM_NAME = "iRe"
LSL_TIMEOUT = 5.0           # resolve_streams 等待时间 (秒)

# ============================================================
# EEG 通道
# ============================================================

CHANNEL_NAMES = [
    "Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8", "FC5",
    "FC1", "FC2", "FC6", "T7", "C3", "Cz", "C4", "T8",
    "TP9", "CP5", "CP1", "CP2", "CP6", "TP10", "P7", "P3",
    "Pz", "P4", "P8", "PO9", "O1", "Oz", "O2", "PO10",
]
DEFAULT_SFREQ = 250

# ============================================================
# 可视化
# ============================================================

PLOT_WINDOW_SEC = 2.0           # 波形窗口时长
LATERAL_HISTORY_SEC = 4.0       # 偏侧化历史时长

# PSD / Topomap 刷新间隔 (秒)
ANALYSIS_INTERVAL = 0.3

# ============================================================
# 摄像头 (OpenCV + dshow)
# ============================================================

# 后端: "dshow" (Windows DirectShow) | "msmf" (Media Foundation) | "" (自动)
CAMERA_BACKEND = "dshow"

# ---- 方式一：按索引（0 = 内置摄像头, 1 = 外接 USB 摄像头）----
CAMERA_INDEX = 1

# ---- 方式二：按名称（优先级更高，非空时忽略 CAMERA_INDEX）----
# Windows dshow 格式: "video=<设备名>"，用 ffmpeg -list_devices 查看
# 常见外接摄像头名称示例:
#   "USB2.0 PC CAMERA" / "HD USB Camera" / "C922 Pro Stream Webcam"
#   "Logitech Webcam C930e" / "Integrated Camera"
CAMERA_NAME = ""

# ---- 参数 ----
CAMERA_FPS = 30
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

# ============================================================
# 脑区映射（供快速索引）
# ============================================================

_IDX = {n: i for i, n in enumerate(CHANNEL_NAMES)}

LEFT_TEMPORAL = [_IDX[ch] for ch in ["T7", "F7", "FC5", "C3", "CP5", "TP9", "P7"] if ch in _IDX]
RIGHT_TEMPORAL = [_IDX[ch] for ch in ["T8", "F8", "FC6", "C4", "CP6", "TP10", "P8"] if ch in _IDX]
OCCIPITAL = [_IDX[ch] for ch in ["O1", "Oz", "O2", "PO9", "PO10"] if ch in _IDX]
FRONTAL = [_IDX[ch] for ch in ["Fp1", "Fp2", "Fz", "F3", "F4"] if ch in _IDX]

del _IDX
