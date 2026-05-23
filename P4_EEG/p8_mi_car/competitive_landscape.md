---
title: "P8 竞品与现有项目调研：MI 脑控车辆/小车"
tags:
  - "#pipeline/2_paradigm"
  - "#modality/eeg"
  - "#method/time_series"
created: 2026-05-19
status: "active"
---

# 竞品与现有项目调研：MI 脑控车辆/小车

---

## 1. GitHub 开源项目

### 1.1 物理小车方案（全部项目）

| 项目 | 设备 | MI 类数 | 控制对象 | 准确率 | 技术栈 | 链接 |
|:---|:---|:---|:---|:---|:---|:---|
| Audrey-Li/EEG-Brainwave-Controlled-RaceCar | Emotiv EPOC+ 14ch | 4 类 | F1TENTH 赛车 | 离线 98%，实时 26→50% | CyKit + OpenViBE + NN | [GitHub](https://github.com/Audrey-Li-CPEN/EEG-Brainwave-Controlled-RaceCar) |
| SSShawnJ/Brainwave_Controller | Muse 2014 | 4 类 (停/左/右/前) | 实体小车 | 离线 98.3% | SVM (RBF) + Arduino | [GitHub](https://github.com/SSShawnJ/Capstone-Brainwave_Controller) |
| AjayKrP/MindControlledCar | NeuroSky MindWave | 2 类 (左/右) | 网页+物理 | -- | DNN + Python | [GitHub](https://github.com/AjayKrP/MindControlledCar) |
| whydanishwhy/BrainControlCar | EEG + ESP32 | -- | 物理小车 | -- | -- | [GitHub](https://github.com/whydanishwhy/BrainControlCar) |
| ecuadior/EEG-Car | -- | -- | 物理小车 | -- | C++ | [GitHub](https://github.com/ecuadior/EEG-Car) |
| bandidhanush/Car-Controlled-by-Brain-Waves- | 模拟数据 | -- | 物理小车 | -- | TypeScript | [GitHub](https://github.com/bandidhanush/Car-Controlled-by-Brain-Waves-) |
| varunxcode/eeg | -- | -- | RC 车/无人机 | -- | Jupyter | [GitHub](https://github.com/varunxcode/eeg) |
| Azad-1123/CerebralCommandAutomation | -- | -- | 物理系统 | -- | Python | [GitHub](https://github.com/Azad-1123/CerebralCommandAutomation-EEG-) |

### 1.2 关键发现

- **没有任何项目做纯电脑端模拟小车**——全部需要 Arduino/ESP32 等硬件
- **Audrey-Li 项目最有参考价值**：
  - 14 通道 Emotiv EPOC+，4 类 MI
  - 离线 98% → 实时 26%（惊人落差）→ 调参后提升到 ~50%
  - 使用 CyKit 采集 + OpenViBE 流处理 + Python 神经网络分类
  - 明确记录了"offline accuracy ≠ online accuracy"的教训
- **SSShawnJ 项目**：4 类控制（停/左/右/前），SVM 分类，Muse 设备，报告离线 98.3%
- **NeuroSky MindWave** 是消费级单通道设备，精度有限但门槛最低

### 1.3 基础设施框架（可作为底层依赖）

| 框架 | 用途 | 实时能力 | MI 支持 | 链接 |
|:---|:---|:---|:---|:---|
| BrainFlow | 多设备 EEG 采集 SDK | 流式采集，40+ 设备 | 无内置分类器 | [GitHub](https://github.com/brainflow-dev/brainflow) |
| Muse LSL | Muse → LSL 流 | 实时蓝牙流 | 无 | [GitHub](https://github.com/alexandrebarachant/muse-lsl) |
| MNE-Python | 预处理 + CSP 分类 | 支持实时流 | CSP + LDA/SVM | [mne.tools](https://mne.tools) |
| MOABB | 离线 benchmark | 无实时能力 | 多个 MI 数据集 | [GitHub](https://github.com/NeuroTechX/moabb) |
| OpenViBE | BCI 范式设计平台 | 支持实时 | MI training scenario | [openvibe.inria.fr](https://openvibe.inria.fr) |
| EEG-ExPy | 消费级 EEG 实验 | 支持实时流 | P300/SSVEP 实验 | [GitHub](https://github.com/neurotechx/eeg-notebooks) |

---

## 2. 学术论文（PubMed）

搜索条件：`"motor imagery" "vehicle control" brain-computer interface`，共 9 篇（2017-2025）。

**核心研究组**：Bi L. 团队（5 篇），聚焦 EEG 脑控车辆的横向+纵向控制。

| 年份 | 论文 | 控制维度 | 关键发现 | PM |
|:---|:---|:---|:---|:---|
| 2025 | Xu et al. — 双目 SSVEP 脑控无人车 | 横向 | SSVEP 棋盘格+相位编码范式 | -- |
| 2023 | Lian et al. — 异步 EEG 驾驶员-车辆接口 | 横向+纵向 | 为神经肌肉障碍者恢复驾驶能力 | -- |
| 2022 | Zhang et al. — 2D 导航机器人 | 2D 平面 | 超越二元命令，实现连续导航 | -- |
| 2019 | Lu & Bi — 横向+纵向联合控制 | 横向+纵向 | EEG 同时控制方向盘和油门/刹车 | -- |
| 2019 | Lu & Bi — 纵向控制系统 | 纵向 (速度) | 专注速度控制 | -- |
| 2019 | Nguyen & Chung — 制动意图检测 | 安全 | 8ch EEG 检测紧急制动意图 | -- |
| 2018 | Bi et al. — 紧急情况检测 | 安全 | EEG + 环境信息融合检测紧急状态 | -- |
| 2017 | Bi et al. — 排队网络建模 | 横向 | 脑控转向模型性能接近真人驾驶 | -- |

### 论文趋势

- 从**二元命令**（左/右）→ **连续控制**（方向盘角度 + 速度）
- 从**纯 EEG** → **EEG + 环境信息融合**（安全冗余）
- **SSVEP 比 MI 更常用于车辆控制**（命令数多、准确率高）
- Bi L. 团队是该方向的持续深耕者

---

## 3. 竞赛与活动

### Cybathlon BCI Race

- ETH Zurich 主办的 BCI 竞赛，MI 控制游戏角色通过障碍
- 游戏平台私有，不开源
- 2024 年关键发现：简单模型在实际部署中可能优于复杂模型
- 90% 实验室准确率 → 竞赛中可能降到 60%

---

## 4. 差距分析：P8 的机会

| 维度 | 现状 | P8 可填补的空白 |
|:---|:---|:---|
| 纯模拟方案 | 无 | 首个纯 Python 端到端模拟方案 |
| 离线→在线差距 | 被提及但未系统研究 | 系统性对比离线 vs 实时性能 |
| 基础模型集成 | 无 | Foundation Model + 在线自适应在控制任务上的首次验证 |
| 标准化 benchmark | 无统一评测 | 可定义 MI 控制任务的标准评测协议 |
| 开源可复现 | 大部分项目代码不完整 | 完整开源、文档齐全 |

---

## 5. 关键参考链接

### GitHub
- [EEG-Brainwave-Controlled-RaceCar](https://github.com/Audrey-Li-CPEN/EEG-Brainwave-Controlled-RaceCar) — 最接近的参考项目
- [Brainwave_Controller](https://github.com/SSShawnJ/Capstone-Brainwave_Controller) — 4 类 MI + SVM
- [MindControlledCar](https://github.com/AjayKrP/MindControlledCar) — NeuroSky + DNN
- [BrainFlow](https://github.com/brainflow-dev/brainflow) — 多设备采集 SDK
- [MNE-Python](https://mne.tools) — 预处理 + CSP
- [MOABB](https://github.com/NeuroTechX/moabb) — BCI benchmark

### 框架
- [OpenViBE](https://openvibe.inria.fr) — BCI 范式设计平台
- [LSL (Lab Streaming Layer)](https://labstreaminglayer.org) — 时间同步协议

### 论文数据库
- PubMed: `EEG brain-controlled vehicle driving`（9 篇）
- Google Scholar: `"motor imagery" "vehicle control" "brain-computer interface"`

---

<!-- 
  ═══════════════════════════════════════════════════════════════
  Obsidian 格式硬规则 (来自 CLAUDE.md §6)
  ═══════════════════════════════════════════════════════════════
  1. 图片嵌入必须使用 ![[filename.png|800]]，禁止 ![](path%20encoded)
  2. Wikilink 必须带 display alias：[[File_Name|Display Title]]，禁止裸 [[File_Name]]
  3. 禁止用 --- 作为"无数据"占位符，用 -- 替代
  4. YAML 字符串值必须用双引号包围
  5. 标签名中禁止空格，用短横线替代
  6. 数学公式：行内 $ $，行间 $$ $$
  ═══════════════════════════════════════════════════════════════
-->
