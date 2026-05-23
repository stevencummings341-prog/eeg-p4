# P4 — EEG 降噪与任务特征保真

> 父级 README：[`../README.md`](../README.md) · 全局规则：[`../CLAUDE.md`](../CLAUDE.md)

P4 旨在搭建一套 **可复现的 EEG 数据采集 + 数据净化** 基础设施。核心做法是用 4 个 Session 把"干净任务信号"和"伪迹噪声"在源头拆开，并同步录制相机视频，便于后续视频侧动作事件 ↔ EEG Marker 对齐。

## 子目录角色

```text
P4_EEG/
├── README.md          本文件
├── ARCHITECTURE.md    详细模块说明（建议第一次进项目先读它）
│
├── docs/              所有静态文档（方案、论文蓝图、操作指南、复盘日志）
├── experiment/        S1-S4 采集主流程 + 相机录制 + 视频动作提取工具
├── processing/        EEG 后处理 pipeline（BDF↔NPZ 配对 / 预处理 / 切片 / 任务特征 / QC）
├── derivatives/       processing 产物（gitignore；可重跑）
└── p8_mi_car/         下游 Demo：在线双手 MI 脑控小车（用 P4 S4 的数据闭环）
```

| 目录 | 何时进去 |
|:---|:---|
| `docs/` | 项目方案、论文蓝图、SOP 操作指南、历次复盘日志。详见 [`docs/README.md`](docs/README.md)。 |
| `experiment/` | 跑 4-Session 采集、调试 Marker / Trigger、做无硬件冒烟测试、跑视频动作提取。详见 [`experiment/README.md`](experiment/README.md)。 |
| `experiment/video/video_action_tool/` | 单独对相机视频做 YOLOv8-Pose + MediaPipe 分析，输出逐帧特征与事件表。详见 [`experiment/video/README.md`](experiment/video/README.md)。 |
| `processing/` | 从 `experiment/data/` 的 BDF + NPZ 跑出 `derivatives/<subject>/` 的预处理 raw、epoch、任务特征、QC HTML 报告。详见 [`processing/README.md`](processing/README.md)。 |
| `p8_mi_car/` | 在 P4 S4 离线双手 MI 数据基础上，做在线分类 / 模拟小车控制。详见 [`p8_mi_car/experiment/README.md`](p8_mi_car/experiment/README.md)。 |

## 4-Session 一张表

| Session | 入口脚本 | 作用 | Marker 范围 |
|:---|:---|:---|:---|
| S1 静息态 | `experiment/sessions/session1_resting.py` | 干净脑电底色 / Alpha 阻断 | 11/12, 21/22 |
| S2 伪迹模板 | `experiment/sessions/session2_artifacts.py` | 独立眼电/肌电噪声库 | 30/31, 41-48 |
| S3 银标准任务态 | `experiment/sessions/session3_oddball.py` + `session3_ssvep.py` | 干净 P300 / SSVEP | 61-63, 71-74 |
| S4 离线双手 MI | `experiment/sessions/session4_mi.py` | 左右手运动想象采集 | 81-89 |

> 权威 Marker 与时长口径请始终以 [`experiment/config.py:MARKER_TABLE`](experiment/config.py) 为准。

## 数据流概览

```text
S1-S4 采集
  └─ EEG (.bdf, iRecorder 第三方软件保存)  →  experiment/data/eeg-bdf/
  └─ Trial 元数据 (.npz, PsychoPy 保存)    →  experiment/data/eeg-npz/
  └─ 相机视频 + 时间戳 (.mp4/.csv/.json)   →  experiment/data/video_records/

后处理产物 (与 data/ 读写分离)
  └─ 视频动作提取                          →  experiment/video/analysis_outputs/<video_stem>/
                                              per_frame.parquet / events.csv / meta.json
  └─ EEG pipeline                          →  derivatives/<subject>/{01_raw_index,02_preproc,03_epochs,04_features,05_qc}/
```

下游 `p8_mi_car/` 复用 S4 的 MI 数据训练在线分类器，再通过键盘 Demo (`p8_mi_car/keyboard_car_demo.py`) 模拟小车控制接口。

## 数据安全提醒

- **永远不要修改 / 删除 / 移动** `experiment/data/`（包含 `eeg-bdf/`、`eeg-npz/`、`video_records/`）、`p8_mi_car/experiment/eeg/` 中的任何文件。
- 生成测试数据请使用 `scratch/`、`tmp/` 或显式声明的非真实数据目录。
- 任何 `.bdf` / `.fif` / `.npz` / 真实视频都禁止入库（已被 `.gitignore` 覆盖，但仍要手动确认）。
