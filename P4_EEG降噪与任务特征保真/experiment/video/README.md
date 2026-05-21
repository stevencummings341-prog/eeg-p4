# experiment/video/ — 相机录制 + 视频动作提取

本目录承担 **两件互相独立的事**，请按用途选择入口：

| 用途 | 何时用 | 入口 |
|:---|:---|:---|
| **采集中同步录制相机** | 跑 `experiment/launcher.py` 时被 import；也可单独调试相机 | `camera_recorder_controlled.py` / `record_camera_with_timestamps.py` |
| **采集后做视频动作提取** | 想从录制好的 `.mp4` 抽 YOLO 关键点、面部 EAR/MAR、头部姿态、事件表 | `video_action_tool/` 子项目 |

## 文件分工

```text
experiment/video/
├── README.md                              本文件
│
├── camera_recorder_controlled.py          被 experiment/launcher.py import
│                                          (FFmpegCameraRecorder：实验期间自动启/停相机)
├── record_camera_with_timestamps.py       独立 CLI：单独录一段相机视频 + 逐帧时间戳
│
├── CLAUDE_CODE_HANDOFF.md                 给"另一台机器接手"的 Claude Code 用的说明
├── README_无缝迁移指南.md                 视频工具迁移到实验室电脑的完整步骤
│
├── check_environment.bat                  检查 video_action_tool 所需依赖是否齐全
├── install_env_conda.bat                  用 conda 创建/更新 eeg-p4 环境
├── install_env_pip.bat                    用 pip 创建本地 .venv
│
├── scratch/                               (gitignore) 本地大文件 / 临时输出
│   └── video_records/                     用 record_camera_with_timestamps.py 的默认输出
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

## 路径约束（请勿改动）

下列硬编码路径已经被代码依赖，重命名 / 移动会立刻报错：

- [`camera_recorder_controlled.py`](camera_recorder_controlled.py)：默认输出 `<this_dir>/../data/video_records/`，被 `experiment/launcher.py` 通过 `from video.camera_recorder_controlled import FFmpegCameraRecorder` 引用。
- [`record_camera_with_timestamps.py`](record_camera_with_timestamps.py)：默认输出 `<this_dir>/scratch/video_records/`。
- [`video_action_tool/analysis/`](video_action_tool/analysis/)：包内全部用相对 import (`from .extractors`, `from .pipeline` …)，整个包名 / 子模块名都不能改。
- [`video_action_tool/analysis/models/face_landmarker.task`](video_action_tool/analysis/models/) 与 [`video_action_tool/yolov8n-pose.pt`](video_action_tool/yolov8n-pose.pt)：模型文件位置被 `extractors.py` 与 `check_environment.py` 硬编码读取。

## 推荐工作流

1. **采集阶段**：直接跑 `experiment/launcher.py`，相机录制会自动启停，视频与时间戳落到 `experiment/data/video_records/`。
2. **想抽一段做事后分析**：把 `.mp4` 拷到 `video_action_tool/scratch/video_records/`，双击 `run_gui.bat`，选视频 → 选时段 → 选输出目录。
3. **迁移到新电脑**：跟随 [`README_无缝迁移指南.md`](README_无缝迁移指南.md)。
