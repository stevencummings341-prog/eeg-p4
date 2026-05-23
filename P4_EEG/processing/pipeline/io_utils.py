"""数据 I/O 与 annotation 解析。

只读 data/，从不写 data/。所有解析失败都返回明确的错误对象，
而不是吞掉异常 — 上层流水线据此决定是否跳过该 Session。
"""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# MNE 在 import 时会很慢，延迟到真正用到的函数里
from . import constants as C


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class BdfEvent:
    """从 BDF annotations 解析出来的单个 Marker。"""
    onset_s: float
    marker: int
    description: str       # 原始 "T62" 这种字符串


@dataclass
class BdfInfo:
    """轻量级 BDF 元数据，不持有 raw 对象。"""
    path: str
    sfreq: float
    n_channels: int
    ch_names: List[str]
    duration_s: float
    n_annotations: int
    meas_date: Optional[str]    # ISO 字符串
    events: List[BdfEvent] = field(default_factory=list)


@dataclass
class NpzSession:
    """从 PsychoPy .npz 解析出来的单次 Session 元数据。"""
    path: str
    subject_id: str
    session: str               # "1"/"2"/"3"/"4"
    suffix: str                # "session1"/"session3_oddball"/...
    exp_timestamp: str         # 原始字符串 "YYYY-MM-DD HH:MM:SS"
    exp_dt: Optional[datetime] # 解析后的 datetime，可能 None
    events: List[Dict[str, Any]]   # 每 trial 的 dict
    raw: Dict[str, Any]        # 其他顶层字段 (n_trials, frequencies, ...)


# --------------------------------------------------------------------------- #
# BDF
# --------------------------------------------------------------------------- #
_MARKER_RE = re.compile(r"^T(\d+)$")


def _parse_marker_desc(desc: Any) -> Optional[int]:
    """把 'T62' 转成 62；不匹配返回 None。"""
    s = str(desc).strip()
    m = _MARKER_RE.match(s)
    if not m:
        return None
    return int(m.group(1))


def _open_edf_or_bdf(path: str | Path, preload: bool = False):
    """同一份代码同时支持 BDF (iRecorder 真实数据) 和 EDF (合成测试数据)。"""
    import mne
    ext = Path(path).suffix.lower()
    if ext == ".edf":
        return mne.io.read_raw_edf(str(path), preload=preload, verbose="ERROR")
    return mne.io.read_raw_bdf(str(path), preload=preload, verbose="ERROR")


def read_bdf_info(bdf_path: str | Path) -> BdfInfo:
    """轻量读取 BDF/EDF (preload=False)：拿元数据 + annotations。"""
    bdf_path = str(Path(bdf_path).resolve())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = _open_edf_or_bdf(bdf_path, preload=False)

    events: List[BdfEvent] = []
    for ann in raw.annotations:
        marker = _parse_marker_desc(ann["description"])
        if marker is None:
            continue
        events.append(BdfEvent(
            onset_s=float(ann["onset"]),
            marker=marker,
            description=str(ann["description"]),
        ))

    meas_date = raw.info.get("meas_date")
    meas_date_str: Optional[str] = None
    if meas_date is not None:
        try:
            meas_date_str = meas_date.isoformat() if hasattr(meas_date, "isoformat") else str(meas_date)
        except Exception:
            meas_date_str = None

    return BdfInfo(
        path=bdf_path,
        sfreq=float(raw.info["sfreq"]),
        n_channels=len(raw.ch_names),
        ch_names=list(raw.ch_names),
        duration_s=float(raw.times[-1]) if raw.times.size else 0.0,
        n_annotations=len(raw.annotations),
        meas_date=meas_date_str,
        events=events,
    )


def load_raw_bdf(bdf_path: str | Path, preload: bool = True):
    """加载 BDF/EDF 为 mne.io.Raw，调用方决定 preload。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _open_edf_or_bdf(bdf_path, preload=preload)


def bdf_events_to_array(events: List[BdfEvent], sfreq: float) -> np.ndarray:
    """把 BdfEvent 列表转成 MNE 风格的 events ndarray: (n, 3) → [sample, 0, marker]。"""
    if not events:
        return np.zeros((0, 3), dtype=int)
    samples = np.round(np.array([e.onset_s for e in events]) * sfreq).astype(int)
    markers = np.array([e.marker for e in events], dtype=int)
    return np.column_stack([samples, np.zeros_like(samples), markers])


# --------------------------------------------------------------------------- #
# NPZ
# --------------------------------------------------------------------------- #
# 文件名格式：P4_S<session>_<subject>_<YYYYMMDD_HHMMSS>_<suffix>.npz
# subject_id 允许含下划线（"Sub_01"），所以用非贪婪 + 时间戳锚点切分
_NPZ_NAME_RE = re.compile(
    r"^P4_S(?P<session>\d|all)_(?P<subject>.+?)_(?P<ts>\d{8}_\d{6})(?:_(?P<suffix>.+))?$"
)


def parse_npz_filename(path: str | Path) -> Optional[Dict[str, str]]:
    """从文件名解析 P4_S<session>_<subject>_<YYYYMMDD_HHMMSS>_<suffix>.npz。"""
    stem = Path(path).stem
    m = _NPZ_NAME_RE.match(stem)
    if not m:
        return None
    return {
        "session": m.group("session"),
        "subject": m.group("subject"),
        "ts_raw":  m.group("ts"),
        "suffix":  m.group("suffix") or "",
    }


def _coerce_events_list(arr: np.ndarray) -> List[Dict[str, Any]]:
    """np.savez 保存的 list-of-dict 会变成 object ndarray，统一回成 list[dict]。"""
    if arr is None:
        return []
    arr = np.asarray(arr)
    if arr.ndim == 0:
        item = arr.item()
        if isinstance(item, list):
            return [dict(x) if isinstance(x, dict) else {"value": x} for x in item]
        if isinstance(item, dict):
            return [dict(item)]
        return []
    return [dict(x) if isinstance(x, dict) else {"value": x} for x in arr.tolist()]


def _coerce_scalar(arr: np.ndarray) -> Any:
    arr = np.asarray(arr)
    if arr.ndim == 0:
        item = arr.item()
        return item
    return arr.tolist()


def load_npz_session(npz_path: str | Path) -> NpzSession:
    """读取一份 Session 的 .npz 并归一化为 NpzSession。"""
    npz_path = Path(npz_path).resolve()
    with np.load(npz_path, allow_pickle=True) as z:
        keys = list(z.keys())
        cfg_raw = str(z["config_json"]) if "config_json" in keys else "{}"
        try:
            cfg = json.loads(cfg_raw)
        except Exception:
            cfg = {}

        events = _coerce_events_list(z["events"]) if "events" in keys else []
        raw_extras: Dict[str, Any] = {}
        for k in keys:
            if k in ("config_json", "events"):
                continue
            try:
                raw_extras[k] = _coerce_scalar(z[k])
            except Exception:
                raw_extras[k] = None

    name_info = parse_npz_filename(npz_path) or {}
    subject_id = cfg.get("subject_id") or name_info.get("subject") or "unknown"
    session = str(cfg.get("session") or name_info.get("session") or "unknown")
    suffix = name_info.get("suffix") or f"session{session}"
    exp_ts = cfg.get("exp_timestamp") or ""
    exp_dt: Optional[datetime] = None
    if exp_ts:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d_%H%M%S"):
            try:
                exp_dt = datetime.strptime(exp_ts, fmt)
                break
            except ValueError:
                continue

    return NpzSession(
        path=str(npz_path),
        subject_id=str(subject_id),
        session=session,
        suffix=str(suffix),
        exp_timestamp=str(exp_ts),
        exp_dt=exp_dt,
        events=events,
        raw=raw_extras,
    )


# --------------------------------------------------------------------------- #
# 输出辅助
# --------------------------------------------------------------------------- #
def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (datetime,)):
        return o.isoformat()
    if hasattr(o, "__dict__"):
        return o.__dict__
    return str(o)


def dump_json(obj: Any, path: str | Path, *, indent: int = 2) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, default=_json_default)
    return path


def dataclass_to_dict(obj) -> Dict[str, Any]:
    """递归地把 dataclass 转成 dict，方便 JSON 序列化。"""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, list):
        return [dataclass_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: dataclass_to_dict(v) for k, v in obj.items()}
    return obj
