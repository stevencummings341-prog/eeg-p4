"""按 Marker 把 raw 切成 mne.Epochs（按 Session 分支）。

每个 epoch_session_* 函数都做一件事：返回该 Session 的关键 Epochs
（以及关于剔除/丢失 trial 的统计），调用方决定怎么存。

关键设计：
- **S2 伪迹**：iRecorder 在 5ms 内连发两个 Marker 时常常吃掉一个，导致
  BDF 里只剩 T31，缺了 T41-T48 的类型标签。这里用 NPZ events 的顺序
  按 T31 序号回推每个 trial 的类型，恢复出完整的 (类型, 时间) 映射。
- **S3 SSVEP**：直接按 T71-T74 切，无需 NPZ 帮忙（除非要剔除丢帧 trial）。
- **S4 MI**：按 T85/T86 (运动想象起点) 切片，cue/rest 留作 baseline window。

所有 Epochs 使用 metadata 列存 trial 级元信息，方便后续 features 模块查询。
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import constants as C
from .indexer import SubBdfSession


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #
def _events_from_segment(seg: SubBdfSession, raw, marker_filter: Optional[set] = None):
    """读取本 SubBdfSession 时间窗口内的所有 Marker，转成 MNE events ndarray。

    返回 (events, event_id)，event_id 以 Marker int → str 形式，
    例如 {61: "T61", 62: "T62"}（这样 mne.Epochs 会自动接受 int key）。
    """
    import mne
    from .io_utils import _parse_marker_desc

    sfreq = raw.info["sfreq"]
    in_window: List[Tuple[int, int]] = []   # (sample, marker)
    for ann in raw.annotations:
        on = float(ann["onset"])
        if on < seg.start_s - 0.01 or on > seg.end_s + 0.01:
            continue
        m = _parse_marker_desc(ann["description"])
        if m is None:
            continue
        if marker_filter is not None and m not in marker_filter:
            continue
        in_window.append((int(round(on * sfreq)), m))

    if not in_window:
        return np.zeros((0, 3), dtype=int), {}
    events = np.array(
        [[s, 0, m] for s, m in in_window],
        dtype=int,
    )
    unique_markers = sorted(set(m for _, m in in_window))
    event_id = {f"T{m}": int(m) for m in unique_markers}
    return events, event_id


# --------------------------------------------------------------------------- #
# Session 1 — EO/EC 静息态长 epoch (滑窗切成 2s 段)
# --------------------------------------------------------------------------- #
def epoch_session1(raw, seg: SubBdfSession, win_s: float = 2.0,
                   skip_s: float = C.S1_BASELINE_SKIP_S):
    """把 EO/EC 各 ~2 分钟切成 win_s 秒的小 epoch（不重叠）。

    返回 {"EO": Epochs, "EC": Epochs}。
    """
    import mne, pandas as pd
    sfreq = raw.info["sfreq"]

    # 找 EO 和 EC 的开始/结束时间
    eo_start = eo_end = ec_start = ec_end = None
    for ann in raw.annotations:
        if seg.start_s - 0.01 <= ann["onset"] <= seg.end_s + 0.01:
            from .io_utils import _parse_marker_desc
            m = _parse_marker_desc(ann["description"])
            if m == C.MARKERS["S1_EO_START"]:
                eo_start = float(ann["onset"])
            elif m == C.MARKERS["S1_EO_END"]:
                eo_end = float(ann["onset"])
            elif m == C.MARKERS["S1_EC_START"]:
                ec_start = float(ann["onset"])
            elif m == C.MARKERS["S1_EC_END"]:
                ec_end = float(ann["onset"])

    out: Dict[str, "mne.Epochs"] = {}
    for cond, t0, t1 in (("EO", eo_start, eo_end), ("EC", ec_start, ec_end)):
        if t0 is None or t1 is None or t1 - t0 < win_s:
            out[cond] = None
            continue
        # 跳过前 skip_s 秒（让被试稳定）
        seg_start = t0 + skip_s
        seg_end = t1
        if seg_end - seg_start < win_s:
            out[cond] = None
            continue
        # 生成 fake events 用作 epoch 起点，间隔 win_s
        n_wins = int((seg_end - seg_start) // win_s)
        sample_idxs = np.round(
            (seg_start + np.arange(n_wins) * win_s) * sfreq
        ).astype(int)
        events = np.column_stack(
            [sample_idxs, np.zeros_like(sample_idxs), np.full_like(sample_idxs, 1 if cond == "EO" else 2)]
        )
        event_id = {cond: 1 if cond == "EO" else 2}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            epochs = mne.Epochs(
                raw, events, event_id=event_id,
                tmin=0.0, tmax=win_s, baseline=None,
                preload=True, reject=None, picks="eeg",
                verbose="ERROR",
            )
        epochs.metadata = pd.DataFrame({
            "condition": [cond] * len(epochs),
            "window_index": list(range(len(epochs))),
        })
        out[cond] = epochs
    return out


# --------------------------------------------------------------------------- #
# Session 2 — 伪迹模板（按 T31 + NPZ 回推类型）
# --------------------------------------------------------------------------- #
def epoch_session2(raw, seg: SubBdfSession):
    """切伪迹模板。

    - 在 BDF 里找所有 T31 的 onset (伪迹起始)；
    - 如果 NPZ 存在，按 events 顺序映射每个 T31 对应的伪迹类型 (artifact name)；
    - 若有 T41-T48，也用它们覆盖 NPZ 的类型，作为冗余校验。
    返回 dict: {artifact_name: Epochs}。
    """
    import mne, pandas as pd
    sfreq = raw.info["sfreq"]
    from .io_utils import _parse_marker_desc

    # 1. 收集本段内所有 T31 和 T4x marker，按时间排序
    on_artifact: List[Tuple[float, Optional[int]]] = []  # (onset_s, art_marker_or_None)
    last_t31: Optional[float] = None
    saw_art_after_t31 = False
    for ann in raw.annotations:
        on = float(ann["onset"])
        if not (seg.start_s - 0.01 <= on <= seg.end_s + 0.01):
            continue
        m = _parse_marker_desc(ann["description"])
        if m is None:
            continue
        if m == C.MARKERS["S2_ARTIFACT_ON"]:
            if last_t31 is not None and not saw_art_after_t31:
                on_artifact.append((last_t31, None))
            last_t31 = on
            saw_art_after_t31 = False
        elif 41 <= m <= 48:
            if last_t31 is not None:
                on_artifact.append((last_t31, m))
                last_t31 = None
                saw_art_after_t31 = True
            else:
                on_artifact.append((on, m))
    if last_t31 is not None and not saw_art_after_t31:
        on_artifact.append((last_t31, None))

    # 2. 如果有 NPZ，用 NPZ 的 events 顺序回推 marker
    npz_types: List[Tuple[int, str]] = []  # (marker, artifact_name)
    if seg.npz and seg.npz.events:
        for ev in seg.npz.events:
            mk = ev.get("marker_type") or ev.get("marker") or 0
            name = ev.get("artifact", "")
            try:
                mk = int(mk)
            except (TypeError, ValueError):
                mk = 0
            if mk in C.MARKER_NAME or 41 <= mk <= 48:
                npz_types.append((mk, str(name)))
    n_trials = len(on_artifact)
    n_npz = len(npz_types)
    note = ""
    if n_npz and n_npz != n_trials:
        note = f"NPZ trials={n_npz} != BDF trials={n_trials}; 按 min() 截断"

    # 3. 合并：BDF marker (如有) 优先于 NPZ marker
    merged: List[Tuple[float, int, str]] = []  # (onset, marker, name)
    for i, (on, m_bdf) in enumerate(on_artifact):
        if m_bdf is not None:
            marker = m_bdf
            name = _marker_to_artifact_name(marker)
        elif i < n_npz:
            marker, name = npz_types[i]
        else:
            continue
        if not name:
            name = _marker_to_artifact_name(marker)
        merged.append((on, marker, name))

    # 4. 按 artifact name 分桶切 Epochs
    if not merged:
        return {"_meta": {"note": note, "n_trials": 0}}

    by_name: Dict[str, List[Tuple[int, int, str]]] = {}
    for on, mk, name in merged:
        sample = int(round(on * sfreq))
        by_name.setdefault(name, []).append((sample, mk, name))

    import mne
    out: Dict[str, "mne.Epochs"] = {"_meta": {"note": note, "n_trials": n_trials}}
    for name, trials in by_name.items():
        samples = [t[0] for t in trials]
        markers = [t[1] for t in trials]
        events = np.column_stack([samples, np.zeros(len(samples), dtype=int), markers])
        # 用 unique marker 字符串作为 event_id key
        ev_id = {f"T{m}": int(m) for m in sorted(set(markers))}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            epochs = mne.Epochs(
                raw, events, event_id=ev_id,
                tmin=C.S2_EPOCH_TMIN, tmax=C.S2_EPOCH_TMAX,
                baseline=C.S2_BASELINE, preload=True,
                reject=None, picks="eeg",
                verbose="ERROR",
            )
        epochs.metadata = pd.DataFrame({
            "artifact": [name] * len(epochs),
            "marker": markers[:len(epochs)],
        })
        out[name] = epochs
    return out


def _marker_to_artifact_name(marker: int) -> str:
    name_map = {
        41: "单次眨眼", 42: "连续眨眼", 43: "水平眼动", 44: "轻度咬牙",
        45: "吞咽口水", 46: "向左摇头", 47: "向右摇头", 48: "上下点头",
        31: "未知伪迹",
    }
    return name_map.get(marker, f"marker_{marker}")


# --------------------------------------------------------------------------- #
# Session 3 — Oddball
# --------------------------------------------------------------------------- #
def epoch_session3_oddball(raw, seg: SubBdfSession):
    """切 P300 Oddball：返回 {"standard": Epochs, "target": Epochs, "merged": Epochs}。

    merged 是合并 std+target 的总 Epochs，metadata 里有 trial_type 列，
    用于后续画 ERP 差异。
    """
    import mne, pandas as pd
    sfreq = raw.info["sfreq"]
    targets = {C.MARKERS["S3_ODDBALL_STD"], C.MARKERS["S3_ODDBALL_TARGET"]}
    events, ev_id = _events_from_segment(seg, raw, marker_filter=targets)
    if events.shape[0] == 0:
        return {"_meta": {"n_trials": 0}}

    # metadata
    type_map = {C.MARKERS["S3_ODDBALL_STD"]: "standard",
                C.MARKERS["S3_ODDBALL_TARGET"]: "target"}
    metadata = pd.DataFrame({
        "trial_type": [type_map[m] for m in events[:, 2]],
        "marker": events[:, 2].astype(int),
    })

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        epochs = mne.Epochs(
            raw, events, event_id=ev_id,
            tmin=C.S3_ODD_EPOCH_TMIN, tmax=C.S3_ODD_EPOCH_TMAX,
            baseline=C.S3_ODD_BASELINE,
            reject={"eeg": C.S3_ODD_REJECT_PTP_UV * 1e-6} if C.S3_ODD_REJECT_PTP_UV else None,
            preload=True, picks="eeg",
            metadata=metadata,
            verbose="ERROR",
        )
    out = {"merged": epochs, "_meta": {"n_total_events": int(events.shape[0])}}
    std_key = f"T{C.MARKERS['S3_ODDBALL_STD']}"
    tgt_key = f"T{C.MARKERS['S3_ODDBALL_TARGET']}"
    if std_key in epochs.event_id:
        out["standard"] = epochs[std_key]
    if tgt_key in epochs.event_id:
        out["target"] = epochs[tgt_key]
    return out


# --------------------------------------------------------------------------- #
# Session 3 — SSVEP
# --------------------------------------------------------------------------- #
def epoch_session3_ssvep(raw, seg: SubBdfSession):
    """切 SSVEP：按 marker 71-74 划分。返回 {freq_label: Epochs}。

    会从 NPZ 中读取 dropped_frames 标记并附在 metadata 上，
    供 features 模块剔除丢帧 trial。
    """
    import mne, pandas as pd
    sfreq = raw.info["sfreq"]
    targets = set(C.S3_SSVEP_MARKER_TO_FREQ.keys())
    events, ev_id = _events_from_segment(seg, raw, marker_filter=targets)
    if events.shape[0] == 0:
        return {"_meta": {"n_trials": 0}}

    metadata = pd.DataFrame({
        "freq_label": [C.S3_SSVEP_MARKER_TO_FREQ[int(m)] for m in events[:, 2]],
        "freq_hz": [C.S3_SSVEP_FREQS[C.S3_SSVEP_MARKER_TO_FREQ[int(m)]] for m in events[:, 2]],
        "marker": events[:, 2].astype(int),
    })

    # 把 NPZ 里的 dropped_frames 按顺序附上
    if seg.npz and seg.npz.events:
        dropped = []
        for ev in seg.npz.events:
            try:
                dropped.append(int(ev.get("dropped_frames", 0)))
            except Exception:
                dropped.append(0)
        if len(dropped) >= len(metadata):
            metadata["dropped_frames"] = dropped[:len(metadata)]
        else:
            metadata["dropped_frames"] = dropped + [0] * (len(metadata) - len(dropped))
    else:
        metadata["dropped_frames"] = 0

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        epochs = mne.Epochs(
            raw, events, event_id=ev_id,
            tmin=C.S3_SSVEP_EPOCH_TMIN, tmax=C.S3_SSVEP_EPOCH_TMAX,
            baseline=None, preload=True, picks="eeg",
            reject=None,    # SSVEP 不剔除
            metadata=metadata,
            verbose="ERROR",
        )
    out = {"_meta": {"n_total_events": int(events.shape[0]),
                     "refresh_warning": (seg.npz.raw.get("refresh_warning") if seg.npz else "")}}
    for marker, label in C.S3_SSVEP_MARKER_TO_FREQ.items():
        key = f"T{marker}"
        if key in epochs.event_id:
            out[label] = epochs[key]
    out["merged"] = epochs
    return out


# --------------------------------------------------------------------------- #
# Session 4 — Motor Imagery
# --------------------------------------------------------------------------- #
def epoch_session4_mi(raw, seg: SubBdfSession):
    """切运动想象 Epochs：在「运动想象期」marker (T85=左手, T86=右手) 上切。

    epoch 窗口为 [-2, 4] 秒，前 2 秒做 baseline（包含 cue 阶段），后 4 秒是 imagery。
    """
    import mne, pandas as pd
    targets = {
        C.MARKERS["S4_MI_FORMAL_LEFT"],
        C.MARKERS["S4_MI_FORMAL_RIGHT"],
    }
    events, ev_id = _events_from_segment(seg, raw, marker_filter=targets)
    if events.shape[0] == 0:
        return {"_meta": {"n_trials": 0}}

    class_map = {
        C.MARKERS["S4_MI_FORMAL_LEFT"]:  "left_hand",
        C.MARKERS["S4_MI_FORMAL_RIGHT"]: "right_hand",
    }
    metadata = pd.DataFrame({
        "class": [class_map[m] for m in events[:, 2]],
        "marker": events[:, 2].astype(int),
    })

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        epochs = mne.Epochs(
            raw, events, event_id=ev_id,
            tmin=C.S4_MI_EPOCH_TMIN, tmax=C.S4_MI_EPOCH_TMAX,
            baseline=C.S4_MI_BASELINE, preload=True, picks="eeg",
            reject={"eeg": C.S4_MI_REJECT_PTP_UV * 1e-6} if C.S4_MI_REJECT_PTP_UV else None,
            metadata=metadata,
            verbose="ERROR",
        )

    out = {"merged": epochs, "_meta": {"n_total_events": int(events.shape[0])}}
    left_key = f"T{C.MARKERS['S4_MI_FORMAL_LEFT']}"
    right_key = f"T{C.MARKERS['S4_MI_FORMAL_RIGHT']}"
    if left_key in epochs.event_id:
        out["left_hand"] = epochs[left_key]
    if right_key in epochs.event_id:
        out["right_hand"] = epochs[right_key]
    return out


# --------------------------------------------------------------------------- #
# Session 4 — Emotion Recognition (scheme="emotion")
# --------------------------------------------------------------------------- #
def epoch_session4_emotion(raw, seg: SubBdfSession):
    """切情绪识别 Epochs：在视频起点 marker (T101/T102/T103) 上切。

    epoch 窗口为 [S4_EMOTION_EPOCH_TMIN, S4_EMOTION_EPOCH_TMAX]，
    baseline 取 fixation 段；分析窗在特征模块里再 crop。

    NPZ 里 events 是 stimulus_start 阶段的视频文件名等元信息，按 trial_index
    顺序回填 metadata，让下游分析可以追到具体的视频片段。

    返回 {
        "negative": Epochs,
        "neutral":  Epochs,
        "positive": Epochs,
        "merged":   Epochs,
        "_meta":    {...},
    }
    """
    import mne, pandas as pd
    targets = set(C.S4_EMOTION_MARKER_TO_LABEL.keys())
    events, ev_id = _events_from_segment(seg, raw, marker_filter=targets)
    if events.shape[0] == 0:
        return {"_meta": {"n_trials": 0}}

    label_map = C.S4_EMOTION_MARKER_TO_LABEL  # {101: 'negative', ...}
    metadata = pd.DataFrame({
        "category":       [label_map[int(m)] for m in events[:, 2]],
        "category_label": [C.S4_EMOTION_LABEL_TO_CN[label_map[int(m)]] for m in events[:, 2]],
        "marker":         events[:, 2].astype(int),
    })

    # 从 NPZ 里挂上 video_file / video_duration_s（按 stimulus_start 行顺序匹配）
    video_files: List[str] = []
    video_durs: List[Optional[float]] = []
    if seg.npz and seg.npz.events:
        stim_rows = [ev for ev in seg.npz.events
                     if (ev.get("phase") == "stimulus_start"
                         and int(ev.get("marker") or 0) in label_map)]
        for ev in stim_rows:
            vf = ev.get("video_file") or ""
            try:
                dur = float(ev.get("video_duration_s")) if ev.get("video_duration_s") is not None else None
            except (TypeError, ValueError):
                dur = None
            video_files.append(str(vf))
            video_durs.append(dur)
    # 长度对齐到 events
    n = len(metadata)
    video_files = (video_files + [""] * n)[:n]
    video_durs = (video_durs + [None] * n)[:n]
    metadata["video_file"] = video_files
    metadata["video_duration_s"] = video_durs

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        epochs = mne.Epochs(
            raw, events, event_id=ev_id,
            tmin=C.S4_EMOTION_EPOCH_TMIN, tmax=C.S4_EMOTION_EPOCH_TMAX,
            baseline=C.S4_EMOTION_BASELINE, preload=True, picks="eeg",
            reject={"eeg": C.S4_EMOTION_REJECT_PTP_UV * 1e-6} if C.S4_EMOTION_REJECT_PTP_UV else None,
            metadata=metadata,
            verbose="ERROR",
        )

    out: Dict = {
        "merged": epochs,
        "_meta": {
            "n_total_events": int(events.shape[0]),
            "n_after_reject": int(len(epochs)),
        },
    }
    for marker, label in label_map.items():
        key = f"T{marker}"
        if key in epochs.event_id:
            out[label] = epochs[key]
    return out
