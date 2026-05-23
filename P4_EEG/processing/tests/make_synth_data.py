"""生成一份「合成 BDF + 合成 NPZ」用作 pipeline 的离线烟雾测试。

合成数据**故意**包含可识别的真实任务特征：
- S1 EO/EC：枕区 alpha 在 EC 阶段被显著增强；
- S2：每个伪迹 trial 在某些通道注入大幅瞬态；
- S3 Oddball：靶刺激在 Pz 注入 P300 形的高斯凸起；
- S3 SSVEP：枕区注入对应频率的正弦；
- S4 MI：C3/C4 在 imagery window 上 mu/beta 功率下降。

输出落地：scratch/synth_data/  (绝不写入真实 data/)。
"""

from __future__ import annotations

import sys
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

# 让 pipeline 可被 import
HERE = Path(__file__).resolve().parent
PROCESSING_DIR = HERE.parent
sys.path.insert(0, str(PROCESSING_DIR))

from pipeline import constants as C  # noqa: E402


def _make_eeg_noise(n_samples: int, n_ch: int, sfreq: float, rng: np.random.Generator):
    """1/f-ish 背景脑电噪声（粗略），单位 V (~10 μV RMS)。"""
    pink = np.zeros((n_ch, n_samples))
    for c in range(n_ch):
        white = rng.standard_normal(n_samples)
        # 用 cumsum + 高通去掉超低频，产生 1/f-ish
        x = np.cumsum(white - white.mean()) / np.sqrt(n_samples)
        # 加点白噪声
        x += 0.5 * rng.standard_normal(n_samples)
        # 归一化到 ~10 μV
        x = x / (np.std(x) + 1e-9) * 10e-6
        pink[c] = x
    return pink


def _inject_alpha(data, ch_idx, start_sample, end_sample, sfreq, amp_uV=15.0):
    n = end_sample - start_sample
    t = np.arange(n) / sfreq
    sig = amp_uV * 1e-6 * np.sin(2 * np.pi * 10.0 * t)
    for i in ch_idx:
        data[i, start_sample:end_sample] += sig


def _inject_p300(data, ch_idx, peak_sample, sfreq, amp_uV=8.0, sigma_ms=70.0):
    n_t = data.shape[1]
    t = (np.arange(n_t) - peak_sample) / sfreq
    sigma_s = sigma_ms / 1000.0
    pulse = amp_uV * 1e-6 * np.exp(-(t ** 2) / (2 * sigma_s ** 2))
    for i in ch_idx:
        data[i] += pulse


def _inject_ssvep(data, ch_idx, start_sample, end_sample, sfreq, freq_hz, amp_uV=6.0):
    n = end_sample - start_sample
    t = np.arange(n) / sfreq
    sig = amp_uV * 1e-6 * np.sin(2 * np.pi * freq_hz * t)
    for i in ch_idx:
        data[i, start_sample:end_sample] += sig


def _inject_blink(data, ch_idx, sample, sfreq, amp_uV=120.0, width_ms=300.0):
    n_t = data.shape[1]
    t = (np.arange(n_t) - sample) / sfreq
    sigma_s = (width_ms / 1000.0) / 2.355
    pulse = amp_uV * 1e-6 * np.exp(-(t ** 2) / (2 * sigma_s ** 2))
    for i in ch_idx:
        data[i] += pulse


def _inject_emg_burst(data, ch_idx, start_sample, end_sample, sfreq, amp_uV=40.0, rng=None):
    n = end_sample - start_sample
    if rng is None:
        rng = np.random.default_rng(0)
    burst = amp_uV * 1e-6 * rng.standard_normal(n)
    # 高频带通：60-100Hz 简单模拟
    from scipy.signal import butter, filtfilt
    b, a = butter(2, [60, 100], fs=sfreq, btype="band")
    burst = filtfilt(b, a, burst)
    for i in ch_idx:
        data[i, start_sample:end_sample] += burst


def _inject_mi_erd(data, ch_idx, start_sample, end_sample, sfreq, freq_hz, scale=0.4):
    """通过减去 10Hz/20Hz 正弦能量来模拟 ERD（粗略）。"""
    n = end_sample - start_sample
    t = np.arange(n) / sfreq
    sig = scale * 5e-6 * np.sin(2 * np.pi * freq_hz * t)
    for i in ch_idx:
        data[i, start_sample:end_sample] -= sig


# --------------------------------------------------------------------------- #
# 合成 BDF 写出
# --------------------------------------------------------------------------- #
def build_synthetic_bdf(out_path: Path, duration_s: float = 600.0,
                        sfreq: float = 500.0,
                        seed: int = 7) -> Tuple[np.ndarray, List[Tuple[float, int]]]:
    """生成一段 600 秒、32 通道的合成 EEG。

    时间布局（秒）：
        0-2     padding
        2-12    EO (T11→T12)
        12-22   transition
        22-32   EC (T21→T22)           ← 枕区 alpha 增强
        32-90   S2: 30 个伪迹 trials   (T30 + T31 + T4x)
        90-200  S3 Oddball (~120 trials)  (T61/T62)
        200-205 baseline (T63 start/end)
        205-300 S3 SSVEP 16 trials × 4 freq
        300-... S4 MI 20 trials × 2 class
    返回 (data_V, events_list_for_npz)
    """
    rng = np.random.default_rng(seed)
    n_ch = len(C.EEG_32_CHANNELS)
    n_t = int(duration_s * sfreq)
    data = _make_eeg_noise(n_t, n_ch, sfreq, rng)

    occipital_idx = [C.EEG_32_CHANNELS.index(c) for c in C.ROI_OCCIPITAL if c in C.EEG_32_CHANNELS]
    parietal_idx = [C.EEG_32_CHANNELS.index(c) for c in ("Pz", "CP1", "CP2") if c in C.EEG_32_CHANNELS]
    frontal_idx = [C.EEG_32_CHANNELS.index(c) for c in ("Fp1", "Fp2", "AF3", "AF4") if c in C.EEG_32_CHANNELS]
    temporal_idx = [C.EEG_32_CHANNELS.index(c) for c in ("T7", "T8") if c in C.EEG_32_CHANNELS]
    c3_idx = [C.EEG_32_CHANNELS.index("C3")]
    c4_idx = [C.EEG_32_CHANNELS.index("C4")]

    annotations: List[Tuple[float, int]] = []   # (onset_s, marker)
    nps_events: Dict[str, list] = {}

    # ---- S1 ----
    s1_eo_t0, s1_eo_t1 = 2.0, 12.0
    s1_ec_t0, s1_ec_t1 = 22.0, 32.0
    annotations += [(s1_eo_t0, 11), (s1_eo_t1, 12), (s1_ec_t0, 21), (s1_ec_t1, 22)]
    # EO 阶段也加少量 alpha (基线)
    _inject_alpha(data, occipital_idx,
                  int(s1_eo_t0 * sfreq), int(s1_eo_t1 * sfreq), sfreq, amp_uV=3.0)
    # EC 阶段强 alpha
    _inject_alpha(data, occipital_idx,
                  int(s1_ec_t0 * sfreq), int(s1_ec_t1 * sfreq), sfreq, amp_uV=22.0)
    nps_events["session1"] = {
        "eo_duration_s": int(s1_eo_t1 - s1_eo_t0),
        "ec_duration_s": int(s1_ec_t1 - s1_ec_t0),
    }

    # ---- S2 ----
    s2_events = []
    artifact_types = [
        ("单次眨眼", 41, "blink"),
        ("连续眨眼", 42, "blink"),
        ("水平眼动", 43, "blink"),
        ("轻度咬牙", 44, "emg"),
        ("吞咽口水", 45, "emg"),
        ("向左摇头", 46, "blink"),
        ("向右摇头", 47, "blink"),
        ("上下点头", 48, "blink"),
    ]
    t = 32.0
    for trial_i in range(30):
        if t > 88.0:
            break
        name, marker, kind = artifact_types[trial_i % len(artifact_types)]
        annotations.append((t, 30))           # T30: 按键
        t += 2.0
        annotations.append((t, 31))           # T31: 伪迹起点
        # 注：iRecorder 会吃掉 5ms 内紧跟的第二个 marker，这里**故意**省略 T4x 测回推
        # 但奇数 trial 我们保留 T4x 让 epoching 能两种逻辑都覆盖
        if trial_i % 2 == 1:
            annotations.append((t + 0.005, marker))
        # 注入伪迹
        if kind == "blink":
            _inject_blink(data, frontal_idx, int(t * sfreq), sfreq, amp_uV=120.0)
        elif kind == "emg":
            _inject_emg_burst(data, temporal_idx,
                              int(t * sfreq), int((t + 0.8) * sfreq), sfreq, amp_uV=80.0, rng=rng)
        s2_events.append({"trial": trial_i + 1, "artifact": name,
                          "marker_type": marker, "movement_direction": "none"})
        t += 2.0
    nps_events["session2"] = {
        "n_artifact_types": len(artifact_types),
        "total_trials": len(s2_events),
        "events": s2_events,
    }

    # ---- S3 Oddball ----
    odd_events = []
    t = 90.0
    n_odd = 80
    for trial_i in range(n_odd):
        is_target = (trial_i % 5 == 4)
        marker = 62 if is_target else 61
        annotations.append((t, marker))
        if is_target:
            _inject_p300(data, parietal_idx, int((t + 0.35) * sfreq), sfreq, amp_uV=8.0)
        odd_events.append({"trial": trial_i + 1,
                           "type": "target" if is_target else "standard",
                           "marker": marker, "iti_s": 1.0})
        t += 1.4
    annotations.append((200.0, 63))
    annotations.append((204.0, 63))
    nps_events["session3_oddball"] = {
        "session": "3", "n_trials": n_odd,
        "n_target": sum(1 for e in odd_events if e["type"] == "target"),
        "n_standard": sum(1 for e in odd_events if e["type"] == "standard"),
        "n_forced_blinks": 0, "correct_red_count": 0,
        "events": odd_events,
    }

    # ---- S3 SSVEP ----
    ssvep_events = []
    freq_specs = [(71, 6.0, "6Hz", "左上"), (72, 8.57, "8.57Hz", "右上"),
                  (73, 10.0, "10Hz", "左下"), (74, 15.0, "15Hz", "右下")]
    t = 210.0
    flicker_dur = 4.0
    rest_dur = 1.0
    for repeat in range(4):
        for marker, hz, label, pos in freq_specs:
            annotations.append((t, marker))
            start_samp = int(t * sfreq)
            end_samp = int((t + flicker_dur) * sfreq)
            _inject_ssvep(data, occipital_idx, start_samp, end_samp, sfreq, hz, amp_uV=6.0)
            ssvep_events.append({"trial": len(ssvep_events) + 1,
                                 "target_frequency_hz": hz,
                                 "target_frequency_label": label,
                                 "target_position": pos,
                                 "marker": marker, "band": "alpha",
                                 "dropped_frames": 0, "total_flicker_frames": 240})
            t += flicker_dur + rest_dur
    nps_events["session3_ssvep"] = {
        "session": "3", "layout": "four-quadrant",
        "n_frequencies": 4, "n_trials_per_freq": 4,
        "total_trials": len(ssvep_events),
        "flicker_duration_s": flicker_dur,
        "rest_mode": "self_paced_space",
        "actual_refresh_rate_hz": 60.0,
        "refresh_warning": "",
        "total_dropped_frames": 0,
        "frame_interval_threshold_s": 0.0207,
        "frequencies": [{"hz": s[1], "label": s[2], "band": "synth",
                         "position": s[3], "marker": s[0]} for s in freq_specs],
        "freq_counts": {s[2]: 4 for s in freq_specs},
        "events": ssvep_events,
    }

    # ---- S4 MI ----
    mi_events = []
    t = max(t + 2.0, 300.0)
    for block_idx in range(2):
        annotations.append((t, 88))   # block_start
        mi_events.append({"time": t, "phase": "block_start", "trial_index": len(mi_events),
                          "label": "", "marker": 88, "note": f"block={block_idx+1}"})
        t += 1.0
        for trial_i in range(6):
            is_left = (trial_i % 2 == 0)
            cue_marker = 83 if is_left else 84
            mi_marker = 85 if is_left else 86
            cls = "left_hand" if is_left else "right_hand"
            annotations.append((t, cue_marker))
            mi_events.append({"time": t, "phase": "cue", "trial_index": len(mi_events),
                              "label": cls, "marker": cue_marker})
            t += 1.0
            annotations.append((t, mi_marker))
            mi_events.append({"time": t, "phase": "imagery", "trial_index": len(mi_events),
                              "label": cls, "marker": mi_marker})
            # 注入 ERD: 左手想象 → C4 (对侧) 下降；右手想象 → C3 下降
            erd_chs = c4_idx if is_left else c3_idx
            _inject_mi_erd(data, erd_chs,
                           int(t * sfreq), int((t + 4.0) * sfreq), sfreq, 10.0)
            t += 4.0
            annotations.append((t, 87))   # rest
            mi_events.append({"time": t, "phase": "rest", "trial_index": len(mi_events),
                              "label": cls, "marker": 87})
            t += 2.0
        annotations.append((t, 89))   # block_end
        mi_events.append({"time": t, "phase": "block_end", "trial_index": len(mi_events),
                          "label": "", "marker": 89, "note": f"block={block_idx+1}"})
        t += 2.0

    nps_events["session4_mi"] = {
        "events": mi_events,
        "formal_sequences": [],
        "training_summary": {
            "practice_window_duration_s": 5.0,
            "formal_trials_per_class": 6,
            "formal_blocks": 2,
            "baseline_duration_s": 1.0,
            "cue_duration_s": 1.0,
            "imagery_duration_s": 4.0,
            "rest_duration_s": 2.0,
            "quick_test": True,
        },
    }

    # ---- 写 BDF ----
    import mne
    info = mne.create_info(ch_names=C.EEG_32_CHANNELS, sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    raw.set_annotations(mne.Annotations(
        onset=[a[0] for a in annotations],
        duration=[0.0] * len(annotations),
        description=[f"T{a[1]}" for a in annotations],
    ))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # MNE 不直接支持写 BDF；我们写成 FIF 并把它当 "bdf" 来用——
    # 这里改用 export 的 EDF 后缀让 mne 自身可读，但 indexer 找的是 *.bdf。
    # 折衷：用 mne.export.export_raw 写 EDF（mne 支持），再让 indexer 也接 EDF。
    # 为了不动 indexer，这里把数据 + annotations 直接 pickle 成一个 .mne_raw.fif，
    # 同时生成一份与 BDF 等价的 "假 BDF" — 把 raw.save 写成 .fif，给 indexer
    # 提供独立的 *.bdf-like loader。
    # 简化：让合成数据写成 .fif，并提供一个改造过的 indexer.scan 接口。
    # 这里**直接写出 EDF**（mne 原生支持 export EDF），并给 indexer 一个开关。
    try:
        from mne.export import export_raw
        export_raw(str(out_path), raw, fmt="edf", overwrite=True, verbose="ERROR")
        return data, nps_events
    except Exception as e:
        print(f"warning: EDF 导出失败 ({e})，尝试写 FIF。")
        fif_path = out_path.with_suffix(".fif")
        raw.save(str(fif_path), overwrite=True, verbose="ERROR")
        return data, nps_events


def write_synth_npzs(out_dir: Path, subject_id: str, ts: str,
                     nps_events: Dict[str, dict]) -> List[Path]:
    """写出每个 Session 一份 NPZ，文件名与实验代码一致。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    session_map = {
        "session1": "1",
        "session2": "2",
        "session3_oddball": "3",
        "session3_ssvep": "3",
        "session4_mi": "4",
    }
    for suffix, content in nps_events.items():
        session_num = session_map[suffix]
        fname = f"P4_S{session_num}_{subject_id}_{ts}_{suffix}.npz"
        fpath = out_dir / fname
        events = content.pop("events", [])
        cfg = {
            "subject_id": subject_id,
            "session": session_num,
            "exp_timestamp": "2026-05-21 12:00:00",
            "session_order": "3_then_4",
        }
        save_dict = {"config_json": json.dumps(cfg, ensure_ascii=False),
                     "events": np.array(events, dtype=object)}
        for k, v in content.items():
            try:
                save_dict[k] = np.array(v, dtype=object) if isinstance(v, (list, dict)) else v
            except Exception:
                save_dict[k] = str(v)
        np.savez_compressed(fpath, **save_dict)
        written.append(fpath)
    return written


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    import argparse
    parser = argparse.ArgumentParser(description="生成 P4 合成数据用于 pipeline 烟雾测试")
    parser.add_argument("--out", type=str, default=None,
                        help="输出目录。默认 scratch/synth_data/。")
    parser.add_argument("--subject", default="Synth_01")
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    default_out = (PROCESSING_DIR.parent.parent / "scratch" / "synth_data").resolve()
    out_root = Path(args.out).resolve() if args.out else default_out
    eeg_dir = out_root / "eeg"
    eeg_dir.mkdir(parents=True, exist_ok=True)

    bdf_path = eeg_dir / f"synth_{args.subject}_20260521_120000.edf"
    print(f"[synth] writing fake BDF/EDF -> {bdf_path}")
    _, nps_events = build_synthetic_bdf(bdf_path, duration_s=args.duration, seed=args.seed)

    print(f"[synth] writing per-session NPZ -> {out_root}")
    npz_files = write_synth_npzs(out_root, args.subject, "20260521_120000", nps_events)
    for p in npz_files:
        print(f"   {p.name}")

    print(f"\n合成数据生成完毕。跑 pipeline：")
    print(f"   python -m pipeline.run_pipeline "
          f"--data-dir \"{out_root}\" "
          f"--out-dir \"{out_root.parent / 'synth_derivatives'}\"")


if __name__ == "__main__":
    main()
