"""P4 EEG 处理 pipeline — 图形化启动器。

设计目标：主试不用记命令行参数，双击 .bat 就能：
    1. 选实验方案 (运动想象 / 情绪识别)
    2. 选要处理的被试和日期（dry-run 扫描自动列出）
    3. 一键跑 pipeline，实时看到 stdout，结束后自动打开 QC HTML

整个 GUI 由本文件实现；命令行 / 自动化用例仍然直接调
``python -m pipeline.run_pipeline``，本 GUI 只是包装层。
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent
EXPERIMENT_DATA_DIR = PROJECT_DIR / "experiment" / "data"
DEFAULT_DERIVATIVES_DIR = PROJECT_DIR / "derivatives"


# --------------------------------------------------------------------------- #
# Scheme 元信息
# --------------------------------------------------------------------------- #
SCHEMES = [
    {
        "id": "motor_imagery",
        "label": "运动想象 (MI)",
        "desc": "S4 = 离线双手运动想象。特征：μ/β ERD + C3/C4 拉特化",
    },
    {
        "id": "emotion",
        "label": "情绪识别 (Emotion)",
        "desc": "S4 = 视频诱发情绪。特征：Frontal Alpha Asymmetry + 频段功率",
    },
]


@dataclass
class RunEntry:
    subject: str
    date: str       # YYYYMMDD
    time: str       # HHMMSS
    count: int
    kinds: str

    @property
    def display(self) -> str:
        d = self.date
        t = self.time
        date_fmt = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d
        time_fmt = f"{t[:2]}:{t[2:4]}:{t[4:6]}" if len(t) == 6 else t
        return f"{self.subject:12s}  {date_fmt}  {time_fmt}   n={self.count:>2}   [{self.kinds}]"


# --------------------------------------------------------------------------- #
# 子进程调用
# --------------------------------------------------------------------------- #
def _python_exe() -> str:
    """返回当前 Python 解释器路径 (确保 GUI 和 pipeline 用同一个环境)。"""
    return sys.executable or "python"


def _build_cli(scheme: str, *, data_dir: Optional[Path], out_dir: Optional[Path],
               extra: List[str]) -> List[str]:
    cmd = [_python_exe(), "-m", "pipeline.run_pipeline", "--scheme", scheme]
    if data_dir:
        cmd += ["--data-dir", str(data_dir)]
    if out_dir:
        cmd += ["--out-dir", str(out_dir)]
    cmd += extra
    return cmd


def _spawn(cmd: List[str], cwd: Path, out_q: queue.Queue, done_evt: threading.Event,
           rc_holder: dict) -> None:
    """后台跑子进程，逐行把 stdout/stderr 塞到 GUI 队列里。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            bufsize=1,
        )
    except FileNotFoundError as e:
        out_q.put(f"[启动失败] {e}\n")
        rc_holder["rc"] = 127
        done_evt.set()
        return

    assert proc.stdout is not None
    for line in proc.stdout:
        out_q.put(line)
    proc.stdout.close()
    rc_holder["rc"] = proc.wait()
    done_evt.set()


def _list_runs(scheme: str, data_dir: Optional[Path]) -> List[RunEntry]:
    """同步调用 --list-runs 并解析 RUN| 行。"""
    cmd = _build_cli(scheme, data_dir=data_dir, out_dir=None, extra=["--list-runs"])
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            cmd, cwd=str(HERE), capture_output=True,
            text=True, encoding="utf-8", errors="replace", env=env, timeout=60,
        )
    except Exception as e:
        return []
    runs: List[RunEntry] = []
    for line in (result.stdout or "").splitlines():
        if not line.startswith("RUN|"):
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        try:
            runs.append(RunEntry(
                subject=parts[1],
                date=parts[2],
                time=parts[3],
                count=int(parts[4]),
                kinds=parts[5],
            ))
        except Exception:
            continue
    return runs


# --------------------------------------------------------------------------- #
# 主 GUI
# --------------------------------------------------------------------------- #
class ProcessingLauncher:
    POLL_MS = 80

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("P4 EEG 处理 pipeline — 启动器")
        self.root.geometry("960x720")
        self.root.minsize(820, 600)

        self.var_scheme = tk.StringVar(value="motor_imagery")
        self.var_data_dir = tk.StringVar(value="")
        self.var_out_dir = tk.StringVar(value="")
        self.var_dry_run = tk.BooleanVar(value=False)
        self.var_force = tk.BooleanVar(value=False)
        self.var_filter_subject = tk.StringVar(value="")
        self.var_filter_date = tk.StringVar(value="")
        self.var_status = tk.StringVar(value="就绪")
        self.runs: List[RunEntry] = []
        self.run_listbox: Optional[tk.Listbox] = None
        self._out_q: queue.Queue = queue.Queue()
        self._done_evt: Optional[threading.Event] = None
        self._rc_holder: dict = {}
        self._worker: Optional[threading.Thread] = None
        self._pending_qc: Optional[Path] = None

        self._build_ui()
        self._on_scheme_change()
        self.root.after(self.POLL_MS, self._poll_output)

    # ------------------------- UI 构建 -------------------------------------
    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        # ---- 标题 ----
        ttk.Label(outer, text="P4 EEG 处理 pipeline",
                  font=("Microsoft YaHei", 14, "bold")).pack(anchor=tk.W)
        ttk.Label(outer, text="从 experiment/data/<scheme>/ 读到 derivatives/<scheme>/",
                  foreground="#666").pack(anchor=tk.W, pady=(0, 10))

        # ---- 方案选择 ----
        frame_scheme = ttk.LabelFrame(outer, text="① 实验方案", padding=8)
        frame_scheme.pack(fill=tk.X, pady=(0, 8))
        for s in SCHEMES:
            row = ttk.Frame(frame_scheme)
            row.pack(fill=tk.X, pady=2)
            ttk.Radiobutton(row, text=s["label"], variable=self.var_scheme,
                            value=s["id"], command=self._on_scheme_change).pack(side=tk.LEFT)
            ttk.Label(row, text="  " + s["desc"],
                      foreground="#555").pack(side=tk.LEFT)
        self.scheme_status = ttk.Label(frame_scheme, text="",
                                        font=("Microsoft YaHei", 10, "bold"),
                                        foreground="#0066AA")
        self.scheme_status.pack(anchor=tk.W, pady=(4, 0))

        # ---- 路径 ----
        frame_paths = ttk.LabelFrame(outer, text="② 路径", padding=8)
        frame_paths.pack(fill=tk.X, pady=(0, 8))

        row = ttk.Frame(frame_paths); row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="data-dir:", width=12).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.var_data_dir, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4,4))
        ttk.Button(row, text="浏览...", command=self._browse_data_dir, width=8).pack(side=tk.LEFT)

        row = ttk.Frame(frame_paths); row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="out-dir:", width=12).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.var_out_dir, width=70).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4,4))
        ttk.Button(row, text="浏览...", command=self._browse_out_dir, width=8).pack(side=tk.LEFT)

        ttk.Label(frame_paths,
                  text="留空 = 自动使用 experiment/data/<scheme> 和 derivatives/<scheme>",
                  foreground="#888").pack(anchor=tk.W, pady=(2, 0))

        # ---- 可用录制 ----
        frame_runs = ttk.LabelFrame(outer, text="③ 选择录制 (双击 = 跑该次)", padding=8)
        frame_runs.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        toolbar = ttk.Frame(frame_runs); toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="扫描可用录制", command=self._refresh_runs).pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(toolbar, text="清空选择", command=self._clear_selection).pack(side=tk.LEFT, padx=(0,6))
        ttk.Label(toolbar, text="或在下方手填:").pack(side=tk.LEFT, padx=(12, 4))
        ttk.Label(toolbar, text="subject").pack(side=tk.LEFT)
        ttk.Entry(toolbar, textvariable=self.var_filter_subject, width=14).pack(side=tk.LEFT, padx=(2,8))
        ttk.Label(toolbar, text="date(YYYYMMDD)").pack(side=tk.LEFT)
        ttk.Entry(toolbar, textvariable=self.var_filter_date, width=12).pack(side=tk.LEFT, padx=(2,8))

        list_frame = ttk.Frame(frame_runs)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.run_listbox = tk.Listbox(list_frame, font=("Consolas", 10),
                                       activestyle="dotbox", selectmode=tk.SINGLE)
        self.run_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(list_frame, command=self.run_listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.run_listbox.config(yscrollcommand=sb.set)
        self.run_listbox.bind("<<ListboxSelect>>", self._on_run_select)
        self.run_listbox.bind("<Double-Button-1>", lambda e: self._run_pipeline())

        # ---- 选项 ----
        frame_opt = ttk.LabelFrame(outer, text="④ 选项", padding=8)
        frame_opt.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(frame_opt, text="dry-run (只扫描配对，不做处理)",
                        variable=self.var_dry_run).pack(side=tk.LEFT, padx=(0,12))
        ttk.Checkbutton(frame_opt, text="--force (重写已存在的产物)",
                        variable=self.var_force).pack(side=tk.LEFT)

        # ---- 按钮 ----
        frame_btn = ttk.Frame(outer); frame_btn.pack(fill=tk.X, pady=(0, 8))
        self.btn_run = ttk.Button(frame_btn, text="▶  开始处理", command=self._run_pipeline, width=14)
        self.btn_run.pack(side=tk.LEFT)
        self.btn_open_qc = ttk.Button(frame_btn, text="打开最近 QC", command=self._open_last_qc, width=14)
        self.btn_open_qc.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_open_out = ttk.Button(frame_btn, text="打开 out-dir", command=self._open_out_dir, width=14)
        self.btn_open_out.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(frame_btn, text="退出", command=self.root.destroy, width=8).pack(side=tk.RIGHT)

        # ---- 日志 ----
        frame_log = ttk.LabelFrame(outer, text="⑤ 日志", padding=4)
        frame_log.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(frame_log, height=14, font=("Consolas", 9),
                                background="#111", foreground="#cfcfcf",
                                insertbackground="#fff", wrap="word")
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_sb = ttk.Scrollbar(frame_log, command=self.log_text.yview)
        log_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=log_sb.set, state=tk.DISABLED)

        # ---- 状态栏 ----
        ttk.Label(outer, textvariable=self.var_status,
                  foreground="#888").pack(anchor=tk.W, pady=(4, 0))

    # ------------------------- 事件处理 ------------------------------------
    def _scheme_dir(self) -> Path:
        return EXPERIMENT_DATA_DIR / self.var_scheme.get()

    def _scheme_out_dir(self) -> Path:
        return DEFAULT_DERIVATIVES_DIR / self.var_scheme.get()

    def _on_scheme_change(self) -> None:
        scheme = self.var_scheme.get()
        meta = next((s for s in SCHEMES if s["id"] == scheme), SCHEMES[0])
        self.scheme_status.configure(text=f"→ 当前方案：{meta['label']}")
        # 自动填默认路径（若用户没改过）
        if not self.var_data_dir.get() or self._is_auto_path(self.var_data_dir.get()):
            self.var_data_dir.set(str(self._scheme_dir()))
        if not self.var_out_dir.get() or self._is_auto_path(self.var_out_dir.get()):
            self.var_out_dir.set(str(self._scheme_out_dir()))
        # 切方案后旧的 runs 列表已失效
        self._clear_runs_display(note="(切换方案后请重新点 “扫描可用录制”)")

    def _is_auto_path(self, p: str) -> bool:
        """判断当前路径是不是 GUI 自己填进去的两套默认值之一。"""
        try:
            P = Path(p).resolve()
        except Exception:
            return True
        candidates = []
        for s in SCHEMES:
            candidates.append((EXPERIMENT_DATA_DIR / s["id"]).resolve())
            candidates.append((DEFAULT_DERIVATIVES_DIR / s["id"]).resolve())
        return P in candidates

    def _browse_data_dir(self) -> None:
        d = filedialog.askdirectory(title="选择 data-dir",
                                    initialdir=self.var_data_dir.get() or str(EXPERIMENT_DATA_DIR))
        if d:
            self.var_data_dir.set(d)

    def _browse_out_dir(self) -> None:
        d = filedialog.askdirectory(title="选择 out-dir",
                                    initialdir=self.var_out_dir.get() or str(DEFAULT_DERIVATIVES_DIR))
        if d:
            self.var_out_dir.set(d)

    # ------------------------- 扫描 / 列出录制 -----------------------------
    def _refresh_runs(self) -> None:
        scheme = self.var_scheme.get()
        data_dir = self._effective_data_dir()
        if data_dir and not data_dir.exists():
            messagebox.showwarning("路径不存在", f"data-dir 不存在：\n{data_dir}")
            return
        self._set_status(f"扫描 {scheme} 数据 ...")
        self.root.update_idletasks()
        runs = _list_runs(scheme, data_dir)
        self.runs = runs
        if self.run_listbox is not None:
            self.run_listbox.delete(0, tk.END)
            if not runs:
                self.run_listbox.insert(tk.END, "  (没扫到任何录制；请先用实验脚本采集数据)")
                self._set_status("没有可处理的录制。")
            else:
                for r in runs:
                    self.run_listbox.insert(tk.END, "  " + r.display)
                self._set_status(f"扫到 {len(runs)} 次录制。")

    def _clear_runs_display(self, note: str = "") -> None:
        if self.run_listbox is None:
            return
        self.run_listbox.delete(0, tk.END)
        if note:
            self.run_listbox.insert(tk.END, "  " + note)
        self.runs = []

    def _clear_selection(self) -> None:
        self.var_filter_subject.set("")
        self.var_filter_date.set("")
        if self.run_listbox is not None:
            self.run_listbox.selection_clear(0, tk.END)

    def _on_run_select(self, _evt=None) -> None:
        if self.run_listbox is None:
            return
        sel = self.run_listbox.curselection()
        if not sel or sel[0] >= len(self.runs):
            return
        r = self.runs[sel[0]]
        self.var_filter_subject.set(r.subject)
        self.var_filter_date.set(r.date)

    # ------------------------- 跑 pipeline ---------------------------------
    def _effective_data_dir(self) -> Optional[Path]:
        s = self.var_data_dir.get().strip()
        return Path(s).expanduser() if s else None

    def _effective_out_dir(self) -> Optional[Path]:
        s = self.var_out_dir.get().strip()
        return Path(s).expanduser() if s else None

    def _run_pipeline(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            messagebox.showinfo("正在运行", "已经有一个 pipeline 在跑，等它结束再说。")
            return

        scheme = self.var_scheme.get()
        data_dir = self._effective_data_dir()
        out_dir = self._effective_out_dir()
        if data_dir and not data_dir.exists():
            messagebox.showerror("data-dir 不存在", f"找不到：\n{data_dir}")
            return

        extra: List[str] = []
        if self.var_dry_run.get():
            extra.append("--dry-run")
        if self.var_force.get():
            extra.append("--force")
        subj = self.var_filter_subject.get().strip()
        date = self.var_filter_date.get().strip()
        if subj:
            extra += ["--subject", subj]
        if date:
            if not (len(date) == 8 and date.isdigit()):
                messagebox.showerror("date 格式错误", "日期请用 YYYYMMDD (例如 20260521)")
                return
            extra += ["--date", date]

        cmd = _build_cli(scheme, data_dir=data_dir, out_dir=out_dir, extra=extra)
        self._append_log("\n" + "=" * 72 + "\n")
        self._append_log(f"[run] {' '.join(_quote(a) for a in cmd)}\n")
        self._append_log("=" * 72 + "\n")

        self._done_evt = threading.Event()
        self._rc_holder = {}
        self._pending_qc = self._guess_qc_path(out_dir or self._scheme_out_dir(), subj, date)
        self._set_status(f"运行中 ... ({scheme}{'  dry-run' if self.var_dry_run.get() else ''})")
        self.btn_run.configure(state=tk.DISABLED, text="处理中...")

        self._worker = threading.Thread(
            target=_spawn,
            args=(cmd, HERE, self._out_q, self._done_evt, self._rc_holder),
            daemon=True,
        )
        self._worker.start()

    def _poll_output(self) -> None:
        try:
            while True:
                line = self._out_q.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        if self._done_evt is not None and self._done_evt.is_set():
            rc = self._rc_holder.get("rc", -1)
            self._append_log(f"\n[done] exit code = {rc}\n")
            self._set_status(f"完成 (exit={rc})。")
            self.btn_run.configure(state=tk.NORMAL, text="▶  开始处理")
            self._done_evt = None
            self._worker = None
            # 跑成功且不是 dry-run，尝试自动打开 QC
            if rc == 0 and not self.var_dry_run.get() and self._pending_qc:
                self._try_open(self._pending_qc, fallback_search=True)
        self.root.after(self.POLL_MS, self._poll_output)

    # ------------------------- 工具栏按钮 ----------------------------------
    def _open_last_qc(self) -> None:
        out_dir = self._effective_out_dir() or self._scheme_out_dir()
        if not out_dir.exists():
            messagebox.showinfo("out-dir 不存在", f"还没有产物：\n{out_dir}")
            return
        reports = sorted(out_dir.rglob("report*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            messagebox.showinfo("没有 QC", f"{out_dir} 下还没有 QC HTML 报告。")
            return
        self._try_open(reports[0], fallback_search=False)

    def _open_out_dir(self) -> None:
        out_dir = self._effective_out_dir() or self._scheme_out_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(out_dir))   # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(out_dir)])
            else:
                subprocess.Popen(["xdg-open", str(out_dir)])
        except Exception as e:
            messagebox.showinfo("打开失败", f"{e}")

    # ------------------------- 辅助 ----------------------------------------
    def _try_open(self, path: Path, fallback_search: bool) -> None:
        if not path.exists() and fallback_search:
            # 找最近改动过的 report
            out_dir = self._effective_out_dir() or self._scheme_out_dir()
            reports = sorted(out_dir.rglob("report*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
            if reports:
                path = reports[0]
        if not path.exists():
            return
        try:
            webbrowser.open(path.resolve().as_uri())
        except Exception as e:
            self._append_log(f"[open] 打开 QC 失败: {e}\n")

    def _guess_qc_path(self, out_dir: Path, subject: str, date: str) -> Optional[Path]:
        if subject and date:
            return out_dir / subject / "05_qc" / f"report_{date}.html"
        if subject:
            return out_dir / subject / "05_qc" / "report.html"
        return None

    def _append_log(self, s: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, s)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_status(self, s: str) -> None:
        self.var_status.set(s)

    def run(self) -> None:
        self.root.mainloop()


def _quote(arg: str) -> str:
    if " " in arg or "\\" in arg:
        return f'"{arg}"'
    return arg


def main() -> int:
    try:
        ProcessingLauncher().run()
    except Exception as e:
        print(f"[fatal] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
