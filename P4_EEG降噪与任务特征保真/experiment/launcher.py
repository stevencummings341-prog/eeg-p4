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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import traceback

from config import ExperimentConfig, ExperimentLauncher, MARKER_TABLE

TASK_BASELINE_DURATION = 60.0


def cleanup_all():
    if "utils" not in sys.modules:
        return
    try:
        from utils import cleanup_all as _cleanup_all
        _cleanup_all()
    except Exception:
        pass


# ============================================================
# 单个 Session 运行 (带错误保护)
# ============================================================

def run_session_safe(cfg: ExperimentConfig, session_num: str):
    """运行指定 Session, 带异常捕获和资源清理"""
    try:
        if session_num == "1":
            from session1_resting import run_session1
            run_session1(cfg)
        elif session_num == "2":
            from session2_artifacts import run_session2
            run_session2(cfg)
        elif session_num == "3":
            from session3_oddball import run_oddball
            from session3_ssvep import run_ssvep
            # Session 3: Oddball → 重基线 → SSVEP
            if cfg.run_oddball:
                print("\n" + "="*60)
                print("  Session 3 — 任务 3.1: 视觉 Oddball (P300)")
                print("="*60 + "\n")
                run_oddball(cfg)

                # 任务间重基线 (1 min 睁眼静息)
                if cfg.run_ssvep:
                    print("\n>>> 任务间重基线: 1 分钟睁眼静息 (Marker 63) <<<\n")
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
                            "任务间基线\n\n请盯住中央十字，保持放松\n持续 1 分钟\n\n按 空格键 开始",
                            font_size=38
                        )
                        trigger.send_and_log(MARKER_TABLE["S3_REST_BASELINE"], "S3_REST_BASELINE")

                        base_start = core.getTime()
                        while core.getTime() - base_start < TASK_BASELINE_DURATION:
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
            from session3_oddball import run_oddball
            from session3_ssvep import run_ssvep
            # Session 4: 自然态 (重跑 Oddball + SSVEP, 使用 S4 独立 8-bit Marker)
            cfg.natural_mode = True

            if cfg.run_oddball:
                print("\n" + "="*60)
                print("  Session 4 (自然态) — 任务 4.1: 视觉 Oddball")
                print("="*60 + "\n")
                run_oddball(cfg)

            if cfg.run_ssvep:
                # run_oddball 末尾会 cleanup_all() 关闭 COM3, 但 Windows 串口驱动
                # 有 ~100-300ms 的释放延迟, 立刻新建 TriggerSender 会撞 "Access denied"。
                from psychopy import core as _core
                _core.wait(0.5)
                print("\n" + "="*60)
                print("  Session 4 (自然态) — 任务 4.2: SSVEP")
                print("="*60 + "\n")
                run_ssvep(cfg)

    except SystemExit:
        pass
    except Exception as e:
        print(f"\n❌ Session {session_num} 异常: {e}")
        traceback.print_exc()
    finally:
        cleanup_all()


# ============================================================
# 完整实验流程 (S1 → S2 → S3 → S4)
# ============================================================

def run_full_experiment(cfg: ExperimentConfig):
    """运行完整实验流程 (4 个 Session 依次)"""
    order = cfg.session_order  # "3_then_4" 或 "4_then_3"

    session_sequence = []

    # Session 1 + 2 总是先跑 (与顺序无关)
    session_sequence += [
        ("1", "Session 1 — 纯净静息态基线 (4 min)"),
        ("2", "Session 2 — 伪迹模板采集 (15 min)"),
    ]

    if order == "3_then_4":
        session_sequence += [
            ("3", "Session 3 — 银标准任务态 (~19 min)"),
            ("4", "Session 4 — 自然态测试集 (~18 min)"),
        ]
    else:  # "4_then_3" — 反向平衡
        session_sequence += [
            ("4", "Session 4 — 自然态测试集 (~18 min)"),
            ("3", "Session 3 — 银标准任务态 (~19 min)"),
        ]

    total_sessions = len(session_sequence)

    for idx, (sess_num, sess_desc) in enumerate(session_sequence):
        print("\n" + "█"*60)
        print(f"  [{idx+1}/{total_sessions}] {sess_desc}")
        print("█"*60 + "\n")

        # 更新 session 号
        cfg.session = sess_num
        if sess_num == "4":
            cfg.natural_mode = True
        else:
            cfg.natural_mode = False

        run_session_safe(cfg, sess_num)

        if idx < total_sessions - 1:
            print("\n>>> 准备进入下一阶段。请确认被试状态良好 (Ctrl+C 可中止全流程) <<<\n")
            # 5 秒倒计时, 支持 Ctrl+C 中止 (这里没有 PsychoPy 窗口, 用 KeyboardInterrupt 即可)
            import time
            try:
                for t in range(5, 0, -1):
                    print(f"  {t}...", end=" ", flush=True)
                    time.sleep(1)
                print("开始!\n")
            except KeyboardInterrupt:
                print("\n\n>>> 主试在过渡期中止了全流程 (Ctrl+C) <<<")
                raise SystemExit(0)

    print("\n" + "="*60)
    print("  全部实验完成!")
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

if __name__ == "__main__":
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
                sys.exit(0)

        print("\n" + "="*60)
        print(f"  P4 EEG 降噪实验")
        print(f"  被试: {cfg.subject_id}")
        print(f"  Session: {cfg.session}")
        print(f"  串口: {'无硬件' if cfg.no_hardware else cfg.port_name}")
        print("="*60 + "\n")

        if cfg.session == "all":
            # 完整流程
            run_full_experiment(cfg)
        else:
            # 单个 Session
            run_session_safe(cfg, cfg.session)

    except SystemExit:
        pass
    except KeyboardInterrupt:
        print("\n\n>>> 实验被用户中断 (Ctrl+C) <<<")
    except Exception as e:
        print(f"\n❌ 启动器异常: {e}")
        traceback.print_exc()
    finally:
        cleanup_all()
        print("\n实验程序已退出。")
