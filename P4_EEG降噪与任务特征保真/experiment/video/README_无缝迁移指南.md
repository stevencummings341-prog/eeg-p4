# P4 视频动作提取工具迁移包

这是一份可以拷贝到实验室电脑的独立迁移包，用于运行 P4 EEG 实验视频动作提取 GUI。

## 1. 这个包里有什么

```text
video_action_tool_migration_package/
├── README_无缝迁移指南.md
├── CLAUDE_CODE_HANDOFF.md
├── install_env_conda.bat
├── install_env_pip.bat
├── check_environment.bat
├── video_action_tool/
│   ├── run_gui.bat
│   ├── run_cli_60s_example.bat
│   ├── check_environment.py
│   ├── environment.yml
│   ├── requirements.txt
│   ├── yolov8n-pose.pt
│   └── analysis/
│       ├── gui.py
│       ├── pipeline.py
│       ├── extractors.py
│       ├── features.py
│       ├── events.py
│       ├── run_analysis.py
│       ├── README.md
│       ├── 视频动作提取流程报告.md
│       └── models/
│           └── face_landmarker.task
```

不包含内容：

- 原始实验视频。
- 处理结果。
- EEG 数据。
- 任何 `data/` 目录。

## 2. 推荐迁移方式

把整个 `video_action_tool_migration_package` 文件夹拷贝到实验室电脑，例如：

```text
D:\video_action_tool_migration_package
```

推荐放到英文路径，避免部分第三方库在中文路径下出问题。

## 3. 配置环境：Conda 方式，推荐

实验室电脑需要先安装 Anaconda 或 Miniconda。

双击：

```text
install_env_conda.bat
```

它会执行：

```bash
conda env create -f video_action_tool/environment.yml
```

创建环境名：

```text
eeg-p4
```

如果电脑上已经有 `eeg-p4` 环境，可以进入 `video_action_tool` 后运行：

```bash
conda env update -n eeg-p4 -f environment.yml
```

## 4. 配置环境：pip 方式，备选

如果不用 conda，可以双击：

```text
install_env_pip.bat
```

它会创建本地虚拟环境：

```text
video_action_tool/.venv
```

然后安装 `requirements.txt`。

注意：PsychoPy 等完整 EEG 实验依赖更适合 conda。这个 pip 方式主要用于视频动作提取工具。

## 5. 检查环境

双击：

```text
check_environment.bat
```

如果看到类似下面的输出，说明环境基本可用：

```text
Python: ...
cv2: ...
torch: ...
ultralytics: ...
mediapipe: ...
pyarrow: ...
Face model: OK
YOLO weight: OK
```

## 6. 启动 GUI

进入：

```text
video_action_tool/
```

双击：

```text
run_gui.bat
```

界面里可以：

- 选择要处理的视频文件。
- 设置起始秒。
- 设置处理时长，或勾选处理完整视频。
- 选择输出目录。
- 勾选是否保存叠加预览视频。
- 查看进度条和结果摘要。

## 7. 输出在哪里

如果你不手动修改输出目录，默认输出到所选视频旁边：

```text
<视频所在目录>/analysis_outputs/<视频文件名>/
```

主要输出：

| 文件 | 说明 |
| --- | --- |
| `per_frame.parquet` | 逐帧特征表，推荐后续程序读取 |
| `per_frame.csv` | 逐帧特征表，方便 Excel/人工查看 |
| `events.csv` | 动作事件表 |
| `meta.json` | 参数、检出率、输出路径 |
| `preview_overlay.mp4` | 带关键点叠加的检查视频 |

## 8. 处理视频的建议

第一次在实验室电脑上运行时，建议：

1. 先选一个视频。
2. 起始秒填 `0`。
3. 处理时长填 `5`。
4. 勾选保存预览视频。
5. 处理完成后打开 `preview_overlay.mp4` 检查关键点是否正常。
6. 再处理 `60` 秒或完整视频。

## 9. 如果要让另一台电脑上的 Claude Code 无缝接手

把整个迁移包交给 Claude Code，并告诉它：

```text
请先阅读 CLAUDE_CODE_HANDOFF.md，然后帮我在这台电脑配置并运行 P4 视频动作提取 GUI。
```

Claude Code 应该先检查环境，再运行 `check_environment.bat`，最后启动 `video_action_tool/run_gui.bat`。

## 10. 常见问题

### Q1：为什么要放英文路径？

MediaPipe 的底层 C++ 在 Windows 上曾经出现中文路径读取模型失败的问题。当前代码用 in-memory buffer 规避了 Face 模型路径问题，但仍建议把迁移包放在英文路径，减少 ffmpeg/OpenCV/模型库兼容风险。

### Q2：没有网络能不能用？

可以。包里已经包含：

- `analysis/models/face_landmarker.task`
- `yolov8n-pose.pt`

这两个模型文件足够离线运行。

### Q3：可以识别表情吗？

可以识别基础面部动作，例如眨眼、眯眼、张口、皱眉等 blendshape。它不是严格的情绪分类器，不建议直接输出“开心/生气/悲伤”作为 EEG 实验真值。

### Q4：完整视频很慢怎么办？

CPU 下大约 20-25 fps。先处理 5 秒测试，再处理 60 秒抽查，最后再跑完整视频。取消预览视频可略微加速。
