# EEG_Project — 项目总览

本仓库是 **P4: EEG 降噪与任务特征保真** 的工作目录，包含：

- 一套 4-Session 的 EEG 离线采集程序（PsychoPy + iRecorder Trigger）。
- 与采集程序同步的相机录制 + 时间戳对齐工具。
- 基于 YOLOv8-Pose + MediaPipe Face Landmarker 的视频动作提取与事件检测工具。
- 一个下游在线 Demo：脑控小车（P4 Session 4 离线 MI → 在线分类雏形）。
- 第三方 EEG 采集软件与 SDK（仅本地保留，不参与版本管理）。

> 项目级长期规则、Marker 表、数据保护策略请优先看 [`CLAUDE.md`](CLAUDE.md)。

## 目录结构

```text
EEG_Project/
├── README.md                           本文件
├── CLAUDE.md                           项目级规则（必读）
├── environment.yml / requirements.txt  顶层环境（PsychoPy / numpy 等）
├── .gitignore                          数据与三方组件不入库
│
├── eConScan_AiO/                       三方 EEG 采集软件（gitignore，机器本地）
├── iRecorder W32产品光盘/              iRecorder 设备 SDK / 驱动（gitignore，机器本地）
│
└── P4_EEG降噪与任务特征保真/           P4 主体（见其下 README.md）
    ├── README.md
    ├── dataset/                        预留：清洗后可发布的数据集导出位置
    ├── experiment/                     S1–S4 采集 + 相机录制 + 视频动作提取
    └── p8_mi_car/                      下游 Demo：在线双手 MI 脑控小车
```

## 顶层目录用途

| 路径 | 角色 | 是否入库 |
|:---|:---|:---|
| `P4_EEG降噪与任务特征保真/` | 全部自研代码、采集脚本、分析工具、下游 Demo | 是 |
| `eConScan_AiO/` | 三方采集软件（图形化记录 EEG） | 否（gitignore） |
| `iRecorder W32产品光盘/` | iRecorder 32 通道设备 SDK / 驱动 / 文档 | 否（gitignore） |
| `**/data/`, `**/*.bdf` 等 | 真实采集数据 | **永不入库，永不修改** |

## 快速入口

| 你想做 | 入口 |
|:---|:---|
| 跑一次 4-Session 采集 | `cd P4_EEG降噪与任务特征保真/experiment && python launcher.py` |
| 仅跑离线双手 MI（在线小车前置采集） | `cd P4_EEG降噪与任务特征保真/p8_mi_car/experiment && python launcher.py` |
| 对录制的相机视频跑 YOLO+面部动作分析 | 双击 `P4_EEG降噪与任务特征保真/experiment/video/video_action_tool/run_gui.bat` |
| 配置 / 修复视频工具环境 | `P4_EEG降噪与任务特征保真/experiment/video/` 下的 `install_env_conda.bat` 等 |

## 设计原则速记

1. **采集 SOP 与代码同源**：实验 Marker、Session 时序的权威来源在 `experiment/config.py:MARKER_TABLE`，文档侧只做解释。
2. **代码改动小步、可回滚**：禁止在未授权情况下重命名 `config.py / utils.py / session*.py / video/` 等被 import 的模块。
3. **数据零侵入**：任何 `data/` / `eeg/` / `*.bdf` / 真实被试 `*.mp4` 都视为只读。生成测试数据请走 `scratch/`、`tmp/`。
4. **版本管理保守**：只在用户明确说"提交"时才 commit；不使用 `git add .`。
