# P8 离线双手运动想象采集程序

## 依赖安装

推荐在独立环境里安装：

```bash
pip install psychopy pyserial numpy
```

如果后续需要直接做 EEG 预处理或 MNE 分析，可再补：

```bash
pip install mne scikit-learn matplotlib
```

## 功能

本目录提供 `P8_MI脑控模拟小车` 的 **实验 4A** 离线采集程序，用于真实被试完成双手运动想象任务，并保存事件与标签供后续离线分析。

当前实现的是：

- 2 类 MI：左手 / 右手
- 标准训练顺序：
  1. 讲解
  2. 真实动作示范（左右手各 5 次，打标）
  3. 纯想象练习（左右手各 5 次，不打标，只用于练习）
  4. 准备度确认
  5. 正式采集（默认左右手各 40 次，分 4 blocks）

## 被试想象口径

- 左手：想象左手正在反复“握拳—松开”
- 右手：想象右手正在反复“握拳—松开”
- 强调：
  - 不要真的动手
  - 不要耸肩、咬牙或做脸部动作
  - 不只是“看到一只手在动”，而是尽量感受动作本身
  - 整场实验内保持同一种想象方式

## 运行方式

### GUI 模式

```bash
python launcher.py
```

### 命令行模式

```bash
python launcher.py --subject Sub_01 --windowed --no-hardware --screen 0
```

### 常用参数

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `--subject` | `Sub_01` | 被试 ID |
| `--port` | `COM5` | Trigger 串口号 |
| `--no-hardware` | False | 无硬件模式 |
| `--screen` | `0` | 屏幕 ID |
| `--windowed` | False | 窗口模式 |
| `--data-dir` | `data` | 数据保存目录 |
| `--baseline-duration` | `2.0` | 基线时长 |
| `--cue-duration` | `1.0` | cue 时长 |
| `--imagery-duration` | `4.0` | 运动想象时长 |
| `--rest-duration` | `2.0` | 休息时长 |
| `--demo-trials-per-class` | `5` | 真实动作示范每类次数 |
| `--practice-trials-per-class` | `5` | 纯想象练习每类次数（不打标） |
| `--formal-trials-per-class` | `40` | 正式采集每类次数 |
| `--formal-blocks` | `4` | 正式采集 block 数 |

## 数据输出

程序结束后会在 `data_dir` 下保存 `.npz` 文件，包含：

- `config_json`：实验配置
- `events`：事件日志
- `training_summary`：训练与正式采集摘要

## 最小验证命令

```bash
python launcher.py --subject Test_MI --windowed --no-hardware --screen 0 --formal-trials-per-class 4 --formal-blocks 2
```

这个命令适合先做无硬件冒烟测试，确认流程、提示文本和保存逻辑正常。
