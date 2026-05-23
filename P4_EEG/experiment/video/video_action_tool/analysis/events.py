"""Event detection from per-frame feature time series.

Conservative defaults, all thresholds tunable via EventConfig.

Supported events:
- blink            : EAR_mean below threshold for a short burst (S2 markers 41/42 candidates)
- head_yaw_motion  : large yaw angular speed (S2 markers 46/47 candidates)
- head_pitch_motion: large pitch angular speed (S2 marker 48 candidate)
- mouth_open       : MAR above threshold (rough S2 marker 44/45 surrogate)

For EEG alignment use the per-frame ``unix_time_ns`` column upstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass
class EventConfig:
    fps: float = 30.0

    blink_blendshape_threshold: float = 0.45
    blink_ear_threshold: float = 0.21
    blink_min_frames: int = 2
    blink_max_frames: int = 15
    blink_merge_gap_frames: int = 2

    yaw_speed_threshold_dps: float = 60.0
    pitch_speed_threshold_dps: float = 60.0
    head_motion_min_frames: int = 3
    head_motion_merge_gap_frames: int = 3

    mouth_open_mar_threshold: float = 0.45
    mouth_open_min_frames: int = 3

    smooth_window_frames: int = 3


def _smooth(series: pd.Series, window: int) -> pd.Series:
    if window <= 1:
        return series
    return series.rolling(window=window, min_periods=1, center=True).mean()


def _segments_from_mask(mask: np.ndarray, min_len: int, max_len: int | None, merge_gap: int) -> list[tuple[int, int]]:
    """Return list of (start_idx, end_idx_inclusive) for True runs in mask after merging."""
    if not mask.any():
        return []

    padded = np.r_[False, mask, False]
    diffs = np.diff(padded.astype(np.int8))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0] - 1

    if merge_gap > 0:
        merged: list[list[int]] = []
        for s, e in zip(starts, ends):
            if merged and s - merged[-1][1] - 1 <= merge_gap:
                merged[-1][1] = int(e)
            else:
                merged.append([int(s), int(e)])
        segs = [(s, e) for s, e in merged]
    else:
        segs = list(zip(map(int, starts), map(int, ends)))

    out = []
    for s, e in segs:
        length = e - s + 1
        if length < min_len:
            continue
        if max_len is not None and length > max_len:
            continue
        out.append((s, e))
    return out


def _build_event_rows(
    segments: Iterable[tuple[int, int]],
    df: pd.DataFrame,
    event_type: str,
    metric_col: str,
    metric_agg: str = "min",
) -> list[dict]:
    rows = []
    for s, e in segments:
        chunk = df.iloc[s : e + 1]
        if metric_agg == "min":
            metric_val = float(np.nanmin(chunk[metric_col].values))
        elif metric_agg == "max":
            metric_val = float(np.nanmax(chunk[metric_col].values))
        else:
            metric_val = float(np.nanmean(chunk[metric_col].values))

        rows.append(
            {
                "event_type": event_type,
                "onset_frame": int(chunk["frame_index"].iloc[0]),
                "offset_frame": int(chunk["frame_index"].iloc[-1]),
                "duration_frames": int(e - s + 1),
                "onset_unix_ns": int(chunk["unix_time_ns"].iloc[0])
                if "unix_time_ns" in chunk
                else None,
                "offset_unix_ns": int(chunk["unix_time_ns"].iloc[-1])
                if "unix_time_ns" in chunk
                else None,
                "duration_seconds": float(
                    (chunk["unix_time_ns"].iloc[-1] - chunk["unix_time_ns"].iloc[0]) / 1e9
                )
                if "unix_time_ns" in chunk
                else None,
                "metric_name": metric_col,
                "metric_value": metric_val,
            }
        )
    return rows


def detect_events(
    df: pd.DataFrame,
    cfg: EventConfig | None = None,
) -> pd.DataFrame:
    """Detect events from a per-frame feature DataFrame.

    Required columns: ``frame_index``, ``ear_mean``, ``mar``, ``yaw_deg``, ``pitch_deg``.
    ``unix_time_ns`` is used when available for absolute time stamps.
    """
    if cfg is None:
        cfg = EventConfig()

    df = df.sort_values("frame_index").reset_index(drop=True).copy()

    ear = _smooth(df["ear_mean"], cfg.smooth_window_frames)
    mar = _smooth(df["mar"], cfg.smooth_window_frames)
    yaw = _smooth(df["yaw_deg"], cfg.smooth_window_frames)
    pitch = _smooth(df["pitch_deg"], cfg.smooth_window_frames)

    dt = 1.0 / cfg.fps
    yaw_speed = yaw.diff().abs() / dt
    pitch_speed = pitch.diff().abs() / dt

    df["yaw_speed_dps"] = yaw_speed
    df["pitch_speed_dps"] = pitch_speed

    if {"bs_eyeBlinkLeft", "bs_eyeBlinkRight"}.issubset(df.columns):
        blink_score = _smooth(
            df[["bs_eyeBlinkLeft", "bs_eyeBlinkRight"]].mean(axis=1),
            cfg.smooth_window_frames,
        )
        df["blink_score"] = blink_score
        blink_mask = (blink_score > cfg.blink_blendshape_threshold).fillna(False).to_numpy()
        blink_metric = "blink_score"
        blink_metric_agg = "max"
    else:
        blink_mask = (ear < cfg.blink_ear_threshold).fillna(False).to_numpy()
        blink_metric = "ear_mean"
        blink_metric_agg = "min"
    blink_segs = _segments_from_mask(
        blink_mask,
        min_len=cfg.blink_min_frames,
        max_len=cfg.blink_max_frames,
        merge_gap=cfg.blink_merge_gap_frames,
    )

    yaw_mask = (yaw_speed > cfg.yaw_speed_threshold_dps).fillna(False).to_numpy()
    yaw_segs = _segments_from_mask(
        yaw_mask,
        min_len=cfg.head_motion_min_frames,
        max_len=None,
        merge_gap=cfg.head_motion_merge_gap_frames,
    )

    pitch_mask = (pitch_speed > cfg.pitch_speed_threshold_dps).fillna(False).to_numpy()
    pitch_segs = _segments_from_mask(
        pitch_mask,
        min_len=cfg.head_motion_min_frames,
        max_len=None,
        merge_gap=cfg.head_motion_merge_gap_frames,
    )

    mouth_mask = (mar > cfg.mouth_open_mar_threshold).fillna(False).to_numpy()
    mouth_segs = _segments_from_mask(
        mouth_mask,
        min_len=cfg.mouth_open_min_frames,
        max_len=None,
        merge_gap=cfg.head_motion_merge_gap_frames,
    )

    rows = []
    rows += _build_event_rows(blink_segs, df, "blink", blink_metric, metric_agg=blink_metric_agg)
    rows += _build_event_rows(yaw_segs, df, "head_yaw_motion", "yaw_speed_dps", metric_agg="max")
    rows += _build_event_rows(pitch_segs, df, "head_pitch_motion", "pitch_speed_dps", metric_agg="max")
    rows += _build_event_rows(mouth_segs, df, "mouth_open", "mar", metric_agg="max")

    if not rows:
        return pd.DataFrame(
            columns=[
                "event_type",
                "onset_frame",
                "offset_frame",
                "duration_frames",
                "onset_unix_ns",
                "offset_unix_ns",
                "duration_seconds",
                "metric_name",
                "metric_value",
            ]
        )

    events_df = pd.DataFrame(rows).sort_values("onset_frame").reset_index(drop=True)
    return events_df
