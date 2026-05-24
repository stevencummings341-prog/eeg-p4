# CSBrain 论文与运动想象基准数据记录

> 来源：`C:\Users\SLAI\Downloads\csbrain.pdf` + `EEG_MI_Experiment_Data.xlsx`
> 记录日期：2026-05-24

## 论文速览

**标题**：CSBrain: A Cross-scale Spatiotemporal Brain Foundation Model for EEG Decoding

**作者**：Yuchen Zhou, Jiamin Wu, Zichen Ren, Zhouheng Yao, Weiheng Lu, Kunyu Peng, Qihao Zheng, Chunfeng Song, Wanli Ouyang, Chao Gou

**机构**：Shanghai AI Laboratory, Sun Yat-sen University, CUHK, KIT

**发表**：arXiv:2506.23075v1 (2025-06-29)，Under Review

### 核心贡献

CSBrain 是一个跨尺度时空脑电基础模型，针对现有 EEG 基础模型的三大缺陷提出改进：

1. **尺度无关的 Tokenization** → 提出 **Cross-scale Spatiotemporal Tokenization (CST)**，在局部时间窗口和解剖脑区内聚合多尺度特征为紧凑的 scale-aware token。
2. **结构无关的 Dense Attention** → 提出 **Structured Sparse Attention (SSA)**，分 Inter-window Attention 和 Inter-region Attention 两步，以线性复杂度捕捉跨窗口/跨脑区的长程依赖，避免伪相关。
3. **CST 与 SSA 交替堆叠 L 层**，逐步融合跨尺度时空依赖。

### 预训练

- 数据：TUEG (Temple University Hospital EEG)，110 万+ 段，超 9000 小时
- 方法：Masked Autoencoding (MAE)，mask ratio = 50%
- 算力：4× NVIDIA A100，40 epochs，约 101 小时
- 信号预处理：0.3–75Hz 带通 → 60Hz 陷波 → 重采样 200Hz → 归一化 ±100μV

### 下游评估规模

**11 类任务 × 16 个公开数据集**，是目前 EEG 基础模型最全面的评估之一：

| 任务类型 | 数据集 |
|:---|:---|
| 运动想象分类 | BCIC-IV-2a, PhysioNet-MI, SHU-MI |
| 情绪识别 | FACED, SEED-V |
| 癫痫检测 | CHB-MIT, Siena |
| 睡眠分期 | ISRUC, HMC |
| 想象言语分类 | BCIC2020-3 |
| 警觉度估计 | SEED-VIG |
| 心理压力检测 | MentalArithmetic |
| 精神障碍诊断 | Mumtaz2016 |
| 事件类型分类 | TUEV |
| 异常检测 | TUAB |
| 慢波事件分类 | TUSL |

### 关键结论

- CSBrain 在几乎所有任务上达到 SOTA，Macro-average 超越 CbraMod +3.35%、LaBraM +3.98%、BIOT +7.73%。
- 跨尺度 Tokenization 消融：多尺度 (K=3) + 交替堆叠显著优于单尺度 (K=1)；在运动想象任务上提升 10.8%–20.7%。
- SSA vs Dense Attention：SSA 在性能和效率上双赢（TUEV 上 B-Acc +8.1%）。
- Topography 可视化验证：运动想象激活高度局域化（对侧运动皮层 ERD/ERS），情绪和想象言语则呈广泛分布式激活。

---

## 运动想象基准数据

> 以下数据来自 Excel 表格，是 CSBrain 论文 Table 2 中运动想象部分的核心指标。

### 数据集概览

| 数据集 | 采样率 | 通道数 | Trial 时长 | 样本数 | 被试数 | 类别 |
|:---|:---|:---|:---|:---|:---|:---|
| BCIC-IV-2a | 250 Hz | 22 | 4s | 5,184 | 9 | 4-class (L/R hand, feet, tongue) |
| PhysioNet-MI | 160 Hz | 64 | 4s | 9,837 | 109 | 4-class (L/R fist, both fists, both feet) |
| SHU-MI | 250 Hz | 32 | 4s | 11,988 | 25 | 2-class (L/R hand) |

### 模型性能对比

#### BCIC-IV-2a (4-class MI)

| 模型 | B-Acc | F1-W |
|:---|:---|:---|
| EEGNet | 0.4482 | 0.4226 |
| Conformer | 0.4696 | 0.4533 |
| SPaRCNet | 0.4635 | 0.4432 |
| ContraWR | 0.4678 | 0.4413 |
| CNN-Trans | 0.4600 | 0.4460 |
| FFCL | 0.4470 | 0.4238 |
| ST-Trans | 0.4575 | 0.4471 |
| BIOT | 0.4748 | 0.4607 |
| LaBraM | 0.4758 | 0.4666 |
| CbraMod | 0.5138 | 0.4984 |
| **CSBrain** | **0.5657** | **0.5637** |

#### SHU-MI (2-class MI)

| 模型 | B-Acc | AUROC |
|:---|:---|:---|
| EEGNet | 0.5889 | 0.6283 |
| Conformer | 0.5900 | 0.6351 |
| SPaRCNet | 0.5978 | 0.6431 |
| ContraWR | 0.5873 | 0.6273 |
| CNN-Trans | 0.5975 | 0.6343 |
| FFCL | 0.5692 | 0.6326 |
| ST-Trans | 0.5992 | 0.6431 |
| BIOT | 0.6179 | 0.6609 |
| LaBraM | 0.6166 | 0.6604 |
| CbraMod | 0.6370 | 0.6988 |
| **CSBrain** | **0.6417** | **0.7200** |

#### PhysioNet-MI (4-class MI)

| 模型 | B-Acc | F1-W |
|:---|:---|:---|
| EEGNet | 0.5814 | 0.5796 |
| Conformer | 0.6049 | 0.6062 |
| SPaRCNet | 0.5932 | 0.5937 |
| ContraWR | 0.5892 | 0.5918 |
| CNN-Trans | 0.6053 | 0.6041 |
| FFCL | 0.5726 | 0.5701 |
| ST-Trans | 0.6035 | 0.6053 |
| BIOT | 0.6153 | 0.6158 |
| LaBraM | 0.6173 | 0.6177 |
| CbraMod | 0.6174 | 0.6179 |
| **CSBrain** | **0.6304** | **0.6308** |

---

## 对我方 P4 项目的参考价值

### 1. 性能基线

如果后续用 P4 采集的 S4 离线 MI 数据训练模型，以上三表的数值可以作为参考上限（这些是公开大规模数据集的 SOTA）。特别关注：

- **BCIC-IV-2a** 与 P4 最相关（4-class MI，22ch，250Hz），其 SOTA B-Acc 约 0.57。P4 S4 目前只有 8 通道且未经大规模预训练，直接对标不现实，但可作为远期目标。
- **SHU-MI** 是 2-class (L/R hand)，与 P4 S4 的左右手 MI 设定一致，其 SOTA AUROC 0.72。

### 2. 架构思路可借鉴

CSBrain 几个设计要点与 P4 降噪目标有交集：

- **CST 多尺度卷积核**：类似思路可用于我们的 denoiser——不同尺度的时序卷积核分别捕捉瞬态伪迹（眼电尖峰）和慢变漂移。
- **SSA 结构化稀疏注意力**：按脑区和时间窗口分组做 attention，避免全连接带来的噪声关联。这个思想与 P4 的"从 S2 独立采集伪迹模板"思路互补——一个靠数据组织，一个靠架构约束。
- **预训练策略**：Masked Autoencoding 在 EEG 上有效。若后续积累足够的 P4 数据，可考虑在 TUEG 预训练 CSBrain 权重上做 S4 MI 的微调。

### 3. 对比模型清单

论文覆盖了 10 个代表性 baseline（7 个任务特定 + 3 个基础模型），可以作为 P4 后续建模时的方法参照系：

- **任务特定**：EEGNet, EEGConformer, SPaRCNet, ContraWR, CNN-Transformer, FFCL, ST-Transformer
- **基础模型**：BIOT, LaBraM, CBraMod

### 4. 脑区地形图参考

论文 Grad-CAM 可视化（Figure 6）显示左手运动想象激活对侧运动皮层（C3/C4 附近），与 P4 的 8 通道配置（含 C3、C4）一致，验证了我们的通道布局对 MI 任务具备足够的空间覆盖。
