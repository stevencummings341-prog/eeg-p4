"""Session 1：Alpha 阻断指数。

输入：epoching.epoch_session1 产出的 {"EO": Epochs, "EC": Epochs}。
输出：
  {
    "alpha_band": [8, 13],
    "channels": [...],
    "ec_alpha_uv2": ...,
    "eo_alpha_uv2": ...,
    "alpha_blocking_index": ...,    # (EC - EO) / EC, 应 > 0.3
    "ec_band_power": {...},         # delta/theta/alpha/beta 各带功率
    "eo_band_power": {...},
  }
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from .. import constants as C


_BANDS = {
    "delta": (0.5, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta":  (13.0, 30.0),
}


def compute_alpha_blocking(eo_epochs, ec_epochs, channels: Optional[List[str]] = None) -> Dict:
    """计算 EO/EC 各通道在 4 个频带的平均功率 + Alpha 阻断指数。"""
    import mne
    channels = channels or [c for c in C.ROI_OCCIPITAL]

    if eo_epochs is None or ec_epochs is None:
        return {"status": "missing", "channels": channels}

    picks = [ch for ch in channels if ch in eo_epochs.ch_names]
    if not picks:
        return {"status": "no_target_channel", "channels": channels}

    def _band_power(ep):
        """返回 dict[band -> mean power (uV^2)] 在指定通道上。"""
        # epoch 长度限制 n_fft，不然合成数据 / quick test 短 epoch 会触发
        # ValueError(n_fft > n_times)
        n_times_per_ep = ep.get_data().shape[-1]
        n_fft = min(int(C.S1_PSD_WIN_S * ep.info["sfreq"]), n_times_per_ep)
        spectrum = ep.compute_psd(
            method="welch", fmin=0.5, fmax=40.0,
            n_fft=n_fft,
            n_per_seg=n_fft,
            n_overlap=int(n_fft * C.S1_PSD_OVERLAP),
            picks=picks, verbose="ERROR",
        )
        psd_data, freqs = spectrum.get_data(return_freqs=True)  # (n_ep, n_ch, n_f)
        # 平均 epoch 维和通道维
        psd_mean = psd_data.mean(axis=(0, 1))  # → V^2/Hz
        out = {}
        for band, (lo, hi) in _BANDS.items():
            mask = (freqs >= lo) & (freqs < hi)
            # 积分得到带内功率（uV^2）
            if not mask.any():
                out[band] = float("nan")
                continue
            df = float(np.diff(freqs).mean())
            band_power = float(psd_mean[mask].sum() * df * 1e12)  # V^2 → uV^2
            out[band] = band_power
        return out, freqs.tolist(), (psd_mean * 1e12).tolist()

    eo_bp, freqs, eo_psd = _band_power(eo_epochs)
    ec_bp, _, ec_psd = _band_power(ec_epochs)

    ec_alpha = ec_bp.get("alpha", float("nan"))
    eo_alpha = eo_bp.get("alpha", float("nan"))
    if ec_alpha and ec_alpha > 0:
        alpha_blocking = (ec_alpha - eo_alpha) / ec_alpha
    else:
        alpha_blocking = float("nan")

    return {
        "status": "ok",
        "channels": picks,
        "alpha_band": list(C.S1_ALPHA_BAND),
        "eo_band_power_uV2": eo_bp,
        "ec_band_power_uV2": ec_bp,
        "alpha_blocking_index": float(alpha_blocking),
        "n_eo_epochs": int(len(eo_epochs)),
        "n_ec_epochs": int(len(ec_epochs)),
        "psd_freqs_hz": freqs,
        "psd_eo_uV2_per_Hz": eo_psd,
        "psd_ec_uV2_per_Hz": ec_psd,
    }


def plot_psd_comparison(result: Dict, ax=None):
    """画 EO vs EC 的 PSD 对比图，返回 figure。"""
    import matplotlib.pyplot as plt
    if result.get("status") != "ok":
        return None
    fig = None
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 4))
    freqs = np.array(result["psd_freqs_hz"])
    eo = np.array(result["psd_eo_uV2_per_Hz"])
    ec = np.array(result["psd_ec_uV2_per_Hz"])
    ax.semilogy(freqs, eo, label="EO (eyes open)", color="#1f77b4")
    ax.semilogy(freqs, ec, label="EC (eyes closed)", color="#d62728")
    ax.axvspan(8, 13, color="orange", alpha=0.18, label="Alpha 8-13Hz")
    ax.set_xlim(0.5, 40)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("PSD (μV²/Hz)")
    ax.set_title(
        f"S1 Alpha blocking @ {','.join(result['channels'])}  "
        f"(index={result['alpha_blocking_index']:.2f})"
    )
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    return fig
