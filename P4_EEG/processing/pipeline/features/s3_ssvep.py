"""Session 3 SSVEP：SNR + ITPC，覆盖窄带频谱 + 相位锁相精度。

paper 里这个 Session 同时考验「窄带频谱」和「锁相」两件事，所以这里既
算频域 SNR（目标频率峰功率 / 邻近频带平均功率），也算 ITPC（试次间相
位一致性）。降噪模型评估时调同样的函数比较保留率。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from .. import constants as C


def _fft_per_epoch(epochs, picks):
    """对每个 epoch 做单频率分辨率的 FFT，返回 (freqs, complex_spectrum)。

    complex_spectrum shape: (n_ep, n_ch, n_freq)
    """
    data = epochs.get_data(picks=picks)              # (n_ep, n_ch, n_t)
    sfreq = epochs.info["sfreq"]
    n_t = data.shape[-1]
    # 用整个 epoch 长度做 FFT（不加 hanning，便于精确读频）
    spec = np.fft.rfft(data, n=n_t, axis=-1)
    freqs = np.fft.rfftfreq(n_t, d=1 / sfreq)
    return freqs, spec


def compute_ssvep_metrics(epochs_by_freq: Dict,
                          channels: Optional[List[str]] = None,
                          drop_dropped_frames_above: int = 5) -> Dict:
    """对每个目标频率算 SNR + ITPC。

    Args:
        epochs_by_freq: epoching.epoch_session3_ssvep 的产出
                        (键是 "6Hz"/"8.57Hz"/"10Hz"/"15Hz")。
        channels: 用于积分的通道（默认枕区）。
        drop_dropped_frames_above: 单 trial 丢帧数 > 此值即剔除该 trial。
    """
    channels = channels or C.ROI_OCCIPITAL
    out = {"by_freq": {}, "_meta": epochs_by_freq.get("_meta", {})}

    for label, target_hz in C.S3_SSVEP_FREQS.items():
        ep = epochs_by_freq.get(label)
        if ep is None or len(ep) == 0:
            out["by_freq"][label] = {"status": "missing", "target_hz": target_hz}
            continue

        picks = [c for c in channels if c in ep.ch_names]
        if not picks:
            out["by_freq"][label] = {"status": "no_target_channel", "target_hz": target_hz}
            continue

        # 剔除高丢帧 trial
        if ep.metadata is not None and "dropped_frames" in ep.metadata.columns:
            keep_mask = ep.metadata["dropped_frames"] <= drop_dropped_frames_above
            kept = int(keep_mask.sum())
            ep_use = ep[list(np.where(keep_mask.to_numpy())[0])] if kept < len(ep) else ep
        else:
            ep_use = ep
            kept = len(ep)

        freqs, spec = _fft_per_epoch(ep_use, picks)
        n_ep, n_ch, n_f = spec.shape
        amp = np.abs(spec)                  # (n_ep, n_ch, n_f)

        # 算 SNR (target ± exclude 不算邻近)
        target_idx = int(np.argmin(np.abs(freqs - target_hz)))
        lo = target_hz - C.S3_SSVEP_SNR_NEIGHBOR_HZ
        hi = target_hz + C.S3_SSVEP_SNR_NEIGHBOR_HZ
        exclude_mask = (freqs >= target_hz - C.S3_SSVEP_SNR_EXCLUDE_HZ) & \
                       (freqs <= target_hz + C.S3_SSVEP_SNR_EXCLUDE_HZ)
        neighbor_mask = (freqs >= lo) & (freqs <= hi) & ~exclude_mask
        if not neighbor_mask.any():
            out["by_freq"][label] = {
                "status": "snr_window_empty",
                "target_hz": target_hz,
                "freq_resolution_hz": float(freqs[1] - freqs[0]) if len(freqs) > 1 else float("nan"),
            }
            continue

        # 频谱平均试次和通道，再算 SNR
        amp_avg = amp.mean(axis=(0, 1))     # (n_f,)
        snr = float(amp_avg[target_idx] / amp_avg[neighbor_mask].mean())

        # ITPC: |mean across trials of complex normalized|
        # 在 (epoch, ch) 上先归一化为单位向量，再 mean，最后取通道平均
        unit = spec / (amp + 1e-30)
        itpc = np.abs(unit.mean(axis=0))   # (n_ch, n_f)
        itpc_target = float(itpc[:, target_idx].mean())

        # 谐波（2 次谐波 SNR），只在频率范围内有数据时算
        harmonics_snr = {}
        for h in C.S3_SSVEP_HARMONICS:
            if h == 1:
                continue
            hf = target_hz * h
            if hf < freqs[-1]:
                hi_idx = int(np.argmin(np.abs(freqs - hf)))
                hi_neighbor = (freqs >= hf - C.S3_SSVEP_SNR_NEIGHBOR_HZ) & \
                              (freqs <= hf + C.S3_SSVEP_SNR_NEIGHBOR_HZ) & \
                              ~((freqs >= hf - C.S3_SSVEP_SNR_EXCLUDE_HZ) &
                                (freqs <= hf + C.S3_SSVEP_SNR_EXCLUDE_HZ))
                if hi_neighbor.any():
                    harmonics_snr[f"{h}x"] = float(amp_avg[hi_idx] / amp_avg[hi_neighbor].mean())

        out["by_freq"][label] = {
            "status": "ok",
            "target_hz": target_hz,
            "channels": picks,
            "freq_resolution_hz": float(freqs[1] - freqs[0]),
            "n_trials_total": int(len(ep)),
            "n_trials_kept": int(kept),
            "snr": snr,
            "itpc": itpc_target,
            "harmonic_snr": harmonics_snr,
            "amp_freqs_hz": freqs.tolist(),
            "amp_spectrum": amp_avg.tolist(),    # 各频率振幅 (已 trial+ch 平均)
        }
    return out


def plot_ssvep_grid(result: Dict):
    """4 个频率画 2×2 振幅谱图。"""
    import matplotlib.pyplot as plt
    by_freq = result.get("by_freq", {})
    labels = list(C.S3_SSVEP_FREQS.keys())
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    axes = axes.flatten()
    for ax, label in zip(axes, labels):
        info = by_freq.get(label, {})
        if info.get("status") != "ok":
            ax.set_title(f"{label}  ({info.get('status', 'missing')})", fontsize=10)
            ax.set_xlim(C.S3_SSVEP_PSD_FMIN, C.S3_SSVEP_PSD_FMAX)
            continue
        freqs = np.array(info["amp_freqs_hz"])
        amp = np.array(info["amp_spectrum"])
        mask = (freqs >= C.S3_SSVEP_PSD_FMIN) & (freqs <= C.S3_SSVEP_PSD_FMAX)
        ax.plot(freqs[mask], amp[mask], color="#1f77b4")
        ax.axvline(info["target_hz"], color="orange", ls="--",
                   label=f"target {info['target_hz']:.2f}Hz")
        ax.set_title(
            f"{label}  SNR={info['snr']:.2f}  ITPC={info['itpc']:.2f}  "
            f"N={info['n_trials_kept']}/{info['n_trials_total']}",
            fontsize=10,
        )
        ax.set_xlim(C.S3_SSVEP_PSD_FMIN, C.S3_SSVEP_PSD_FMAX)
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Amplitude (a.u.)")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig
