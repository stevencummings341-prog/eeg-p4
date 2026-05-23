"""Session 3 Oddball：P300 振幅 / 潜伏期 / 相关系数。

paper 里这个 Session 是「时域瞬时特征」的验证锚点。本模块算的是 raw 信号
上的 P300 (用作 baseline)；降噪模型跑完后再用同样的函数算降噪信号上的
P300，做 振幅保留率 / 潜伏期漂移 / 波形相关系数 的对比。
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from .. import constants as C


def compute_p300(epochs_by_cond: Dict, channels: Optional[List[str]] = None) -> Dict:
    """epochs_by_cond 至少要有 "standard" 和 "target"。"""
    standard = epochs_by_cond.get("standard")
    target = epochs_by_cond.get("target")
    if standard is None or target is None:
        return {"status": "missing"}

    chs = channels or C.S3_ODD_P300_CHANNELS
    picks = [c for c in chs if c in target.ch_names]
    if not picks:
        return {"status": "no_target_channel"}

    avg_std = standard.average(picks=picks)
    avg_tgt = target.average(picks=picks)

    times = avg_tgt.times
    win_lo, win_hi = C.S3_ODD_P300_WIN
    win_mask = (times >= win_lo) & (times <= win_hi)
    if not win_mask.any():
        return {"status": "p300_window_outside_epoch"}

    # 通道平均（midline P300）
    target_wave = avg_tgt.data.mean(axis=0) * 1e6     # → μV
    std_wave = avg_std.data.mean(axis=0) * 1e6
    diff_wave = target_wave - std_wave

    peak_idx_local = int(np.argmax(diff_wave[win_mask]))
    peak_time = float(times[win_mask][peak_idx_local])
    peak_amp = float(diff_wave[win_mask][peak_idx_local])

    return {
        "status": "ok",
        "channels": picks,
        "p300_window_s": list(C.S3_ODD_P300_WIN),
        "peak_amplitude_uV": peak_amp,
        "peak_latency_s": peak_time,
        "n_standard_kept": int(len(standard)),
        "n_target_kept": int(len(target)),
        "times_s": times.tolist(),
        "wave_target_uV": target_wave.tolist(),
        "wave_standard_uV": std_wave.tolist(),
        "wave_diff_uV": diff_wave.tolist(),
    }


def plot_p300(result: Dict, ax=None):
    import matplotlib.pyplot as plt
    if result.get("status") != "ok":
        return None
    fig = None
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4))
    times = np.array(result["times_s"])
    ax.plot(times, result["wave_standard_uV"], label="Standard (N=%d)" % result["n_standard_kept"], color="#1f77b4")
    ax.plot(times, result["wave_target_uV"], label="Target (N=%d)" % result["n_target_kept"], color="#d62728")
    ax.plot(times, result["wave_diff_uV"], label="Target − Standard", color="black", lw=1.4)
    win = result["p300_window_s"]
    ax.axvspan(win[0], win[1], color="orange", alpha=0.18, label=f"P300 search win ({win[0]}-{win[1]}s)")
    ax.axvline(result["peak_latency_s"], color="orange", ls="--",
               label=f"peak {result['peak_amplitude_uV']:.1f} μV @ {result['peak_latency_s']*1000:.0f} ms")
    ax.axhline(0, color="k", lw=0.6)
    ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("μV")
    ax.set_title(f"S3 Oddball P300 @ {','.join(result['channels'])}")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    return fig
