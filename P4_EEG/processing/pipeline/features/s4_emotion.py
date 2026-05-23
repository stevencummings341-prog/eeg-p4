"""Session 4 情绪识别 — 频段功率 + Frontal Alpha Asymmetry (FAA)。

设计动机：
- 情绪 EEG 的标准量化指标是 **FAA (Frontal Alpha Asymmetry)**：
      FAA = log(α_right) - log(α_left)
  右额叶 alpha 抑制相对左侧越深 → FAA 越正 → approach motivation / 正性效价；
  反之 FAA 越负 → withdrawal motivation / 负性效价 (Davidson 1992 经典模型)。
- 同时输出 theta/alpha/beta/gamma 各频段在代表通道上的功率，便于
  跨被试 / 跨类别 (negative/neutral/positive) 横向比较。
- 与 S4 MI 风格保持一致：先按 trial 算，再做 outlier 拒绝，再聚合 mean / median。

输出层级：
    by_category[<negative|neutral|positive>]
        n_trials_total / n_trials_kept
        bands[<band_name>]
            channels                 : list[str]
            absolute_power_uV2_per_ch: list[float]    # active 窗 mean
            log_power_per_ch         : list[float]    # log(absolute)
            relative_change_pct_per_ch: list[float]   # (active - baseline) / baseline * 100
        FAA_alpha
            mean / median / std
            per_pair[<F4-F3 / AF4-AF3 / right-left_pooled>]
                value_per_trial      : list[float]
                mean / median
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from .. import constants as C


# --------------------------------------------------------------------------- #
# 帮助函数
# --------------------------------------------------------------------------- #
def _bandpower_per_trial(epochs, picks, band, tmin, tmax) -> np.ndarray:
    """对每个 trial 在 (band, time window) 算 bandpower，返回 (n_ep, n_ch) µV²。"""
    if epochs is None or len(epochs) == 0 or not picks:
        return np.zeros((0, len(picks) if picks else 0), dtype=float)
    sfreq = epochs.info["sfreq"]
    ep = epochs.copy().crop(tmin=tmin, tmax=tmax)
    n_times_per_ep = ep.get_data().shape[-1]
    n_fft = min(int(1.0 * sfreq), n_times_per_ep)
    n_fft = max(n_fft, 16)
    spectrum = ep.compute_psd(
        method="welch", fmin=band[0], fmax=band[1],
        n_fft=n_fft, n_per_seg=n_fft,
        picks=picks, verbose="ERROR",
    )
    psd, freqs = spectrum.get_data(return_freqs=True)  # (n_ep, n_ch, n_f)
    df = float(np.diff(freqs).mean()) if len(freqs) > 1 else 1.0
    # PSD 单位是 V²/Hz，乘以带宽 → V²；再 *1e12 → µV²
    return psd.sum(axis=-1) * df * 1e12


def _safe_log(x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return np.log(np.clip(x, eps, None))


def _to_list(arr) -> List[Optional[float]]:
    out = []
    for v in np.asarray(arr).ravel().tolist():
        try:
            f = float(v)
            out.append(None if not np.isfinite(f) else f)
        except (TypeError, ValueError):
            out.append(None)
    return out


def _faa_per_trial(epochs, right_picks: List[str], left_picks: List[str],
                   win: Tuple[float, float]) -> Tuple[np.ndarray, List[str], List[str]]:
    """对每个 trial 计算 alpha bandpower 的左/右额叶平均，然后做 log 差。

    返回 (faa_per_trial, used_right, used_left)。
    若某侧通道全缺则返回长度 0 的数组 + 空 picks。
    """
    used_right = [c for c in right_picks if c in epochs.ch_names]
    used_left = [c for c in left_picks if c in epochs.ch_names]
    if not used_right or not used_left:
        return np.zeros((0,), dtype=float), used_right, used_left

    band = C.S4_EMOTION_BANDS["alpha"]
    bp_r = _bandpower_per_trial(epochs, used_right, band, win[0], win[1])  # (n, n_r)
    bp_l = _bandpower_per_trial(epochs, used_left, band, win[0], win[1])   # (n, n_l)
    if bp_r.size == 0 or bp_l.size == 0:
        return np.zeros((0,), dtype=float), used_right, used_left
    # 各自 channel 平均，再 log 差
    mean_r = bp_r.mean(axis=1)
    mean_l = bp_l.mean(axis=1)
    faa = _safe_log(mean_r) - _safe_log(mean_l)
    return faa, used_right, used_left


def _trial_stats(values: np.ndarray) -> Dict[str, Optional[float]]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"n": 0, "mean": None, "median": None, "std": None}
    return {
        "n":      int(values.size),
        "mean":   float(np.mean(values)),
        "median": float(np.median(values)),
        "std":    float(np.std(values, ddof=0)),
    }


# --------------------------------------------------------------------------- #
# 主特征计算
# --------------------------------------------------------------------------- #
def compute_emotion_features(epochs_by_category: Dict,
                             bands: Dict[str, Tuple[float, float]] = None,
                             active_win: Tuple[float, float] = C.S4_EMOTION_ACTIVE_WIN,
                             baseline_win: Tuple[float, float] = C.S4_EMOTION_BASELINE_WIN) -> Dict:
    """对 negative / neutral / positive 三类 epochs 分别算频段功率 + FAA。"""
    bands = bands or C.S4_EMOTION_BANDS

    out: Dict = {
        "_meta": epochs_by_category.get("_meta", {}),
        "_config": {
            "active_win_s":   list(active_win),
            "baseline_win_s": list(baseline_win),
            "bands_hz":       {k: list(v) for k, v in bands.items()},
            "frontal_left":   list(C.ROI_EMOTION_FRONTAL_LEFT),
            "frontal_right":  list(C.ROI_EMOTION_FRONTAL_RIGHT),
            "broad_channels": list(C.ROI_EMOTION_BROAD),
        },
        "by_category": {},
    }

    for cat in ("negative", "neutral", "positive"):
        ep = epochs_by_category.get(cat)
        if ep is None or len(ep) == 0:
            out["by_category"][cat] = {"status": "missing"}
            continue

        broad_picks = [c for c in C.ROI_EMOTION_BROAD if c in ep.ch_names]
        cat_block: Dict = {
            "status":            "ok",
            "n_trials_total":    int(len(ep)),
            "channels_used":    broad_picks,
            "bands":             {},
        }

        for band_name, band in bands.items():
            if not broad_picks:
                cat_block["bands"][band_name] = {"status": "no_eeg_channel"}
                continue
            bp_act  = _bandpower_per_trial(ep, broad_picks, band, active_win[0], active_win[1])
            bp_base = _bandpower_per_trial(ep, broad_picks, band, baseline_win[0], baseline_win[1])
            # 取通道均值（在该频段上）
            abs_active   = np.nanmean(bp_act, axis=0)        # (n_ch,)
            log_active   = np.nanmean(_safe_log(bp_act), axis=0)
            rel_pct = (bp_act - bp_base) / (bp_base + 1e-12) * 100.0
            rel_mean = np.nanmean(rel_pct, axis=0)
            cat_block["bands"][band_name] = {
                "channels":                broad_picks,
                "absolute_power_uV2_per_ch": _to_list(abs_active),
                "log_power_per_ch":          _to_list(log_active),
                "relative_change_pct_per_ch": _to_list(rel_mean),
                "absolute_power_uV2_mean":    float(np.nanmean(abs_active)) if np.isfinite(abs_active).any() else None,
                "log_power_mean":             float(np.nanmean(log_active)) if np.isfinite(log_active).any() else None,
                "relative_change_pct_mean":   float(np.nanmean(rel_mean)) if np.isfinite(rel_mean).any() else None,
            }

        # ---- Frontal Alpha Asymmetry ----
        faa_block: Dict = {}
        # 不同电极对的 FAA：F4-F3, AF4-AF3，以及"右额叶池化-左额叶池化"
        pairs = [
            ("F4_minus_F3",     ["F4"],   ["F3"]),
            ("AF4_minus_AF3",   ["AF4"],  ["AF3"]),
            ("right_minus_left_pooled",
             list(C.ROI_EMOTION_FRONTAL_RIGHT),
             list(C.ROI_EMOTION_FRONTAL_LEFT)),
        ]
        all_faa_values: List[float] = []
        for pair_name, right_picks, left_picks in pairs:
            faa, used_r, used_l = _faa_per_trial(ep, right_picks, left_picks, active_win)
            stats = _trial_stats(faa)
            faa_block[pair_name] = {
                "right_channels": used_r,
                "left_channels":  used_l,
                "value_per_trial": _to_list(faa) if faa.size <= 200 else _to_list(faa[:200]),
                **stats,
            }
            if pair_name == "right_minus_left_pooled":
                all_faa_values = faa.tolist()

        # pooled 版作为总体 FAA 代表
        pooled_stats = _trial_stats(np.asarray(all_faa_values, dtype=float))
        cat_block["FAA_alpha"] = {
            "pooled_summary": pooled_stats,
            "per_pair":       faa_block,
            "note": "log(α_right) - log(α_left)；正值偏向 approach/正性效价。",
        }

        out["by_category"][cat] = cat_block

    # 跨类别对比摘要：FAA 的 (positive - negative)、(positive - neutral) 差异
    try:
        faa_means = {}
        for cat in ("negative", "neutral", "positive"):
            blk = out["by_category"].get(cat, {})
            faa = blk.get("FAA_alpha", {}).get("pooled_summary", {})
            mean = faa.get("mean")
            if mean is not None:
                faa_means[cat] = float(mean)
        contrast = {}
        if "positive" in faa_means and "negative" in faa_means:
            contrast["positive_minus_negative"] = faa_means["positive"] - faa_means["negative"]
        if "positive" in faa_means and "neutral" in faa_means:
            contrast["positive_minus_neutral"] = faa_means["positive"] - faa_means["neutral"]
        if "neutral" in faa_means and "negative" in faa_means:
            contrast["neutral_minus_negative"] = faa_means["neutral"] - faa_means["negative"]
        out["faa_pooled_mean_by_category"] = faa_means
        out["faa_contrasts"] = contrast
    except Exception:
        out["faa_contrasts"] = {}

    return out


# --------------------------------------------------------------------------- #
# 画图
# --------------------------------------------------------------------------- #
def plot_emotion_summary(result: Dict):
    """两个面板：
       左：FAA per category（条 = mean、误差 = std；红参考线 0）
       右：alpha 绝对功率 per category（柱）+ theta / beta / gamma 折线
    """
    import matplotlib.pyplot as plt

    by_cat = result.get("by_category", {})
    cats = [c for c in ("negative", "neutral", "positive")
            if by_cat.get(c, {}).get("status") == "ok"]
    if not cats:
        return None
    label_cn = {c: C.S4_EMOTION_LABEL_TO_CN[c] for c in cats}

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))

    # ---- FAA ----
    ax = axes[0]
    means = []
    stds = []
    for c in cats:
        s = by_cat[c]["FAA_alpha"]["pooled_summary"]
        means.append(s.get("mean") or 0.0)
        stds.append(s.get("std") or 0.0)
    x = np.arange(len(cats))
    colors = {"negative": "#d62728", "neutral": "#7f7f7f", "positive": "#2ca02c"}
    ax.bar(x, means, yerr=stds, color=[colors[c] for c in cats], alpha=0.85,
           ecolor="#333", capsize=4)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{c}\n{label_cn[c]}" for c in cats])
    ax.set_ylabel("FAA = log(α_right) − log(α_left)")
    ax.set_title("Frontal Alpha Asymmetry (pooled right-left)")
    ax.grid(True, axis="y", alpha=0.3)
    # n 标签
    for xi, c in zip(x, cats):
        n = by_cat[c]["FAA_alpha"]["pooled_summary"].get("n", 0)
        ax.text(xi, ax.get_ylim()[0] * 0.9 if ax.get_ylim()[0] < 0 else 0.02,
                f"n={n}", ha="center", fontsize=8, color="#555")

    # ---- 频段功率 ----
    ax = axes[1]
    band_names = list(result.get("_config", {}).get("bands_hz", C.S4_EMOTION_BANDS).keys())
    width = 0.8 / max(len(band_names), 1)
    band_colors = {"theta": "#9467bd", "alpha": "#1f77b4",
                   "beta": "#ff7f0e", "gamma": "#8c564b"}
    for bi, b in enumerate(band_names):
        vals = []
        for c in cats:
            v = by_cat[c]["bands"].get(b, {}).get("absolute_power_uV2_mean")
            vals.append(v if v is not None else np.nan)
        ax.bar(x + (bi - (len(band_names) - 1) / 2) * width, vals, width,
               label=b, color=band_colors.get(b, None), alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels([label_cn[c] for c in cats])
    ax.set_ylabel("Absolute bandpower (µV²)")
    ax.set_title("Bandpower by emotion category")
    ax.legend(fontsize=8, loc="best")
    ax.grid(True, axis="y", alpha=0.3)

    fig.suptitle("S4 Emotion — FAA & Bandpower", y=1.02)
    fig.tight_layout()
    return fig
