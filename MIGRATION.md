# EEG_Project 跨电脑迁移指南 (MIGRATION.md)

> 适用场景：把整个 `D:\yuan_dataset\EEG_Project` 从 A 电脑无缝挪到 B 电脑（实验室主机、备用本、出差机等），保证：
>
> 1. **AI 工具的"灵魂指示"全部跟着走** — `CLAUDE.md` / `.claude/` hooks / `.claude/skills/` / `.agents/skills/` / `skills-lock.json` / 各子目录 README 全部保留。
> 2. **代码、Marker、SOP、文档零差异** — 新电脑上 Claude Code / Cursor 读完这份文件就能继续工作。
> 3. **真实被试数据不会被误传、误改、误提交**。
> 4. **机器本地依赖（驱动、SDK、Conda 环境、相机、串口）有明确的恢复路径**。
>
> 新电脑上接手的入口提示词放在最后一节 [§13 给新电脑上 Claude/Cursor 的接手提示词](#13-给新电脑上-claude--cursor-的接手提示词)，可以直接复制粘贴。

---

## 0. 现状速读：项目里有什么、哪些必须跟着走

| 类别 | 路径 | 入库 | 迁移必带 | 备注 |
|:---|:---|:---:|:---:|:---|
| **项目级 AI 规则** | `CLAUDE.md` | 是 | **必带** | Claude Code 进入项目第一件事就要读它 |
| **Claude hooks + 权限** | `.claude/settings.json`、`.claude/hooks/*.py` | 是 | **必带** | 数据目录保护 + 每次结束自动 git status |
| **Claude project skills** | `.claude/skills/` (5 个 Obsidian skills) | 是 | **必带** | Cursor 也会在 agent_skills 里看到这些 |
| **Obsidian Agent skills** | `.agents/skills/` (与 .claude/skills 对应) | 是 | **必带** | 给 Obsidian 端 agent 用 |
| **Skills 锁定哈希** | `skills-lock.json` | 是 | **必带** | 防止 skill 内容被静默篡改 |
| **VS Code 配置** | `.vscode/settings.json` | 是 | **必带，但要改路径** | Python 解释器写死了 `C:/Users/SLAI/...`，换机要改 |
| **Obsidian vault 配置** | `.obsidian/*.json` | 部分 | **建议带** | `workspace.json` 是 UI 状态，可不带 |
| **顶层环境定义** | `environment.yml`、`requirements.txt` | 是 | **必带** | Conda 环境 `eeg-p4`，Python 3.10 |
| **视频工具子环境** | `P4_.../video/video_action_tool/environment.yml` + `requirements.txt` | 是 | **必带** | 单独装 ultralytics / mediapipe / pyarrow |
| **子项目 Claude 权限** | `P4_.../p8_mi_car/.claude/settings.local.json` | 是（已加 .gitignore 例外） | git clone 会自带 | 见 §4.2 |
| **YOLO / 面部模型权重** | `yolov8n-pose.pt`、`face_landmarker.task` | 是（已入库） | git clone 会自带 | ~10MB，离线运行靠它们 |
| **三方采集软件** | `eConScan_AiO/`、`iRecorder W32产品光盘/` | 否（gitignore） | **看情况** | 推荐重新装设备厂家光盘，不强迁 |
| **真实被试数据** | `**/data/`、`*.bdf`、`*.npz`、`*.mp4` 等 | **永不入库** | **不要随便带** | 见 §10 数据安全 |
| **Python 缓存** | `**/__pycache__/`、`.pytest_cache/` | 否 | **不带** | 新机重新生成 |

> 一句话：**带走 git 仓库里的所有跟踪文件 + 三个 gitignore 例外（`p8_mi_car/.claude/settings.local.json`、`yolov8n-pose.pt`、`face_landmarker.task`）**，其余按机器本地依赖重新装。

---

## 1. 传输方式：GitHub remote + 一键同步脚本

本仓库已经把跨电脑同步**脚本化**了，正常情况下只需要：

```powershell
# A 电脑做完改动后
.\scripts\sync_to_github.ps1            # 自动 commit + push 到 origin/main

# B 电脑接手
git clone git@github.com:stevencummings341-prog/eeg-p4.git D:\yuan_dataset\EEG_Project
# ... B 电脑工作完 ...
.\scripts\sync_to_github.ps1            # 再传回去
```

### 1.1 Remote 与分支

- Remote URL：`git@github.com:stevencummings341-prog/eeg-p4.git`（SSH）
- 主分支：`main`
- 可见性：private

如果 SSH 不通（公司网络/校园网 22 端口被封是常见情况），可改用：

```powershell
git remote set-url origin https://github.com/stevencummings341-prog/eeg-p4.git
```

然后用 Personal Access Token 作为 HTTPS 密码（GitHub Settings → Developer settings → Tokens → Tokens (classic)，scope 选 `repo`），第一次 push 会被 git credential manager 缓存。

或者走 SSH-over-443（防火墙环境下最稳）— 在 `~\.ssh\config` 写：

```text
Host github.com
  Hostname ssh.github.com
  Port 443
  User git
```

### 1.2 一键同步脚本：`scripts\sync_to_github.ps1`

| 用法 | 行为 |
|:---|:---|
| `.\scripts\sync_to_github.ps1` | 自动写 commit message：`chore(sync): 日期 (n files)`，commit + push |
| `.\scripts\sync_to_github.ps1 -Message "feat: ..."` | 用自定义 message |
| `.\scripts\sync_to_github.ps1 -NoPush` | 只 commit 不 push（离线 / 想再 review） |
| `.\scripts\sync_to_github.ps1 -DryRun` | 只打印将做的事，不真改 git 状态 |

**安全保障**（在脚本里硬编码，绕不过）：

- 一旦发现要 stage 的 path 含 `/data/` 或扩展名属于 `{bdf, npz, fif, edf, mp4, set, cnt, vhdr, vmrk, eeg, mat}`，脚本会**直接拒绝执行并退出 2**，提示先检查 `.gitignore` 或挪到 `scratch/`。
- 永远走当前分支（`main`），不切分支。
- 永远不会 reset / push --force / clean。

> AI 端：当用户说"提交 / 同步 / sync / push"时，按 `CLAUDE.md` 的"快速提交流程"一节直接调用此脚本，不要再自己写 `git add / commit / push`。

### 1.3 应急备份方式（脚本不可用 / 离线场景）

如果某天 GitHub 不可达，可以用压缩包：

```powershell
cd D:\yuan_dataset
7z a -tzip EEG_Project_migration.zip EEG_Project `
  "-xr!EEG_Project\eConScan_AiO" `
  "-xr!EEG_Project\iRecorder*" `
  "-xr!EEG_Project\**\__pycache__" `
  "-xr!EEG_Project\**\.pytest_cache" `
  "-xr!EEG_Project\**\data" `
  "-xr!EEG_Project\**\scratch" `
  "-xr!EEG_Project\**\tmp" `
  "-xr!EEG_Project\**\*.bdf" `
  "-xr!EEG_Project\**\*.npz" `
  "-xr!EEG_Project\**\*.fif" `
  "-xr!EEG_Project\**\*.edf" `
  "-xr!EEG_Project\**\*.mp4" `
  "-xr!EEG_Project\**\*.set" `
  "-xr!EEG_Project\**\.venv"
```

> 用压缩包路线时，记得**手动确认**两个模型权重 `yolov8n-pose.pt` 和 `face_landmarker.task` 在包里。git 路线则不用担心，它们已经入库。

---

## 2. 路径常量速查表（不能写死的地方）

下表是项目里"写死了 A 电脑路径"或"机器本地能跑就够、新机要改"的所有位置：

| 文件 | 写死的内容 | 新机要做什么 |
|:---|:---|:---|
| `.vscode/settings.json` | `python.defaultInterpreterPath: C:/Users/SLAI/miniconda3/envs/eeg-p4/python.exe` | 改成新机实际 `.../envs/eeg-p4/python.exe`。如果 Miniconda 装在 `D:\Miniconda3` 也要相应调整 |
| `.vscode/settings.json` | `jupyter.kernels.excludePythonEnvironments` 同上路径 | 同上 |
| `P4_.../experiment/config.py` | `port_name = "COM5"` | 新机串口可能是 COM3/COM4/…，无硬件测试可加 `--no-hardware` 跳过 |
| `P4_.../experiment/config.py` | `camera_device_name = "FF-Camera"` | 新机相机 dshow 名可能不同。可通过 `ffmpeg -list_devices true -f dshow -i dummy` 查 |
| `P4_.../experiment/config.py` | `screen_id = 1`（外接拓展屏） | 没接外接屏时改用 `--screen 0` 或 GUI 里选 |
| `eeg-p4` Conda 环境 | 命令行/IDE 都依赖此名 | **环境名固定为 `eeg-p4`**，新机也用同名（见 §3） |
| 没有 git remote | `git push` 会失败 | 见 §1A 一次性配上 |

> 经验法则：项目里**只有上述 5 行需要因机器而异**，其他都是平台无关的。

---

## 3. 在新电脑上恢复 Conda 环境

### 3.1 先决条件

| 项 | 推荐版本 | 说明 |
|:---|:---|:---|
| Windows | 10/11 x64 | macOS / Linux 也行，但 PsychoPy + iRecorder 串口在 Windows 最稳 |
| Miniconda 或 Anaconda | 任意近期版本 | 推荐 Miniconda3，装在用户目录或 `D:\Miniconda3` |
| Git | 任意 | 推荐启用 Git LFS（如果以后要把模型权重纳管） |
| FFmpeg | 任意 | 加入 PATH，相机录制脚本依赖 |
| VS Code 或 Cursor | 最新 | 装好 Python / Ruff 扩展 |

> 安装顺序：Miniconda → Git → FFmpeg → VS Code/Cursor → 拉项目 → 装 conda env。

### 3.2 创建主环境 `eeg-p4`

在项目根目录：

```powershell
cd D:\yuan_dataset\EEG_Project
conda env create -f environment.yml
conda activate eeg-p4
python -m ipykernel install --user --name eeg-p4 --display-name "Python (eeg-p4)"
```

> ⚠️ `environment.yml` 锁定 `python=3.10`。不要让 Conda 自作主张升到 3.11/3.13，PsychoPy 在 3.13 上经常崩。

### 3.3 视频工具的子环境（共用同一个 eeg-p4）

视频工具 `environment.yml` 和顶层是同名 `eeg-p4`，但额外加了 `ultralytics / mediapipe / pyarrow`。在已有 `eeg-p4` 的基础上做 update 即可：

```powershell
cd D:\yuan_dataset\EEG_Project\P4_EEG降噪与任务特征保真\experiment\video
conda env update -n eeg-p4 -f video_action_tool\environment.yml
```

或者直接双击 `install_env_conda.bat`（已写好同样的逻辑）。

### 3.4 快速自检

```powershell
conda activate eeg-p4

# 顶层关键依赖
python -c "import psychopy, serial, numpy, scipy, mne, pylsl, torch; print('top-level OK')"

# 视频工具
cd P4_EEG降噪与任务特征保真\experiment\video
.\check_environment.bat
```

`check_environment.bat` 会逐项检查 numpy / pandas / cv2 / torch / ultralytics / mediapipe / pyarrow / 两个模型文件 / analysis 包是否能 import，全 `[OK]` 就过关。

### 3.5 修正 VS Code/Cursor 解释器路径

`.vscode/settings.json` 里两行写死了 A 电脑路径。换机后必改：

```jsonc
{
  "python.defaultInterpreterPath": "C:/Users/<新用户名>/miniconda3/envs/eeg-p4/python.exe",
  "jupyter.kernels.excludePythonEnvironments": [
    "C:/Users/<新用户名>/miniconda3/envs/eeg-p4/python.exe"
  ]
}
```

或者通过 `where python`（先 `conda activate eeg-p4`）拿到真实路径再回填。Cursor 用户：`Ctrl+Shift+P` → `Python: Select Interpreter` → 选 `eeg-p4`，会自动覆盖。

---

## 4. AI 工具配置：不能丢的"灵魂指示文件"

这一节列出所有 Claude Code / Cursor / Obsidian-Agent 必须看到的文件。**B 电脑上务必逐一确认它们存在且内容一致**。

### 4.1 顶层

```text
EEG_Project/
├── CLAUDE.md                       # 项目级长期规则（必读，Claude Code 自动加载）
├── README.md                       # 项目总览
├── MIGRATION.md                    # 本文件
├── skills-lock.json                # Skill 内容哈希锁，防漂移
│
├── .claude/                        # Claude Code 项目目录
│   ├── settings.json               # permissions + hooks 配置
│   ├── hooks/
│   │   ├── protect_data.py         # PreToolUse: 禁止改 data/
│   │   └── git_status_summary.py   # Stop: 自动报告 git 状态
│   └── skills/                     # Project-local skills
│       ├── defuddle/SKILL.md
│       ├── json-canvas/SKILL.md
│       ├── obsidian-bases/SKILL.md
│       ├── obsidian-cli/SKILL.md
│       └── obsidian-markdown/SKILL.md
│
├── .agents/                        # Obsidian 端 Agent skills（与 .claude/skills 镜像）
│   └── skills/...                  # 同上 5 个
│
└── .vscode/settings.json           # IDE 解释器、ruff 等
```

### 4.2 子项目内的 Claude 配置

`p8_mi_car/.claude/settings.local.json` 原本被 `.gitignore` 里的 `**/.claude/settings.local.json` 通配规则忽略了。现在 `.gitignore` 里已经加了一条**例外**：

```text
!P4_EEG降噪与任务特征保真/p8_mi_car/.claude/settings.local.json
```

意思是：这一个文件**会**跟 git 走，其他位置的 `settings.local.json` 仍然是机器本地。

文件内容很短：

```json
{
  "permissions": {
    "allow": [
      "Bash(python *)"
    ]
  }
}
```

如果以后想在某个新子项目也启用这种"项目级权限"，要么再加一条 `!路径` 例外，要么把文件名改成 `settings.json`（不带 `local`）。

### 4.3 子目录里的"指导性"Markdown（都必须随项目走）

下面这些文件**不是 AI 自动加载的**，但 Claude/Cursor 接手时会读，缺一不可：

```text
P4_EEG降噪与任务特征保真/
├── README.md                                       P4 总览 + 数据流
└── experiment/
    ├── README.md                                   实验代码用法、Session 时序
    └── video/
        ├── README_无缝迁移指南.md                  视频工具迁移指南（嵌套子方案）
        ├── CLAUDE_CODE_HANDOFF.md                  给视频工具的 Claude 接手提示
        └── video_action_tool/
            └── analysis/
                ├── README.md
                └── 视频动作提取流程报告.md
```

> Cursor / Claude Code 第一次进项目时，按以下顺序读完，就能 100% 还原"原电脑上的 AI 视角"：
> `CLAUDE.md` → `MIGRATION.md` → `README.md` → `P4_.../README.md` → `P4_.../experiment/README.md` → `.claude/settings.json` → `.claude/hooks/*.py`。

### 4.4 Skill 哈希校验（可选但推荐）

`skills-lock.json` 记录了 5 个 obsidian skills 的内容哈希。换机后跑一次校验：

```powershell
# PowerShell 简易校验，逐文件比对哈希
python -c "
import json, hashlib, pathlib
lock = json.loads(pathlib.Path('skills-lock.json').read_text(encoding='utf-8'))
for name, meta in lock['skills'].items():
    p = pathlib.Path('.claude/skills') / name / 'SKILL.md'
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    ok = h == meta['computedHash']
    print(('OK   ' if ok else 'DIFF '), name, h[:12])
"
```

全部 `OK` 就说明 skill 内容和 A 电脑一致；出现 `DIFF` 时，去 `.claude/skills/<name>/SKILL.md` 对比 A 电脑版本。

---

## 5. 硬件/驱动/外设（不入 git，单独处理）

以下东西按机器装一次即可，不要硬塞进项目目录：

| 设备 | 安装方式 | 验证 |
|:---|:---|:---|
| **iRecorder W32 EEG** | 用原厂光盘 `iRecorder W32产品光盘/` 装驱动 + eConScan_AiO；A 电脑这两个文件夹被 `.gitignore`，**不传到 B 电脑**，B 电脑用自己的光盘装 | 设备管理器看得到 COM 口；记下口号回填给 `--port` |
| **Trigger 串口** | 上一步驱动装好后自动出现 | A 电脑是 COM5；B 电脑可能不同。先 `--no-hardware` 跑通流程，再接硬件 |
| **FF-Camera（或新机相机）** | 装相机驱动；如不叫 FF-Camera，需要改 `--camera-device` | `ffmpeg -list_devices true -f dshow -i dummy` 查 dshow 设备名 |
| **FFmpeg** | 官网下载 `release essentials` 解压，加入 PATH | `ffmpeg -version` 能出版本号 |
| **显示器布局** | 单屏时所有 `--screen 1` 改成 `--screen 0`，并加 `--windowed` 测试 | 见 §6 冒烟测试 |

---

## 6. 接管后第一件事：无硬件冒烟测试

在 B 电脑做完环境恢复后，先**不接 EEG/相机**，按下面 4 个命令完整跑一遍，确认代码、Marker、键盘、保存路径都没被搬坏：

```powershell
conda activate eeg-p4
cd D:\yuan_dataset\EEG_Project\P4_EEG降噪与任务特征保真\experiment

python launcher.py --subject Test --session 1 --windowed --no-hardware --screen 0 --no-camera
python launcher.py --subject Test --session 2 --windowed --no-hardware --screen 0 --no-camera
python launcher.py --subject Test --session 3 --windowed --no-hardware --screen 0 --no-camera
python launcher.py --subject Test --session 4 --windowed --no-hardware --screen 0 --no-camera --mi-formal-trials-per-class 4 --mi-formal-blocks 2
```

期望：

- 每个 Session 进入窗口、能用空格推进、ESC 安全退出。
- 结束后 `experiment/data/` 下出现 `P4_S?_Test_*.npz`（这是测试数据，可以删；删之前请遵守 §10 数据规则——`Test_*` 不算真实被试，删除是安全的）。
- 没有 `pyserial` / `psychopy` / `tkinter` ImportError。

视频工具：

```powershell
cd P4_EEG降噪与任务特征保真\experiment\video
.\check_environment.bat   # 应全 [OK]
```

---

## 7. Obsidian Vault 的迁移要点

`.obsidian/` 是 Obsidian 的本地 vault 配置：

| 文件 | 作用 | 是否随迁 |
|:---|:---|:---|
| `app.json` | App 设置 | 带 |
| `appearance.json` | 主题/字体 | 带（可不带，新机自选） |
| `core-plugins.json` | 启用了哪些核心插件（包含 `bases: true`） | **带** |
| `workspace.json` | UI 状态（打开了哪些 tab） | 不带也行 |

新电脑首次打开：

1. Obsidian → 打开仓库 → 选 `D:\yuan_dataset\EEG_Project`。
2. 如果 Obsidian 提示要启用 plugin，按 `core-plugins.json` 里 `true` 的逐项启用。
3. `bases: true` 需要 Obsidian ≥ 1.7（带 Bases 功能）。
4. 检查 `.agents/skills/` 是否被识别（Obsidian Agent 模式下能看到 5 个 skills）。

---

## 8. Cursor / VS Code 端的特殊操作

### 8.1 让 Cursor 看到项目 skills

Cursor 启动时会扫描：

- `~/.cursor/skills-cursor/` (用户全局 skills)
- 项目 `.claude/skills/` 和 `.cursor/rules/`（如果有）

你这个项目目前**没有** `.cursor/rules/`。`.claude/skills/` 的 5 个 obsidian skills 会自动出现在 agent_skills 列表。

如果以后要加 Cursor 专属 rules，使用 `create-rule` skill 创建到 `.cursor/rules/<name>.mdc`，注意要随项目入 git。

### 8.2 让 Cursor 自动读 `CLAUDE.md`

Cursor 默认会把仓库根的 `CLAUDE.md` 当作 always-applied workspace rule（你这个项目已生效，从顶部的 `<always_applied_workspace_rules>` 注入可以看到）。所以只要 `CLAUDE.md` 没被删，新电脑也会自动生效。

### 8.3 解释器选择

`Ctrl+Shift+P` → `Python: Select Interpreter` → 选 `eeg-p4` 那条。如果列表里没有，先在终端 `conda activate eeg-p4`，再重启 Cursor。

---

## 9. Git 工作流约束（CLAUDE.md 的硬规则）

迁移完成后，所有 git 操作必须仍然遵守 `CLAUDE.md` 里写的：

- **不要** `git commit / push / reset --hard / clean / checkout -- / restore` 自动跑。
- **不要** `git add .` 或 `git add -A`，永远显式 add。
- 只有用户明确说"提交/commit"才创建 commit。
- 每次开始工作前 `git status --short` 看一眼，结束时再看一眼。
- `.claude/hooks/git_status_summary.py` 会在每次 Claude session 结束时自动提醒未提交变更。

---

## 10. 数据安全：永远不能跨机带的东西

下面这些东西**禁止**靠迁移指南带走（除非用户明确说要）：

| 类型 | 路径示例 | 怎么处理 |
|:---|:---|:---|
| 真实被试 EEG | `**/data/`、`**/*.bdf`、`*.npz`（真实被试）、`*.fif` | A 电脑保留；B 电脑要分析就走加密硬盘单独传 |
| 真实被试视频 | `**/video_records/*.mp4`、对应 `*.csv/*.json` | 同上 |
| 视频处理结果 | `**/analysis_outputs/` | 一般可重新生成，不必随机传 |
| 三方 SDK / 驱动光盘 | `eConScan_AiO/`、`iRecorder W32产品光盘/` | B 电脑用自己手上的厂家光盘装，不靠 git |
| 临时 scratch | `scratch/`、`tmp/`、`*.tmp` | 不带 |

> 即便 `.gitignore` 已经覆盖了上述大部分扩展名（看 `.gitignore` 第 12-24 行），仍然要**人工**在打包/同步时再确认一次。

---

## 11. 三方依赖快速恢复 Cheatsheet

下面这些是新电脑上 Conda env 之外、可能要再装一次的东西：

| 名称 | 安装方式 | 是否必须 |
|:---|:---|:---:|
| Miniconda3 | <https://docs.conda.io/en/latest/miniconda.html> | ✅ |
| Git for Windows | <https://git-scm.com/download/win> | ✅ |
| FFmpeg | <https://www.gyan.dev/ffmpeg/builds/> release essentials，解压加 PATH | ✅ |
| iRecorder 设备驱动 | 设备原厂光盘 | 实验用时必须 |
| eConScan_AiO 采集软件 | 设备原厂光盘 | 实验用时必须 |
| Obsidian | <https://obsidian.md/> | 编辑 SOP/日志时必须 |
| Cursor 或 VS Code | <https://cursor.com/> / <https://code.visualstudio.com/> | ✅ |
| 7-Zip | <https://www.7-zip.org/> | 解迁移包用 |

---

## 12. 完整迁移 Checklist（人 + AI 共用）

打钩式跑一遍，全过就完成无缝迁移。

### A 电脑（出发前）

- [ ] `git status --short`，确认所有想带走的改动都在仓库里
- [ ] 跑 `.\scripts\sync_to_github.ps1`（或说"提交"让 AI 调用），把当前改动 push 到 GitHub
- [ ] 不要把 `data/`、`*.bdf`、`*.mp4`、`eConScan_AiO`、`iRecorder W32产品光盘` 带过去（脚本已有二次拦截）

### B 电脑（到了之后）

- [ ] 装 Miniconda3 / Git / FFmpeg / Cursor (或 VS Code) / Obsidian
- [ ] `git clone git@github.com:stevencummings341-prog/eeg-p4.git D:\yuan_dataset\EEG_Project`（SSH 不通就改 HTTPS URL）
- [ ] 在本仓库 local 作用域配 git 身份：`git config user.name "Leo"` + `git config user.email "3024593639@qq.com"`
- [ ] 确认根目录 `CLAUDE.md`、`MIGRATION.md`、`scripts/sync_to_github.ps1`、`.claude/`、`.agents/`、`.vscode/`、`skills-lock.json` 都在
- [ ] `conda env create -f environment.yml` → `conda activate eeg-p4`
- [ ] `conda env update -n eeg-p4 -f P4_EEG降噪与任务特征保真\experiment\video\video_action_tool\environment.yml`
- [ ] 检查 `.vscode/settings.json` 中 `${env:USERPROFILE}` 是否能解析到本机 `.../envs/eeg-p4/python.exe`；如 Miniconda 不在用户目录，改这一行
- [ ] 跑 §6 的 4 条无硬件冒烟测试，全部通过
- [ ] 跑 §3.4 的依赖自检脚本
- [ ] 跑 §4.4 的 skill 哈希校验
- [ ] 打开 Obsidian、确认 `bases` 等核心插件已启用
- [ ] 启动 Cursor / Claude Code，让它读 §13 的提示词，确认 AI 视角已接管

---

## 13. 给新电脑上 Claude / Cursor 的接手提示词

把整段复制粘贴到新电脑的 Cursor / Claude Code 聊天里，作为第一条消息：

```text
我刚从另一台电脑把整个 EEG_Project 仓库迁移到这台机器上，工作目录是
D:\yuan_dataset\EEG_Project（如不同请自己识别）。

请严格按以下顺序、用工具调用真正读取文件，不要凭印象回答：

1. 读取 MIGRATION.md（仓库根），先建立完整迁移视角。
2. 读取 CLAUDE.md（仓库根），把它作为长期项目规则。
3. 读取 README.md、P4_EEG降噪与任务特征保真/README.md、
   P4_EEG降噪与任务特征保真/experiment/README.md。
4. 读取 .claude/settings.json 和 .claude/hooks/*.py，确认数据保护
   hook 和 git 状态 hook 都在原位。
5. 跑 git status --short，告诉我当前未提交的内容，但不要自动 commit。
6. 跑 MIGRATION.md §12 "B 电脑" 的 Checklist：
   - 检查 conda 是否能 activate eeg-p4
   - 检查 .vscode/settings.json 里的 ${env:USERPROFILE} 路径是否对得上
     本机实际的 .../envs/eeg-p4/python.exe（如不对，列出修改方案给我
     确认，不要直接改）
   - 确认 git remote 已指向 git@github.com:stevencummings341-prog/eeg-p4.git
   - 跑 skills-lock.json 哈希校验（MIGRATION.md §4.4 给了脚本）
   - 不需要再单独确认模型权重 / p8_mi_car/.claude/settings.local.json：
     这两类东西已经入库，git clone 自带。
7. 报告：
   - 哪些 Checklist 项已通过
   - 哪些项失败、缺失或需要我手动操作
   - 建议的下一步（按 CLAUDE.md 的工作风格：小步、可回滚、不擅自 commit）

绝对不要：
- 修改 data/、**/data/、**/*.bdf、**/*.npz、**/*.mp4 等真实数据
- git commit / push / reset / clean / add . / add -A
- 自动重命名 config.py / utils.py / session*.py 等模块
- 把 eConScan_AiO/ 和 iRecorder W32产品光盘/ 加进 git

完成后只回一段中文总结，按"已通过 / 待处理 / 建议下一步"三段写。
```

> 该提示词只让 AI 做"检查 + 报告"，不做任何破坏性写操作；完全符合 `CLAUDE.md` 的工作流。

---

## 14. 维护这份指南

只要发生下面任何一件事，就回来更新本文件：

1. 新增了 AI 工具配置文件（`.cursor/rules/`、`.claude/agents/` 等）→ 在 §0、§4 加一行
2. 改了 Conda 环境（增减依赖、升级 Python）→ 同步改 §3 和 `environment.yml`
3. 改了硬件路径常量（COM 口默认值、相机名、screen_id 默认）→ 改 §2
4. 给项目加了 git remote → 改 §1A
5. 新增子项目时，确认其 README / `.claude/` 是否需要列入"灵魂文件"清单

保持这份指南是"**新电脑上 AI 一次性读完就能接管**"的唯一入口。
