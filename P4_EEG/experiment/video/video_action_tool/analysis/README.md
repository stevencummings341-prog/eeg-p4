# 视频动作提取工具

本目录提供一个用于 P4 EEG 实验视频的动作提取工具。它把 YOLOv8-Pose 和 MediaPipe Face Landmarker 组合起来，输出：

- `per_frame.parquet` / `per_frame.csv`：逐帧特征，包括人体关键点、Face landmark 派生的 EAR/MAR、头部 yaw/pitch/roll、眨眼 blendshape 分数。
- `events.csv`：动作事件表，包括 blink、head_yaw_motion、head_pitch_motion、mouth_open 等候选事件。
- `preview_overlay.mp4`：可选的叠加预览视频，方便人工检查检测效果。
- `meta.json`：处理参数、检出率、事件数量和输出路径。

原始视频不修改（位于 `experiment/data/video_records/`，data 目录只读）。分析产物默认输出到：

```text
experiment/video/analysis_outputs/<video_stem>/
```

## 推荐使用 GUI

在 Windows 资源管理器中双击：

```text
P4_EEG/experiment/video/video_action_tool/run_gui.bat
```

界面中可以：

- 选择要处理的 `.mp4` 视频。
- 设置起始秒和处理时长，或勾选“处理完整视频”。
- 选择输出目录。
- 勾选是否保存叠加预览视频。
- 查看进度条、运行日志和结果摘要。

如果界面提示 Face 模型缺失，点击“下载/修复模型”。模型文件是 `analysis/models/face_landmarker.task`，已被 `.gitignore` 忽略，不会提交到仓库。

## 命令行用法

快速处理前 60 秒：

```bash
cd P4_EEG/experiment/video/video_action_tool
python -m analysis.run_analysis --video ../../data/video_records/camera_20260518_193936.mp4 --duration 60 --save-preview
```

处理完整视频：

```bash
python -m analysis.run_analysis --video ../../data/video_records/camera_20260518_193936.mp4 --save-preview
```

## 当前解释边界

YOLO-Pose 适合检测头部/身体大动作，MediaPipe Face Landmarker 更适合眨眼、嘴部和头部姿态。吞咽、咬牙这类外观变化很弱的动作只能作为候选事件，后续仍建议结合 EEG marker 和人工抽查校准阈值。
