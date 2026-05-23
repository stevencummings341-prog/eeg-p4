# experiment/video/ — 相机录制 + 视频动作提取

本目录承担 **两件互相独立的事**，请按用途选择入口：

| 用途 | 何时用 | 入口 |
|:---|:---|:---|
| **采集中同步录制相机** | 跑 `experiment/launcher.py` 时被 import | `camera_recorder_controlled.py` |
| **采集后做视频动作提取** | 想从录制好的 `.mp4` 抽 YOLO 关键点、面部 EAR/MAR、头部姿态、事件表 | `video_action_tool/` 子项目 |

## 目录结构

```text
experiment/video/
├── README.md                              本文件
│
├── camera_recorder_controlled.py          被 experiment/launcher.py import
│                                          (FFmpegCameraRecorder：实验期间自动启/停相机)
│
├── analysis_outputs/                      视频动作提取产物（每个视频一个子目录）
│   └── <video_stem>/
│       ├── per_frame.parquet              逐帧特征（YOLO 17 关键点 + 面部 EAR/MAR 等）
│       ├── per_frame.csv                  同上 CSV 副本
│       ├── events.csv                     从特征里检测出的动作事件表
│       ├── meta.json                      运行配置和统计摘要
│       └── preview_overlay.mp4            （可选）叠加可视化的预览短片
│
└── video_action_tool/                     YOLOv8-Pose + MediaPipe 动作提取子项目
    ├── analysis/                          (Python 包：pipeline / extractors / features / events / gui)
    │   └── README.md                      子项目使用说明（命令行 + GUI）
    ├── run_gui.bat                        双击启动图形化提取工具
    ├── run_cli_60s_example.bat            命令行 60s 抽样示例
    ├── check_environment.py               依赖与模型自检
    ├── environment.yml                    conda 环境定义
    ├── requirements.txt                   pip 依赖
    └── yolov8n-pose.pt                    YOLOv8 Pose 权重（首次运行也会自动下载）
```

## 数据流

原始视频与分析产物 **读写分离**：

```text
experiment/data/video_records/<video>.mp4          ← 相机录制原始 (data/ 只读)
       │
       ▼  video_action_tool/analysis 处理
experiment/video/analysis_outputs/<video_stem>/    ← 派生分析产物 (可重跑)
```

## 路径约束（请勿改动）

下列硬编码路径已经被代码依赖，重命名 / 移动会立刻报错：

- [`camera_recorder_controlled.py`](camera_recorder_controlled.py)：默认输出 `<this_dir>/../data/video_records/`，被 `experiment/launcher.py` 通过 `from video.camera_recorder_controlled import FFmpegCameraRecorder` 引用。
- [`video_action_tool/analysis/`](video_action_tool/analysis/)：包内全部用相对 import（`from .extractors`, `from .pipeline` …），整个包名 / 子模块名都不能改。
- [`video_action_tool/analysis/models/face_landmarker.task`](video_action_tool/analysis/models/) 与 [`video_action_tool/yolov8n-pose.pt`](video_action_tool/yolov8n-pose.pt)：模型文件位置被 `extractors.py` 与 `check_environment.py` 硬编码读取。
- 分析输出默认落到 `experiment/video/analysis_outputs/<video_stem>/`（`run_analysis.py` 和 `gui.py` 都用此约定）。

## 推荐工作流

1. **采集阶段**：直接跑 `experiment/launcher.py`，相机录制会自动启停，视频与时间戳落到 `experiment/data/video_records/`。
2. **事后跑动作提取**：
   - 图形界面：双击 [`video_action_tool/run_gui.bat`](video_action_tool/run_gui.bat)，默认会列出 `experiment/data/video_records/` 里的视频，选一段即可。
   - 命令行：

     ```bash
     cd P4_EEG/experiment/video/video_action_tool
     python -m analysis.run_analysis \
         --video ../../data/video_records/camera_20260518_193936.mp4 \
         --duration 60 --save-preview
     ```
   - 产物自动落到 `experiment/video/analysis_outputs/<video_stem>/`。
3. **环境安装**：详见 [`video_action_tool/environment.yml`](video_action_tool/environment.yml) / [`requirements.txt`](video_action_tool/requirements.txt) / [`check_environment.py`](video_action_tool/check_environment.py)。
