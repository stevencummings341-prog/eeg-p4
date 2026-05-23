"""S4 MI 诊断脚本：ERSP 时频图 + 单 trial ERD 直方图。

只读 derivatives/，所有输出落到 scratch/s4_mi_diag/。
不修改 data/、不修改 derivatives/。

用法：
    conda activate eeg-p4
    python scripts\diagnose_s4_mi.py
    # 或指定不同被试 / 录制
    python scripts\diagnose_s4_mi.py --epo-fif <path>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EPO = (
    PROJECT_ROOT
    / "P4_EEG"
    / "derivatives"
    / "Sub_01"
    / "03_epochs"
    / "Sub_01_S4_MI_0521_syx_20260521173744_1104s_mi-epo.fif"
)
DEFAULT_OUT = PROJECT_ROOT / "scratch" / "s4_mi_diag"

ROI_CHS = ("C3", "C4", "Cz")
# baseline 必须落在 fixation 段（marker T85/T86 之前 −3~−1s 是 fixation，−1~0s 是 cue）
# 老版本用 (-1.5, -0.5) 在 cue 期，会被 anticipatory ERS/视觉反弹污染
BASELINE_WIN = (-2.5, -1.0)
ACTIVE_WIN = (0.5, 3.5)
MU_BAND = (8.0, 13.0)
BETA_BAND = (13.0, 30.0)
ERSP_FREQS = np.arange(4.0, 30.5, 1.0)


def _bandpower_per_trial(epochs, picks, fmin, fmax, tmin, tmax) -> np.ndarray:
    """Per-trial bandpower in µV². shape (n_ep, n_ch)."""
    sfreq = epochs.info["sfreq"]
    ep = epochs.copy().crop(tmin=tmin, tmax=tmax)
    n_samp = ep.get_data().shape[-1]
    n_fft = max(16, min(int(1.0 * sfreq), n_samp))
    spec = ep.compute_psd(
        method="welch", fmin=fmin, fmax=fmax,
        n_fft=n_fft, n_per_seg=n_fft,
        picks=picks, verbose="ERROR",
    )
    psd, freqs = spec.get_data(return_freqs=True)
    df = float(np.diff(freqs).mean()) if len(freqs) > 1 else 1.0
    bp = psd.sum(axis=-1) * df * 1e12
    return bp


def compute_ersp(epochs, picks):
    """Morlet TFR, baseline-corrected to (-1.5,-0.5) in percent.

    Returns (tfr_data, times, freqs, ch_names) — tfr_data shape (n_ch, n_f, n_t).
    """
    import mne
    n_cycles = ERSP_FREQS / 2.0
    tfr = mne.time_frequency.tfr_morlet(
        epochs, freqs=ERSP_FREQS, n_cycles=n_cycles,
        picks=picks, return_itc=False,
        use_fft=True, decim=3, average=True, verbose="ERROR",
    )
    tfr.apply_baseline(baseline=BASELINE_WIN, mode="percent", verbose="ERROR")
    return tfr.data * 100.0, tfr.times, tfr.freqs, tfr.ch_names


def plot_ersp_grid(ersp_by_class, out_path):
    classes = list(ersp_by_class.keys())
    fig, axes = plt.subplots(len(classes), len(ROI_CHS),
                             figsize=(4.2 * len(ROI_CHS), 3.4 * len(classes)),
                             sharex=True, sharey=True)
    if len(classes) == 1:
        axes = axes[None, :]

    vmax = 0.0
    for data, _, _, _ in ersp_by_class.values():
        v = np.nanpercentile(np.abs(data), 98)
        vmax = max(vmax, v)
    vmax = min(vmax, 200.0)
    vmax = max(vmax, 40.0)

    for i, cls in enumerate(classes):
        data, times, freqs, ch_names = ersp_by_class[cls]
        for j, ch in enumerate(ROI_CHS):
            ax = axes[i, j]
            if ch not in ch_names:
                ax.set_title(f"{cls} | {ch} (missing)")
                continue
            cidx = ch_names.index(ch)
            im = ax.imshow(
                data[cidx], aspect="auto", origin="lower",
                extent=[times[0], times[-1], freqs[0], freqs[-1]],
                cmap="RdBu_r", vmin=-vmax, vmax=vmax,
                interpolation="nearest",
            )
            ax.axvline(0.0, color="k", lw=0.8, ls="--")
            ax.axvspan(ACTIVE_WIN[0], ACTIVE_WIN[1], facecolor="none",
                       edgecolor="black", lw=1.2, ls=":")
            ax.axhline(MU_BAND[0], color="0.3", lw=0.5, ls="-")
            ax.axhline(MU_BAND[1], color="0.3", lw=0.5, ls="-")
            ax.axhline(BETA_BAND[1], color="0.3", lw=0.5, ls="-")
            ax.set_title(f"{cls} | {ch}")
            if i == len(classes) - 1:
                ax.set_xlabel("Time (s)  [0 = imagery start]")
            if j == 0:
                ax.set_ylabel("Freq (Hz)")
    cbar = fig.colorbar(
        im, ax=axes, shrink=0.85,
        label=f"ERSP % vs baseline ({BASELINE_WIN[0]:+.1f} to {BASELINE_WIN[1]:+.1f} s)\n(blue = ERD)",
    )
    fig.suptitle(
        f"S4 MI — ERSP (Morlet) · baseline={BASELINE_WIN} · syx 0521",
        y=1.0,
    )
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out_path}")


def plot_trial_histograms(epochs_by_class, out_path):
    """对每个 (class, channel) 算单 trial mu ERD%，画直方图。"""
    classes = list(epochs_by_class.keys())
    fig, axes = plt.subplots(len(classes), len(ROI_CHS),
                             figsize=(4.2 * len(ROI_CHS), 3.4 * len(classes)),
                             sharex=True)
    if len(classes) == 1:
        axes = axes[None, :]

    summary = {}
    all_erd = []
    for cls, ep in epochs_by_class.items():
        picks = [c for c in ROI_CHS if c in ep.ch_names]
        bp_base = _bandpower_per_trial(ep, picks, MU_BAND[0], MU_BAND[1],
                                       BASELINE_WIN[0], BASELINE_WIN[1])
        bp_act = _bandpower_per_trial(ep, picks, MU_BAND[0], MU_BAND[1],
                                      ACTIVE_WIN[0], ACTIVE_WIN[1])
        erd = (bp_act - bp_base) / (bp_base + 1e-12) * 100.0
        summary[cls] = {"channels": picks, "erd_pct_per_trial": erd.tolist()}
        all_erd.append(erd.flatten())

        for j, ch in enumerate(ROI_CHS):
            ax = axes[classes.index(cls), j]
            if ch not in picks:
                ax.set_title(f"{cls} | {ch} (missing)")
                continue
            cidx = picks.index(ch)
            x = erd[:, cidx]
            x_clip = np.clip(x, -200, 200)
            ax.hist(x_clip, bins=np.linspace(-200, 200, 25),
                    color="#1f77b4", edgecolor="white", alpha=0.85)
            ax.axvline(0, color="k", lw=0.8)
            mean_ = float(np.nanmean(x))
            med_ = float(np.nanmedian(x))
            ax.axvline(mean_, color="#d62728", lw=1.4, label=f"mean={mean_:+.1f}%")
            ax.axvline(med_,  color="#2ca02c", lw=1.0, ls="--",
                       label=f"median={med_:+.1f}%")
            ax.set_title(f"{cls} | {ch} (n={len(x)})")
            ax.legend(fontsize=8)
            if j == 0:
                ax.set_ylabel("# trials")
    for ax in axes[-1]:
        ax.set_xlabel("μ-band ERD %  (negative = desync)")

    fig.suptitle(
        "S4 MI — per-trial μ-band ERD% histogram · syx 0521\n"
        "bimodal ⇒ subject only engaged on some trials; long left tail ⇒ a few outliers driving mean",
        y=1.02,
    )
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out_path}")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epo-fif", type=str, default=str(DEFAULT_EPO),
                        help="S4 MI merged epochs (-epo.fif).")
    parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()

    epo_path = Path(args.epo_fif)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not epo_path.exists():
        raise SystemExit(f"找不到 epochs 文件：{epo_path}")
    print(f"[input]  {epo_path}")
    print(f"[output] {out_dir}")

    import mne
    epochs = mne.read_epochs(str(epo_path), preload=True, verbose="ERROR")
    print(f"[epochs] n={len(epochs)} ch={len(epochs.ch_names)} "
          f"sfreq={epochs.info['sfreq']:.1f} Hz")
    print(f"[event_id] {epochs.event_id}")

    if "class" not in epochs.metadata.columns:
        raise SystemExit("epochs.metadata 没有 'class' 列；可能切片代码改过。")

    classes = ("left_hand", "right_hand")
    epochs_by_class = {}
    for cls in classes:
        mask = epochs.metadata["class"] == cls
        if mask.sum() == 0:
            print(f"[warn] class {cls} 没有 trial")
            continue
        epochs_by_class[cls] = epochs[mask.values]
        print(f"  {cls}: n={len(epochs_by_class[cls])} trials")

    picks_for_ersp = [c for c in ROI_CHS if c in epochs.ch_names]
    print(f"[ersp picks] {picks_for_ersp}")

    ersp_by_class = {}
    for cls, ep in epochs_by_class.items():
        print(f"[ersp] computing morlet for {cls} ...")
        ersp_by_class[cls] = compute_ersp(ep, picks_for_ersp)

    plot_ersp_grid(ersp_by_class, out_dir / "ersp_C3C4Cz.png")
    summary = plot_trial_histograms(epochs_by_class, out_dir / "trial_erd_hist_mu.png")

    summary_path = out_dir / "trial_erd_mu_per_class.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump({
            "epochs_file": str(epo_path),
            "baseline_win_s": BASELINE_WIN,
            "active_win_s": ACTIVE_WIN,
            "mu_band_hz": MU_BAND,
            "summary": summary,
        }, f, ensure_ascii=False, indent=2)
    print(f"[saved] {summary_path}")
    print("done.")


if __name__ == "__main__":
    main()
