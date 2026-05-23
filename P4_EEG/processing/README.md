# P4 EEG 后处理 Pipeline

把 `experiment/data/<scheme>/` 里采集到的 **BDF + NPZ + 视频** 自动化处理成一份
可复现、可比较、面向降噪模型训练的 **derivatives/<scheme>/**。

> **两套实验方案均支持**：`motor_imagery`（默认）/ `emotion`。S1/S2/S3 完全共用；
> S4 根据方案切换：`motor_imagery → s4_mi`，`emotion → s4_emotion`（FAA + 频段功率）。

---

## 最简单的用法 — 一键 GUI

```text
processing\run_processing.bat
```

双击会启动 Tk GUI：
1. 选实验方案（运动想象 / 情绪识别）
2. 点 "扫描可用录制"，从列表里挑被试 + 日期
3. 点 "▶ 开始处理"，跑完后会自动在浏览器里打开 QC 报告

GUI 内部直接调 `python -m pipeline.run_pipeline`，所以 GUI / 命令行 / CI 输出完全一致。

---

## 它是干什么的

实验脚本 (`experiment/`) 每跑一次会同时生成：

```text
experiment/data/<scheme>/                   # scheme ∈ {motor_imagery, emotion}
├── eeg-bdf/<recording>.bdf                 # iRecorder 连续录制 (含 Marker annotations)
├── eeg-npz/
│   ├── P4_S1_<subj>_<ts>_session1.npz
│   ├── P4_S2_<subj>_<ts>_session2.npz
│   ├── P4_S3_<subj>_<ts>_session3_oddball.npz
│   ├── P4_S3_<subj>_<ts>_session3_ssvep.npz
│   └── P4_S4_<subj>_<ts>_session4_mi.npz       # scheme=motor_imagery
│       或 P4_S4_<subj>_<ts>_session4_emotion.npz  # scheme=emotion
└── video_records/<...>.mp4 + timestamps.csv
```

Pipeline 把它们组合起来变成：

```text
derivatives/<scheme>/
└── <subject_id>/
    ├── 01_raw_index.json          # BDF↔NPZ 配对清单 + 每段 Session 概要
    ├── 02_preproc/                # 滤波/montage/重参考后的 raw (FIF)
    ├── 03_epochs/                 # 按 Marker 切好的 mne.Epochs
    ├── 04_features/               # JSON 形式的任务特征
    │     ├── *_s1_alpha.json      # Alpha 阻断指数
    │     ├── *_s2_artifacts.json  # 伪迹模板峰峰/主导 ROI
    │     ├── *_s3_p300.json       # P300 振幅 + 潜伏期 + 波形
    │     ├── *_s3_ssvep.json      # SNR + ITPC（含 2× 谐波）
    │     ├── *_s4_mi.json         # μ/β ERD% + C3/C4 拉特化 (scheme=motor_imagery)
    │     └── *_s4_emotion.json    # FAA + theta/alpha/beta/gamma 功率 (scheme=emotion)
    └── 05_qc/report.html          # 全部数字 + 图自包含 HTML 报告
```

两套方案的 derivatives 互相独立，不会覆盖。运动想象的产物落在
`derivatives/motor_imagery/`，情绪识别落在 `derivatives/emotion/`。

---

## 快速开始

### 1. 准备环境

依赖已经在项目级 conda 环境 `eeg-p4` 里：

```powershell
conda activate eeg-p4
pip install -r processing/requirements.txt   # 多数包已装；只装漏的
```

### 2. 跑一遍合成数据冒烟测试（不碰真实 data/）

```powershell
# 生成 10 分钟合成 EDF + NPZ
python "P4_EEG\processing\tests\make_synth_data.py"

# 跑全套 pipeline，5 个 Sub-Session 30s 跑完
cd "P4_EEG\processing"
python -m pipeline.run_pipeline `
    --data-dir "..\..\scratch\synth_data" `
    --out-dir  "..\..\scratch\synth_derivatives"
```

打开 `scratch\synth_derivatives\Synth_01\05_qc\report.html` 应该看到：
- S1 EO/EC PSD 对比图，alpha_blocking_index ≈ 0.97
- S3 P300 ERP，target − standard 峰 ~ 8 μV @ ~325 ms
- S3 SSVEP 四宫格谱，每个目标频率 SNR > 4
- S4 MI C3/C4 ERD 柱状图

### 3. 真实数据（先 dry-run 看索引）

```powershell
cd "P4_EEG\processing"

# 一键 GUI（推荐日常用）
.\run_processing.bat

# 命令行：只扫描，验证 BDF↔NPZ 配对（默认 scheme=motor_imagery）
python -m pipeline.run_pipeline --dry-run

# 全跑（默认 data_dir=../experiment/data/<scheme>, out_dir=../derivatives/<scheme>）
python -m pipeline.run_pipeline --scheme motor_imagery
python -m pipeline.run_pipeline --scheme emotion

# 只跑一个被试 + 强制重跑
python -m pipeline.run_pipeline --scheme emotion --subject Sub_01 --force

# 自定义滤波/陷波
python -m pipeline.run_pipeline --scheme motor_imagery --hp-hz 0.3 --lp-hz 70 --notch-hz 50 100
```

---

## 数据保护

- **绝不写入 `data/` 或任何 `**/data/**`** — `data/` 全程只读。
- 所有产物落在 `--out-dir`（默认 `derivatives/`），可以放心 `rm -rf` 重跑。
- BDF 不会被改名/移动；只在内存里 `crop` 到当前 Session 时间窗。
- 合成测试数据写到 `scratch/synth_data/`，永远不会污染真实数据。

---

## Pipeline 6 步法

```text
indexer   →  preprocess  →  epoching       →  features         →  qc
扫数据       带通+陷波       按 Marker 切片      P300/Alpha/        HTML 报告
配 BDF↔NPZ  +montage       (S2 用 NPZ 回推    SSVEP/MI 指标       自包含 PNG
                            伪迹类型)
```

### 1. `indexer.py` — 数据扫描与配对

- 扫 `data/eeg-bdf/*.bdf` 与 `data/eeg-npz/P4_*.npz`
  （历史布局 `data/eeg/*.bdf` 与 `data/*.npz` 仍然兼容兜底，方便合成测试与旧数据）
- 一个 BDF 可能含多个 Session：按 Marker 自动切成 SubBdfSession
  （S1/S2/S3_ODDBALL/S3_SSVEP/S4_MI）
- 按「event-count 接近」+「时间接近」配对 NPZ ↔ BDF segment
- 未配对的部分留在 `unmatched_npzs` / `unmatched_bdf_segments` 字段里
  方便人工排查（多见于半途中止的 quick-test）

### 2. `preprocess.py` — 通用预处理

- 默认：HP 0.5 Hz / LP 80 Hz / notch 50 Hz / average reference / standard_1020 montage
- **不做** ICA / 自动伪迹剔除 —— 那会模糊「降噪模型应该干什么」的研究问题
- 所有参数都在 `constants.py` 顶层；命令行 `--hp-hz / --lp-hz / --notch-hz` 可覆盖

### 3. `epoching.py` — Session 感知的切片

| Session | tmin | tmax | baseline | reject (PTP) | 说明 |
|:--|:--|:--|:--|:--|:--|
| S1 EO/EC | 0 | 2.0 | 无 | 无 | 跳过开头 5s，2s 滑窗 |
| S2 伪迹 | -0.2 | 1.2 | (-0.2, 0) | 无 | T31 切，类型从 T4x 或 NPZ events 回推 |
| S3 P300 | -0.2 | 0.8 | (-0.2, 0) | 150 μV | metadata.trial_type ∈ {standard, target} |
| S3 SSVEP | 0.3 | 4.0 | 无 | 无 | 跳前 300ms 稳态；metadata.dropped_frames |
| S4 MI | -3.0 | 4.0 | (-3.0, -1.0) | 200 μV | 在 T85/T86 上切（imagery onset） |
| S4 Emotion | -2.0 | 6.0 | (-2.0, 0) | 250 μV | 在 T101/T102/T103 上切（视频起点）；metadata.category/video_file |

特别注意：**S2 伪迹类型回推**。iRecorder 在 5ms 内连发 T31 + T4x 时
经常吃掉 T4x（已在 0518 的真实数据里观察到）。`epoch_session2` 会：
1. 先按 T31 计算每个 trial 的 onset；
2. 若紧跟着有 T4x，用 T4x 写 marker；
3. 没有 T4x 就按 NPZ `events` 的顺序填回 artifact 类型。

### 4. `features/*.py` — 任务特征

| 模块 | 输出关键指标 | 论文里对应的「保真维度」 |
|:--|:--|:--|
| `s1_alpha.py` | EO/EC 各频段功率 + alpha_blocking_index | 宽频功率谱 |
| `s2_artifacts.py` | 每类伪迹 trial 数 + 峰峰 + 主导 ROI | （供伪迹库构建） |
| `s3_p300.py` | peak_amplitude_uV + peak_latency_s + 波形数组 | 时域瞬时 |
| `s3_ssvep.py` | SNR + ITPC + 2× 谐波 SNR | 窄带频谱 + 锁相 |
| `s4_mi.py` | μ/β ERD% per 通道 + 左右手 C3/C4 拉特化（scheme=motor_imagery） | MI 任务参考 |
| `s4_emotion.py` | FAA = log(α_right)-log(α_left) + theta/alpha/beta/gamma 功率 per 类别（scheme=emotion） | 情绪效价（approach / withdrawal） |

JSON 完整保留 raw 数据（PSD 频率轴/谱数组、ERP 时间轴/波形），方便
降噪模型跑完后直接 reload 比较保留率。

### 5. `qc.py` — 自动 QC HTML 报告

- 每个 sub-session 一个 section
- 数字部分用键值表渲染（数组超过 8 长度自动折叠）
- 图自动 base64 内嵌（不依赖外部 PNG 路径），单文件可直接转发
- 顶部带导航栏，跳转每个 Session

---

## 输出文件命名规范

所有产物名都满足同一个模式：

```text
<subject_id>_<session_kind>_<bdf_stem>_<start_s>s_<kind_suffix>.<ext>
```

例如：

```text
# 运动想象 scheme
derivatives/motor_imagery/Sub_01/03_epochs/Sub_01_S3_ODDBALL_0521_syx_20260521173744_104s_oddball-epo.fif
derivatives/motor_imagery/Sub_01/04_features/Sub_01_S3_ODDBALL_0521_syx_20260521173744_104s_s3_p300.json
derivatives/motor_imagery/Sub_01/03_epochs/Sub_01_S4_MI_0521_syx_20260521180851_1104s_mi-epo.fif
derivatives/motor_imagery/Sub_01/04_features/Sub_01_S4_MI_0521_syx_20260521180851_1104s_s4_mi.json

# 情绪识别 scheme
derivatives/emotion/Sub_01/03_epochs/Sub_01_S4_EMOTION_<rec>_<t>s_emotion-epo.fif       # 合并版（含 metadata.category）
derivatives/emotion/Sub_01/03_epochs/Sub_01_S4_EMOTION_<rec>_<t>s_emotion_negative-epo.fif
derivatives/emotion/Sub_01/03_epochs/Sub_01_S4_EMOTION_<rec>_<t>s_emotion_neutral-epo.fif
derivatives/emotion/Sub_01/03_epochs/Sub_01_S4_EMOTION_<rec>_<t>s_emotion_positive-epo.fif
derivatives/emotion/Sub_01/04_features/Sub_01_S4_EMOTION_<rec>_<t>s_s4_emotion.json
```

`start_s` 是这段 sub-session 在原始 BDF 内的起始时间（整数秒），用来
区分**同一 BDF 文件**里多次出现同一 Session kind（quick-test + 正式
采集）的情况。

---

## 添加新的特征模块

```python
# processing/pipeline/features/s3_p300_lateralized.py
def compute(epochs_by_cond):
    # 拿到 epoching.epoch_session3_oddball 的输出
    ...
    return {"left_pz_uV": ..., "right_pz_uV": ...}

def plot(result):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ...
    return fig
```

然后在 `run_pipeline.py:process_sub_session()` 对应分支里调一下并塞进 `summary["features"]`、`figures` 即可。其他模块不用动。

---

## 常见问题

1. **「未配对的 BDF 段」是什么？**  
   `--dry-run` 输出里出现「(no NPZ available)」的段落，通常是
   quick-test 的几十秒调试数据，或被试中途中止后没来得及保存 NPZ。
   建议保留作为对照，但不会进入特征计算（pipeline 自动跳过）。

2. **「BDF 里没看到 T41-T48」怎么办？**  
   iRecorder 5ms 间隔会吃掉一个 marker，这是已知硬件问题。pipeline
   会自动 fall back 到 NPZ events 的顺序回推每个 T31 对应的伪迹类型，
   不影响最终模板分类。建议下次实验把 `S2_ARTIFACT_ON` 和 `art_marker`
   的间隔从 5ms 提到 15-20ms。

3. **「SSVEP refresh_rate_hz != 60」**  
   `04_features/*_s3_ssvep.json` 里会保留 NPZ 的 `refresh_warning`。
   出现 80+ Hz 测得值说明 Windows 启用了 VRR/动态刷新率，SSVEP 实际
   频率会偏移，**这些 trial 不要进入论文最终结果**——但 pipeline 仍
   会给你完整产物方便诊断。

4. **「out-dir 已经存在，怎么强制重跑？」**  
   `python -m pipeline.run_pipeline --force`。默认会跳过已经存在的
   `*-preproc-raw.fif`，加 `--force` 重写。

5. **「真实被试数据有隐私顾虑」**  
   pipeline 只把数字摘要 (`04_features/*.json`) + 渲染好的 PNG 嵌入
   HTML，**不会在 derivatives 里**复制原始 BDF。`02_preproc/*.fif`
   依旧是脑电波形数据，与 BDF 同隐私级别——不要 commit 到 git。
   `derivatives/` 已被加进 `.gitignore`（如果还没，请检查）。

---

## 给降噪模型用的接口

训练降噪模型时，把 derivative 当 dataset：

```python
import mne
from pathlib import Path

# 加载某个 Session 的 epochs
ep = mne.read_epochs(
    "derivatives/Sub_01/03_epochs/Sub_01_S3_ODDBALL_..._oddball-epo.fif",
    preload=True
)
target_epochs = ep["T62"]   # 50 个 P300 trial，作为 clean signal

# 配对 S2 的伪迹模板
art_ep = mne.read_epochs(
    "derivatives/Sub_01/03_epochs/Sub_01_S2_..._单次眨眼-epo.fif"
)
# 随机叠加构造训练对
X_input = target_epochs.get_data() + lambda_ * art_ep.get_data()[:50]
Y_label = target_epochs.get_data()

# 降噪完后用 features 模块算保留率
from pipeline.features import s3_p300
denoised_epochs = ...        # 跑完模型的 mne.Epochs
denoised_p300 = s3_p300.compute_p300({"target": denoised_epochs["T62"],
                                       "standard": denoised_epochs["T61"]})
amp_retention = denoised_p300["peak_amplitude_uV"] / clean_p300["peak_amplitude_uV"]
```

这就是 `proposal.md` 里「策略 A + 策略 B」数据对构建的完整 Python 路径。
