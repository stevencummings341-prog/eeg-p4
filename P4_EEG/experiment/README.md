# P4 EEG 降噪实验 — PsychoPy 实验代码

> **两套实验方案合并入口**：本目录现在同时支持 **运动想象 (MI)** 和 **情绪识别 (Emotion)** 两套方案。
> S1/S2/S3 完全一致，Session 4 根据 `cfg.scheme` 切换：
> - `scheme="motor_imagery"` → `sessions/session4_mi.py`（默认）
> - `scheme="emotion"`       → `sessions/session4_emotion.py`
>
> GUI 启动时顶部有 **实验方案 (Scheme)** 单选按钮；命令行用 `--scheme {motor_imagery,emotion}` 指定。
> 数据落点自动分流到 `<data_dir>/motor_imagery/...` 或 `<data_dir>/emotion/...`，两边目录结构完全一致。

## 依赖安装

```bash
pip install psychopy pyserial numpy
```

> Windows 用户建议在 Anaconda 环境中安装：`conda install -c conda-forge psychopy`

```bash
# 主入口：启动 EEG 实验；默认自动开启相机录制
python launcher.py
```

> 说明：`launcher.py` 统一负责 EEG + Camera 启动流程。相机默认启用；如需关闭，使用 `--no-camera`。

## 快速启动

```bash
# GUI 模式 (推荐, 有图形化参数配置对话框；默认自动开启相机)
python launcher.py

# 命令行模式 (跳过 GUI)
#   --session 既支持单值 1/2/3/4/all，也支持逗号列表 (例如 3,4 / 1,3,4)
python launcher.py --subject Sub_01 --session 1 --windowed --no-hardware
python launcher.py --subject Sub_01 --session 3,4 --windowed --no-hardware

# 运动想象方案 (默认)
python launcher.py --scheme motor_imagery --subject Sub_01 --session 4 --windowed --no-hardware --screen 0
python launcher.py --scheme motor_imagery --subject Sub_01 --session all --windowed --no-hardware --screen 0

# 情绪识别方案
python launcher.py --scheme emotion --subject Sub_01 --session 4 --windowed --no-hardware --screen 0
python launcher.py --scheme emotion --subject Sub_01 --session all --windowed --no-hardware --screen 0

# 任意子集串联（两个方案都支持）
python launcher.py --scheme emotion --subject Sub_01 --session 3,4 --windowed --no-hardware
python launcher.py --scheme motor_imagery --subject Sub_01 --session 1,2,4 --windowed --no-hardware

# 如需禁用相机录制
python launcher.py --subject Sub_01 --session 4 --windowed --no-hardware --screen 0 --no-camera
```

```bash
# SSVEP 四宫格单独调试（screen1，四个频率同时闪烁）
python -m sessions.session3_ssvep --ssvep-grid-debug --screen 1 --windowed --no-hardware
```

## 文件结构

```text
experiment/
├── launcher.py              # 主入口 (GUI + Session 调度 + 相机启停)
├── config.py                # 配置数据类 + 图形化启动对话框 + Marker 编码表
├── utils.py                 # 底层工具 (Trigger 串口、键盘队列、文本渲染、音频、数据保存)
│
├── sessions/                # 4 个 Session 的实验脚本
│   ├── __init__.py
│   ├── session1_resting.py      # S1: 睁眼/闭眼静息态        (两套方案共用)
│   ├── session2_artifacts.py    # S2: 8 类伪迹模板采集        (两套方案共用)
│   ├── session3_oddball.py      # S3.1: 视觉 Oddball (P300)   (两套方案共用)
│   ├── session3_ssvep.py        # S3.2: SSVEP (4 频率)        (两套方案共用)
│   ├── session4_mi.py           # S4: 离线双手运动想象         (scheme="motor_imagery")
│   └── session4_emotion.py      # S4: 情绪识别 (音视频刺激)    (scheme="emotion")
│
├── stimuli/                 # 实验刺激素材
│   ├── stimuli_config.json      # 情绪方案 S4 的视频清单（必需）
│   ├── negative/ neutral/ positive/  # 视频文件（gitignore，永不入库）
│   └── README.md
│
├── data/                    # 真实采集数据（gitignore，永不修改）
│   ├── motor_imagery/           # 运动想象方案的数据
│   │   ├── eeg-bdf/             #   iRecorder 录制的 *.bdf
│   │   ├── eeg-npz/             #   PsychoPy 每个 Session 的 *.npz
│   │   └── video_records/       #   FFmpeg 相机录制 + 时间戳
│   └── emotion/                 # 情绪识别方案的数据 (结构同 motor_imagery)
│       ├── eeg-bdf/
│       ├── eeg-npz/
│       └── video_records/
│
├── video/                   # 相机录制 + 视频动作提取工具
│   ├── camera_recorder_controlled.py    # 被 launcher.py import
│   ├── analysis_outputs/                # 视频动作分析产物
│   └── video_action_tool/               # YOLOv8-Pose + MediaPipe 子项目
│
├── stimuli/                 # 实验刺激素材（情绪视频等）
├── legacy/                  # MATLAB 旧版本（仅作历史参考）
└── README.md                # 本文件
```

## 各 Session 说明

| 脚本 | 可运行 Session | 时长 | Marker 范围 |
|:---|:---|:---|:---|
| `sessions/session1_resting.py` | S1 | ~5 min | 11 / 12 / 21 / 22 |
| `sessions/session2_artifacts.py` | S2 | ~10-12 min + 按键等待 | 30 / 31 / 41-48 |
| `sessions/session3_oddball.py` | S3.1 | ~5.3 min + 验证等待 | 61 / 62 / 63 |
| `sessions/session3_ssvep.py` | S3.2 | 最短 ~7.3 min + 自定休息 | 71 / 72 / 73 / 74 |
| `sessions/session4_mi.py` | S4 (scheme="motor_imagery") | ~12-18 min | 81-89 |
| `sessions/session4_emotion.py` | S4 (scheme="emotion") | ~3-5 min（18 trials） | 100-106 |

> Session 4 已合并 **两套方案**：运动想象 (MI) 与 情绪识别 (Emotion)，通过 `cfg.scheme` 切换。
> 所有 Marker 严格 < 128, 与 iRecorder 单字节 Trigger 协议兼容。权威表见 `config.py:MARKER_TABLE`。

## Session 4（离线双手 MI）流程

当前 Session 4 已按"人性化"思路简化，与 S1/S2/S3 的两段式结构对齐：

1. 讲解 + 一行练习引导文本，停留 30 秒（按空格可提前进入正式实验）。
2. 正式采集（默认左右手各 40 次，分 4 blocks）—— **只有此阶段才开始打标**。

> 之前的"真实动作示范 / 纯想象练习 / 准备度确认"三阶段已合并为单一引导窗口。
> 这样既保证被试在心里复习了一遍想象方式，也避免无意义的反复按键和发标。

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
| `--scheme` | motor_imagery | 实验方案：`motor_imagery` 或 `emotion`，影响 S4 走哪一套流程，以及数据落点子目录 |
| `--subject` | Sub_01 | 被试 ID |
| `--session` | 1 | Session 选择：单值 (1/2/3/4)、`all`、或逗号列表（如 `3,4` / `1,3,4`），多 Session 之间会按 `--session-order` 串联 |
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
| `--emotion-fixation-duration` | 2.0 | 情绪方案：刺激前注视十字时长 (s) |
| `--emotion-rest-duration` | 2.0 | 情绪方案：刺激后休息时长 (s) |
| `--emotion-seed` | 42 | 情绪方案：视频顺序随机化种子 |
| `--natural-mode` | False | Session 3 自然态 (历史遗留，对当前 Marker 表无影响) |
| `--forced-blink-ratio` | 0.0 | Session 3 Oddball 自然态强制眨眼比例 |
| `--quick-test` | False | 全流程冒烟测试：所有 Session 用极短时长 / 极少 trial 快速过完，便于验证 GUI / Marker / 保存逻辑 |

## 界面说明

- **全部提示文本为中文**
- **空格键 = 确认 / 前进**
- **ESC = 任何时候终止实验**（触发 `SystemExit`，自动清理所有资源）
- **Session 4 练习阶段不打标，只用于熟悉想象方式**

## 数据输出

每个 Session 结束时自动保存 `.npz` 到 `<cfg.data_dir>/<scheme>/eeg-npz/`；EEG 主机的 iRecorder 软件应配置成把 `.bdf` 落到 `<cfg.data_dir>/<scheme>/eeg-bdf/`（路径与本目录约定一致即可）；如果启用相机录制，视频、时间戳、metadata 和 FFmpeg 日志默认保存到 `<cfg.data_dir>/<scheme>/video_records`（可用 `--camera-output-dir` 覆盖）。

两套方案的输出结构**完全一致**，只是顶层多了一个 `motor_imagery/` 或 `emotion/` 分流目录：

```text
data/
├── motor_imagery/                                    # scheme="motor_imagery"
│   ├── eeg-bdf/                                          # iRecorder 连续录制
│   │   ├── 20260503_<subj>_<ts>.bdf
│   │   └── ...
│   ├── eeg-npz/                                          # PsychoPy 每个 Session 的元数据
│   │   ├── P4_S1_Sub_01_20260503_140000_session1.npz
│   │   ├── P4_S2_Sub_01_20260503_141500_session2.npz
│   │   ├── P4_S3_Sub_01_20260503_143000_session3_oddball.npz
│   │   ├── P4_S3_Sub_01_20260503_144000_session3_ssvep.npz
│   │   └── P4_S4_Sub_01_20260503_150000_session4_mi.npz
│   └── video_records/                                    # FFmpeg 相机录制
│       ├── camera_20260503_135950.mp4
│       ├── camera_20260503_135950_timestamps.csv
│       ├── camera_20260503_135950_metadata.json
│       └── camera_20260503_135950_ffmpeg.log
└── emotion/                                          # scheme="emotion" (结构同 motor_imagery)
    ├── eeg-bdf/
    ├── eeg-npz/
    │   └── P4_S4_Sub_01_20260503_150000_session4_emotion.npz
    └── video_records/
```

> 落点策略由 `utils.save_data` 和 `launcher.get_scheme_data_dir/get_camera_output_dir` 统一控制。
> 后处理 pipeline 可以针对每个方案各自指定 `--data-dir`（例如 `--data-dir data/motor_imagery`）。

> BDF 与 NPZ 通过 Marker 在时间轴上对齐，后处理 pipeline (`processing/`) 会扫描 `eeg-bdf/` + `eeg-npz/` 并自动配对每个 Session。

Session 4 `.npz` 至少包含：

- `config_json`（含 `scheme` 字段，便于下游识别）
- `events`
- MI 方案：`formal_sequences`、`training_summary`
- 情绪方案：`task="emotion_recognition"`、`total_trials`、`successful_trials`、`category_counts`、`pre_stimulus_fixation_s`、`post_stimulus_rest_s`

## 关键设计特性

1. **try-catch-finally 资源清理** — 任何异常退出都会自动释放串口、关闭窗口、恢复键盘
2. **KbQueue 等价物** — 使用 PsychoPy `keyboard.Keyboard` 代替 `event.waitKeys`，不丢键
3. **ESC 全局终止** — 任何时候按 ESC 都会安全退出，不需等待当前 Trial 完成
4. **无硬件降级** — 串口连接失败时自动切换到无硬件模式继续运行
5. **练习与正式采集分离** — Session 4 练习窗口完全不打标，进入正式阶段才发送 Trigger
6. **快速冒烟测试** — `--quick-test` 让 4 个 Session 在数十秒内跑完，验证整套链路是否还通

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

### 全流程冒烟测试（推荐，验证 4 个 Session 是否能跑通）

```bash
# 运动想象方案
python launcher.py --scheme motor_imagery --subject Test --session all --quick-test --windowed --no-hardware --no-camera --screen 0

# 情绪识别方案（需要 stimuli/ 下有真实视频；缺失时单 trial 会跳过但流程不中断）
python launcher.py --scheme emotion --subject Test --session all --quick-test --windowed --no-hardware --no-camera --screen 0
```

- `--quick-test` 让 S1-S4 都用极短时长 / 极少 trial 快速过完：
  - S1: 睁眼 5s + 闭眼 5s + 过渡 2s
  - S2: 8 类伪迹 × 每类 2 trials，时长全部 ≤ 0.5s
  - S3 Oddball: 8 trials；SSVEP: 4 频率 × 1 trial × 1s 闪烁
  - S3 Oddball↔SSVEP 之间的任务间基线缩短为 3s
  - S4: 4 trials/class × 2 blocks，练习引导窗 5s
- 跑通这一版本就说明正式版（不带 `--quick-test`）的提示文本、Marker 逻辑、数据保存结构都正常。
- 中途任何时候按 ESC 都能安全终止；按空格键推进每一段。

### Session 4 单独测试

```bash
# 运动想象
python launcher.py --scheme motor_imagery --subject Test_MI --session 4 --windowed --no-hardware --screen 0 --quick-test

# 情绪识别
python launcher.py --scheme emotion --subject Test_Emo --session 4 --windowed --no-hardware --screen 0 --quick-test
```
