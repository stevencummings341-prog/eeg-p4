"""主入口：把 data/ 处理成 derivatives/ 下的可复用产物。

典型用法：

    # 处理 data/ 目录里所有被试
    python -m pipeline.run_pipeline \\
        --data-dir ../experiment/data \\
        --out-dir ../derivatives

    # 只处理单个被试
    python -m pipeline.run_pipeline --subject Sub_01 \\
        --data-dir ../experiment/data --out-dir ../derivatives

    # 仅扫描 + 出索引，不做特征提取
    python -m pipeline.run_pipeline --dry-run

    # 已经处理过的 sub-session 默认会跳过；强制重跑加 --force
    python -m pipeline.run_pipeline --force

数据保护：
    data/ 路径只读，pipeline 所有写出全部落在 --out-dir 下。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from . import constants as C
from .indexer import (
    SubBdfSession, SubjectRecord,
    scan_data_dir, render_index_table,
)
from .io_utils import (
    BdfInfo, NpzSession,
    load_raw_bdf, dump_json, dataclass_to_dict,
    parse_npz_filename,
)
from .preprocess import apply_preprocessing, PreprocConfig
from .epoching import (
    epoch_session1, epoch_session2,
    epoch_session3_oddball, epoch_session3_ssvep,
    epoch_session4_mi, epoch_session4_emotion,
)
from .features import s1_alpha, s2_artifacts, s3_p300, s3_ssvep, s4_mi, s4_emotion
from .qc import render_session_block, fig_to_b64, write_report


# --------------------------------------------------------------------------- #
# 路径辅助
# --------------------------------------------------------------------------- #
def subject_dir(out_root: Path, subject_id: str) -> Path:
    safe = subject_id.replace("/", "_").replace("\\", "_")
    return out_root / safe


def subject_paths(out_root: Path, subject_id: str) -> Dict[str, Path]:
    root = subject_dir(out_root, subject_id)
    return {
        "root":     root,
        "index":    root / "01_raw_index.json",
        "preproc":  root / C.DERIVATIVES_SUBDIRS["preproc"],
        "epochs":   root / C.DERIVATIVES_SUBDIRS["epochs"],
        "features": root / C.DERIVATIVES_SUBDIRS["features"],
        "qc":       root / C.DERIVATIVES_SUBDIRS["qc"],
    }


def _sanitize(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)


# --------------------------------------------------------------------------- #
# 录制 (subject + date) 过滤
# --------------------------------------------------------------------------- #
def _sub_session_ts(seg: SubBdfSession) -> str:
    """返回该段对应 NPZ 的时间戳字符串 YYYYMMDD_HHMMSS；没有 NPZ 时返回空串。"""
    if seg.npz is None:
        return ""
    info = parse_npz_filename(seg.npz.path) or {}
    return info.get("ts_raw") or ""


def _sub_session_date(seg: SubBdfSession) -> str:
    """日期前缀 YYYYMMDD；没有 NPZ 时返回空串。"""
    ts = _sub_session_ts(seg)
    return ts[:8] if ts else ""


def _filter_record_by_date(rec: SubjectRecord, date_prefix: str) -> int:
    """In-place 过滤：只保留 NPZ 时间戳 ∈ date_prefix 的 sub-session。返回剩余数。"""
    kept: List[SubBdfSession] = []
    for s in rec.sub_sessions:
        if _sub_session_date(s) == date_prefix:
            kept.append(s)
    rec.sub_sessions = kept
    return len(kept)


def _list_runs(subjects: Dict[str, SubjectRecord]) -> List[Dict[str, str]]:
    """聚合 (subject, date) → 该天的 sub-session 列表。

    返回每条 run:
        {subject, date, time, count, kinds}
    其中 date = YYYYMMDD, time = 该天最早 NPZ 的 HHMMSS,
    kinds = "S1,S2,S3_ODDBALL,S3_SSVEP"。
    """
    runs: Dict[tuple, Dict[str, object]] = {}
    for sid, rec in subjects.items():
        for s in rec.sub_sessions:
            ts = _sub_session_ts(s)
            if not ts:
                continue
            date = ts[:8]
            time = ts[9:]   # 跳过下划线
            key = (sid, date)
            if key not in runs:
                runs[key] = {
                    "subject": sid,
                    "date":    date,
                    "time":    time,
                    "kinds":   [],
                    "count":   0,
                }
            r = runs[key]
            if time < r["time"]:
                r["time"] = time
            if s.session_kind not in r["kinds"]:
                r["kinds"].append(s.session_kind)
            r["count"] = int(r["count"]) + 1

    out: List[Dict[str, str]] = []
    for (sid, date), r in sorted(runs.items()):
        out.append({
            "subject": sid,
            "date":    date,
            "time":    str(r["time"]),
            "count":   str(r["count"]),
            "kinds":   ",".join(r["kinds"]),
        })
    return out


# --------------------------------------------------------------------------- #
# 单个 sub-session 处理
# --------------------------------------------------------------------------- #
def process_sub_session(rec: SubjectRecord, seg: SubBdfSession,
                        out_root: Path, *,
                        force: bool,
                        preproc_cfg: PreprocConfig) -> Dict:
    """加载 → 预处理 → 切片 → 特征。返回一个 summary dict（无 mne 对象）。"""
    paths = subject_paths(out_root, rec.subject_id)
    for p in (paths["preproc"], paths["epochs"], paths["features"], paths["qc"]):
        p.mkdir(parents=True, exist_ok=True)

    seg_tag = f"{seg.session_kind}_{Path(seg.bdf_path).stem}_{int(seg.start_s)}s"
    seg_tag = _sanitize(seg_tag)
    preproc_fif = paths["preproc"] / f"{rec.subject_id}_{seg_tag}_preproc-raw.fif"

    summary: Dict = {
        "subject_id": rec.subject_id,
        "session_kind": seg.session_kind,
        "bdf_path": seg.bdf_path,
        "npz_path": seg.npz.path if seg.npz else None,
        "start_s": seg.start_s,
        "end_s": seg.end_s,
        "n_events": seg.n_events,
        "outputs": {},
        "features": {},
        "figures": {},
        "errors": [],
        "skipped": False,
    }

    # ---- 1. 加载 + crop 到本 Session 时间窗 ----
    try:
        raw = load_raw_bdf(seg.bdf_path, preload=False)
        # 给前后各留 5s buffer 给 epoch baseline / SSVEP 切片
        tmin = max(0.0, seg.start_s - 5.0)
        tmax = min(raw.times[-1], seg.end_s + 6.0)
        raw.crop(tmin=tmin, tmax=tmax)
    except Exception as e:
        summary["errors"].append(f"load_raw_bdf 失败: {e}")
        return summary

    # ---- 2. 预处理（注：crop 之后会把 annotations 时间归零，所以下游
    #         对 seg.start_s/end_s 的引用要相对原始 BDF 时间偏移）----
    # 重要：crop 不改变 raw.annotations 的时间（绝对值），但 raw.first_samp 变了。
    # MNE 1.10+ 默认是相对 raw 第一样本时刻，所以 _events_from_segment 直接
    # 对比 ann.onset 与 seg.start/end 是 OK 的——只要保证 seg.start/end 仍然
    # 落在 raw.times 的范围内。crop 时我们已经留了 buffer。
    try:
        apply_preprocessing(raw, preproc_cfg)
    except Exception as e:
        summary["errors"].append(f"apply_preprocessing 失败: {e}")
        # 仍然尝试继续 epoching（用未滤波数据）
        try:
            raw.load_data()
        except Exception:
            return summary

    # ---- 3. 保存 preproc raw (FIF) 供降噪模型后续使用 ----
    if force or not preproc_fif.exists():
        try:
            raw.save(str(preproc_fif), overwrite=True, verbose="ERROR")
            summary["outputs"]["preproc_fif"] = str(preproc_fif)
        except Exception as e:
            summary["errors"].append(f"raw.save 失败: {e}")
    else:
        summary["outputs"]["preproc_fif"] = str(preproc_fif)
        summary["skipped"] = True

    # ---- 4. 按 Session 类型切 epochs + 算特征 ----
    epochs_dir = paths["epochs"]
    features_dir = paths["features"]
    figures: Dict[str, str] = {}

    try:
        if seg.session_kind == "S1":
            ep_dict = epoch_session1(raw, seg)
            for cond, ep in ep_dict.items():
                if ep is None:
                    continue
                fp = epochs_dir / f"{rec.subject_id}_{seg_tag}_{cond}-epo.fif"
                if force or not fp.exists():
                    ep.save(str(fp), overwrite=True, verbose="ERROR")
                summary["outputs"][f"epochs_{cond}"] = str(fp)
            feat = s1_alpha.compute_alpha_blocking(ep_dict.get("EO"), ep_dict.get("EC"))
            summary["features"]["s1_alpha"] = feat
            dump_json(feat, features_dir / f"{rec.subject_id}_{seg_tag}_s1_alpha.json")
            fig = s1_alpha.plot_psd_comparison(feat)
            if fig is not None:
                figures["S1 Alpha PSD"] = fig_to_b64(fig)

        elif seg.session_kind == "S2":
            ep_dict = epoch_session2(raw, seg)
            for name, ep in ep_dict.items():
                if name == "_meta" or ep is None:
                    continue
                safe_name = _sanitize(name)
                fp = epochs_dir / f"{rec.subject_id}_{seg_tag}_{safe_name}-epo.fif"
                if force or not fp.exists():
                    ep.save(str(fp), overwrite=True, verbose="ERROR")
                summary["outputs"][f"epochs_{safe_name}"] = str(fp)
            feat = s2_artifacts.compute_artifact_template_stats(ep_dict)
            summary["features"]["s2_artifacts"] = feat
            dump_json(feat, features_dir / f"{rec.subject_id}_{seg_tag}_s2_artifacts.json")
            fig = s2_artifacts.plot_artifact_butterfly(ep_dict)
            if fig is not None:
                figures["S2 Artifact templates (butterfly)"] = fig_to_b64(fig)

        elif seg.session_kind == "S3_ODDBALL":
            ep_dict = epoch_session3_oddball(raw, seg)
            merged = ep_dict.get("merged")
            if merged is not None:
                fp = epochs_dir / f"{rec.subject_id}_{seg_tag}_oddball-epo.fif"
                if force or not fp.exists():
                    merged.save(str(fp), overwrite=True, verbose="ERROR")
                summary["outputs"]["epochs_oddball"] = str(fp)
            feat = s3_p300.compute_p300(ep_dict)
            summary["features"]["s3_p300"] = feat
            dump_json(feat, features_dir / f"{rec.subject_id}_{seg_tag}_s3_p300.json")
            fig = s3_p300.plot_p300(feat)
            if fig is not None:
                figures["S3 Oddball P300"] = fig_to_b64(fig)

        elif seg.session_kind == "S3_SSVEP":
            ep_dict = epoch_session3_ssvep(raw, seg)
            merged = ep_dict.get("merged")
            if merged is not None:
                fp = epochs_dir / f"{rec.subject_id}_{seg_tag}_ssvep-epo.fif"
                if force or not fp.exists():
                    merged.save(str(fp), overwrite=True, verbose="ERROR")
                summary["outputs"]["epochs_ssvep"] = str(fp)
            feat = s3_ssvep.compute_ssvep_metrics(ep_dict)
            summary["features"]["s3_ssvep"] = feat
            dump_json(feat, features_dir / f"{rec.subject_id}_{seg_tag}_s3_ssvep.json")
            fig = s3_ssvep.plot_ssvep_grid(feat)
            if fig is not None:
                figures["S3 SSVEP spectra"] = fig_to_b64(fig)

        elif seg.session_kind == "S4_MI":
            ep_dict = epoch_session4_mi(raw, seg)
            merged = ep_dict.get("merged")
            if merged is not None:
                fp = epochs_dir / f"{rec.subject_id}_{seg_tag}_mi-epo.fif"
                if force or not fp.exists():
                    merged.save(str(fp), overwrite=True, verbose="ERROR")
                summary["outputs"]["epochs_mi"] = str(fp)
            feat = s4_mi.compute_mi_erd(ep_dict)
            summary["features"]["s4_mi"] = feat
            dump_json(feat, features_dir / f"{rec.subject_id}_{seg_tag}_s4_mi.json")
            fig = s4_mi.plot_mi_erd(feat)
            if fig is not None:
                figures["S4 MI ERD"] = fig_to_b64(fig)

        elif seg.session_kind == "S4_EMOTION":
            ep_dict = epoch_session4_emotion(raw, seg)
            merged = ep_dict.get("merged")
            if merged is not None:
                fp = epochs_dir / f"{rec.subject_id}_{seg_tag}_emotion-epo.fif"
                if force or not fp.exists():
                    merged.save(str(fp), overwrite=True, verbose="ERROR")
                summary["outputs"]["epochs_emotion"] = str(fp)
            # 每个类别分别也存一份（便于下游直接按类别取）
            for cat in ("negative", "neutral", "positive"):
                ep_cat = ep_dict.get(cat)
                if ep_cat is None or len(ep_cat) == 0:
                    continue
                fp_cat = epochs_dir / f"{rec.subject_id}_{seg_tag}_emotion_{cat}-epo.fif"
                if force or not fp_cat.exists():
                    ep_cat.save(str(fp_cat), overwrite=True, verbose="ERROR")
                summary["outputs"][f"epochs_emotion_{cat}"] = str(fp_cat)
            feat = s4_emotion.compute_emotion_features(ep_dict)
            summary["features"]["s4_emotion"] = feat
            dump_json(feat, features_dir / f"{rec.subject_id}_{seg_tag}_s4_emotion.json")
            fig = s4_emotion.plot_emotion_summary(feat)
            if fig is not None:
                figures["S4 Emotion FAA + Bandpower"] = fig_to_b64(fig)

        else:
            summary["errors"].append(f"unknown session_kind: {seg.session_kind}")
    except Exception as e:
        summary["errors"].append(f"{seg.session_kind} features 阶段异常: {e}")
        summary["errors"].append(traceback.format_exc(limit=2))

    summary["figures"] = figures
    # 清理 raw 防止内存累积
    del raw
    return summary


# --------------------------------------------------------------------------- #
# 处理单个被试
# --------------------------------------------------------------------------- #
def process_subject(rec: SubjectRecord, out_root: Path,
                    *, force: bool, preproc_cfg: PreprocConfig,
                    run_tag: Optional[str] = None) -> Dict:
    """处理一个被试。

    run_tag: 当只处理某次录制（--date）时传入 'YYYYMMDD'，会让 index/QC
             文件名带上日期后缀，避免与"全量跑"或其他日期互相覆盖。
    """
    paths = subject_paths(out_root, rec.subject_id)
    paths["root"].mkdir(parents=True, exist_ok=True)

    tag_label = f" (run={run_tag})" if run_tag else ""
    print(f"\n[{rec.subject_id}] {len(rec.sub_sessions)} sub-sessions" + tag_label)
    summaries: List[Dict] = []
    qc_sections: List[Dict] = []
    for seg in rec.sub_sessions:
        if seg.npz is None:
            print(f"  [skip] {seg.session_kind} {Path(seg.bdf_path).name}@{seg.start_s:.0f}s — no NPZ paired")
            continue
        t0 = time.time()
        print(f"  → {seg.session_kind:11s} {Path(seg.bdf_path).name}@{seg.start_s:.0f}s "
              f"(dur={seg.end_s - seg.start_s:.0f}s, n_ev={seg.n_events})", flush=True)
        s = process_sub_session(rec, seg, out_root, force=force, preproc_cfg=preproc_cfg)
        s["elapsed_s"] = round(time.time() - t0, 1)
        summaries.append(s)
        if s["errors"]:
            for e in s["errors"]:
                print(f"      WARN: {e}")
        # 收集 QC section
        anchor = f"{seg.session_kind.lower()}_{int(seg.start_s)}"
        feat_block = s["features"].get(_kind_to_feat_key(seg.session_kind), {})
        figs = [(cap, b64) for cap, b64 in s["figures"].items()]
        qc_html = render_session_block(seg.session_kind, feat_block, figs)
        qc_sections.append({
            "kind": f"{seg.session_kind}  @  {Path(seg.bdf_path).name} "
                    f"(start={seg.start_s:.0f}s, dur={seg.end_s - seg.start_s:.0f}s)",
            "html": qc_html,
            "anchor": anchor,
        })

    # 写 subject 级 index — 有 run_tag 时分文件，避免覆盖
    index_dump = {
        "subject_id": rec.subject_id,
        "run_tag": run_tag,
        "n_bdfs": len(rec.bdfs),
        "n_npzs": len(rec.npzs),
        "sub_sessions": dataclass_to_dict(rec.sub_sessions),
        "unmatched_npzs": [Path(n.path).name for n in rec.unmatched_npzs],
        "unmatched_bdf_segments": [
            {"bdf_path": s.bdf_path, "session_kind": s.session_kind,
             "start_s": s.start_s, "n_events": s.n_events, "note": s.note}
            for s in rec.unmatched_bdf_segments
        ],
        "summaries": summaries,
    }
    index_name = f"01_raw_index_{run_tag}.json" if run_tag else "01_raw_index.json"
    index_path = paths["root"] / index_name
    dump_json(index_dump, index_path)
    print(f"  [index] -> {index_path}")

    # 写 QC HTML — 同样按 run_tag 分文件
    if qc_sections:
        qc_name = f"report_{run_tag}.html" if run_tag else "report.html"
        report = write_report(paths["qc"] / qc_name, rec.subject_id, qc_sections)
        print(f"  [QC]    -> {report}")

    return index_dump


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def _kind_to_feat_key(kind: str) -> str:
    return {
        "S1":         "s1_alpha",
        "S2":         "s2_artifacts",
        "S3_ODDBALL": "s3_p300",
        "S3_SSVEP":   "s3_ssvep",
        "S4_MI":      "s4_mi",
        "S4_EMOTION": "s4_emotion",
    }.get(kind, "")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="P4 EEG 处理 pipeline：从 data/<scheme>/ 读到 derivatives/<scheme>/。"
    )
    p.add_argument("--scheme", type=str, default="motor_imagery",
                   choices=["motor_imagery", "emotion"],
                   help="实验方案。决定默认 data-dir / out-dir 的子目录："
                        "默认 motor_imagery -> experiment/data/motor_imagery + derivatives/motor_imagery。"
                        "显式给 --data-dir / --out-dir 时本项被覆盖。")
    p.add_argument("--data-dir", type=str, default=None,
                   help="原始数据目录 (含 eeg-bdf/*.bdf 和 eeg-npz/P4_*.npz)。"
                        "默认 ../experiment/data/<scheme>。")
    p.add_argument("--out-dir", type=str, default=None,
                   help="输出目录。默认 ../derivatives/<scheme>。")
    p.add_argument("--subject", type=str, default=None,
                   help="只处理指定 subject_id；不填 = 全部被试。")
    p.add_argument("--date", type=str, default=None,
                   help="只处理 NPZ 时间戳为该日期的录制 (YYYYMMDD, e.g. 20260521)。"
                        "用于聚焦单次实验，不与历史录制混跑。")
    p.add_argument("--list-runs", action="store_true",
                   help="扫描后用机器可读格式输出所有 (subject, date) 录制；"
                        "不做任何处理。stdout 只输出 RUN| 行，便于启动器解析。")
    p.add_argument("--force", action="store_true",
                   help="即使输出已存在也重跑。")
    p.add_argument("--dry-run", action="store_true",
                   help="只扫描数据 + 出索引，不做预处理 / epoching / 特征。")
    p.add_argument("--no-notch", action="store_true",
                   help="跳过工频陷波。")
    p.add_argument("--notch-hz", type=float, nargs="+", default=None,
                   help="覆盖默认陷波频率 (默认 50 Hz；国外用 60)。")
    p.add_argument("--hp-hz", type=float, default=None,
                   help="覆盖默认高通频率。")
    p.add_argument("--lp-hz", type=float, default=None,
                   help="覆盖默认低通频率。")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    here = Path(__file__).resolve().parent
    scheme = args.scheme
    default_data = (here.parent.parent / "experiment" / "data" / scheme).resolve()
    default_out = (here.parent.parent / "derivatives" / scheme).resolve()
    data_dir = Path(args.data_dir).resolve() if args.data_dir else default_data
    out_dir = Path(args.out_dir).resolve() if args.out_dir else default_out

    # --list-runs 是给启动器解析的，stdout 上要干净；其他输出转到 stderr。
    info_out = sys.stderr if args.list_runs else sys.stdout

    if not data_dir.exists():
        print(f"❌ data_dir 不存在：{data_dir}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"scheme   : {scheme}", file=info_out)
    print(f"data_dir : {data_dir}", file=info_out)
    print(f"out_dir  : {out_dir}", file=info_out)

    subjects = scan_data_dir(data_dir)

    # ---------------- --list-runs：机器可读输出 ---------------- #
    if args.list_runs:
        runs = _list_runs(subjects)
        # 每条 run 一行：RUN|subject|date|time|count|kinds
        for r in runs:
            print(f"RUN|{r['subject']}|{r['date']}|{r['time']}|{r['count']}|{r['kinds']}")
        print(f"\n[list-runs] 共 {len(runs)} 次录制", file=sys.stderr)
        return 0

    print(render_index_table(subjects), file=info_out)

    # ---------------- --date 过滤 ---------------- #
    run_tag: Optional[str] = None
    if args.date:
        date_prefix = args.date.strip()
        if len(date_prefix) != 8 or not date_prefix.isdigit():
            print(f"❌ --date 必须是 YYYYMMDD 格式，得到：{args.date!r}", file=sys.stderr)
            return 2
        run_tag = date_prefix
        total_kept = 0
        for sid in list(subjects.keys()):
            kept = _filter_record_by_date(subjects[sid], date_prefix)
            total_kept += kept
            if kept == 0:
                del subjects[sid]
        if total_kept == 0:
            print(f"❌ 没有找到日期 {date_prefix} 的录制。"
                  f" 用 --list-runs 看一下都有哪几次。", file=sys.stderr)
            return 2
        print(f"\n[date] 过滤后剩 {len(subjects)} 个被试 / {total_kept} 个 sub-session"
              f" (date={date_prefix})", file=info_out)

    if args.dry_run:
        print("\n[dry-run] 已生成索引，跳过预处理。", file=info_out)
        return 0

    # 构造 preproc 配置
    preproc_cfg = PreprocConfig(
        hp_hz=args.hp_hz if args.hp_hz is not None else C.HP_FILTER_HZ,
        lp_hz=args.lp_hz if args.lp_hz is not None else C.LP_FILTER_HZ,
        notch_hz=None if args.no_notch else (
            args.notch_hz if args.notch_hz else list(C.NOTCH_FREQS)
        ),
        reference=C.REFERENCE,
        montage=C.MONTAGE,
    )

    if args.subject:
        if args.subject not in subjects:
            print(f"❌ 找不到被试 {args.subject!r}；当前可见：{sorted(subjects)}", file=sys.stderr)
            return 2
        process_subject(subjects[args.subject], out_dir,
                        force=args.force, preproc_cfg=preproc_cfg,
                        run_tag=run_tag)
    else:
        for sid in sorted(subjects):
            try:
                process_subject(subjects[sid], out_dir,
                                force=args.force, preproc_cfg=preproc_cfg,
                                run_tag=run_tag)
            except Exception as e:
                print(f"❌ {sid} 处理失败：{e}")
                traceback.print_exc()

    print("\n全部处理完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
