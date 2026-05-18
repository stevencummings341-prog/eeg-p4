# P4 EEG 降噪实验 — PsychoPy 实验代码

## 依赖安装

```bash
pip install psychopy pyserial numpy
```

> Windows 用户建议在 Anaconda 环境中安装：`conda install -c conda-forge psychopy`

```bash
# 一键启动完整 EEG + Camera 流程（自动开相机，跑 S1→S4，结束后自动关相机）
python eeg-launcher.py
```

> 说明：`eeg-launcher.py` 会自动尊重你在 GUI/命令行里选择的 Session。只有当选择 `all` 时才会跑完整的 S1→S4；如果选择 1/2/3/4，就只跑对应的单个 Session。

## 快速启动

```bash
# GUI 模式 (推荐, 有图形化参数配置对话框)
python launcher.py

# 命令行模式 (跳过 GUI)
python launcher.py --subject Sub_01 --session 1 --windowed --no-hardware
python launcher.py --subject Sub_01 --session 3 --windowed --no-hardware
python launcher.py --subject Sub_01 --session all --windowed --no-hardware
```

```bash
# SSVEP 四宫格单独调试（screen1，四个频率同时闪烁）
python session3_ssvep.py --ssvep-grid-debug --screen 1 --windowed --no-hardware
```

## 文件结构

```
experiment/
├── launcher.py              # 主入口 (GUI + Session 调度)
├── config.py                # 配置数据类 + 图形化启动对话框 + Marker 编码表
├── utils.py                 # 底层工具 (Trigger 串口、键盘队列、文本渲染、音频、数据保存)
├── session1_resting.py      # Session 1: 睁眼/闭眼静息态
├── session2_artifacts.py    # Session 2: 5 类伪迹模板采集
├── session3_oddball.py      # Session 3/4: 视觉 Oddball (P300)
├── session3_ssvep.py        # Session 3/4: SSVEP (6/8.57/10/15 Hz, 4频率)
└── README.md                # 本文件
```

## 各 Session 说明

| 脚本 | 可运行 Session | 时长 | Marker 范围 |
|:---|:---|:---|:---|
| `session1_resting.py` | S1 | ~5 min | 11 / 12 / 21 / 22 |
| `session2_artifacts.py` | S2 | ~10-12 min + 按键等待 | 30 / 31 / 41-48 |
| `session3_oddball.py` | S3 / S4 | ~5.3 min + 验证等待 | 61 / 62 (S3) 或 81 / 82 (S4) |
| `session3_ssvep.py` | S3 / S4 | 最短 ~7.3 min + 自定休息 | 71 / 72 / 73 / 74 (S3) 或 91 / 92 / 93 / 94 (S4) |

> Session 4 通过设置 `natural_mode=True` 自动切换到 S4 的独立 8-bit Marker (不再使用 "+1000" 方案)。
> 所有 Marker 严格 < 128, 与 iRecorder 单字节 Trigger 协议兼容。权威表见 `config.py:MARKER_TABLE`。

## 命令行参数完整列表

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `--subject` | Sub_01 | 被试 ID |
| `--session` | 1 | Session 号 (1/2/3/4/all) |
| `--no-oddball` | False | 跳过 Oddball 任务 |
| `--no-ssvep` | False | 跳过 SSVEP 任务 |
| `--port` | COM3 | Trigger 串口号 |
| `--no-hardware` | False | 无硬件模式 (不发送 Trigger) |
| `--screen` | 1 | 屏幕 ID，默认外接拓展屏；单屏测试可设为 0。**当 `--screen 1` 时会自动强制全屏。** |
| `--windowed` | False | 窗口模式 (默认全屏) |
| `--data-dir` | data | 数据保存目录 |
| `--forced-blink` | 0.3 | Session 4 强制眨眼比例 (0-1) |

## 界面说明

- **全部提示文本为中文**
- **空格键 = 确认 / 前进**
- **ESC = 任何时候终止实验**（触发 SystemExit，自动清理所有资源）
- **T/F 键 = 仅 AAD 类型实验使用**，当前 P4 范式不使用

## 数据输出

每个 Session 结束时自动保存 `.npz` 文件至 `cfg.data_dir`：

```
data/
├── P4_S1_Sub_01_20260503_140000_session1.npz
├── P4_S2_Sub_01_20260503_141500_session2.npz
├── P4_S3_Sub_01_20260503_143000_session3_oddball.npz
├── P4_S3_Sub_01_20260503_144000_session3_ssvep.npz
├── P4_S4_Sub_01_20260503_150000_session4_oddball.npz
└── P4_S4_Sub_01_20260503_151000_session4_ssvep.npz
```

每个文件包含：
- `config_json`: 实验配置 (JSON 字符串)
- `events`: 试次列表 (type, marker, timing)
- 任务特有字段 (如 Oddball 的 `correct_red_count`, SSVEP 的 `frequency_hz`)

## 关键设计特性 (对齐 MATLAB 原始代码的健壮性)

1. **try-catch-finally 资源清理** — 任何异常退出都会自动释放串口、关闭窗口、恢复键盘
2. **KbQueue 等价物** — 使用 PsychoPy `keyboard.Keyboard` 代替 `event.waitKeys`，不丢键
3. **ESC 全局终止** — 任何时候按 ESC 都会安全退出，不需等待当前 Trial 完成
4. **无硬件降级** — 串口连接失败时自动切换到无硬件模式继续运行
5. **帧计数精确闪烁** — SSVEP 用帧计数而非 `core.wait()` 控制闪烁频率，正式采集需确认外接屏为 60Hz
6. **自定步长休息** — SSVEP 每 trial 闪烁 4 秒后进入休息界面，准备好后按空格进入下一 trial

## 修改后预实验参数

- **S1 静息态**：睁眼开始/结束、闭眼开始/结束均播放提示音，Marker 仍为 11/12/21/22。
- **S2 伪迹模板**：单次眨眼 20、连续眨眼 10、水平眼动 30、咬牙 30、吞咽 10、向左摇头 10、向右摇头 10、上下点头 10，共 130 trials；水平眼动为红球向左/向右移动各 15 次；摇头/点头为中等幅度。
- **Oddball**：每次 200 trials，标准刺激 150、靶刺激 50。
- **SSVEP**：4 个频率各 20 trials，共 80 trials；正式版为四宫格同时闪烁，每 trial 先提示目标位置，方块标签只显示位置，闪烁 4 秒后休息，按空格进入下一 trial。

## 单次完整流程时间估计

| 阶段 | 程序时间 | 有效数据时间 |
|:---|:---|:---|
| S1 静息 | ~4.5 min | 4.0 min |
| S2 伪迹 | ~8.3 min + 准备按键等待 | ~1.7 min 伪迹动作窗 |
| S3 Oddball | ~5.3 min + 验证等待 | ~5.3 min trial 窗口 |
| S3 任务间基线 | 1.0 min | 1.0 min |
| S3 SSVEP | 最短 ~7.3 min + 自定休息 | ~5.3 min 闪烁窗 |
| S4 Oddball | ~5.3 min + 验证等待 | ~5.3 min trial 窗口 |
| S4 SSVEP | 最短 ~7.3 min + 自定休息 | ~5.3 min 闪烁窗 |

全流程最短程序时间约 **39 min**；若两次 SSVEP 每 trial 后平均休息 3 秒，约 **47 min**；有效数据时间约 **28 min**。如保留 S2 后 5 分钟休息和 S3/S4 之间 10 分钟长休息，现场运行约 **62 min**，不含戴帽、打膏和阻抗调整。

## 与 MATLAB 代码的对照关系

| MATLAB 功能                   | Python 实现                                   |
| :-------------------------- | :------------------------------------------ |
| `inputdlg`                  | `config.ExperimentLauncher` (tkinter GUI)   |
| `serialport`                | `utils.TriggerSender` (pyserial)            |
| `KbQueueCreate/Check`       | `utils.KeyboardManager` (psychopy.keyboard) |
| `Screen('Flip')`            | `win.flip()`                                |
| `PsychPortAudio`            | `psychopy.sound.Sound`                      |
| `try-catch-finally cleanup` | `utils.cleanup_all()` + `atexit`            |
| `ListenChar`                | PsychoPy 默认不拦截，无需等价物                        |
|                             |                                             |

## 运行前检查清单

- [ ] 确认 PsychoPy + pyserial 已安装
- [ ] 确认刺激呈现在外接拓展屏 (`--screen 1`)，单屏测试时改用 `--screen 0`
- [ ] 使用 `screen 1` 时默认会自动进入全屏，不需要再手动控制窗口模式
- [ ] 确认刺激屏刷新率为 60Hz (直接影响 SSVEP 实际频率)
- [ ] 确认 Trigger 串口号和波特率
- [ ] 确认数据保存目录有写入权限，真实 `data/` 目录不要加入 git
- [ ] 先以 `--windowed --no-hardware --screen 0` 模式测试一遍全流程
