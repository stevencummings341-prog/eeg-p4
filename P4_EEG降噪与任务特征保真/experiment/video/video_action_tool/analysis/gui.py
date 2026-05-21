"""Tkinter GUI for P4 video action extraction.

This is a thin, user-friendly wrapper around ``analysis.pipeline``. It keeps the
raw videos untouched and writes all derived files to a chosen output directory.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.request
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk

from .extractors import DEFAULT_FACE_LANDMARKER_MODEL
from .pipeline import PipelineConfig, run_pipeline


SCRIPT_DIR = Path(__file__).resolve().parent
VIDEO_DIR = SCRIPT_DIR.parent
DEFAULT_RECORDS_DIR = VIDEO_DIR / "scratch" / "video_records"
FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)


class VideoActionGUI:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("P4 EEG 视频动作提取工具")
        self.root.geometry("920x700")
        self.root.minsize(860, 640)

        self.video_path_var = StringVar()
        self.output_dir_var = StringVar()
        self.start_var = StringVar(value="0")
        self.duration_var = StringVar(value="60")
        self.process_all_var = BooleanVar(value=False)
        self.save_preview_var = BooleanVar(value=True)
        self.preview_seconds_var = StringVar(value="60")
        self.skip_yolo_var = BooleanVar(value=False)
        self.skip_face_var = BooleanVar(value=False)
        self.status_var = StringVar(value="请选择视频文件，然后点击“开始处理”。")
        self.model_status_var = StringVar()

        self.last_output_dir: Path | None = None
        self.worker_thread: threading.Thread | None = None
        self.msg_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self._build_ui()
        self._set_default_paths()
        self._refresh_model_status()
        self.root.after(100, self._poll_queue)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = ttk.Frame(self.root, padding=(18, 16, 18, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="P4 EEG 视频动作提取工具", font=("Microsoft YaHei UI", 18, "bold"))
        title.grid(row=0, column=0, sticky="w")
        subtitle = ttk.Label(
            header,
            text="YOLOv8-Pose + MediaPipe Face Landmarker：输出逐帧特征、动作事件表和可选预览视频。",
            foreground="#555555",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(6, 0))

        form = ttk.Frame(self.root, padding=(18, 8, 18, 8))
        form.grid(row=1, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="视频文件").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.video_path_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(form, text="选择视频...", command=self._choose_video).grid(row=0, column=2, sticky="e")

        ttk.Label(form, text="输出目录").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.output_dir_var).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(form, text="选择目录...", command=self._choose_output_dir).grid(row=1, column=2, sticky="e")

        time_box = ttk.LabelFrame(form, text="处理范围", padding=(12, 8))
        time_box.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        for i in range(8):
            time_box.columnconfigure(i, weight=0)
        time_box.columnconfigure(7, weight=1)

        ttk.Label(time_box, text="起始秒").grid(row=0, column=0, sticky="w")
        ttk.Entry(time_box, textvariable=self.start_var, width=10).grid(row=0, column=1, sticky="w", padx=(6, 18))
        ttk.Label(time_box, text="处理时长秒").grid(row=0, column=2, sticky="w")
        self.duration_entry = ttk.Entry(time_box, textvariable=self.duration_var, width=10)
        self.duration_entry.grid(row=0, column=3, sticky="w", padx=(6, 12))
        ttk.Checkbutton(
            time_box,
            text="处理完整视频",
            variable=self.process_all_var,
            command=self._toggle_duration,
        ).grid(row=0, column=4, sticky="w", padx=(0, 18))
        ttk.Button(time_box, text="快速 60 秒", command=lambda: self._set_duration("60")).grid(row=0, column=5, padx=4)
        ttk.Button(time_box, text="快速 5 秒测试", command=lambda: self._set_duration("5")).grid(row=0, column=6, padx=4)

        options = ttk.LabelFrame(form, text="输出与高级选项", padding=(12, 8))
        options.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        options.columnconfigure(5, weight=1)

        ttk.Checkbutton(options, text="保存叠加预览视频", variable=self.save_preview_var).grid(row=0, column=0, sticky="w")
        ttk.Label(options, text="预览最长秒").grid(row=0, column=1, sticky="w", padx=(18, 4))
        ttk.Entry(options, textvariable=self.preview_seconds_var, width=8).grid(row=0, column=2, sticky="w", padx=(0, 18))
        ttk.Checkbutton(options, text="跳过 YOLO", variable=self.skip_yolo_var).grid(row=0, column=3, sticky="w", padx=(0, 12))
        ttk.Checkbutton(options, text="跳过人脸", variable=self.skip_face_var).grid(row=0, column=4, sticky="w")

        model_row = ttk.Frame(form)
        model_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        model_row.columnconfigure(1, weight=1)
        ttk.Label(model_row, text="Face 模型").grid(row=0, column=0, sticky="w")
        ttk.Label(model_row, textvariable=self.model_status_var, foreground="#555555").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Button(model_row, text="下载/修复模型", command=self._download_model).grid(row=0, column=2, sticky="e")

        main = ttk.Frame(self.root, padding=(18, 4, 18, 8))
        main.grid(row=2, column=0, sticky="nsew")
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)

        progress_row = ttk.Frame(main)
        progress_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        progress_row.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ttk.Label(progress_row, textvariable=self.status_var, width=34).grid(row=0, column=1, sticky="e")

        log_box = ttk.LabelFrame(main, text="运行日志", padding=(8, 8))
        log_box.grid(row=1, column=0, sticky="nsew")
        log_box.rowconfigure(0, weight=1)
        log_box.columnconfigure(0, weight=1)
        self.log_text = self._make_log_widget(log_box)

        footer = ttk.Frame(self.root, padding=(18, 8, 18, 16))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(footer, text="开始处理", command=self._start_run)
        self.run_button.grid(row=0, column=1, padx=6)
        ttk.Button(footer, text="打开输出目录", command=self._open_output_dir).grid(row=0, column=2, padx=6)
        ttk.Button(footer, text="退出", command=self.root.destroy).grid(row=0, column=3, padx=6)

    def _make_log_widget(self, parent: ttk.Frame):
        import tkinter as tk

        text = tk.Text(parent, wrap="word", height=15, state="disabled", font=("Consolas", 10))
        yscroll = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=yscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        return text

    def _set_default_paths(self) -> None:
        videos = sorted(DEFAULT_RECORDS_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if videos:
            self.video_path_var.set(str(videos[0]))
            self._auto_output_dir(videos[0])
            self._log(f"默认选择最近视频：{videos[0].name}")
        else:
            self.output_dir_var.set(str(DEFAULT_RECORDS_DIR / "analysis_outputs"))

    def _refresh_model_status(self) -> None:
        if DEFAULT_FACE_LANDMARKER_MODEL.exists():
            size_kb = DEFAULT_FACE_LANDMARKER_MODEL.stat().st_size / 1024
            self.model_status_var.set(f"已就绪 ({size_kb:.0f} KB)")
        else:
            self.model_status_var.set("缺失：请点击“下载/修复模型”")

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要处理的视频",
            initialdir=str(DEFAULT_RECORDS_DIR if DEFAULT_RECORDS_DIR.exists() else VIDEO_DIR),
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")],
        )
        if path:
            video_path = Path(path)
            self.video_path_var.set(str(video_path))
            self._auto_output_dir(video_path)
            self._log(f"已选择视频：{video_path}")

    def _choose_output_dir(self) -> None:
        path = filedialog.askdirectory(
            title="选择输出目录",
            initialdir=self.output_dir_var.get() or str(DEFAULT_RECORDS_DIR),
        )
        if path:
            self.output_dir_var.set(path)
            self._log(f"输出目录：{path}")

    def _auto_output_dir(self, video_path: Path) -> None:
        self.output_dir_var.set(str(video_path.parent / "analysis_outputs" / video_path.stem))

    def _toggle_duration(self) -> None:
        state = "disabled" if self.process_all_var.get() else "normal"
        self.duration_entry.configure(state=state)

    def _set_duration(self, value: str) -> None:
        self.process_all_var.set(False)
        self._toggle_duration()
        self.duration_var.set(value)

    def _download_model(self) -> None:
        if self._is_busy():
            return
        self.run_button.configure(state="disabled")
        self.status_var.set("正在下载 Face 模型...")
        self._log("开始下载 MediaPipe Face Landmarker 模型。")
        thread = threading.Thread(target=self._download_model_worker, daemon=True)
        thread.start()

    def _download_model_worker(self) -> None:
        try:
            DEFAULT_FACE_LANDMARKER_MODEL.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = DEFAULT_FACE_LANDMARKER_MODEL.with_suffix(".task.tmp")
            with urllib.request.urlopen(FACE_MODEL_URL, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                with tmp_path.open("wb") as f:
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            self.msg_queue.put(("progress", (done, total)))
            tmp_path.replace(DEFAULT_FACE_LANDMARKER_MODEL)
            self.msg_queue.put(("log", f"模型下载完成：{DEFAULT_FACE_LANDMARKER_MODEL}"))
            self.msg_queue.put(("model", None))
            self.msg_queue.put(("done_download", None))
        except Exception as exc:  # noqa: BLE001 - GUI should surface any failure.
            self.msg_queue.put(("error", f"模型下载失败：{exc}"))
            self.msg_queue.put(("done_download", None))

    def _start_run(self) -> None:
        if self._is_busy():
            messagebox.showinfo("正在运行", "当前已有任务在运行，请等待完成。")
            return

        try:
            cfg = self._build_config()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        if not cfg.skip_face_mesh and not DEFAULT_FACE_LANDMARKER_MODEL.exists():
            messagebox.showerror("模型缺失", "Face Landmarker 模型缺失，请先点击“下载/修复模型”。")
            return

        self.progress["value"] = 0
        self.status_var.set("处理中...")
        self.run_button.configure(state="disabled")
        self.last_output_dir = cfg.output_dir
        self._log("=" * 72)
        self._log(f"开始处理：{cfg.video_path}")
        self._log(f"输出目录：{cfg.output_dir}")
        self._log(f"起始秒：{cfg.start_seconds}；时长：{'完整视频' if cfg.duration_seconds is None else cfg.duration_seconds}")

        self.worker_thread = threading.Thread(target=self._run_worker, args=(cfg,), daemon=True)
        self.worker_thread.start()

    def _build_config(self) -> PipelineConfig:
        video_path = Path(self.video_path_var.get().strip())
        if not video_path.exists():
            raise ValueError("请选择一个存在的视频文件。")

        output_dir_text = self.output_dir_var.get().strip()
        if not output_dir_text:
            raise ValueError("请选择输出目录。")

        start_seconds = self._parse_float(self.start_var.get(), "起始秒", allow_zero=True)
        duration_seconds = None
        if not self.process_all_var.get():
            duration_seconds = self._parse_float(self.duration_var.get(), "处理时长秒", allow_zero=False)

        preview_seconds = self._parse_float(self.preview_seconds_var.get(), "预览最长秒", allow_zero=False)

        def progress_callback(done: int, total: int) -> None:
            self.msg_queue.put(("progress", (done, total)))

        return PipelineConfig(
            video_path=video_path,
            output_dir=Path(output_dir_text),
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            save_preview=self.save_preview_var.get(),
            preview_max_seconds=preview_seconds,
            skip_yolo=self.skip_yolo_var.get(),
            skip_face_mesh=self.skip_face_var.get(),
            progress=False,
            progress_callback=progress_callback,
        )

    def _run_worker(self, cfg: PipelineConfig) -> None:
        start = time.perf_counter()
        try:
            meta = run_pipeline(cfg)
            elapsed = time.perf_counter() - start
            self.msg_queue.put(("result", (meta, elapsed)))
        except Exception as exc:  # noqa: BLE001 - GUI should surface any failure.
            self.msg_queue.put(("error", f"处理失败：{exc}"))

    def _parse_float(self, text: str, label: str, allow_zero: bool) -> float:
        try:
            value = float(text.strip())
        except Exception as exc:
            raise ValueError(f"{label}必须是数字。") from exc
        if value < 0 or (value == 0 and not allow_zero):
            raise ValueError(f"{label}必须{'大于等于 0' if allow_zero else '大于 0'}。")
        return value

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "progress":
                    done, total = payload
                    pct = 0 if not total else min(100.0, done * 100.0 / total)
                    self.progress["value"] = pct
                    self.status_var.set(f"{done}/{total} 帧 ({pct:.1f}%)")
                elif kind == "log":
                    self._log(str(payload))
                elif kind == "model":
                    self._refresh_model_status()
                elif kind == "done_download":
                    self.run_button.configure(state="normal")
                    self.status_var.set("模型就绪。")
                elif kind == "result":
                    meta, elapsed = payload
                    self._handle_success(meta, elapsed)
                elif kind == "error":
                    self._handle_error(str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle_success(self, meta: dict, elapsed: float) -> None:
        processed = meta.get("processed", {})
        outputs = meta.get("outputs", {})
        self.progress["value"] = 100
        self.status_var.set("处理完成")
        self.run_button.configure(state="normal")
        self._log("处理完成。")
        self._log(f"耗时：{elapsed:.1f} 秒")
        self._log(f"逐帧数量：{processed.get('frames_written')}")
        self._log(f"Face 检出率：{processed.get('face_detection_rate'):.3f}")
        self._log(f"YOLO 检出率：{processed.get('yolo_detection_rate'):.3f}")
        self._log(f"事件数量：{processed.get('events_count')}，分类：{json.dumps(processed.get('events_breakdown', {}), ensure_ascii=False)}")
        self._log(f"事件表：{outputs.get('events_csv')}")
        self._log(f"逐帧表：{outputs.get('per_frame_parquet')}")
        messagebox.showinfo("完成", "视频动作提取已完成，结果已写入输出目录。")

    def _handle_error(self, message: str) -> None:
        self.status_var.set("出错")
        self.run_button.configure(state="normal")
        self._log(message)
        messagebox.showerror("处理失败", message)

    def _open_output_dir(self) -> None:
        path_text = self.output_dir_var.get().strip()
        path = Path(path_text) if path_text else self.last_output_dir
        if path is None:
            messagebox.showinfo("没有输出目录", "请先选择或生成输出目录。")
            return
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]

    def _is_busy(self) -> bool:
        return self.worker_thread is not None and self.worker_thread.is_alive()

    def _log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main() -> None:
    root = Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except Exception:
        pass
    app = VideoActionGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
