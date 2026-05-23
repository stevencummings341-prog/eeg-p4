"""P4 EEG 后处理 pipeline。

模块组织（按数据流方向）：
    constants  — Marker 表、通道分组、滤波/特征常量
    io_utils   — 读 BDF/NPZ、解析 annotations
    indexer    — 扫描 data/、配对 BDF↔NPZ
    preprocess — 滤波、参考、montage
    epoching   — 按 Marker 切片成 mne.Epochs
    features/  — 各 Session 的任务特征 (P300 / Alpha / SSVEP / MI)
    qc         — 自动 QC HTML 报告
    run_pipeline — CLI 主入口

所有写入操作只发生在 derivatives/ 目录下，data/ 永远只读。
"""

__version__ = "0.1.0"
