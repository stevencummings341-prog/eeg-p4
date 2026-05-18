"""
Session 3 — 视觉 Oddball (P300 时域瞬时特征验证)
──────────────────────────────────────────────
标准刺激 (蓝色圆, 75%) vs 靶刺激 (红色圆, 25%)
刺激呈现 200ms, ITI 800-1000ms 随机
每 Trial 刺激前 500ms 强制静息窗口

Marker 体系:
  S3: 61=标准, 62=靶刺激
  S4: 81=标准, 82=靶刺激 (natural_mode=True)

依赖: config.py, utils.py
用法:
  python session3_oddball.py                                    (GUI启动)
  python session3_oddball.py --subject Sub_01 --windowed        (S3)
  python session3_oddball.py --session 4 --forced-blink 0.3
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import random
import numpy as np
from psychopy import visual, core

from config import (
    ExperimentConfig, MARKER_TABLE, get_marker, config_from_args, ExperimentLauncher
)
from utils import (
    TriggerSender, KeyboardManager, draw_fixation, draw_text_centered,
    show_message, show_message_and_wait, save_data, cleanup_all
)


# ============================================================
# 刺激参数
# ============================================================

N_TOTAL = 200          # 总试次
TARGET_RATIO = 0.25    # 靶刺激 25% = 50 次
N_TARGET = int(N_TOTAL * TARGET_RATIO)    # 50
N_STANDARD = N_TOTAL - N_TARGET           # 150

STIM_DURATION = 0.200          # 刺激呈现 200ms
ITI_MIN = 0.800                # ITI 最小值
ITI_MAX = 1.000                # ITI 最大值
PRE_STIM_QUIET = 0.500         # 刺激前强制静息 500ms
BEHAVIOR_CHECK_INTERVAL = 100  # 每 100 trials 行为验证

# 刺激视觉参数
CIRCLE_RADIUS = 0.08            # 归一化高度单位
BLUE_COLOR = (0.0, 0.4, 0.8)
RED_COLOR = (0.9, 0.1, 0.1)
FORCED_BLINK_EMOJI = "👀"


# ============================================================
# Main
# ============================================================

def run_oddball(cfg: ExperimentConfig):
    """运行视觉 Oddball 任务 (Session 3 或 Session 4)"""

    is_natural = cfg.natural_mode
    session_label = "S4 (自然态)" if is_natural else "S3 (银标准)"

    # ---- 初始化 ----
    trigger = TriggerSender(cfg.port_name, cfg.baud_rate, cfg.no_hardware)

    win = visual.Window(
        size=(cfg.screen_width, cfg.screen_height),
        screen=cfg.screen_id, fullscr=cfg.full_screen,
        color=cfg.background_color, units="height",
        allowGUI=False
    )
    from utils import register_resource
    register_resource("window", win)

    kb = KeyboardManager()

    # 预创建刺激对象
    fixation_cross = None  # 用 draw_fixation 函数

    circle_std = visual.Circle(
        win, radius=CIRCLE_RADIUS, fillColor=BLUE_COLOR,
        lineColor=None, edges=128
    )
    circle_target = visual.Circle(
        win, radius=CIRCLE_RADIUS, fillColor=RED_COLOR,
        lineColor=None, edges=128
    )

    forced_blink_stim = visual.TextStim(
        win, text=FORCED_BLINK_EMOJI, font="Segoe UI Emoji",
        pos=(0, 0.15), height=0.1, color=(1, 1, 1)
    )

    # ---- 生成试次序列 (伪随机: 连续靶刺激不超过 2 个) ----
    trials = _generate_trial_sequence(N_STANDARD, N_TARGET)
    n_forced_blinks = 0
    if is_natural and cfg.forced_blink_ratio > 0:
        target_indices = [i for i, t in enumerate(trials) if t == "target"]
        n_forced_blinks = int(len(target_indices) * cfg.forced_blink_ratio)
        forced_blink_indices = set(random.sample(target_indices, n_forced_blinks))
    else:
        forced_blink_indices = set()

    if is_natural:
        instruction_text = (
            "视觉 Oddball 任务 (自然态)\n\n"
            "屏幕会闪烁蓝色或红色的圆\n"
            "请在心中默数红圆的个数\n\n"
            "你可以完全放松\n"
            "不需要刻意控制眨眼或面部\n\n"
            "按 空格键 开始"
        )
    else:
        instruction_text = (
            "视觉 Oddball 任务\n\n"
            "屏幕会随机闪烁蓝色（多数）或红色（少数）的圆\n"
            "请在心里默数红色圆的个数\n\n"
            "⚠ 绝对不要出声，绝对不要按键\n"
            "⚠ 只有黑屏的时候才能眨眼！\n\n"
            "按 空格键 开始"
        )

    show_message_and_wait(win, kb, instruction_text, font_size=36)

    trial_events = []
    correct_red_count = 0

    for trial_i, trial_type in enumerate(trials):
        is_target = (trial_type == "target")
        is_forced_blink = (trial_i in forced_blink_indices)

        quiet_start = core.getTime()
        while core.getTime() - quiet_start < PRE_STIM_QUIET:
            draw_fixation(win, size=0.02, color=(0.25, 0.25, 0.25))
            win.flip()

        marker = get_marker(
            "ODDBALL_TARGET" if is_target else "ODDBALL_STD",
            natural_mode=is_natural
        )

        stim_obj = circle_target if is_target else circle_std
        trigger.send_and_log(marker, f"{'TARGET' if is_target else 'STD'} (trial {trial_i+1}/{N_TOTAL})")

        stim_onset = core.getTime()
        while core.getTime() - stim_onset < STIM_DURATION:
            stim_obj.draw()
            if is_forced_blink:
                forced_blink_stim.draw()
            win.flip()

        if is_target:
            correct_red_count += 1

        iti = random.uniform(ITI_MIN, ITI_MAX)
        iti_start = core.getTime()
        while core.getTime() - iti_start < iti:
            win.flip()

        trial_events.append({
            "trial": trial_i + 1,
            "type": trial_type,
            "marker": marker,
            "iti_s": round(iti, 4),
        })

        if (trial_i + 1) % 20 == 0:
            print(f"[Session {'4' if is_natural else '3'} Oddball] {trial_i + 1}/{N_TOTAL}")

        if (trial_i + 1) % BEHAVIOR_CHECK_INTERVAL == 0 and (trial_i + 1) < N_TOTAL:
            show_message(win,
                f"已完成 {trial_i + 1}/{N_TOTAL} 个试次\n\n"
                f"刚才这组出现了几个红色圆？\n\n"
                f"请口头告诉主试\n\n"
                f"按 空格键 继续",
                font_size=40
            )
            kb.wait_for_space()

    show_message(win,
        f"全部 {N_TOTAL} 个试次完成\n\n"
        f"总共出现了 {correct_red_count} 个红色圆 (正确答案)\n\n"
        f"请口头告诉主试您数的个数\n\n"
        f"按 空格键 结束",
        font_size=40
    )
    kb.wait_for_space()

    suffix = "session4_oddball" if is_natural else "session3_oddball"
    session_data = {
        "session": "4" if is_natural else "3",
        "natural_mode": is_natural,
        "n_trials": N_TOTAL,
        "n_target": N_TARGET,
        "n_standard": N_STANDARD,
        "n_forced_blinks": n_forced_blinks,
        "correct_red_count": correct_red_count,
        "events": trial_events,
    }
    save_data(cfg, session_data, suffix=suffix)

    print(f"[Oddball {session_label}] {N_TOTAL} trials 完成, {correct_red_count} 靶刺激")
    kb.close()
    cleanup_all()


def _generate_trial_sequence(n_std: int, n_tgt: int, max_retries: int = 1000) -> list:
    """生成伪随机试次序列: 连续靶刺激不超过 2 个

    带 max_retries 上限以避免理论死循环 (极端 std/tgt 比例下可能反复 shuffle 失败)。
    超出上限直接抛 RuntimeError, 由外层 SystemExit 路径统一清理资源。
    """
    for _ in range(max_retries):
        seq = ["standard"] * n_std + ["target"] * n_tgt
        random.shuffle(seq)
        run = 0
        valid = True
        for t in seq:
            if t == "target":
                run += 1
                if run > 2:
                    valid = False
                    break
            else:
                run = 0
        if valid:
            return seq
    raise RuntimeError(
        f"无法在 {max_retries} 次尝试内生成连续靶刺激≤2 的序列 "
        f"(n_std={n_std}, n_tgt={n_tgt})。请检查 TARGET_RATIO 是否设置过高。"
    )


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            cfg = config_from_args()
        else:
            launcher = ExperimentLauncher()
            cfg = launcher.run()
            if cfg is None:
                print("实验被用户取消。")
                sys.exit(0)

        run_oddball(cfg)

    except SystemExit:
        pass
    except Exception as e:
        print(f"\n❌ 实验异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup_all()
