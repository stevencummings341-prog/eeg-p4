# P4 项目架构与模块详解

> 第一次进项目先读这一份。它说明 **每个目录的角色、每个模块的职责、数据流走向、跨模块依赖关系**。
> SOP / 方案 / 论文叙事在 [`docs/`](docs/) 里；具体怎么跑命令在各代码目录的 `README.md`。

---

## 1. 顶层目录

```text
EEG_Project/                                # 仓库根
├── CLAUDE.md                              AI 协作规则（必读）
├── README.md                              仓库总览
├── environment.yml / requirements.txt     顶层 conda + pip 依赖
├── .gitignore                             数据 / 三方组件 / 衍生产物全部不入库
│
├── scripts/                               项目级辅助脚本
│   ├── sync_to_github.ps1                   一键提交（带数据扩展名拦截）
│   ├── run_pipeline.ps1                     后处理 pipeline 启动器
│   └── diagnose_s4_mi.py                    S4 MI 单独诊断脚本
│
├── eConScan_AiO/                          三方采集软件（gitignore）
├── iRecorder W32产品内容/                 iRecorder 设备 SDK / 驱动（gitignore）
├── scratch/                               临时输出 / 合成测试 / MI 诊断（gitignore）
│
└── P4_EEG/              本项目主体 ↓↓
```

## 2. P4 项目主体

```text
P4_EEG/
├── README.md                              入口导览
├── ARCHITECTURE.md                        本文件
│
├── docs/                                  所有静态文档（方案 / 论文 / SOP / 复盘）
│   ├── README.md                            文档索引
│   ├── proposal.md                          采集 SOP 主方案
│   ├── paper_blueprint.md                   Paper 1 蓝图
│   ├── 实验操作指南.md                      上机检查清单
│   ├── 真实设备连接与正式采集指南.md        设备联调
│   └── changelog/
│       ├── 2026-05-19_全流程稳定性修复.md
│       └── Trigger打标联调复盘.md
│
├── experiment/                            S1-S4 采集主流程  ← 详见 §3
│   ├── launcher.py / config.py / utils.py
│   ├── sessions/                            5 个 session*.py
│   ├── data/                                真实采集数据 (eeg-bdf/ eeg-npz/ video_records/)
│   ├── video/                               相机录制 + 视频动作提取
│   ├── stimuli/                             实验刺激素材
│   └── legacy/                              MATLAB 旧版（仅历史参考）
│
├── processing/                            EEG 后处理 pipeline  ← 详见 §4
│   ├── pipeline/                            indexer / preprocess / epoching / features / qc / run_pipeline
│   └── tests/                               合成数据冒烟测试
│
├── derivatives/                           processing 产物（gitignore）
│   └── <subject_id>/{01_raw_index, 02_preproc, 03_epochs, 04_features, 05_qc}/
│
└── p8_mi_car/                             下游 MI 小车 Demo  ← 详见 §5
    ├── experiment/                          自己的 4a_mi 采集脚本
    ├── keyboard_car_demo.py                 键盘模拟控车
    └── proposal.md / results.md / ...
```

---

## 3. `experiment/` — 实验采集层

**职责**：把被试坐到电脑前、按 SOP 依次完成 4 个 Session，同时把 Marker 准点送给 iRecorder 放大器、并录下同步相机视频。

### 3.1 顶层 API（3 个 Python 文件）

| 文件 | 职责 |
|:---|:---|
| [`launcher.py`](experiment/launcher.py) | **唯一主入口**。负责 GUI 启动、参数收集、按 `cfg.session` 调度 `sessions/session*.py`、自动启停相机录制、统一异常清理。 |
| [`config.py`](experiment/config.py) | `ExperimentConfig` 数据类 + `ExperimentLauncher`（tkinter GUI）+ **`MARKER_TABLE`（权威 Marker 表）**。任何 Session 时长 / Marker 编码改动都要先改这里。 |
| [`utils.py`](experiment/utils.py) | 跨 Session 复用的底层工具：`TriggerSender`（串口）、`KeyboardManager`（KbQueue 包装）、`draw_fixation` / `show_message_and_wait`、滴声合成、`save_data`（落 NPZ 到 `data/eeg-npz/`）、`register_resource` / `cleanup_all`（统一资源释放）。 |

### 3.2 `sessions/` — 4 个 Session 的实验脚本

| 模块 | 任务 | Marker | 时长 | 关键设计 |
|:---|:---|:---|:---|:---|
| `session1_resting.py` | 睁眼/闭眼静息态 | 11/12, 21/22 | ~5 min | 睁 2 min + 闭 2 min + 过渡 30 s，全部支持 ESC 即时退出 |
| `session2_artifacts.py` | 8 类伪迹模板采集 | 30/31, 41-48 | ~10-12 min | T31 触发动作起点；水平眼动小球独立参数化避免数据丢失 |
| `session3_oddball.py` | 视觉 Oddball (P300) | 61/62/63 | ~5.3 min | `_generate_trial_sequence` 有 retry 上限防死循环 |
| `session3_ssvep.py` | SSVEP 闪烁 (6/8.57/10/15 Hz) | 71/72/73/74 | ~7.3 min | **按帧计数循环 + warm-up 60 帧 + recordFrameIntervals**，丢帧统计写入 NPZ |
| `session4_mi.py` | 离线双手运动想象 | 81-89 | ~12-18 min | 单一引导窗 + 正式采集，避免反复按键发标 |

每个 `session*.py` 都导出一个 `run_*(cfg)` 函数，由 `launcher.py` 按需 import。session 之间**互不引用**。

### 3.3 `data/` — 真实采集数据（**只读**）

```text
data/
├── eeg-bdf/           iRecorder 第三方软件保存的连续 EEG 录制（含 Marker annotations）
├── eeg-npz/           PsychoPy 每个 Session 落的 trial 元数据（events / config_json / ...）
└── video_records/     FFmpeg 相机录制：camera_<stamp>.{mp4, _timestamps.csv, _metadata.json, _ffmpeg.log}
```

> **BDF 和 NPZ 是互补不是冗余**：BDF 有信号没语义，NPZ 有语义没信号。两者通过 Marker 在时间轴上对齐。详见 `processing/pipeline/indexer.py` 的配对逻辑。

### 3.4 `video/` — 相机录制 + 视频动作提取

```text
video/
├── camera_recorder_controlled.py          被 launcher.py import 的 FFmpegCameraRecorder
├── analysis_outputs/<video_stem>/         动作提取产物（per_frame.parquet / events.csv / meta.json / preview_overlay.mp4）
└── video_action_tool/                     YOLOv8-Pose + MediaPipe 子项目
    ├── analysis/
    │   ├── pipeline.py                      管道编排（视频读取 → 抽帧 → 特征 → 事件）
    │   ├── extractors.py                    YOLOv8-Pose / MediaPipe Face Landmarker 包装
    │   ├── features.py                      逐帧 EAR / MAR / 头部姿态等派生特征
    │   ├── events.py                        从特征流里检测候选事件（眨眼、头部摆动等）
    │   ├── run_analysis.py                  命令行入口
    │   ├── gui.py                           tkinter GUI
    │   └── models/face_landmarker.task      Face Landmarker 权重
    ├── run_gui.bat                        双击启动 GUI
    ├── run_cli_60s_example.bat            CLI 60s 抽样示例
    ├── check_environment.py               依赖与模型自检
    ├── environment.yml / requirements.txt
    └── yolov8n-pose.pt                    YOLO 权重
```

**输入**：`experiment/data/video_records/*.mp4`
**输出**：`experiment/video/analysis_outputs/<video_stem>/` —— **不写入 data/**。

### 3.5 `stimuli/` & `legacy/`

- `stimuli/`：实验用的情绪视频素材（positive*.mp4 / negative*.mp4），用 `.gitignore` 的 `**/sucai/` 与通用 `*.mp4` 双重忽略。前身叫 `sucai/`。
- `legacy/`：MATLAB 旧版本（`task3_v4.m`），仅作历史参考，**不参与现行流程**。

---

## 4. `processing/` — EEG 后处理 pipeline

**职责**：把 `experiment/data/` 的 BDF + NPZ 配对成可复现的 `derivatives/<subject>/`。

### 4.1 6 步法（按依赖顺序）

```text
indexer  →  preprocess  →  epoching  →  features  →  qc  →  (run_pipeline 编排所有)
```

| 文件 | 职责 |
|:---|:---|
| [`pipeline/indexer.py`](processing/pipeline/indexer.py) | 扫 `data/eeg-bdf/*.bdf` + `data/eeg-npz/P4_*.npz`，按 Marker 把 BDF 切成 `SubBdfSession`，再用 event-count + 时间最近原则与 NPZ 配对。 |
| [`pipeline/io_utils.py`](processing/pipeline/io_utils.py) | BDF / NPZ 读取的薄包装：`read_bdf_info`、`load_npz_session`。 |
| [`pipeline/preprocess.py`](processing/pipeline/preprocess.py) | HP 0.5 / LP 80 / notch 50 / average reference / standard_1020 montage。**不做 ICA**——那会模糊"降噪模型应该干什么"的研究问题。 |
| [`pipeline/epoching.py`](processing/pipeline/epoching.py) | Session 感知切片：S1 (2 s 滑窗)、S2 (T31 切 + T4x 回推)、S3 P300 (±0.2/0.8 s)、S3 SSVEP (0.3/4.0 s)、S4 MI (-2.0/4.0 s)。 |
| [`pipeline/features/`](processing/pipeline/features/) | 任务特征：`s1_alpha`（Alpha 阻断指数）、`s2_artifacts`（峰峰 + ROI）、`s3_p300`（峰幅 + 潜伏期）、`s3_ssvep`（SNR + ITPC + 2× 谐波）、`s4_mi`（μ/β ERD% + C3/C4 拉特化）。 |
| [`pipeline/qc.py`](processing/pipeline/qc.py) | 自动 QC HTML 报告：每个 sub-session 一段，图自动 base64 内嵌。 |
| [`pipeline/run_pipeline.py`](processing/pipeline/run_pipeline.py) | CLI 主入口；支持 `--subject` / `--date` / `--list-runs` / `--dry-run` / `--force` / `--hp-hz` / `--lp-hz` / `--notch-hz`。 |
| [`pipeline/constants.py`](processing/pipeline/constants.py) | 顶层超参（滤波频段、Session Marker 集合、特征窗口等）。 |
| [`tests/make_synth_data.py`](processing/tests/make_synth_data.py) | 生成合成 EDF + NPZ，跑 30 s 冒烟测试完整 pipeline。 |

### 4.2 产物布局

```text
derivatives/<subject_id>/
├── 01_raw_index.json          BDF↔NPZ 配对清单
├── 02_preproc/                滤波 / montage / 重参考后的 raw FIF
├── 03_epochs/                 按 Marker 切好的 mne.Epochs
├── 04_features/               *.json 形式的任务特征（含原始 PSD / 波形数组）
└── 05_qc/report.html          自包含 HTML QC 报告
```

`derivatives/` 与 `data/` **读写分离**：pipeline 只读 `data/`，所有产物落到 `derivatives/`，可随时 `rm -rf` 重跑。

---

## 5. `p8_mi_car/` — 下游 MI 脑控小车 Demo

**职责**：复用 P4 S4 的离线双手 MI 数据，做在线分类 / 模拟小车控制接口。

```text
p8_mi_car/
├── README / proposal / experiment_log / results / competitive_landscape   叙事 + 阶段记录
├── keyboard_car_demo.py                   键盘模拟控车（先把控车接口做出来）
└── experiment/
    ├── launcher.py / config.py / utils.py / session4a_mi.py    MI 在线采集（与 P4 S4 算同源但参数独立）
    └── eeg/<recording>.bdf                自己的真实数据（与 P4 data/ 互不干扰）
```

> p8_mi_car 是 **独立子项目**：自己的 launcher、自己的 config、自己的 eeg/。不与 P4 `experiment/` 互相 import。

---

## 6. 数据流总览

```text
被试 + 显示器
    │
    │   PsychoPy 屏幕刺激 + 键盘
    ▼
launcher.py + sessions/session*.py
    │
    │   ─── TriggerSender ───►  iRecorder 放大器  ──►  experiment/data/eeg-bdf/<rec>.bdf
    │   ─── save_data ────────────────────────────►  experiment/data/eeg-npz/P4_S*_*.npz
    │   ─── FFmpegCameraRecorder ─────────────────►  experiment/data/video_records/camera_*.mp4
    ▼
        ┌──────────────────────────────┬──────────────────────────────┐
        ▼                              ▼                              ▼
   processing/pipeline           video_action_tool             p8_mi_car (将来)
   indexer + preprocess           pipeline.py (YOLO+MP)         在线分类器
   epoching + features                                          键盘小车 Demo
        │                              │
        ▼                              ▼
  derivatives/<subj>/            experiment/video/
  *.fif / *.json / report.html   analysis_outputs/<stem>/
                                 *.parquet / *.csv / *.mp4
```

---

## 7. 跨模块依赖速查（哪改了会爆炸）

| 谁依赖谁 | 怎么连的 | 改动这里会影响 |
|:---|:---|:---|
| `launcher.py` → `sessions/session*.py` | `from sessions.session1_resting import run_session1` 等 | 改 sessions/ 包路径 / 文件名 / `run_*` 函数签名 |
| `launcher.py` → `video.camera_recorder_controlled` | `from video.camera_recorder_controlled import FFmpegCameraRecorder` | 改 `camera_recorder_controlled.py` 位置 |
| `sessions/session*.py` → `config`, `utils` | `from config import ExperimentConfig, MARKER_TABLE, get_marker` 等 | 改 `config.py` 的 dataclass 字段、`MARKER_TABLE` 键名 |
| `utils.save_data` → `cfg.data_dir` | NPZ 落到 `<data_dir>/eeg-npz/` | 改 `data_dir` 子目录约定 |
| `processing/pipeline/indexer.py` → `data/eeg-bdf/` + `data/eeg-npz/` | `glob("*.bdf")` / `glob("P4_S*_*.npz")` | 把 BDF / NPZ 挪走 |
| `video_action_tool/analysis/gui.py` → `experiment/data/video_records/` | `DEFAULT_RECORDS_DIR` 硬编码 | 改视频默认输出目录 |
| `video_action_tool/analysis/extractors.py` → `analysis/models/face_landmarker.task` | 硬编码模型路径 | 模型文件位置 |
| `video_action_tool/analysis/run_analysis.py` → `experiment/video/analysis_outputs/` | `_DEFAULT_OUTPUT_PARENT` | 改分析产物落点 |

## 8. 入门顺序（给新接触本项目的人）

1. 读 [`README.md`](README.md) + 本文档（10 min）。
2. 读 [`docs/proposal.md`](docs/proposal.md) §1-3（30 min）了解为什么要 4 Session。
3. 读 [`experiment/README.md`](experiment/README.md)，跑无硬件冒烟测试：

   ```bash
   cd experiment
   python launcher.py --subject Test --session all --quick-test --windowed --no-hardware --no-camera --screen 0
   ```
4. 读 [`processing/README.md`](processing/README.md)，跑合成数据 pipeline：

   ```bash
   python "processing/tests/make_synth_data.py"
   cd processing
   python -m pipeline.run_pipeline --data-dir "..\..\scratch\synth_data" --out-dir "..\..\scratch\synth_derivatives"
   ```
5. 打开 `scratch\synth_derivatives\Synth_01\05_qc\report.html` 看 QC 长什么样。
6. 真要做事的话：约一个被试 → 跑 4-Session → 跑 pipeline → 看 QC → 进入降噪模型迭代。
