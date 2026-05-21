# Claude Code 迁移接手说明

你正在实验室电脑上接手 P4 EEG 项目的视频动作提取工具。请按以下顺序工作。

## 目标

让用户能在这台电脑上通过 GUI 选择实验视频，提取动作事件：

- blink
- head_yaw_motion
- head_pitch_motion
- mouth_open
- per-frame YOLO/MediaPipe 特征

## 安全边界

- 不要修改、删除、移动用户的原始视频。
- 不要读取或修改任何 EEG `data/` 目录，除非用户明确要求。
- 输出应写入用户选择的输出目录，默认可以是视频旁边的 `analysis_outputs/`。

## 推荐步骤

1. 阅读 `README_无缝迁移指南.md`。
2. 确认当前目录结构是否完整。
3. 运行 `check_environment.bat`。
4. 如果缺环境，运行 `install_env_conda.bat`。
5. 再次运行 `check_environment.bat`。
6. 启动 `video_action_tool/run_gui.bat`。
7. 先让用户用 5 秒视频做 smoke test。

## 技术说明

入口：

```text
video_action_tool/analysis/gui.py
```

命令行入口：

```text
video_action_tool/analysis/run_analysis.py
```

核心流程：

```text
video -> OpenCV -> YOLOv8-Pose + MediaPipe Face Landmarker -> per_frame -> events
```

模型文件：

```text
video_action_tool/analysis/models/face_landmarker.task
video_action_tool/yolov8n-pose.pt
```

环境：

```text
video_action_tool/environment.yml
video_action_tool/requirements.txt
```

## 验证命令

进入 `video_action_tool` 后：

```bash
python -m py_compile analysis/gui.py analysis/pipeline.py analysis/run_analysis.py analysis/extractors.py analysis/features.py analysis/events.py
python check_environment.py
```

如果用户给出测试视频：

```bash
python -m analysis.run_analysis --video "PATH_TO_VIDEO.mp4" --duration 5 --save-preview
```
