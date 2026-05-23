"""扫描 data/ 目录，把每个被试的 BDF 与 NPZ 配成 SubjectRecord。

核心难点：
1. 一个 BDF 通常是**连续录制**，里面可能同时包含 S1+S2+S3 (甚至加 S4)。
2. PsychoPy 每个 Session 单独存一份 NPZ，且文件名只有 PsychoPy 那台机器的
   本地时间戳，**不一定**和 EEG 主机时钟严格一致 (常见 1-30 分钟漂移)。
3. iRecorder 在两个 Marker 间隔很短时会丢一个 (S2 的 T31/T4x 间隔 5ms 已知会丢)，
   这时必须靠 NPZ 的 events 顺序回推每个 T31/T62/T71-74 对应的 trial 元数据。

配对策略：
- 先按 Marker 把 BDF 切成几段「子 Session」(SubBdfSession)。
- 再用 (subject_id, session_num) + 时间最近原则把 NPZ 挂上去。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from . import constants as C
from .io_utils import (
    BdfEvent, BdfInfo, NpzSession,
    read_bdf_info, load_npz_session,
)


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class SubBdfSession:
    """BDF 里被识别出来的某一段 Session（按 Marker 切分）。"""
    session_kind: str           # "S1" / "S2" / "S3_ODDBALL" / "S3_SSVEP" / "S4_MI"
    bdf_path: str
    start_s: float              # 该段 Session 的第一个 marker 时刻
    end_s: float                # 该段 Session 的最后一个 marker 时刻
    n_events: int
    npz: Optional[NpzSession] = None   # 配对成功后挂上
    note: str = ""


@dataclass
class SubjectRecord:
    subject_id: str
    bdfs: List[BdfInfo] = field(default_factory=list)
    npzs: List[NpzSession] = field(default_factory=list)
    sub_sessions: List[SubBdfSession] = field(default_factory=list)
    unmatched_npzs: List[NpzSession] = field(default_factory=list)
    unmatched_bdf_segments: List[SubBdfSession] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 扫描
# --------------------------------------------------------------------------- #
def scan_data_dir(data_dir: str | Path) -> Dict[str, SubjectRecord]:
    """扫描 data_dir：
        <data_dir>/eeg-bdf/*.bdf               — 原始 EEG (iRecorder 录制)
        <data_dir>/eeg-npz/P4_S*_<subject>_*.npz — PsychoPy 每个 Session 的元数据
    返回 {subject_id: SubjectRecord}。

    兼容性：合成测试 / 历史布局下，NPZ 可能落在 data_dir 根目录、BDF 可能落在
    data_dir/eeg/ 或 data_dir 根目录，均会被一并扫到。
    """
    data_dir = Path(data_dir).resolve()
    if not data_dir.is_dir():
        raise FileNotFoundError(f"data_dir 不存在：{data_dir}")

    npz_paths: List[Path] = []
    if (data_dir / "eeg-npz").is_dir():
        npz_paths += sorted((data_dir / "eeg-npz").glob("P4_S*_*.npz"))
    # 兼容：合成测试 / 历史布局把 NPZ 直接放 data_dir 根目录
    npz_paths += sorted(data_dir.glob("P4_S*_*.npz"))

    bdf_paths: List[Path] = []
    if (data_dir / "eeg-bdf").is_dir():
        bdf_paths += sorted((data_dir / "eeg-bdf").glob("*.bdf"))
        bdf_paths += sorted((data_dir / "eeg-bdf").glob("*.edf"))
    # 兼容：旧 `eeg/` 子目录
    if (data_dir / "eeg").is_dir():
        bdf_paths += sorted((data_dir / "eeg").glob("*.bdf"))
        bdf_paths += sorted((data_dir / "eeg").glob("*.edf"))
    # 合成测试场景下，bdf 直接放在 data_dir 根目录
    bdf_paths += sorted(data_dir.glob("*.bdf"))
    bdf_paths += sorted(data_dir.glob("*.edf"))

    subjects: Dict[str, SubjectRecord] = {}

    # ---- 第一步：读 NPZ ----
    for npz_path in npz_paths:
        try:
            sess = load_npz_session(npz_path)
        except Exception as e:
            print(f"⚠ [indexer] 跳过损坏的 NPZ {npz_path.name}: {e}")
            continue
        rec = subjects.setdefault(sess.subject_id, SubjectRecord(subject_id=sess.subject_id))
        rec.npzs.append(sess)

    # ---- 第二步：读所有 BDF 元数据 ----
    bdf_infos: List[BdfInfo] = []
    for bdf_path in bdf_paths:
        try:
            info = read_bdf_info(bdf_path)
        except Exception as e:
            print(f"⚠ [indexer] 跳过损坏的 BDF {bdf_path.name}: {e}")
            continue
        bdf_infos.append(info)

    # ---- 第三步：BDF 没有显式 subject_id，先用「时间最近」把 BDF 挂到被试上 ----
    # 取每个 BDF 的 meas_date (UTC) 作为参考时间；如果缺失，退化成「全部挂到唯一被试」
    subject_ids = sorted(subjects.keys())
    for info in bdf_infos:
        target_subject = _guess_bdf_subject(info, subjects)
        rec = subjects.setdefault(target_subject, SubjectRecord(subject_id=target_subject))
        rec.bdfs.append(info)

    # ---- 第四步：把每个 BDF 按 Marker 切成 SubBdfSession ----
    for rec in subjects.values():
        for info in rec.bdfs:
            rec.sub_sessions.extend(_split_bdf_into_sub_sessions(info))

    # ---- 第五步：把 NPZ 挂到对应的 SubBdfSession ----
    for rec in subjects.values():
        _attach_npz_to_sub_sessions(rec)

    return subjects


# --------------------------------------------------------------------------- #
# BDF → 多个 Sub-Session
# --------------------------------------------------------------------------- #
def _split_bdf_into_sub_sessions(info: BdfInfo) -> List[SubBdfSession]:
    """根据 Marker 集合识别 BDF 里包含哪些 Session 片段。

    策略：按时间排序所有 Marker，每遇到一个 *不同* kind 的 Marker 就开一个新
    sub-session。同一 kind 内部允许任意时间间隔（S1 的 EO→EC 中间可能间隔 5min
    以上；S3 Oddball 内的 T63 任务间基线也属于 S3_ODDBALL kind）。
    """
    if not info.events:
        return []

    tagged: List[tuple] = []  # (onset_s, marker, kind)
    for ev in info.events:
        kind = _marker_to_session_kind(ev.marker)
        if kind is None:
            continue
        tagged.append((ev.onset_s, ev.marker, kind))
    if not tagged:
        return []
    tagged.sort(key=lambda x: x[0])

    segments: List[SubBdfSession] = []
    cur_kind = tagged[0][2]
    cur_events = [tagged[0]]
    for onset, marker, kind in tagged[1:]:
        if kind == cur_kind:
            cur_events.append((onset, marker, kind))
        else:
            segments.append(_make_sub_session(info, cur_kind, cur_events))
            cur_kind = kind
            cur_events = [(onset, marker, kind)]
    segments.append(_make_sub_session(info, cur_kind, cur_events))
    return segments


def _make_sub_session(info: BdfInfo, kind: str, events) -> SubBdfSession:
    return SubBdfSession(
        session_kind=kind,
        bdf_path=info.path,
        start_s=float(events[0][0]),
        end_s=float(events[-1][0]),
        n_events=len(events),
        npz=None,
        note="",
    )


def _marker_to_session_kind(marker: int) -> Optional[str]:
    for kind, mset in C.SESSION_MARKERS.items():
        if marker in mset:
            return kind
    return None


# --------------------------------------------------------------------------- #
# NPZ ↔ SubBdfSession 配对
# --------------------------------------------------------------------------- #
# 把 NPZ 的 suffix 映射到 session_kind
_NPZ_SUFFIX_TO_KIND = {
    "session1":         "S1",
    "session2":         "S2",
    "session3_oddball": "S3_ODDBALL",
    "session3_ssvep":   "S3_SSVEP",
    "session4_mi":      "S4_MI",
    "session4_emotion": "S4_EMOTION",
}


def _attach_npz_to_sub_sessions(rec: SubjectRecord) -> None:
    """按 (session_kind, event-count proximity) 把 NPZ 配到 SubBdfSession。

    优先按 trial 数对齐，因为：
        1. 同一类 Session 里 trial 数是预先确定的（S2=130/260, P300=200,
           SSVEP=80, MI=248 等），匹配上的概率极高；
        2. 多个 BDF 段共存时（例如有一段是 quick-test 调试），
           按时间顺序会错配，按数量顺序更稳。
    数量平手或都不存在时退化为时间顺序。
    """
    by_kind_npz: Dict[str, List[NpzSession]] = {}
    matched_npz_ids: set = set()

    for n in rec.npzs:
        kind = _NPZ_SUFFIX_TO_KIND.get(n.suffix)
        if kind is None:
            rec.unmatched_npzs.append(n)
            continue
        by_kind_npz.setdefault(kind, []).append(n)

    by_kind_bdf: Dict[str, List[SubBdfSession]] = {}
    for s in rec.sub_sessions:
        by_kind_bdf.setdefault(s.session_kind, []).append(s)

    all_kinds = set(by_kind_bdf.keys()) | set(by_kind_npz.keys())
    for kind in all_kinds:
        bdf_segs = list(by_kind_bdf.get(kind, []))
        npz_list = list(by_kind_npz.get(kind, []))

        # Greedy: 每个 NPZ 选 (|n_ev_bdf - n_ev_npz|, time_gap) 最小且未占用的 BDF 段
        used_bdf_idx: set = set()
        for n in sorted(npz_list, key=lambda n: -len(n.events)):  # 大 trial 数优先
            n_events_npz = len(n.events)
            best_i = -1
            best_key = None
            for i, s in enumerate(bdf_segs):
                if i in used_bdf_idx:
                    continue
                ev_diff = abs(s.n_events - n_events_npz)
                # 时间间隔作为次要 tiebreaker
                time_gap = 0.0
                if n.exp_dt is not None:
                    info = next((b for b in rec.bdfs if b.path == s.bdf_path), None)
                    if info and info.meas_date:
                        try:
                            bdf_dt = datetime.fromisoformat(info.meas_date.split("+")[0])
                            time_gap = abs((bdf_dt - n.exp_dt).total_seconds())
                        except Exception:
                            pass
                key = (ev_diff, time_gap)
                if best_key is None or key < best_key:
                    best_key = key
                    best_i = i
            if best_i >= 0:
                bdf_segs[best_i].npz = n
                matched_npz_ids.add(id(n))
                used_bdf_idx.add(best_i)

        for i, s in enumerate(bdf_segs):
            if i not in used_bdf_idx:
                s.note = f"no NPZ available for {kind}"
                rec.unmatched_bdf_segments.append(s)

    for n in rec.npzs:
        if _NPZ_SUFFIX_TO_KIND.get(n.suffix) is None:
            continue
        if id(n) not in matched_npz_ids and n not in rec.unmatched_npzs:
            rec.unmatched_npzs.append(n)


def _guess_bdf_subject(info: BdfInfo, subjects: Dict[str, "SubjectRecord"]) -> str:
    """BDF 文件没有显式的 subject ID。

    策略：
    1. 如果只有 1 个被试，全部 BDF 都挂给这个被试。
    2. 多个被试时，用 BDF 的 meas_date 找时间上最接近的被试的 exp_dt。
    3. 都失败 → 用 BDF 文件名前缀去找 (如 "0521_syx_xxx.bdf" 里的 "syx")，
       如果没有匹配，挂到「unknown」。
    """
    subject_ids = sorted(subjects.keys())
    if not subject_ids:
        # 还没有 NPZ 时，尝试从 BDF 文件名抽
        stem = Path(info.path).stem.lower()
        for part in stem.split("_"):
            if part and not part.isdigit():
                return f"bdf_only:{part}"
        return "unknown"
    if len(subject_ids) == 1:
        return subject_ids[0]

    # 多个被试 — 按 meas_date 找最近邻
    if info.meas_date:
        try:
            bdf_dt = datetime.fromisoformat(info.meas_date.split("+")[0])
        except Exception:
            bdf_dt = None
        if bdf_dt is not None:
            best_subj = subject_ids[0]
            best_gap = timedelta.max
            for sid in subject_ids:
                rec = subjects[sid]
                for n in rec.npzs:
                    if n.exp_dt is None:
                        continue
                    gap = abs(bdf_dt - n.exp_dt)
                    if gap < best_gap:
                        best_gap = gap
                        best_subj = sid
            return best_subj

    return subject_ids[0]


# --------------------------------------------------------------------------- #
# 文本化报告（给 CLI 输出 / QC 报告用）
# --------------------------------------------------------------------------- #
def render_index_table(subjects: Dict[str, SubjectRecord]) -> str:
    lines: List[str] = []
    lines.append(f"=== 数据扫描结果：{len(subjects)} 个被试 ===")
    for sid, rec in sorted(subjects.items()):
        lines.append(f"\n[{sid}]")
        lines.append(f"  BDF: {len(rec.bdfs)}  NPZ: {len(rec.npzs)}  "
                     f"sub-sessions: {len(rec.sub_sessions)}")
        for s in rec.sub_sessions:
            npz_label = Path(s.npz.path).name if s.npz else "(no NPZ)"
            lines.append(
                f"    - {s.session_kind:12s} "
                f"start={s.start_s:8.2f}s  dur={s.end_s - s.start_s:7.2f}s  "
                f"n_ev={s.n_events:4d}  {npz_label}"
            )
        if rec.unmatched_npzs:
            lines.append(f"  ⚠ 未配对的 NPZ: {[Path(n.path).name for n in rec.unmatched_npzs]}")
        if rec.unmatched_bdf_segments:
            lines.append(f"  ⚠ 未配对的 BDF 段: "
                         f"{[(s.session_kind, s.note) for s in rec.unmatched_bdf_segments]}")
    return "\n".join(lines)
