"""
实验启动器 — 图形化主入口 + Session 调度
────────────────────────────────────────
支持单独运行某个 Session 或自动串联 Session 3 → 4

用法:
  python launcher.py                    (GUI 模式)
  python launcher.py --subject Sub_01 --session 1 --windowed
  python launcher.py --subject Sub_01 --session all --windowed
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import traceback

from config import ExperimentConfig, ExperimentLauncher, MARKER_TABLE, parse_sessions
from video.camera_recorder_controlled import FFmpegCameraRecorder

TASK_BASELINE_DURATION = 60.0


def cleanup_all():
    if "utils" not in sys.modules:
        return
    try:
        from utils import cleanup_all as _cleanup_all
        _cleanup_all()
    except Exception:
        pass


def _scheme(cfg: ExperimentConfig) -> str:
    return getattr(cfg, "scheme", "motor_imagery") or "motor_imagery"


def get_scheme_data_dir(cfg: ExperimentConfig) -> Path:
    """<data_dir>/<scheme> — 两套方案的共同数据根目录"""
    return Path(cfg.data_dir) / _scheme(cfg)


def get_camera_output_dir(cfg: ExperimentConfig) -> Path:
    if cfg.camera_output_dir:
        return Path(cfg.camera_output_dir)
    return get_scheme_data_dir(cfg) / "video_records"


def create_camera_recorder(cfg: ExperimentConfig) -> FFmpegCameraRecorder:
    return FFmpegCameraRecorder(
        device_name=cfg.camera_device_name,
        width=cfg.camera_width,
        height=cfg.camera_height,
        fps=cfg.camera_fps,
        output_dir=get_camera_output_dir(cfg),
    )


# ============================================================
# 单个 Session 运行 (带错误保护)
# ============================================================

def run_session_safe(cfg: ExperimentConfig, session_num: str):
    """运行指定 Session, 带异常捕获和资源清理"""
    try:
        if session_num == "1":
            from sessions.session1_resting import run_session1
            run_session1(cfg)
        elif session_num == "2":
            from sessions.session2_artifacts import run_session2
            run_session2(cfg)
        elif session_num == "3":
            from sessions.session3_oddball import run_oddball
            from sessions.session3_ssvep import run_ssvep
            # Session 3: Oddball → 重基线 → SSVEP
            if cfg.run_oddball:
                print("\n" + "="*60)
                print("  Session 3 — 任务 3.1: 视觉 Oddball (P300)")
                print("="*60 + "\n")
                run_oddball(cfg)

                # 任务间重基线 (1 min 睁眼静息)
                if cfg.run_ssvep:
                    quick = bool(getattr(cfg, "quick_test", False))
                    baseline_duration = 3.0 if quick else TASK_BASELINE_DURATION
                    label_min = "3 秒" if quick else "1 分钟"
                    print(f"\n>>> 任务间重基线: {label_min}睁眼静息 (Marker 63) <<<\n")
                    from psychopy import visual, core
                    win = None
                    trigger = None
                    kb = None
                    try:
                        win = visual.Window(
                            size=(cfg.screen_width, cfg.screen_height),
                            screen=cfg.screen_id, fullscr=cfg.full_screen,
                            color=cfg.background_color, units="height",
                            allowGUI=False
                        )
                        from utils import (TriggerSender, KeyboardManager,
                                          draw_fixation, show_message_and_wait, register_resource)
                        register_resource("window", win)
                        trigger = TriggerSender(cfg.port_name, cfg.baud_rate, cfg.no_hardware)
                        kb = KeyboardManager()

                        show_message_and_wait(
                            win, kb,
                            f"任务间基线\n\n请盯住中央十字，保持放松\n持续 {label_min}\n\n按 空格键 开始",
                            font_size=38
                        )
                        trigger.send_and_log(MARKER_TABLE["S3_REST_BASELINE"], "S3_REST_BASELINE")

                        base_start = core.getTime()
                        while core.getTime() - base_start < baseline_duration:
                            draw_fixation(win, size=0.03, color=(0.5, 0.5, 0.5))
                            win.flip()
                            # ESC 安全退出
                            keys = kb.kb.getKeys(["escape"], waitRelease=False, clear=True)
                            for k in keys:
                                if k.name == "escape":
                                    print("\n>>> 实验被用户终止 (ESC) <<<")
                                    raise SystemExit(0)

                        trigger.send_and_log(MARKER_TABLE["S3_REST_BASELINE"], "S3_REST_BASELINE_END")
                    finally:
                        # 关键：必须显式关闭 trigger 和 window，否则下一个 run_ssvep
                        # 创建新 TriggerSender 时会因为 COM 口仍被占用而降级到 no_hardware,
                        # 表现为 SSVEP 阶段 EEG 软件完全收不到 Marker。
                        if trigger is not None:
                            try:
                                trigger.close()
                            except Exception:
                                pass
                        if win is not None:
                            try:
                                win.close()
                            except Exception:
                                pass
                        # 给 Windows 串口驱动留出释放时间，避免下个 TriggerSender 撞上 "Access denied"
                        core.wait(0.5)

            if cfg.run_ssvep:
                print("\n" + "="*60)
                print("  Session 3 — 任务 3.2: SSVEP")
                print("="*60 + "\n")
                run_ssvep(cfg)

        elif session_num == "4":
            scheme = _scheme(cfg)
            # 不论怎么改 GUI，这里的打印必须能让主试在终端看到方案路由结果。
            # 如果用户在 GUI 选了情绪但这里仍打印 motor_imagery，说明 scheme 没传过来。
            print("\n" + "="*60)
            print(f"  [S4 路由] cfg.scheme = {scheme!r}")
            if scheme == "emotion":
                from sessions.session4_emotion import run_session4 as run_session4_emotion
                print("  Session 4 — 情绪识别实验 (音视频刺激, 18 trials)")
                print("="*60 + "\n")
                run_session4_emotion(cfg)
            elif scheme == "auditory_attention":
                from sessions.session4_auditory import run_session4 as run_session4_auditory
                print("  Session 4 — 听觉注意力实验 (HRTF 空间化双说话人, AAD)")
                print("="*60 + "\n")
                run_session4_auditory(cfg)
            elif scheme == "motor_imagery":
                from sessions.session4_mi import run_session4 as run_session4_mi
                print("  Session 4 — 离线双手运动想象采集")
                print("="*60 + "\n")
                run_session4_mi(cfg)
            else:
                raise ValueError(
                    f"未知 scheme={scheme!r}; 期望 'motor_imagery' / 'emotion' / 'auditory_attention'. "
                    f"请检查 GUI / --scheme 参数是否正确传入。"
                )

    except SystemExit:
        pass
    except Exception as e:
        print(f"\nSession {session_num} 异常: {e}")
        traceback.print_exc()
    finally:
        cleanup_all()


# ============================================================
# 多 Session 串联调度 (任意子集 / 全流程 / 单 Session 都走这里)
# ============================================================

SESSION_DESCRIPTIONS = {
    "1": "Session 1 — 纯净静息态基线 (4 min)",
    "2": "Session 2 — 伪迹模板采集 (15 min)",
    "3": "Session 3 — 银标准任务态 (~19 min)",
    # S4 在 _describe_session 里按 scheme 动态返回
}


def _describe_session(cfg: ExperimentConfig, sess_num: str) -> str:
    if sess_num == "4":
        scheme = _scheme(cfg)
        if scheme == "emotion":
            return "Session 4 — 情绪识别 (18 trials)"
        elif scheme == "auditory_attention":
            return "Session 4 — 听觉注意力 AAD (~32 trials)"
        else:
            return "Session 4 — 离线双手 MI 采集 (~12-18 min)"
    return SESSION_DESCRIPTIONS.get(sess_num, f"Session {sess_num}")


def run_session_sequence(cfg: ExperimentConfig, session_list):
    """依次执行 session_list 里的所有 Session。

    单元素时和 run_session_safe 行为完全一致，多元素时在 Session 之间插入 5 秒
    （或 quick-test 时 1 秒）倒计时，期间支持 Ctrl+C 中止整段串联。
    """
    total = len(session_list)
    print("\n" + "="*60)
    print(f"  本次将执行 {total} 个 Session：{' → '.join(session_list)}")
    print("="*60 + "\n")

    for idx, sess_num in enumerate(session_list):
        sess_desc = _describe_session(cfg, sess_num)
        print("\n" + "█"*60)
        print(f"  [{idx+1}/{total}] {sess_desc}")
        print("█"*60 + "\n")

        cfg.session = sess_num
        run_session_safe(cfg, sess_num)

        if idx < total - 1:
            print("\n>>> 准备进入下一阶段。请确认被试状态良好 (Ctrl+C 可中止剩余流程) <<<\n")
            import time
            countdown_seconds = 1 if bool(getattr(cfg, "quick_test", False)) else 5
            try:
                for t in range(countdown_seconds, 0, -1):
                    print(f"  {t}...", end=" ", flush=True)
                    time.sleep(1)
                print("开始!\n")
            except KeyboardInterrupt:
                print("\n\n>>> 主试在过渡期中止了串联流程 (Ctrl+C) <<<")
                raise SystemExit(0)

    print("\n" + "="*60)
    print(f"  全部 {total} 个 Session 已完成！")
    print("="*60 + "\n")


# ============================================================
# 进度显示窗口 (全流程模式)
# ============================================================

class ProgressWindow:
    """全流程模式的进度窗口"""

    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg
        self.root = tk.Tk()
        self.root.title("P4 EEG 实验 — 进度")
        self.root.geometry("400x300")

        main = ttk.Frame(self.root, padding=20)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="实验进行中...",
                 font=("Microsoft YaHei", 14, "bold")).pack(pady=10)

        self.status_label = ttk.Label(main, text="准备开始...",
                                      font=("Microsoft YaHei", 11))
        self.status_label.pack(pady=10)

        self.progress = ttk.Progressbar(main, mode="indeterminate", length=300)
        self.progress.pack(pady=10)
        self.progress.start()

        self.root.update()

    def update_status(self, text: str):
        self.status_label.config(text=text)
        self.root.update()

    def close(self):
        self.progress.stop()
        self.root.quit()
        self.root.destroy()


# ============================================================
# 入口
# ============================================================

def main() -> int:
    recorder = None
    camera_started = False
    exit_code = 0

    try:
        if len(sys.argv) > 1:
            from config import config_from_args
            cfg = config_from_args()
            sys.argv = [sys.argv[0]]
        else:
            launcher = ExperimentLauncher()
            cfg = launcher.run()

            if cfg is None:
                print("实验被用户取消。")
                return 0

        camera_output_dir = get_camera_output_dir(cfg).resolve()
        scheme = _scheme(cfg)
        scheme_label_map = {
            "motor_imagery": "运动想象 (MI)",
            "emotion": "情绪识别 (Emotion)",
            "auditory_attention": "听觉注意力 (AAD)",
        }
        scheme_label = scheme_label_map.get(scheme, scheme)

        # 把用户输入的 "1,3" / "all" / "4" 统一解析成 ["1","3"] 等有序列表
        session_list = parse_sessions(cfg)

        print("\n" + "="*60)
        print(f"  P4 EEG 降噪实验")
        print(f"  方案 (Scheme): {scheme} — {scheme_label}")
        print(f"  被试: {cfg.subject_id}")
        print(f"  Sessions: {cfg.session}  ->  执行顺序: {session_list}")
        print(f"  数据根目录: {get_scheme_data_dir(cfg).resolve()}")
        print(f"  串口: {'无硬件' if cfg.no_hardware else cfg.port_name}")
        print(f"  相机: {'启用' if cfg.camera_enabled else '禁用'}")
        if bool(getattr(cfg, "quick_test", False)):
            print(f"  模式: [quick-test] 冒烟测试，所有 Session 用极短时长 / 极少 trial")
        if cfg.camera_enabled:
            print(f"  相机设备: {cfg.camera_device_name}")
            print(f"  视频保存: {camera_output_dir}")
        print("="*60 + "\n")

        if cfg.camera_enabled:
            print("[Camera] 正在启动相机录制...")
            recorder = create_camera_recorder(cfg)
            try:
                video_path, timestamp_path, metadata_path = recorder.start()
            except Exception as camera_error:
                print(f"\n相机启动失败: {camera_error}")
                if recorder.log_path is not None:
                    print(f"[Camera] FFmpeg 日志: {recorder.log_path.resolve()}")
                return 1
            camera_started = True
            print(f"[Camera] 已开始录制: {video_path.resolve()}")
            print(f"[Camera] 时间戳文件: {timestamp_path.resolve()}")
            print(f"[Camera] Metadata: {metadata_path.resolve()}")
        else:
            print("[Camera] 已禁用，跳过录像。")

        # 单 / 多 / 全流程 统一走 run_session_sequence
        run_session_sequence(cfg, session_list)

    except SystemExit:
        pass
    except KeyboardInterrupt:
        print("\n\n>>> 实验被用户中断 (Ctrl+C) <<<")
    except Exception as e:
        exit_code = 1
        print(f"\n启动器异常: {e}")
        traceback.print_exc()
    finally:
        if camera_started and recorder is not None:
            try:
                print("\n[Camera] 正在停止相机录制...")
                result = recorder.stop()
                print("[Camera] 录制已停止。")
                print(f"[Camera] 视频: {result['video_path']}")
                print(f"[Camera] 时间戳: {result['timestamp_path']}")
                print(f"[Camera] Metadata: {result['metadata_path']}")
                print(f"[Camera] FFmpeg 日志: {result['log_path']}")
            except Exception as camera_error:
                print(f"⚠️ [Camera] 停止录制失败: {camera_error}")
        cleanup_all()
        print("\n实验程序已退出。")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
