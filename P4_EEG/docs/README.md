# P4 项目文档目录

本目录收录 P4 的所有 **静态文档**：方案、论文蓝图、操作 SOP、调试复盘日志。
代码侧文档（`README.md`）仍留在各自的代码目录里，参见根 `README.md` 与 [`../ARCHITECTURE.md`](../ARCHITECTURE.md)。

## 文件列表

### 项目方案与蓝图

| 文档 | 主题 | 何时翻 |
|:---|:---|:---|
| [`proposal.md`](proposal.md) | P4 采集 SOP / Marker / 被试流程 / 数据流主方案 | 设计实验阶段；任何 SOP 更改前先读 |
| [`paper_blueprint.md`](paper_blueprint.md) | Paper 1 论文蓝图：叙事 / 实验矩阵 / 当前完成度 | 想 paper 故事线、查"已实现/规划中/假设结果" |

### 操作 SOP

| 文档 | 主题 | 何时翻 |
|:---|:---|:---|
| [`实验操作指南.md`](实验操作指南.md) | 上机前后被试侧 + 主试侧通用流程检查清单 | 每次预实验 / 正式实验前 |
| [`真实设备连接与正式采集指南.md`](真实设备连接与正式采集指南.md) | iRecorder 放大器、Trigger 串口、相机的连接与调试 | 真实设备 + Trigger 联调前 |

### 复盘日志（按时间倒序）

| 文档 | 主题 |
|:---|:---|
| [`changelog/2026-05-19_全流程稳定性修复.md`](changelog/2026-05-19_全流程稳定性修复.md) | SSVEP 刷新率自适应、S2 水平眼动小球、ESC 立即退出等修复 |
| [`changelog/Trigger打标联调复盘.md`](changelog/Trigger打标联调复盘.md) | iRecorder Trigger / Marker 字节协议联调结论 |

## 与代码侧 README 的关系

- 这里：**为什么这么做** + **不变的 SOP**。
- 代码侧 README（`experiment/README.md`、`experiment/video/README.md`、`processing/README.md`、`p8_mi_car/experiment/README.md`）：**怎么跑** + 当前命令行入口。

如果两边不一致，**以本目录的 SOP 为准**，并修复代码侧 README。
