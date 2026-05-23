"""
Session 4 — 离线双手运动想象采集（人性化版）

流程（与 S1/S2/S3 风格一致）：
1. 讲解 + 一行练习引导，停留固定时长（默认 30s，可中途按空格提前进入正式实验）
2. 正式采集（打标）

设计要点：
- 之前的"真实动作示范 / 纯想象练习 / 准备度确认"三阶段已合并为：屏幕上一行练习引导文字 + 倒计时窗。
- 练习窗内不打标；只有正式采集阶段才发送 Trigger。
- 与 S1/S2/S3 一样：进入正式阶段只展示主任务、读取数据、保存 npz。
"""

from __future__ import annotations

import random
import traceback
from typing import List

from config import ExperimentConfig, MARKER_TABLE
from utils import (
    KeyboardManager,
    TriggerSender,
    cleanup_all,
    draw_fixation,
    draw_text_centered,
    register_resource,
    save_data,
    show_message,
    show_message_and_wait,
)

LEFT_LABEL = "left_hand"
RIGHT_LABEL = "right_hand"

PRACTICE_WINDOW_DURATION_S = 30.0
PRACTICE_WINDOW_DURATION_S_QUICK = 5.0


def _is_quick_test(cfg: ExperimentConfig) -> bool:
    return bool(getattr(cfg, "quick_test", False))


def _effective_trials_per_class(cfg: ExperimentConfig) -> int:
    if _is_quick_test(cfg):
        return max(2, min(4, cfg.mi_formal_trials_per_class))
    return cfg.mi_formal_trials_per_class


def _effective_blocks(cfg: ExperimentConfig) -> int:
    if _is_quick_test(cfg):
        return min(2, cfg.mi_formal_blocks)
    return cfg.mi_formal_blocks


def _effective_durations(cfg: ExperimentConfig) -> dict:
    if _is_quick_test(cfg):
        return {
            "baseline": min(0.5, cfg.mi_baseline_duration),
            "cue": min(0.5, cfg.mi_cue_duration),
            "imagery": min(1.0, cfg.mi_imagery_duration),
            "rest": min(0.5, cfg.mi_rest_duration),
        }
    return {
        "baseline": cfg.mi_baseline_duration,
        "cue": cfg.mi_cue_duration,
        "imagery": cfg.mi_imagery_duration,
        "rest": cfg.mi_rest_duration,
    }


def build_balanced_trials(trials_per_class: int, seed: int, block_count: int) -> List[List[str]]:
    rng = random.Random(seed)
    left_counts = [trials_per_class // block_count] * block_count
    right_counts = [trials_per_class // block_count] * block_count

    for idx in range(trials_per_class % block_count):
        left_counts[idx] += 1
        right_counts[idx] += 1

    blocks = []
    for block_idx in range(block_count):
        block = [LEFT_LABEL] * left_counts[block_idx] + [RIGHT_LABEL] * right_counts[block_idx]
        rng.shuffle(block)
        blocks.append(block)
    return blocks


def append_event(events: list, phase: str, trial_index: int, label: str, marker: int, note: str = "") -> None:
    from psychopy import core

    events.append(
        {
            "time": core.getTime(),
            "phase": phase,
            "trial_index": trial_index,
            "label": label,
            "marker": marker,
            "note": note,
        }
    )


def _drain_escape(kb: KeyboardManager) -> None:
    keys = kb.kb.getKeys(["escape"], waitRelease=False, clear=True)
    for key in keys:
        if key.name == "escape":
            print("\n>>> 实验被用户终止 (ESC) <<<")
            raise SystemExit(0)


def run_fixation_interval(win, kb: KeyboardManager, duration: float) -> None:
    from psychopy import core

    start = core.getTime()
    while core.getTime() - start < duration:
        draw_fixation(win, size=0.03, color=(0.5, 0.5, 0.5))
        win.flip()
        _drain_escape(kb)
        core.wait(0.005)


def show_practice_window(win, kb: KeyboardManager, duration_s: float) -> None:
    """讲解 + 一行练习引导 + 倒计时停留。
    
    本阶段不打标，仅供被试在心里默练。空格键可提前进入正式采集；ESC 终止。
    """
    from psychopy import core

    intro = (
        "Session 4：离线双手运动想象\n\n"
        "请【睁眼】，眼睛正对屏幕中央，自然眨眼即可、不要刻意眨。\n\n"
        "看到\"左手\"时，想象左手反复握拳—松开。\n"
        "看到\"右手\"时，想象右手反复握拳—松开。\n\n"
        "想象方式：用【本体感受】——『感觉自己手在用力握』，\n"
        "不要用【视觉式】——『看着自己手在动』。前者效果强 3-5 倍。\n\n"
        "请勿真的动手、耸肩、咬牙或做面部动作。\n\n"
        "按 空格键 进入练习。"
    )
    show_message_and_wait(win, kb, intro, font_size=36)

    kb.flush()
    start = core.getTime()
    while True:
        elapsed = core.getTime() - start
        remaining = max(0, int(duration_s - elapsed) + 1)
        if elapsed >= duration_s:
            break

        draw_text_centered(
            win,
            f"请在心里练习左右手握拳—松开的运动想象（{remaining} 秒）",
            font_size=36,
        )
        win.flip()

        keys = kb.kb.getKeys(["space", "escape"], waitRelease=False, clear=True)
        for key in keys:
            if key.name == "escape":
                print("\n>>> 实验被用户终止 (ESC) <<<")
                raise SystemExit(0)
            if key.name == "space":
                print("[Session 4] 被试提前按空格，跳过剩余练习窗")
                return
        core.wait(0.005)


def run_formal_phase(win, kb: KeyboardManager, trigger: TriggerSender,
                     cfg: ExperimentConfig, events: list) -> list:
    formal_text = (
        "正式采集\n\n"
        "现在进入正式离线采集。\n"
        "只做纯想象，不做真实动作。\n\n"
        "【睁眼】盯住屏幕中央，看到 + 时放松。\n"
        "看到\"左手\" → 用本体感受想象左手握拳—松开。\n"
        "看到\"右手\" → 用本体感受想象右手握拳—松开。\n"
        "看到\"休息\"立刻停止想象。\n\n"
        "按 空格键 开始。"
    )
    show_message_and_wait(win, kb, formal_text, font_size=36)

    trials_per_class = _effective_trials_per_class(cfg)
    block_count = _effective_blocks(cfg)
    durations = _effective_durations(cfg)

    blocks = build_balanced_trials(trials_per_class, cfg.mi_random_seed + 7, block_count)
    formal_sequences = []
    trial_counter = 0

    for block_idx, block in enumerate(blocks, start=1):
        formal_sequences.append({"block_index": block_idx, "labels": list(block)})
        trigger.send_and_log(MARKER_TABLE["S4_MI_BLOCK_START"], f"S4_MI_BLOCK_{block_idx}_START")
        append_event(events, "block_start", trial_counter, "", MARKER_TABLE["S4_MI_BLOCK_START"],
                     f"block={block_idx}")

        block_text = (
            f"正式采集 Block {block_idx}/{block_count}\n\n"
            f"本 block 共 {len(block)} 个 trial。\n"
            "请尽量减少眨眼和动作。\n\n"
            "按 空格键 进入。"
        )
        show_message_and_wait(win, kb, block_text, font_size=38)

        for label in block:
            trial_counter += 1
            run_fixation_interval(win, kb, durations["baseline"])
            cue_text = "左手" if label == LEFT_LABEL else "右手"
            cue_marker = MARKER_TABLE["S4_MI_FORMAL_LEFT_CUE"] if label == LEFT_LABEL else MARKER_TABLE["S4_MI_FORMAL_RIGHT_CUE"]
            mi_marker = MARKER_TABLE["S4_MI_FORMAL_LEFT"] if label == LEFT_LABEL else MARKER_TABLE["S4_MI_FORMAL_RIGHT"]

            show_message(win, cue_text, font_size=60)
            trigger.send_and_log(cue_marker, f"{cue_text}_CUE")
            append_event(events, "cue", trial_counter, label, cue_marker, f"block={block_idx}")
            kb.wait_for_key([], timeout=durations["cue"], exit_on_esc=True)

            show_message(win, f"请想象：{cue_text}握拳—松开", font_size=48)
            trigger.send_and_log(mi_marker, f"{cue_text}_MI")
            append_event(events, "imagery", trial_counter, label, mi_marker, f"block={block_idx}")
            kb.wait_for_key([], timeout=durations["imagery"], exit_on_esc=True)

            show_message(win, "休息", font_size=46)
            trigger.send_and_log(MARKER_TABLE["S4_MI_REST"], "S4_MI_REST")
            append_event(events, "rest", trial_counter, label, MARKER_TABLE["S4_MI_REST"], f"block={block_idx}")
            kb.wait_for_key([], timeout=durations["rest"], exit_on_esc=True)

        trigger.send_and_log(MARKER_TABLE["S4_MI_BLOCK_END"], f"S4_MI_BLOCK_{block_idx}_END")
        append_event(events, "block_end", trial_counter, "", MARKER_TABLE["S4_MI_BLOCK_END"],
                     f"block={block_idx}")

        if block_idx < block_count:
            show_message_and_wait(
                win, kb,
                "本 block 结束。\n\n请休息一下，准备好后按空格键继续。",
                font_size=38,
            )

    return formal_sequences


def run_session4(cfg: ExperimentConfig) -> str:
    from psychopy import visual

    win = None
    kb = None
    trigger = None
    saved_path = ""
    events = []

    try:
        win = visual.Window(
            size=(cfg.screen_width, cfg.screen_height),
            screen=cfg.screen_id,
            fullscr=cfg.full_screen,
            color=cfg.background_color,
            units="height",
            allowGUI=False,
        )
        register_resource("window", win)
        kb = KeyboardManager()
        trigger = TriggerSender(cfg.port_name, cfg.baud_rate, cfg.no_hardware)

        practice_duration = (
            PRACTICE_WINDOW_DURATION_S_QUICK if _is_quick_test(cfg) else PRACTICE_WINDOW_DURATION_S
        )
        show_practice_window(win, kb, practice_duration)

        formal_sequences = run_formal_phase(win, kb, trigger, cfg, events)

        show_message_and_wait(win, kb, "Session 4 正式采集完成。\n\n按空格键退出。", font_size=42)

        trials_per_class = _effective_trials_per_class(cfg)
        block_count = _effective_blocks(cfg)
        durations = _effective_durations(cfg)

        saved_path = save_data(
            cfg,
            {
                "events": events,
                "formal_sequences": formal_sequences,
                "training_summary": {
                    "practice_window_duration_s": practice_duration,
                    "formal_trials_per_class": trials_per_class,
                    "formal_blocks": block_count,
                    "baseline_duration_s": durations["baseline"],
                    "cue_duration_s": durations["cue"],
                    "imagery_duration_s": durations["imagery"],
                    "rest_duration_s": durations["rest"],
                    "quick_test": _is_quick_test(cfg),
                },
            },
            suffix="session4_mi",
        )
        return saved_path
    except SystemExit:
        raise
    except Exception as exc:
        print(f"\nSession 4 异常: {exc}")
        traceback.print_exc()
        raise
    finally:
        if trigger is not None:
            trigger.close()
        cleanup_all()
