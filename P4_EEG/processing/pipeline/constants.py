"""Pipeline 常量：Marker 表、通道分组、滤波/特征参数。

与 `experiment/config.py:MARKER_TABLE` 保持一一对应；如果实验代码改了
Marker 编号，必须同步更新这里 (跑 pipeline.tests.test_marker_sync 检查)。
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Marker 编码 (与 experiment/config.py:MARKER_TABLE 同步)
# --------------------------------------------------------------------------- #
MARKERS = {
    # Session 1 — 静息态
    "S1_EO_START": 11, "S1_EO_END": 12,
    "S1_EC_START": 21, "S1_EC_END": 22,

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

    # Session 3 — 任务态
    "S3_ODDBALL_STD":    61,
    "S3_ODDBALL_TARGET": 62,
    "S3_REST_BASELINE":  63,
    "S3_SSVEP_6HZ":      71,
    "S3_SSVEP_8_57HZ":   72,
    "S3_SSVEP_10HZ":     73,
    "S3_SSVEP_15HZ":     74,

    # Session 4 (scheme="motor_imagery") — 双手 MI
    "S4_MI_DEMO_LEFT":        81,
    "S4_MI_DEMO_RIGHT":       82,
    "S4_MI_FORMAL_LEFT_CUE":  83,
    "S4_MI_FORMAL_RIGHT_CUE": 84,
    "S4_MI_FORMAL_LEFT":      85,
    "S4_MI_FORMAL_RIGHT":     86,
    "S4_MI_REST":             87,
    "S4_MI_BLOCK_START":      88,
    "S4_MI_BLOCK_END":        89,

    # Session 4 (scheme="emotion") — 情绪识别 (音视频刺激)
    "S4_EMOTION_START":      100,
    "S4_EMOTION_NEGATIVE":   101,
    "S4_EMOTION_NEUTRAL":    102,
    "S4_EMOTION_POSITIVE":   103,
    "S4_EMOTION_END":        104,
    "S4_EMOTION_BASELINE":   105,
    "S4_EMOTION_REST":       106,
}

# 反向查表
MARKER_NAME = {v: k for k, v in MARKERS.items()}

# 每个 Session 涉及到的 Marker 集合（用于自动识别 BDF 中包含哪些 Session）
# 注意 S4_MI 与 S4_EMOTION 互斥；一个 BDF 里通常只会出现其中一套。
SESSION_MARKERS = {
    "S1":          {11, 12, 21, 22},
    "S2":          {30, 31, 41, 42, 43, 44, 45, 46, 47, 48},
    "S3_ODDBALL":  {61, 62, 63},
    "S3_SSVEP":    {71, 72, 73, 74},
    "S4_MI":       {81, 82, 83, 84, 85, 86, 87, 88, 89},
    "S4_EMOTION":  {100, 101, 102, 103, 104, 105, 106},
}

# --------------------------------------------------------------------------- #
# BDF annotation 描述格式：iRecorder 把 marker int 输出为 "T<int>"
# --------------------------------------------------------------------------- #
ANNOT_PREFIX = "T"

# --------------------------------------------------------------------------- #
# EEG 通道分组（32 通道标准 10-20）
# --------------------------------------------------------------------------- #
EEG_32_CHANNELS = [
    "Fp1", "AF3", "F7", "F3", "FC1", "FC5", "T7", "C3",
    "Cz",  "FC2", "FC6", "F8", "F4", "Fz",  "AF4", "Fp2",
    "O2",  "PO4", "P4", "P8",  "CP6", "CP2", "C4", "T8",
    "CP5", "CP1", "Pz", "P3",  "P7",  "PO3", "O1", "Oz",
]

# 关键 ROI（特征提取用）
ROI_FRONTAL = ["Fp1", "Fp2", "AF3", "AF4"]          # 眼电检测
ROI_TEMPORAL = ["T7", "T8"]                          # 肌电 (咬牙)
ROI_CENTRAL = ["C3", "C4", "Cz"]                     # 运动想象 (μ/β ERD)
ROI_PARIETAL = ["Pz", "CP1", "CP2"]                  # P300
ROI_OCCIPITAL = ["O1", "O2", "Oz", "PO3", "PO4"]     # Alpha 阻断 + SSVEP

# 情绪识别专用 ROI（额叶不对称 + 边缘相关投影）
ROI_EMOTION_FRONTAL_LEFT  = ["F3", "AF3", "Fp1"]     # 左额叶（FAA 计算分母侧）
ROI_EMOTION_FRONTAL_RIGHT = ["F4", "AF4", "Fp2"]     # 右额叶（FAA 计算分子侧）
ROI_EMOTION_BROAD = ["F3", "F4", "Fz", "AF3", "AF4",
                     "Cz", "Pz",
                     "O1", "O2", "Oz"]               # 全脑代表通道，跨频段功率

# --------------------------------------------------------------------------- #
# 预处理参数
# --------------------------------------------------------------------------- #
DEFAULT_SFREQ = 500.0          # iRecorder 默认采样率
HP_FILTER_HZ = 0.5             # 高通去漂
LP_FILTER_HZ = 80.0            # 低通去高频肌电
NOTCH_FREQS = (50.0,)          # 中国工频，按需改 60.0
REFERENCE = "average"          # "average" / "mastoids" / None
MONTAGE = "standard_1020"

# --------------------------------------------------------------------------- #
# Session 1 — Alpha 阻断
# --------------------------------------------------------------------------- #
S1_ALPHA_BAND = (8.0, 13.0)
S1_BASELINE_SKIP_S = 5.0       # 切掉 EO/EC 开头 5s, 让被试稳定下来
S1_PSD_WIN_S = 4.0             # PSD welch 窗
S1_PSD_OVERLAP = 0.5

# --------------------------------------------------------------------------- #
# Session 2 — 伪迹模板
# --------------------------------------------------------------------------- #
S2_EPOCH_TMIN = -0.2
S2_EPOCH_TMAX = 1.2
S2_BASELINE = (None, 0.0)
# S2 在伪迹动作期内不希望剔除大幅度信号——伪迹本身就是大幅度的
S2_REJECT_PTP_UV = None        # 不做幅度剔除

# --------------------------------------------------------------------------- #
# Session 3 — Oddball / P300
# --------------------------------------------------------------------------- #
S3_ODD_EPOCH_TMIN = -0.2
S3_ODD_EPOCH_TMAX = 0.8
S3_ODD_BASELINE = (-0.2, 0.0)
S3_ODD_REJECT_PTP_UV = 150.0   # 单 trial 峰峰值 > 150 µV 剔除
S3_ODD_P300_WIN = (0.25, 0.45) # P300 寻峰窗口 (s)
S3_ODD_P300_CHANNELS = ["Pz", "CPz", "CP1", "CP2"]  # CPz 多数 32ch montage 没有，会自动忽略

# --------------------------------------------------------------------------- #
# Session 3 — SSVEP
# --------------------------------------------------------------------------- #
S3_SSVEP_FREQS = {
    "6Hz":    6.00,
    "8.57Hz": 8.57,
    "10Hz":   10.00,
    "15Hz":   15.00,
}
S3_SSVEP_MARKER_TO_FREQ = {
    71: "6Hz",
    72: "8.57Hz",
    73: "10Hz",
    74: "15Hz",
}
S3_SSVEP_EPOCH_TMIN = 0.3      # 切掉前 300ms 让 SSVEP 进入稳态
S3_SSVEP_EPOCH_TMAX = 4.0
S3_SSVEP_PSD_FMIN = 4.0
S3_SSVEP_PSD_FMAX = 30.0
S3_SSVEP_SNR_NEIGHBOR_HZ = 1.0
S3_SSVEP_SNR_EXCLUDE_HZ = 0.2  # 不算在邻近频段内的目标频带半宽
S3_SSVEP_HARMONICS = (1, 2)    # 计算 SNR/ITPC 时把 2 倍频也算进去

# --------------------------------------------------------------------------- #
# Session 4 — Motor Imagery
# --------------------------------------------------------------------------- #
# Trial 时间轴（marker T85/T86 锁在 imagery 起点 t=0）：
#   t = -3 ~ -1 s : fixation（+ 注视十字）   ← 真正的 baseline
#   t = -1 ~  0 s : cue（"左手"/"右手" 文字） ← 已有 anticipatory ERD，不能当 baseline
#   t =  0 ~  4 s : imagery（"请想象…"）     ← active window
#   t =  4 ~  6 s : rest（"休息"）
S4_MI_EPOCH_TMIN = -3.0        # 把整个 fixation 截进来
S4_MI_EPOCH_TMAX = 4.0
S4_MI_BASELINE = (-3.0, -1.0)  # MNE epoching 的 DC baseline = fixation 全段
S4_MI_REJECT_PTP_UV = 200.0
S4_MI_MU_BAND = (8.0, 13.0)
S4_MI_BETA_BAND = (13.0, 30.0)
S4_MI_ERD_BASELINE = (-2.5, -1.0)  # 完全落在 fixation 内，避开 cue 期 anticipatory ERD
S4_MI_ERD_ACTIVE = (0.5, 3.5)
# 单 trial outlier 拒绝（避免极端 trial 把 mean 拉散）
S4_MI_TRIAL_ERD_CLIP_PCT = 200.0   # 单 trial ERD% 绝对值 > 该阈值 → 视为伪迹/baseline 异常，弃用
S4_MI_TRIAL_MIN_BASELINE_UV2 = 0.5 # 单 trial baseline bandpower 太小 (< 0.5 µV²) → 分母不稳，弃用

# --------------------------------------------------------------------------- #
# Session 4 — Emotion Recognition (scheme="emotion")
# --------------------------------------------------------------------------- #
# Trial 时间轴（marker T101/T102/T103 锁在视频起点 t=0）：
#   T105 (BASELINE) at t = -fixation_duration_s, 通常 -2 s 处
#   t = -2 ~ 0 s : 注视十字 (fixation)            ← baseline 窗口
#   t =  0 ~ ~5 s : 视频播放 (实际长度 3-8s 不等) ← active 窗口
#   T106 (REST) at video end，后续 rest 2 s
S4_EMOTION_EPOCH_TMIN = -2.0          # 把整个 fixation 截进来（baseline 用）
S4_EMOTION_EPOCH_TMAX = 6.0           # 视频活跃窗 + 一点 rest buffer
S4_EMOTION_BASELINE = (-2.0, 0.0)     # 注视十字段做 DC baseline
S4_EMOTION_REJECT_PTP_UV = 250.0      # 含眼动 / 头动 → 阈值放宽

# 分析窗：刺激起点后跳过 0.5 s 锁相反应，取到 5.5 s（覆盖大部分视频）
S4_EMOTION_ACTIVE_WIN  = (0.5, 5.5)
S4_EMOTION_BASELINE_WIN = (-1.8, -0.2)

# 情绪 EEG 经典频段
S4_EMOTION_BANDS = {
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta":  (13.0, 30.0),
    "gamma": (30.0, 45.0),
}

# 分类 marker → 标签
S4_EMOTION_MARKER_TO_LABEL = {
    101: "negative",
    102: "neutral",
    103: "positive",
}
S4_EMOTION_LABEL_TO_CN = {
    "negative": "负性",
    "neutral":  "中性",
    "positive": "正性",
}
# 计算 PSD 时的频率范围（图与谱写出去时用）
S4_EMOTION_PSD_FMIN = 2.0
S4_EMOTION_PSD_FMAX = 45.0

# --------------------------------------------------------------------------- #
# 输出目录命名
# --------------------------------------------------------------------------- #
DERIVATIVES_SUBDIRS = {
    "preproc": "02_preproc",
    "epochs":  "03_epochs",
    "features": "04_features",
    "qc":       "05_qc",
}
