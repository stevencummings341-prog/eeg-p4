"""Session 4 双手 MI：μ/β 频段的 ERD/ERS 强度差异 + C3/C4 拉特化指标。

ERD（event-related desynchronization）：运动想象期对侧感觉运动皮层
μ(8-13Hz) / β(13-30Hz) 功率相对 baseline 下降 → 用来定量「想象有没有产生
真正的神经活动」。

设计要点（2026-05-21 改）：
- baseline 必须落在 fixation 段（−2.5 ~ −1.0 s），避开 cue 期 anticipatory ERD。
- 每个 trial 的 ERD% 会做两层 outlier 拒绝再聚合：
    1. baseline bandpower 太小（< S4_MI_TRIAL_MIN_BASELINE_UV2 µV²）→ 弃用；
    2. 单 trial ERD% 绝对值 > S4_MI_TRIAL_ERD_CLIP_PCT → 弃用。
- 聚合统计同时输出 mean / median / trimmed_mean(10%)，避免少数极端 trial
  把 mean 拉散。median 才是教科书意义上的"典型 trial ERD"。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from .. import constants as C


def _bandpower_per_trial(epochs, picks, band, tmin, tmax) -> np.ndarray:
    """对每个 trial 在指定 (band, time window) 算 bandpower。

    返回 shape (n_ep, n_ch_in_picks) 的 µV²。
    """
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
    bp = psd.sum(axis=-1) * df * 1e12   # → µV²
    return bp


def _trim_mean(x: np.ndarray, frac: float) -> float:
    """两端各裁 frac 的 trimmed mean。x 是一维数组。"""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return float("nan")
    n = x.size
    k = int(np.floor(n * frac))
    if 2 * k >= n:
        return float(np.median(x))
    x_sorted = np.sort(x)
    return float(x_sorted[k:n - k].mean())


def _aggregate_trial_erd(
    erd_per_trial: np.ndarray,
    bp_base_per_trial: np.ndarray,
    *,
    min_base_uv2: float,
    clip_pct: float,
    trim_frac: float = 0.1,
) -> Tuple[np.ndarray, Dict]:
    """对 (n_trial, n_ch) 的 ERD% 矩阵做 outlier 拒绝 + 聚合统计。

    返回 (mask_kept, summary_dict)。mask_kept shape = (n_trial, n_ch)，True 表示
    该 trial × ch 进入了聚合。
    summary_dict 包含 mean / median / trimmed_mean / std / n_kept，全部 per-channel。
    """
    erd = np.asarray(erd_per_trial, dtype=float)        # (n_trial, n_ch)
    bp_base = np.asarray(bp_base_per_trial, dtype=float)  # (n_trial, n_ch)
    n_trial, n_ch = erd.shape

    bad_base = bp_base < min_base_uv2                  # 分母太小
    bad_clip = np.abs(erd) > clip_pct                  # ERD 绝对值过大 → 极端 trial
    bad = bad_base | bad_clip | ~np.isfinite(erd)
    erd_masked = np.where(bad, np.nan, erd)

    with np.errstate(all="ignore"):
        ch_mean = np.nanmean(erd_masked, axis=0)
        ch_median = np.nanmedian(erd_masked, axis=0)
        ch_std = np.nanstd(erd_masked, axis=0)
    ch_trim = np.array([_trim_mean(erd_masked[:, j], trim_frac) for j in range(n_ch)])
    n_kept = (~bad).sum(axis=0)

    summary = {
        "n_kept_per_ch": n_kept.tolist(),
        "n_excluded_base_too_small_per_ch": bad_base.sum(axis=0).tolist(),
        "n_excluded_clip_per_ch": bad_clip.sum(axis=0).tolist(),
        "mean_erd_pct_per_ch": _to_list(ch_mean),
        "median_erd_pct_per_ch": _to_list(ch_median),
        "trimmed_mean_erd_pct_per_ch": _to_list(ch_trim),
        "std_erd_pct_per_ch": _to_list(ch_std),
        "mean_erd_pct": float(np.nanmean(ch_mean)) if np.isfinite(ch_mean).any() else float("nan"),
        "median_erd_pct": float(np.nanmean(ch_median)) if np.isfinite(ch_median).any() else float("nan"),
        "trimmed_mean_erd_pct": float(np.nanmean(ch_trim)) if np.isfinite(ch_trim).any() else float("nan"),
    }
    return ~bad, summary


def _to_list(arr: np.ndarray) -> List[Optional[float]]:
    return [None if not np.isfinite(v) else float(v) for v in arr.tolist()]


def compute_mi_erd(epochs_by_class: Dict,
                   mu_band=C.S4_MI_MU_BAND,
                   beta_band=C.S4_MI_BETA_BAND,
                   baseline_win=C.S4_MI_ERD_BASELINE,
                   active_win=C.S4_MI_ERD_ACTIVE,
                   min_base_uv2: float = getattr(C, "S4_MI_TRIAL_MIN_BASELINE_UV2", 0.5),
                   clip_pct: float = getattr(C, "S4_MI_TRIAL_ERD_CLIP_PCT", 200.0)) -> Dict:
    """对每个 MI 类别算 C3/C4/Cz 的 ERD%（mean / median / trimmed_mean）。

    ERD% = (P_active - P_baseline) / P_baseline * 100，负值越大越好。
    """
    out: Dict = {
        "_meta": epochs_by_class.get("_meta", {}),
        "_config": {
            "baseline_win_s": list(baseline_win),
            "active_win_s": list(active_win),
            "mu_band_hz": list(mu_band),
            "beta_band_hz": list(beta_band),
            "min_base_uv2": min_base_uv2,
            "clip_pct": clip_pct,
        },
        "by_class": {},
    }
    for cls in ("left_hand", "right_hand"):
        ep = epochs_by_class.get(cls)
        if ep is None or len(ep) == 0:
            out["by_class"][cls] = {"status": "missing"}
            continue
        picks = [c for c in C.ROI_CENTRAL if c in ep.ch_names]
        if not picks:
            out["by_class"][cls] = {"status": "no_central_channel"}
            continue

        result_band: Dict[str, Dict] = {}
        for band_name, band in (("mu", mu_band), ("beta", beta_band)):
            bp_base = _bandpower_per_trial(ep, picks, band, baseline_win[0], baseline_win[1])
            bp_act = _bandpower_per_trial(ep, picks, band, active_win[0], active_win[1])
            erd_pct = (bp_act - bp_base) / (bp_base + 1e-12) * 100.0  # (n_ep, n_ch)
            _, agg = _aggregate_trial_erd(
                erd_pct, bp_base,
                min_base_uv2=min_base_uv2, clip_pct=clip_pct,
            )
            agg["channels"] = picks
            agg["baseline_uV2_mean"] = float(np.nanmean(bp_base))
            agg["active_uV2_mean"] = float(np.nanmean(bp_act))
            result_band[band_name] = agg
        out["by_class"][cls] = {
            "status": "ok",
            "n_trials_total": int(len(ep)),
            "bands": result_band,
        }

    # 算 C3/C4 拉特化（左右手在 C3 vs C4 上 μ ERD 的差异）—— 用 median 更稳
    try:
        l_mu = out["by_class"]["left_hand"]["bands"]["mu"]
        r_mu = out["by_class"]["right_hand"]["bands"]["mu"]
        chs_l = l_mu["channels"]
        chs_r = r_mu["channels"]
        lat: Dict[str, Dict] = {}
        for ch in ("C3", "C4"):
            if ch in chs_l and ch in chs_r:
                v_l_mean = l_mu["mean_erd_pct_per_ch"][chs_l.index(ch)]
                v_r_mean = r_mu["mean_erd_pct_per_ch"][chs_r.index(ch)]
                v_l_med = l_mu["median_erd_pct_per_ch"][chs_l.index(ch)]
                v_r_med = r_mu["median_erd_pct_per_ch"][chs_r.index(ch)]
                lat[ch] = {
                    "left_hand_erd_pct_mean": v_l_mean,
                    "right_hand_erd_pct_mean": v_r_mean,
                    "left_hand_erd_pct_median": v_l_med,
                    "right_hand_erd_pct_median": v_r_med,
                }
        # contralateral-dominance score (median 版)：右手 - 左手在 C3 应负、C4 应正
        if "C3" in lat and "C4" in lat:
            c3_diff = _safe_sub(lat["C3"].get("right_hand_erd_pct_median"),
                                lat["C3"].get("left_hand_erd_pct_median"))
            c4_diff = _safe_sub(lat["C4"].get("left_hand_erd_pct_median"),
                                lat["C4"].get("right_hand_erd_pct_median"))
            lat["contralateral_dominance_median"] = {
                "C3_right_minus_left_pct": c3_diff,
                "C4_left_minus_right_pct": c4_diff,
                "note": "两值均为负 → 对侧主导成立（左手→C4 更负、右手→C3 更负）",
            }
        out["lateralization"] = lat
    except Exception:
        out["lateralization"] = {}
    return out


def _safe_sub(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    try:
        return float(a) - float(b)
    except Exception:
        return None


def plot_mi_erd(result: Dict):
    """画 C3/C4/Cz 上 μ/β 的 ERD 条形图：median 主、mean 辅。"""
    import matplotlib.pyplot as plt
    by_class = result.get("by_class", {})
    classes = [c for c in ("left_hand", "right_hand") if by_class.get(c, {}).get("status") == "ok"]
    if not classes:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, cls in zip(axes, classes):
        info = by_class[cls]
        bands = info["bands"]
        chs = bands["mu"]["channels"]
        x = np.arange(len(chs))
        w = 0.38
        mu_med = _coerce(bands["mu"]["median_erd_pct_per_ch"])
        be_med = _coerce(bands["beta"]["median_erd_pct_per_ch"])
        mu_mean = _coerce(bands["mu"]["mean_erd_pct_per_ch"])
        be_mean = _coerce(bands["beta"]["mean_erd_pct_per_ch"])
        ax.bar(x - w/2, mu_med, w, label="μ (8-13Hz) median", color="#1f77b4")
        ax.bar(x + w/2, be_med, w, label="β (13-30Hz) median", color="#d62728")
        ax.plot(x - w/2, mu_mean, "o", color="#0b3d91", ms=6, label="μ mean")
        ax.plot(x + w/2, be_mean, "o", color="#8b0000", ms=6, label="β mean")
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(chs)
        n_kept_mu = bands["mu"].get("n_kept_per_ch", [])
        n_total = info.get("n_trials_total", "?")
        ax.set_title(f"{cls}  (n_total={n_total}, μ kept={n_kept_mu})")
        ax.set_ylabel("ERD %  (negative = desync)")
        ax.legend(fontsize=8)
        ax.grid(True, axis="y", alpha=0.3)
    fig.suptitle("S4 MI ERD — median (条) + mean (点)", y=1.0)
    fig.tight_layout()
    return fig


def _coerce(vals: List) -> List[float]:
    return [(np.nan if v is None else float(v)) for v in vals]
