# CLAUDE.md

本文件是 Claude Code 在本仓库工作的项目级指令。进入本项目后必须优先遵守这些规则，并在回答、改代码、整理 Obsidian 笔记和做版本管理时保持一致。

## 项目定位

本项目是 **P4: EEG 降噪与任务特征保真**。核心目标不是先训练大模型，而是先建立一套可复现的 EEG 数据采集与数据净化基础设施：

- 通过 4-Session 采集 SOP 从源头拆分“干净脑电任务信号”和“眼电/肌电伪迹”。
- 构建可控训练对：`X_input = Y_clean + λ · noise`，让降噪模型知道什么该去除、什么必须保留。
- 重点保真三类任务特征：P300 时域波峰、睁眼/闭眼 Alpha 阻断、SSVEP 窄带频谱与相位锁定。
- 近期瓶颈是完成至少 1 个被试的完整 4-Session 预实验，验证 Marker、Trigger、数据保存和后处理管道。

主要参考文件：

1. `P4_EEG/ARCHITECTURE.md` — 当前架构与模块职责（**第一次进项目先读这个**）。
2. `P4_EEG/docs/proposal.md` — 采集 SOP、Marker、被试流程、数据流。
3. `P4_EEG/experiment/README.md` — 实验代码运行方式。
4. `P4_EEG/docs/paper_blueprint.md` — 论文叙事、实验矩阵、当前完成度。

## 当前架构

```text
D:\EEG_Project
├── CLAUDE.md                         # 本文件
├── README.md                         # 仓库总览
├── environment.yml / requirements.txt
├── .obsidian/                        # Obsidian vault 配置
├── .claude/                          # Claude Code 项目配置、hooks 与 project-local skills
├── scripts/                          # 项目级脚本（sync_to_github / run_pipeline / diagnose）
├── scratch/                          # 临时输出 / 合成测试（gitignore）
│
└── P4_EEG/
    ├── README.md                     # 项目入口
    ├── ARCHITECTURE.md               # 详细模块说明（第一次进项目先读）
    │
    ├── docs/                         # 静态文档集中
    │   ├── README.md                   # 文档索引
    │   ├── proposal.md                 # 采集 SOP 主方案
    │   ├── paper_blueprint.md          # Paper 1 蓝图
    │   ├── 实验操作指南.md
    │   ├── 真实设备连接与正式采集指南.md
    │   └── changelog/                  # 复盘日志
    │
    ├── experiment/                   # S1-S4 采集主流程
    │   ├── README.md
    │   ├── launcher.py                 # 主入口（GUI + Session 调度 + 相机启停）
    │   ├── config.py                   # 配置 + MARKER_TABLE（权威）
    │   ├── utils.py                    # Trigger / Keyboard / 保存
    │   ├── sessions/                   # 5 个 session*.py
    │   ├── data/                       # eeg-bdf / eeg-npz / video_records (gitignore，永不修改)
    │   ├── video/                      # 相机录制 + 视频动作提取
    │   ├── stimuli/                    # 实验刺激素材
    │   └── legacy/                     # MATLAB 旧版（历史参考）
    │
    ├── processing/                   # EEG 后处理 pipeline
    │   └── pipeline/{indexer,preprocess,epoching,features,qc,run_pipeline}.py
    │
    ├── derivatives/                  # processing 产物（gitignore，可重跑）
    │
    └── p8_mi_car/                    # 下游 MI 小车 Demo（独立子项目）
```

## 技术栈

### 实验采集

- `python` / `conda` / `pip`：实验运行与环境恢复。
- `ffmpeg`：相机录制脚本与视频后处理依赖。
- `Obsidian`：知识库与实验日志整理。
- `VS Code`：建议把解释器指向当前机器实际的 `eeg-p4` 环境，而不是沿用旧电脑路径。

### EEG 数据处理与建模规划

- MNE-Python 或 EEGLAB：读取原始 EEG、按 Marker 切片、预处理。
- NumPy/SciPy：信号处理、PSD、时频分析、SNR、ITPC。
- PyTorch：后续降噪模型、任务分类器、损失函数实现。
- 规划中的模型方向：任务感知 denoiser、源分离/净化模块、Mamba2 U-Net 风格骨干。

### Obsidian + Claude Code 工作流

- Obsidian 作为项目知识库：SOP、论文蓝图、会议记录、问题清单、实验日志。
- Claude Code 作为执行与审查工具：读文档、解释概念、检查代码、修改脚本、生成 checklist、维护记忆。
- 已安装 Obsidian Agent Skills：`obsidian-markdown`、`obsidian-bases`、`json-canvas`、`obsidian-cli`、`defuddle`。

## 关键命令

所有命令默认在 `P4_EEG/experiment/` 目录下运行。

### 安装/恢复项目环境

推荐使用项目专用 Conda 环境 `eeg-p4`，避免使用系统 Python 3.13 直接运行 PsychoPy。

```bash
conda env create -f environment.yml
conda activate eeg-p4
python -m ipykernel install --user --name eeg-p4 --display-name "Python (eeg-p4)"
```

如果环境已存在，只需激活：

```bash
conda activate eeg-p4
```

备选 pip 安装方式：

```bash
python -m pip install -r requirements.txt
```

### 迁移到新电脑后的恢复要点

- 优先确认 Miniconda / Anaconda 可用，再创建 `eeg-p4` 环境。
- 若 VS Code 沿用旧电脑解释器路径，需手动改为当前机器实际的 `.../envs/eeg-p4/python.exe`。
- `Obsidian`、`ffmpeg`、相机驱动与串口驱动属于机器本地依赖，换机后要单独确认。
- 任何无硬件 smoke test 优先使用 `--windowed --no-hardware --screen 0`，避免把显示器和触发器问题混进代码问题。

### 启动 GUI

```bash
python launcher.py
```

### 无硬件窗口模式测试

```bash
python launcher.py --subject Sub_01 --session 1 --windowed --no-hardware
python launcher.py --subject Sub_01 --session 2 --windowed --no-hardware
python launcher.py --subject Sub_01 --session 3 --windowed --no-hardware
python launcher.py --subject Sub_01 --session 4 --windowed --no-hardware
```

### 完整流程冒烟测试

```bash
python launcher.py --subject Test --session all --quick-test --windowed --no-hardware --no-camera --screen 0
```

`--quick-test` 让 S1-S4 都用极短时长 / 极少 trial 数十秒跑完，验证 GUI / Marker / 保存逻辑无回归。

### EEG 后处理 pipeline

```bash
cd P4_EEG/processing
python -m pipeline.run_pipeline --dry-run        # 只扫描配对、不处理
python -m pipeline.run_pipeline                  # 全跑（默认 ../experiment/data → ../derivatives）
python -m pipeline.run_pipeline --subject Sub_01 --force
```

### Git 检查

```bash
git status --short
git diff --stat
git diff -- CLAUDE.md P4_EEG/experiment
```

## 4-Session 实验核心

> **权威 Marker 表的唯一来源是 [`experiment/config.py:MARKER_TABLE`](P4_EEG/experiment/config.py)**。
> 下表是给 AI 看的速查版，不要靠记忆覆盖代码。

| Session | 作用 | Marker |
| --- | --- | --- |
| S1 静息态 | 干净脑电底色，Alpha 阻断验证 | 11/12 (EO), 21/22 (EC) |
| S2 伪迹模板 | 独立眼电/肌电噪声库 | 30 (按键), 31 (动作起点), 41-48 (8 类伪迹) |
| S3 银标准任务态 | 干净任务信号 Ground Truth | Oddball 61/62, 任务间基线 63, SSVEP 71/72/73/74 |
| S4 离线双手 MI | 左右手运动想象采集 | 81-89 (示范 / cue / 想象 / 休息 / block 标记) |

关键设计原则：

- S2 只截取 Marker 31 后的伪迹动作，排除 Marker 30 按键带来的运动电位。
- S3 刺激窗口严禁眨眼，保留干净 P300/SSVEP/Alpha 特征。
- S4 已从"自然态 Oddball/SSVEP"改为离线双手运动想象，下游接 `p8_mi_car/` 做在线分类。
- 所有 Marker 严格 < 128，与 iRecorder 单字节 Trigger 协议兼容。

## 关键模块速查（哪改了会爆炸）

| 谁依赖谁 | 改这里影响 |
|:---|:---|
| `experiment/launcher.py` → `from sessions.session*` | 改 sessions/ 包路径或 `run_*` 函数签名 |
| `experiment/launcher.py` → `from video.camera_recorder_controlled import FFmpegCameraRecorder` | 改 `video/camera_recorder_controlled.py` 位置 |
| `experiment/sessions/*.py` → `from config import MARKER_TABLE / from utils import save_data / TriggerSender / ...` | 改 `config.py` / `utils.py` 的 API |
| `experiment/utils.py:save_data` → `cfg.data_dir / "eeg-npz"` | 改 NPZ 落点约定 |
| `processing/pipeline/indexer.py` → `data/eeg-bdf/`, `data/eeg-npz/` | 改 BDF / NPZ 存放路径 |
| `processing/pipeline/run_pipeline.py` 默认 `--data-dir` = `../experiment/data` | 改 P4 目录树 |

完整版见 [`P4_EEG/ARCHITECTURE.md`](P4_EEG/ARCHITECTURE.md) §7。

## 代码风格要求

### Python

- 保持脚本式实验代码简单直观，避免过度抽象。
- 优先修复会影响实验可靠性的 bug：Marker、Trigger 时序、资源清理、数据保存、参数解析。
- 实验脚本必须保留安全退出路径：ESC / KeyboardInterrupt / finally cleanup。
- 不要随意改变 Trial 数、Marker 编码、刺激时长、ITI、SSVEP 频率，除非用户明确要求并同步更新 `proposal.md` 与 `experiment/README.md`。
- 修改实验流程时，必须同步检查：指导语、Marker、保存字段、README 命令、proposal SOP 是否一致。
- 默认不添加长注释。只有在说明非显然的实验约束、时序约束或采集安全边界时才写短注释。

### Markdown / Obsidian

- 使用 Obsidian 友好的 Markdown：wikilinks、properties、清晰标题层级、任务清单。
- 不随意重命名已有笔记、标题和 Obsidian 链接目标。
- 修改 SOP 类内容时，必须保持“目的 → 流程 → Marker → 质量检查 → 避坑”的结构。
- 论文蓝图类内容应区分“已实现”“规划中”“假设结果”，不要把假设写成事实。

## 绝对禁止事项

### data 目录保护

- **绝对禁止修改、删除、重命名、移动、格式化 `data/` 或任何 `**/data/**` 下的文件。**
- **绝对禁止把真实 EEG 原始数据、被试数据、`.npz`、`.edf`、`.bdf`、`.set`、`.fif` 等数据文件加入 git。**
- 允许读取数据目录只限于用户明确授权的数据质量检查；默认不要读取真实被试数据。
- 如需生成测试数据，必须写入 `scratch/`、`tmp/` 或用户明确指定的非真实数据目录，并标明 synthetic/demo。

### Git 与版本管理安全

- 不要在没有用户指令的前提下自动 `git commit`、`git push`、`git reset --hard`、`git clean`、`git checkout --`、`git restore` 或改写历史。
- 用户要求“自动版本管理”时，本项目解释为：每次工作前后自动/主动检查 git 状态、保护数据目录、汇报变更；不是擅自提交或推送。
- 每次修改前先看 `git status --short`，识别用户已有改动；不要覆盖不属于本次任务的文件。
- 每次修改后汇报：改了哪些文件、未提交状态、建议的下一步 commit 信息。
- 永远禁止：`git reset --hard`、`git push --force`、`git clean -fdx`、改写已 push 历史、修改 `git config --global`。

### 快速提交流程（用户说"提交"就跑脚本，无需二次确认）

本仓库已经把跨电脑同步流程脚本化 (`scripts/sync_to_github.ps1`)，远端是 `git@github.com:stevencummings341-prog/eeg-p4.git` 的 `main` 分支。

**用户授权范围（已明确同意，不要再问）**：

当用户的消息里包含下列任一**触发词**（中英不限大小写、可在句中出现）：

- `提交` / `commit`
- `推送` / `push`
- `上传` / `upload`
- `同步` / `sync`
- `更新到 github` / `update github`
- `推一下` / `推到远端`

**AI 的行为约定**：

1. **直接跑脚本，不要二次确认、不要"我即将……您确认吗"**：

   ```powershell
   .\scripts\sync_to_github.ps1
   ```

   如果用户在指令里带了备注 / 描述（例如"提交，备注：完成 session4 MI 流程"），把备注作为 `-Message`：

   ```powershell
   .\scripts\sync_to_github.ps1 -Message "feat: 完成 session4 MI 流程"
   ```

   如果用户没给备注，让脚本自己生成 `chore(sync): YYYY-MM-DD HH:mm (n files)`，**不要主动问**。

2. **跑脚本之前的唯一一步检查**：先 `git status --short` 给用户一句话汇报"将提交 N 个文件，其中删除 X 个、新增 Y 个、修改 Z 个"，然后立即跑脚本。这一步只是让用户能取消，不需要等他回复。

3. **跑脚本之后的汇报模板**（保持简短）：

   ```text
   ✅ commit <短hash> · pushed to origin/main
   N files (M added, M modified, M deleted)
   ```

   失败时：

   ```text
   ⚠️ commit 已在本地 <短hash>，push 失败：<原因摘要>
   建议：检查网络/SSH，然后再说"提交"我重试 push。
   ```

4. **脚本的安全约束（已硬编码，可以信任）**：
   - 内置数据保护：任何 path 含 `/data/` 或扩展名属于 `{bdf, npz, fif, edf, mp4, set, cnt, vhdr, vmrk, eeg, mat}` 一律拒绝 stage，退出码 2。
   - 永远走当前分支（`main`），不会切分支。
   - 永远不做 `reset --hard` / `push --force` / `clean` / `amend` 已 push 的 commit。
   - 没有 remote 时只 commit 不 push，并提示。

5. **下面这些情况仍然必须先问用户**（"提交"不覆盖这些）：
   - 用户说 `git reset` / `回滚` / `revert` / `撤销 commit`
   - 用户说 `force push` / `强制 push` / `改写历史`
   - push 失败后想用 `git reset --soft HEAD~` 重整 commit
   - 看到 `git status` 里有意外的大量删除（例如超过 50 个 D 项），先列给用户确认，再跑脚本
   - 即将提交的内容里包含 `data/` 路径或数据扩展名 — 这种情况脚本会自动拒绝，但 AI 也应当先提示用户"看起来有数据文件，是不是 .gitignore 漏了"

6. **如果用户在脚本之外手动让你 `git add` / `git commit`**：仍然遵守原则——**显式 add 文件**，不要 `git add .` 或 `git add -A`。脚本里的 `add -A` 之所以允许，是因为后面接了硬编码的数据扩展名拦截 + `.gitignore` 双层防护，构成了用户对它的明确授权。

7. **PowerShell 调用方式**：在 Cursor / Claude Code 的 shell 工具里调用脚本时，**直接** `.\scripts\sync_to_github.ps1`，不要用 `powershell -File ...` 起子进程（会触发 codepage / encoding 坑）。当前 shell 已经是 PowerShell。

8. **如果该脚本本身被改坏了**（罕见）：仍然可以回退到最小手工流程，但要遵守 8.1-8.3：
   - 8.1 显式 `git add <文件1> <文件2> ...`，不要 `git add .`
   - 8.2 `git commit -m "<message>"`
   - 8.3 `git push origin main`
   并且回头修脚本。

## Claude Code 工作流程

每次接到 P4 相关任务时：

1. 先读相关 Markdown 和代码，不只凭记忆回答。
2. 如果是非平凡改动，先列任务并说明将改哪些区域。
3. 修改前检查 git 状态，注意未跟踪/未提交文件。
4. 修改时优先小步、可审计、可回滚。
5. 修改后运行最小必要检查：语法检查、无硬件窗口模式、或用户要求的测试。
6. 结束时说明：完成内容、受影响文件、未做内容、建议下一步。

## Claude Code + Obsidian 协同方式

### Obsidian 负责沉淀

适合放进 Obsidian：

- 实验 SOP、Marker 表、采集流程。
- 每次预实验记录：被试编号、设备、阻抗、异常、数据质量。
- 论文阅读笔记、方法比较、图表规划。
- 阶段性 TODO 和会议结论。

### Claude memory 负责长期协作偏好

适合放进 memory：

- 用户是 EEG 新手，需要基础解释和可执行步骤。
- P4 近期核心目标是跑通完整 4-Session 预实验。
- data 目录不可修改，版本管理必须保守。
- Claude Code + Obsidian 的协作规则。

不适合放进 memory：

- 可从代码/文档读取的具体函数、路径、Marker 表。
- 临时调试状态、一次性任务清单、运行输出。
- 真实被试信息或敏感数据。

### 推荐使用方式

你可以这样向 Claude 提问：

```text
读取 P4 的 proposal 和 experiment/README，帮我生成明天预实验 checklist。
```

```text
检查 experiment 目录，告诉我无硬件模式跑 S1-S4 前有哪些 bug 风险。
```

```text
把今天的预实验异常整理成 Obsidian 实验日志，但不要碰 data 目录。
```

```text
基于当前 git diff，帮我总结这次改动并建议 commit message，不要提交。
```

## 当前优先级

1. 完成至少 1 个被试的完整 4-Session 正式采集，并跑通 `processing` pipeline 出 QC HTML。
2. 基于 derivatives 实现"策略 A + 策略 B"（详见 `docs/proposal.md`）的训练对构建脚本。
3. 实现 task-aware denoiser baseline（先 Mamba2 U-Net 或纯卷积，再做对照实验）。
4. 把 `p8_mi_car/` 从键盘 Demo 接到 S4 离线 MI 数据，验证在线分类闭环。

## 已经完成的基础设施（≠ 优先级）

- `experiment/sessions/{session1..4}.py` 跑通 `--windowed --no-hardware --quick-test` 全流程。
- `processing/pipeline/` 6 步法完整：indexer / preprocess / epoching / features / qc / run_pipeline。
- `experiment/video/video_action_tool/` 完成 YOLOv8-Pose + MediaPipe 动作提取与 GUI。
- `data/` 重组为 `eeg-bdf / eeg-npz / video_records` 三个子目录，pipeline 自动识别。
