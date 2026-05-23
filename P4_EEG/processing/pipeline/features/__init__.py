"""任务特征提取（一个 Session 一份）。

设计原则：
- 每个模块独立可调用，输入是该 Session 的 epochs dict (epoching 模块产出)，
  输出是一个 dict + 若干 matplotlib Figure（QC 报告用）。
- 不要在这里做参数化／可调超参泛滥；阈值常量都放在 pipeline.constants。
"""

from __future__ import annotations

# 让 matplotlib 显示中文（伪迹类别名、被试 ID 都可能是中文）。
# 找不到合适字体时静默失败，避免阻塞 pipeline。
def _configure_cjk_font() -> None:
    try:
        import matplotlib
        import matplotlib.font_manager as fm
        candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                      "Source Han Sans SC", "PingFang SC", "WenQuanYi Zen Hei"]
        installed = {f.name for f in fm.fontManager.ttflist}
        chosen = next((c for c in candidates if c in installed), None)
        if chosen:
            matplotlib.rcParams["font.family"] = ["sans-serif"]
            matplotlib.rcParams["font.sans-serif"] = [chosen] + matplotlib.rcParams["font.sans-serif"]
            matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass


_configure_cjk_font()
