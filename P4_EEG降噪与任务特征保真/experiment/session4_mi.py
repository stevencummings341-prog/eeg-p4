"""
Session 4 — 离线双手运动想象采集

流程：
1. 讲解
2. 真实动作示范（打标）
3. 纯想象练习（不打标）
4. 准备度确认
5. 正式采集（打标）
"""

from __future__ import annotations

import random
import traceback
from typing import List

from config import ExperimentConfig, MARKER_TABLE
from utils import KeyboardManager, TriggerSender, cleanup_all, draw_fixation, register_resource, save_data, show_message, show_message_and_wait

LEFT_LABEL = "left_hand"
RIGHT_LABEL = "right_hand"


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


def run_fixation_interval(win, kb: KeyboardManager, duration: float) -> None:
    from psychopy import core

    start = core.getTime()
    while core.getTime() - start < duration:
        draw_fixation(win, size=0.03, color=(0.5, 0.5, 0.5))
        win.flip()
        keys = kb.kb.getKeys(["escape"], waitRelease=False, clear=True)
        for key in keys:
            if key.name == "escape":
                print("\n>>> 实验被用户终止 (ESC) <<<")
                raise SystemExit(0)
        core.wait(0.005)


def show_instruction_phase(win, kb: KeyboardManager) -> None:
    text = (
        "Session 4：离线双手运动想象采集\n\n"
        "你将看到“左手”或“右手”的提示。\n"
        "当看到左手时，请想象左手正在反复握拳—松开。\n"
        "当看到右手时，请想象右手正在反复握拳—松开。\n\n"
        "请注意：\n"
        "1. 不要真的动手。\n"
        "2. 不要耸肩、咬牙或做脸部动作。\n"
        "3. 不只是看见一只手在动，而是尽量感受动作本身。\n"
        "4. 整场实验内保持同一种想象方式。\n\n"
        "按空格键进入真实动作示范。"
    )
    show_message_and_wait(win, kb, text, font_size=36)


def run_demo_phase(win, kb: KeyboardManager, trigger: TriggerSender, cfg: ExperimentConfig, events: list) -> None:
    demo_text = (
        "真实动作示范\n\n"
        "现在先让你真的做几次动作：\n"
        "看到左手时，真的做左手握拳—松开。\n"
        "看到右手时，真的做右手握拳—松开。\n\n"
        "目的只是帮助你建立动作感觉。\n\n"
        "按空格键开始。"
    )
    show_message_and_wait(win, kb, demo_text, font_size=36)

    sequence = [LEFT_LABEL] * cfg.mi_demo_trials_per_class + [RIGHT_LABEL] * cfg.mi_demo_trials_per_class
    random.Random(cfg.mi_random_seed).shuffle(sequence)

    for idx, label in enumerate(sequence, start=1):
        run_fixation_interval(win, kb, cfg.mi_baseline_duration)
        cue_text = "左手（真实动作）" if label == LEFT_LABEL else "右手（真实动作）"
        marker = MARKER_TABLE["S4_MI_DEMO_LEFT"] if label == LEFT_LABEL else MARKER_TABLE["S4_MI_DEMO_RIGHT"]
        show_message(win, cue_text, font_size=56)
        trigger.send_and_log(marker, cue_text)
        append_event(events, "demo", idx, label, marker, "真实动作示范")
        kb.wait_for_key([], timeout=cfg.mi_imagery_duration, exit_on_esc=True)
        show_message(win, "休息", font_size=46)
        kb.wait_for_key([], timeout=cfg.mi_rest_duration, exit_on_esc=True)


def run_practice_phase(win, kb: KeyboardManager, cfg: ExperimentConfig) -> None:
    practice_text = (
        "纯想象练习\n\n"
        "接下来不再真实动作，只做运动想象。\n"
        "看到左手时，想象左手在握拳—松开。\n"
        "看到右手时，想象右手在握拳—松开。\n\n"
        "本阶段左右手各做 5 次，不打标，只用于练习。\n\n"
        "按空格键开始。"
    )
    show_message_and_wait(win, kb, practice_text, font_size=36)

    sequence = [LEFT_LABEL] * cfg.mi_practice_trials_per_class + [RIGHT_LABEL] * cfg.mi_practice_trials_per_class
    random.Random(cfg.mi_random_seed + 1).shuffle(sequence)

    for label in sequence:
        run_fixation_interval(win, kb, cfg.mi_baseline_duration)
        cue_text = "左手（纯想象练习）" if label == LEFT_LABEL else "右手（纯想象练习）"
        show_message(win, cue_text, font_size=54)
        kb.wait_for_key([], timeout=cfg.mi_imagery_duration, exit_on_esc=True)
        show_message(win, "休息", font_size=46)
        kb.wait_for_key([], timeout=cfg.mi_rest_duration, exit_on_esc=True)


def run_readiness_check(win, kb: KeyboardManager) -> None:
    check_text = (
        "准备度确认\n\n"
        "请在心里确认以下几点：\n"
        "1. 你是在“感觉自己在握拳”，而不是只看画面。\n"
        "2. 左手和右手的想象区别是明显的。\n"
        "3. 你没有忍不住真的动手。\n"
        "4. 你知道自己哪一边更容易想象。\n\n"
        "如果还不会想，请先停下来和主试沟通。\n"
        "如果已经准备好正式采集，按空格键继续。"
    )
    show_message_and_wait(win, kb, check_text, font_size=34)


def run_formal_phase(win, kb: KeyboardManager, trigger: TriggerSender, cfg: ExperimentConfig, events: list) -> list:
    formal_text = (
        "正式采集\n\n"
        "现在进入正式离线采集。\n"
        "只做纯想象，不做真实动作。\n"
        "看到左手时，想象左手握拳—松开。\n"
        "看到右手时，想象右手握拳—松开。\n\n"
        "按空格键开始。"
    )
    show_message_and_wait(win, kb, formal_text, font_size=36)

    blocks = build_balanced_trials(cfg.mi_formal_trials_per_class, cfg.mi_random_seed + 7, cfg.mi_formal_blocks)
    formal_sequences = []
    trial_counter = 0

    for block_idx, block in enumerate(blocks, start=1):
        formal_sequences.append({"block_index": block_idx, "labels": list(block)})
        trigger.send_and_log(MARKER_TABLE["S4_MI_BLOCK_START"], f"S4_MI_BLOCK_{block_idx}_START")
        append_event(events, "block_start", trial_counter, "", MARKER_TABLE["S4_MI_BLOCK_START"], f"block={block_idx}")

        block_text = (
            f"正式采集 Block {block_idx}/{cfg.mi_formal_blocks}\n\n"
            f"本 block 共 {len(block)} 个 trial。\n"
            "请尽量减少眨眼和动作。\n\n"
            "按空格键进入。"
        )
        show_message_and_wait(win, kb, block_text, font_size=38)

        for label in block:
            trial_counter += 1
            run_fixation_interval(win, kb, cfg.mi_baseline_duration)
            cue_text = "左手" if label == LEFT_LABEL else "右手"
            cue_marker = MARKER_TABLE["S4_MI_FORMAL_LEFT_CUE"] if label == LEFT_LABEL else MARKER_TABLE["S4_MI_FORMAL_RIGHT_CUE"]
            mi_marker = MARKER_TABLE["S4_MI_FORMAL_LEFT"] if label == LEFT_LABEL else MARKER_TABLE["S4_MI_FORMAL_RIGHT"]

            show_message(win, cue_text, font_size=60)
            trigger.send_and_log(cue_marker, f"{cue_text}_CUE")
            append_event(events, "cue", trial_counter, label, cue_marker, f"block={block_idx}")
            kb.wait_for_key([], timeout=cfg.mi_cue_duration, exit_on_esc=True)

            show_message(win, f"请想象：{cue_text}握拳—松开", font_size=48)
            trigger.send_and_log(mi_marker, f"{cue_text}_MI")
            append_event(events, "imagery", trial_counter, label, mi_marker, f"block={block_idx}")
            kb.wait_for_key([], timeout=cfg.mi_imagery_duration, exit_on_esc=True)

            show_message(win, "休息", font_size=46)
            trigger.send_and_log(MARKER_TABLE["S4_MI_REST"], "S4_MI_REST")
            append_event(events, "rest", trial_counter, label, MARKER_TABLE["S4_MI_REST"], f"block={block_idx}")
            kb.wait_for_key([], timeout=cfg.mi_rest_duration, exit_on_esc=True)

        trigger.send_and_log(MARKER_TABLE["S4_MI_BLOCK_END"], f"S4_MI_BLOCK_{block_idx}_END")
        append_event(events, "block_end", trial_counter, "", MARKER_TABLE["S4_MI_BLOCK_END"], f"block={block_idx}")

        if block_idx < cfg.mi_formal_blocks:
            show_message_and_wait(win, kb, "本 block 结束。\n\n请休息一下，准备好后按空格键继续。", font_size=38)

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

        show_instruction_phase(win, kb)
        run_demo_phase(win, kb, trigger, cfg, events)
        run_practice_phase(win, kb, cfg)
        run_readiness_check(win, kb)
        formal_sequences = run_formal_phase(win, kb, trigger, cfg, events)

        show_message_and_wait(win, kb, "Session 4 正式采集完成。\n\n按空格键退出。", font_size=42)

        saved_path = save_data(
            cfg,
            {
                "events": events,
                "formal_sequences": formal_sequences,
                "training_summary": {
                    "demo_trials_per_class": cfg.mi_demo_trials_per_class,
                    "practice_trials_per_class": cfg.mi_practice_trials_per_class,
                    "formal_trials_per_class": cfg.mi_formal_trials_per_class,
                    "formal_blocks": cfg.mi_formal_blocks,
                    "practice_marked": False,
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
