"""Session 2：伪迹模板的基础统计。

不是为 paper 算指标，而是给 QC：
- 每类伪迹的 trial 数；
- 每类伪迹模板的峰峰幅度（μV）—— 用来确认伪迹真的被触发了；
- 哪个 ROI（额/颞/枕/...）幅度最大 —— 用来确认伪迹类型分类正确。
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from .. import constants as C


def compute_artifact_template_stats(epochs_by_name: Dict) -> Dict:
    """对每类 artifact Epochs 计算峰峰幅度 & 主导 ROI。"""
    out = {
        "_meta": epochs_by_name.get("_meta", {}),
        "artifacts": {},
    }
    for name, epochs in epochs_by_name.items():
        if name == "_meta" or epochs is None:
            continue
        try:
            n_ep = len(epochs)
        except Exception:
            continue
        if n_ep == 0:
            out["artifacts"][name] = {"n_trials": 0}
            continue

        data = epochs.get_data() * 1e6   # (n_ep, n_ch, n_t) in μV
        # 整段 (S2_EPOCH_TMIN→TMAX) 内的峰峰幅度
        ptp = data.max(axis=2) - data.min(axis=2)   # (n_ep, n_ch)
        mean_ptp_uv = float(np.mean(ptp))
        # 各 ROI 平均峰峰幅度
        roi_amp = {}
        for roi_name, roi_ch in (
            ("frontal", C.ROI_FRONTAL),
            ("temporal", C.ROI_TEMPORAL),
            ("central", C.ROI_CENTRAL),
            ("parietal", C.ROI_PARIETAL),
            ("occipital", C.ROI_OCCIPITAL),
        ):
            picks = [epochs.ch_names.index(ch) for ch in roi_ch if ch in epochs.ch_names]
            if picks:
                roi_amp[roi_name] = float(np.mean(ptp[:, picks]))
        dominant_roi = max(roi_amp.items(), key=lambda kv: kv[1])[0] if roi_amp else None

        out["artifacts"][name] = {
            "n_trials": int(n_ep),
            "mean_ptp_uV": mean_ptp_uv,
            "roi_ptp_uV": roi_amp,
            "dominant_roi": dominant_roi,
        }
    return out


def plot_artifact_butterfly(epochs_by_name: Dict, max_artifacts: int = 8):
    """对每类伪迹画一张 butterfly 平均图，用于 QC 报告。"""
    import matplotlib.pyplot as plt
    names = [n for n, e in epochs_by_name.items()
             if n != "_meta" and e is not None and len(e) > 0]
    names = names[:max_artifacts]
    n = len(names)
    if n == 0:
        return None
    cols = 2
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(11, 2.6 * rows), sharex=True)
    axes = np.atleast_1d(axes).flatten()
    for ax, name in zip(axes, names):
        ep = epochs_by_name[name]
        avg = ep.average()
        times = avg.times
        data = avg.data * 1e6     # μV
        ax.plot(times, data.T, alpha=0.3, linewidth=0.7)
        ax.axvline(0, color="k", lw=0.6)
        ax.set_title(f"{name}  (n={len(ep)})", fontsize=10)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("μV")
        ax.grid(True, alpha=0.3)
    for ax in axes[n:]:
        ax.axis("off")
    fig.tight_layout()
    return fig
