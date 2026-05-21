# P4 EEG 降噪实验 — PsychoPy 实验代码

## 依赖安装

```bash
pip install psychopy pyserial numpy
```

> Windows 用户建议在 Anaconda 环境中安装：`conda install -c conda-forge psychopy`

```bash
# 主入口：启动 EEG 实验；默认自动开启相机录制
python launcher.py

# 兼容旧命令：内部会转调 launcher.py
python eeg-launcher.py
```

> 说明：现在 `launcher.py` 已统一负责 EEG + Camera 启动流程。相机默认启用；如需关闭，可使用 `--no-camera`。`eeg-launcher.py` 仅保留为兼容包装器。

## 快速启动

```bash
# GUI 模式 (推荐, 有图形化参数配置对话框；默认自动开启相机)
python launcher.py

# 命令行模式 (跳过 GUI)
python launcher.py --subject Sub_01 --session 1 --windowed --no-hardware
python launcher.py --subject Sub_01 --session 3 --windowed --no-hardware
python launcher.py --subject Sub_01 --session 4 --windowed --no-hardware --screen 0
python launcher.py --subject Sub_01 --session all --windowed --no-hardware --screen 0

# 如需禁用相机录制
python launcher.py --subject Sub_01 --session 4 --windowed --no-hardware --screen 0 --no-camera
```

```bash
# SSVEP 四宫格单独调试（screen1，四个频率同时闪烁）
python session3_ssvep.py --ssvep-grid-debug --screen 1 --windowed --no-hardware
```

## 文件结构

```text
experiment/
├── launcher.py              # 主入口 (GUI + Session 调度)
├── config.py                # 配置数据类 + 图形化启动对话框 + Marker 编码表
├── utils.py                 # 底层工具 (Trigger 串口、键盘队列、文本渲染、音频、数据保存)
├── session1_resting.py      # Session 1: 睁眼/闭眼静息态
├── session2_artifacts.py    # Session 2: 5 类伪迹模板采集
├── session3_oddball.py      # Session 3: 视觉 Oddball (P300)
├── session3_ssvep.py        # Session 3: SSVEP (6/8.57/10/15 Hz, 4频率)
├── session4_mi.py           # Session 4: 离线双手运动想象采集
└── README.md                # 本文件
```

## 各 Session 说明

| 脚本 | 可运行 Session | 时长 | Marker 范围 |
|:---|:---|:---|:---|
| `session1_resting.py` | S1 | ~5 min | 11 / 12 / 21 / 22 |
| `session2_artifacts.py` | S2 | ~10-12 min + 按键等待 | 30 / 31 / 41-48 |
| `session3_oddball.py` | S3 | ~5.3 min + 验证等待 | 61 / 62 |
| `session3_ssvep.py` | S3 | 最短 ~7.3 min + 自定休息 | 71 / 72 / 73 / 74 |
| `session4_mi.py` | S4 | ~12-18 min | 81-89 |

> Session 4 现在是离线双手运动想象采集，不再复用自然态 Oddball / SSVEP。
> 所有 Marker 严格 < 128, 与 iRecorder 单字节 Trigger 协议兼容。权威表见 `config.py:MARKER_TABLE`。

## Session 4（离线双手 MI）流程

当前实现的是：

1. 讲解
2. 真实动作示范（左右手各 5 次，打标）
3. 纯想象练习（左右手各 5 次，不打标，只用于练习）
4. 准备度确认
5. 正式采集（默认左右手各 40 次，分 4 blocks）

被试想象口径：

- 左手：想象左手正在反复“握拳—松开”
- 右手：想象右手正在反复“握拳—松开”
- 强调：
  - 不要真的动手
  - 不要耸肩、咬牙或做脸部动作
  - 不只是“看到一只手在动”，而是尽量感受动作本身
  - 整场实验内保持同一种想象方式

## 命令行参数完整列表

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `--subject` | Sub_01 | 被试 ID |
| `--session` | 1 | Session 号 (1/2/3/4/all) |
| `--no-oddball` | False | 跳过 Session 3 Oddball |
| `--no-ssvep` | False | 跳过 Session 3 SSVEP |
| `--port` | COM5 | Trigger 串口号 |
| `--no-hardware` | False | 无硬件模式 (不发送 Trigger) |
| `--screen` | 1 | 屏幕 ID，默认外接拓展屏；单屏测试可设为 0。`--screen 1` 时会自动强制全屏。 |
| `--windowed` | False | 窗口模式 (默认全屏) |
| `--data-dir` | data | 数据保存目录 |
| `--no-camera` | False | 禁用相机自动录制 |
| `--camera-device` | FF-Camera | FFmpeg / dshow 相机设备名 |
| `--camera-output-dir` | 空 | 相机录制目录，默认使用 `<data_dir>/video_records` |
| `--mi-baseline-duration` | 2.0 | Session 4 基线时长 |
| `--mi-cue-duration` | 1.0 | Session 4 cue 时长 |
| `--mi-imagery-duration` | 4.0 | Session 4 运动想象时长 |
| `--mi-rest-duration` | 2.0 | Session 4 休息时长 |
| `--mi-demo-trials-per-class` | 5 | Session 4 真实动作示范每类次数 |
| `--mi-practice-trials-per-class` | 5 | Session 4 纯想象练习每类次数（不打标） |
| `--mi-formal-trials-per-class` | 40 | Session 4 正式采集每类次数 |
| `--mi-formal-blocks` | 4 | Session 4 正式采集 block 数 |
| `--mi-seed` | 42 | Session 4 随机种子 |

## 界面说明

- **全部提示文本为中文**
- **空格键 = 确认 / 前进**
- **ESC = 任何时候终止实验**（触发 `SystemExit`，自动清理所有资源）
- **Session 4 练习阶段不打标，只用于熟悉想象方式**

## 数据输出

每个 Session 结束时自动保存 `.npz` 文件至 `cfg.data_dir`；如果启用相机录制，视频、时间戳、metadata 和 FFmpeg 日志默认保存到 `<cfg.data_dir>/video_records`（可用 `--camera-output-dir` 覆盖）：

```text
data/
├── P4_S1_Sub_01_20260503_140000_session1.npz
├── P4_S2_Sub_01_20260503_141500_session2.npz
├── P4_S3_Sub_01_20260503_143000_session3_oddball.npz
├── P4_S3_Sub_01_20260503_144000_session3_ssvep.npz
└── P4_S4_Sub_01_20260503_150000_session4_mi.npz

video_records/
├── camera_20260503_135950.mp4
├── camera_20260503_135950_timestamps.csv
├── camera_20260503_135950_metadata.json
└── camera_20260503_135950_ffmpeg.log
```

Session 4 `.npz` 至少包含：

- `config_json`
- `events`
- `formal_sequences`
- `training_summary`

## 关键设计特性

1. **try-catch-finally 资源清理** — 任何异常退出都会自动释放串口、关闭窗口、恢复键盘
2. **KbQueue 等价物** — 使用 PsychoPy `keyboard.Keyboard` 代替 `event.waitKeys`，不丢键
3. **ESC 全局终止** — 任何时候按 ESC 都会安全退出，不需等待当前 Trial 完成
4. **无硬件降级** — 串口连接失败时自动切换到无硬件模式继续运行
5. **训练与正式采集分离** — 真实动作示范打标、纯想象练习不打标、正式采集完整打标

## 单次完整流程时间估计

| 阶段 | 程序时间 | 有效数据时间 |
|:---|:---|:---|
| S1 静息 | ~4.5 min | 4.0 min |
| S2 伪迹 | ~8.3 min + 准备按键等待 | ~1.7 min 伪迹动作窗 |
| S3 Oddball | ~5.3 min + 验证等待 | ~5.3 min trial 窗口 |
| S3 任务间基线 | 1.0 min | 1.0 min |
| S3 SSVEP | 最短 ~7.3 min + 自定休息 | ~5.3 min 闪烁窗 |
| S4 双手 MI | ~12-18 min | 正式 MI trial 窗口 |

## 运行前检查清单

- [ ] 确认 PsychoPy + pyserial 已安装
- [ ] 确认刺激呈现在外接拓展屏 (`--screen 1`)，单屏测试时改用 `--screen 0`
- [ ] 确认 Trigger 串口号和波特率（当前默认 `COM5` / 115200）
- [ ] 确认 `FF-Camera` 可用；默认按 1920×1080 @ 30fps 录制，文件保存到 `<data_dir>/video_records`
- [ ] 先以 `--windowed --no-hardware --screen 0` 模式测试一遍 Session 4
- [ ] 正式采集前确认被试已经通过“真实动作示范 → 纯想象练习 → 准备度确认”

## 推荐测试命令

```bash
python launcher.py --subject Test_MI --session 4 --windowed --no-hardware --screen 0 --mi-formal-trials-per-class 4 --mi-formal-blocks 2
```

这个命令适合先做无硬件冒烟测试，确认 Session 4 的提示文本、marker 逻辑和保存结构正常。
