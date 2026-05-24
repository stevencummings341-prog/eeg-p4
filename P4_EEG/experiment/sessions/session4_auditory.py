"""
Session 4 — 听觉注意力实验 (scheme="auditory_attention")
────────────────────────────────────────────────────────────

HRTF 空间化双说话人竞争语音实验 (AAD: Auditory Attention Decoding)。

每个 trial 流程：
    注视十字 (Marker: S4_AAD_BASELINE)
    → 播放空间化双声道音频，被试仅关注先说话的目标说话人
      Marker: S4_AAD_AUDIO_LEFT (目标在左) / S4_AAD_AUDIO_RIGHT (目标在右)
    → 2 道 T/F 判断题 (按键 T=对 / F=错)
    → 休息 (Marker: S4_AAD_REST)

音频素材: experiment/spatialized_90/*.wav
题库: experiment/questions_db.py

数据落点：
    <data_dir>/auditory_attention/eeg-npz/P4_S4_<subject>_<ts>_session4_auditory.npz
"""

from __future__ import annotations

import os
import random
import traceback
from pathlib import Path

import numpy as np
from psychopy import core, visual

from config import ExperimentConfig, MARKER_TABLE
from utils import (
    KeyboardManager,
    TriggerSender,
    cleanup_all,
    draw_fixation,
    register_resource,
    save_data,
    show_message_and_wait,
)

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR_DEFAULT = os.path.join(SCRIPT_DIR, "spatialized_90")


def _is_quick_test(cfg: ExperimentConfig) -> bool:
    return bool(getattr(cfg, "quick_test", False))


def _effective_trials(cfg: ExperimentConfig) -> int:
    if _is_quick_test(cfg):
        return 4
    return getattr(cfg, "aad_trials", 32) or 32


def _effective_fixation_duration(cfg: ExperimentConfig) -> float:
    if _is_quick_test(cfg):
        return 0.5
    return getattr(cfg, "aad_fixation_duration", 2.0) or 2.0


def _effective_rest_duration(cfg: ExperimentConfig) -> float:
    if _is_quick_test(cfg):
        return 0.5
    return getattr(cfg, "aad_rest_duration", 2.0) or 2.0


def _get_difficulty(cfg: ExperimentConfig) -> float:
    return getattr(cfg, "aad_difficulty", 0.0) or 0.0


def _get_speed_multiplier(cfg: ExperimentConfig) -> int:
    return max(1, getattr(cfg, "aad_speed_multiplier", 1) or 1)


def _get_audio_dir(cfg: ExperimentConfig) -> str:
    d = getattr(cfg, "aad_audio_dir", "") or ""
    if d and os.path.isdir(d):
        return d
    return AUDIO_DIR_DEFAULT


def append_event(events: list, phase: str, trial_index: int, condition: str,
                 marker: int, note: str = "", **extra) -> None:
    events.append({
        "time": core.getTime(),
        "phase": phase,
        "trial_index": trial_index,
        "condition": condition,
        "marker": marker,
        "note": note,
        **extra,
    })


def _drain_escape(kb: KeyboardManager) -> None:
    keys = kb.kb.getKeys(["escape"], waitRelease=False, clear=True)
    for key in keys:
        if key.name == "escape":
            print("\n>>> 实验被用户终止 (ESC) <<<")
            raise SystemExit(0)


def run_fixation_interval(win, kb: KeyboardManager, duration: float) -> None:
    start = core.getTime()
    while core.getTime() - start < duration:
        draw_fixation(win, size=0.03, color=(0.5, 0.5, 0.5))
        win.flip()
        _drain_escape(kb)
        core.wait(0.005)


def _extract_trial_id(filename: str) -> str:
    """从文件名提取 trial_id，用于匹配题库。

    '10_seg01_L_first_HRTF_-90_90.wav' → '10_seg01_L_first'
    """
    base = os.path.splitext(filename)[0]
    idx = base.find("_HRTF_")
    if idx >= 0:
        return base[:idx]
    return base


def _parse_condition(filename: str) -> str:
    if "_L_first" in filename:
        return "Left"
    elif "_R_first" in filename:
        return "Right"
    return "Unknown"


def scan_audio_files(audio_dir: str) -> list[dict]:
    """扫描音频目录，返回所有可用音频文件的元数据列表。"""
    if not os.path.isdir(audio_dir):
        raise FileNotFoundError(f"音频目录不存在: {audio_dir}")

    files = sorted([
        f for f in os.listdir(audio_dir)
        if f.lower().endswith(".wav")
    ])
    if not files:
        raise RuntimeError(f"音频目录为空: {audio_dir}")

    results = []
    for f in files:
        full_path = os.path.join(audio_dir, f)
        trial_id = _extract_trial_id(f)
        condition = _parse_condition(f)
        results.append({
            "filename": f,
            "path": full_path,
            "trial_id": trial_id,
            "condition": condition,
        })

    print(f"[AAD] 扫描到 {len(results)} 个音频文件 (目录: {audio_dir})")
    left_count = sum(1 for r in results if r["condition"] == "Left")
    right_count = sum(1 for r in results if r["condition"] == "Right")
    print(f"  Left (目标在左): {left_count}, Right (目标在右): {right_count}")
    return results


def build_trial_list(all_files: list[dict], n_trials: int, seed: int,
                     questions_db: dict) -> list[dict]:
    """构建指定数量的 trial 列表。只选有题库匹配的文件，随机打乱。"""
    available = [f for f in all_files if f["trial_id"] in questions_db]
    if len(available) < n_trials:
        print(f"[AAD] 警告: 可用题库匹配音频 {len(available)} < 需求 {n_trials}，将使用全部可用")
        n_trials = len(available)
    if n_trials == 0:
        raise RuntimeError("没有任何音频文件可以匹配题库，请检查 questions_db.py 和音频目录")

    rng = random.Random(seed)
    selected = rng.sample(available, n_trials)
    rng.shuffle(selected)

    # 确保相邻 trial 条件不同
    for i in range(1, len(selected)):
        if selected[i]["condition"] == selected[i - 1]["condition"]:
            for j in range(i + 1, len(selected)):
                if selected[j]["condition"] != selected[i]["condition"]:
                    selected[i], selected[j] = selected[j], selected[i]
                    break

    return selected


def _read_wav(filepath: str):
    """用标准库 wave + numpy 读取 .wav 文件，返回 (sample_rate, audio_data)。

    audio_data 形状 (n_samples, n_channels)，dtype=float64 归一化到 [-1, 1]。
    """
    import wave as _wave

    with _wave.open(filepath, "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        fs = wf.getframerate()
        nf = wf.getnframes()
        raw = wf.readframes(nf)

    if sw == 2:
        dtype = np.int16
    elif sw == 3:
        dtype = np.uint8
    elif sw == 4:
        dtype = np.int32
    else:
        dtype = np.uint8

    data = np.frombuffer(raw, dtype=dtype).astype(np.float64)

    # 3-byte (24-bit) 需要手动解包
    if sw == 3:
        raw_bytes = np.frombuffer(raw, dtype=np.uint8)
        raw_bytes = raw_bytes.reshape(-1, 3)
        data = (raw_bytes.astype(np.float64) * [1, 256, 65536]).sum(axis=1)
        # 符号扩展
        data[data >= 2**23] -= 2**24

    data = data.reshape(-1, nch)

    # 归一化
    max_val = float(2 ** (sw * 8 - 1))
    if sw == 3:
        max_val = float(2**23)
    data = data / max_val

    return fs, data


def _load_and_process_audio(filepath: str, condition: str, difficulty: float,
                            speed_mult: int):
    """加载 .wav，按难度调整非目标声道音量，返回处理后的 (audio_array, sample_rate)。

    返回 audio_array: float32, (n_samples, n_channels), 值域 [-1, 1]。
    """
    sample_rate, audio_data = _read_wav(filepath)

    # 确保双声道
    if audio_data.shape[1] == 1:
        audio_data = np.column_stack([audio_data, audio_data.copy()])
    elif audio_data.shape[1] > 2:
        audio_data = audio_data[:, :2]

    # 难度调整: 减弱非目标说话人所在声道
    non_target_mult = max(0.0, 1.0 - difficulty)
    if condition == "Left":
        audio_data[:, 1] *= non_target_mult
    elif condition == "Right":
        audio_data[:, 0] *= non_target_mult

    # 限幅
    audio_data = np.clip(audio_data, -1.0, 1.0)

    # 倍速: 每隔 N 个采样点取一个
    if speed_mult > 1:
        audio_data = audio_data[::speed_mult, :]

    return audio_data.astype(np.float32), sample_rate


def _play_audio_and_wait(audio_data: np.ndarray, sample_rate: int,
                         trigger: TriggerSender, marker: int, marker_name: str) -> float:
    """播放音频并发送 Trigger。返回实际播放时长 (秒)。"""
    from psychopy import sound

    duration = audio_data.shape[0] / sample_rate

    snd = sound.Sound(value=audio_data, sampleRate=sample_rate, stereo=True)
    trigger.send_and_log(marker, marker_name)
    snd.play()
    core.wait(duration)
    snd.stop()
    del snd

    return duration


def _present_question(win, kb: KeyboardManager, question_text: str,
                      trial_index: int, q_index: int) -> dict:
    """呈现一道 T/F 判断题，等待被试按键，返回响应数据。"""
    from utils import draw_text_centered

    # 组合显示：题号 + 题目 + 按键提示
    full_text = (
        f"第 {trial_index} 试次 · 第 {q_index} 题\n\n"
        f"{question_text}\n\n"
        f"正确请按  T  键    错误请按  F  键"
    )

    draw_text_centered(win, full_text, font_size=42, color=(1, 1, 1))
    win.flip()

    kb.flush()
    t_start = core.getTime()
    while True:
        keys = kb.kb.getKeys(["t", "f", "escape"], waitRelease=False, clear=True)
        for k in keys:
            if k.name == "escape":
                print("\n>>> 实验被用户终止 (ESC) <<<")
                raise SystemExit(0)
            if k.name in ("t", "f"):
                rt = k.rt  # PsychoPy 自带的反应时间 (从 clearEvents 算起)
                return {
                    "q_index": q_index,
                    "question": question_text,
                    "response": k.name.upper(),
                    "rt": rt,
                }
        core.wait(0.005)


def run_session4(cfg: ExperimentConfig) -> str:
    from questions_db import QUESTIONS_DB

    audio_dir = _get_audio_dir(cfg)
    n_trials = _effective_trials(cfg)
    fixation_duration = _effective_fixation_duration(cfg)
    rest_duration = _effective_rest_duration(cfg)
    difficulty = _get_difficulty(cfg)
    speed_mult = _get_speed_multiplier(cfg)
    seed = getattr(cfg, "aad_random_seed", 42) or 42

    all_files = scan_audio_files(audio_dir)
    trials = build_trial_list(all_files, n_trials, seed, QUESTIONS_DB)
    n_actual = len(trials)

    win = None
    kb = None
    trigger = None
    saved_path = ""
    events = []
    trial_results = []
    correct_count = 0
    total_questions = 0

    try:
        trigger = TriggerSender(cfg.port_name, cfg.baud_rate, cfg.no_hardware)
        win = visual.Window(
            size=(cfg.screen_width, cfg.screen_height),
            screen=cfg.screen_id,
            fullscr=cfg.full_screen,
            color=cfg.background_color,
            units="height",
            allowGUI=False,
        )
        register_resource("window", win)
        win.setMouseVisible(False)
        kb = KeyboardManager()

        # ── 指导语 ──
        show_message_and_wait(
            win, kb,
            "听觉注意力实验\n\n"
            f"您将听到 {n_actual} 段双人对话音频。\n"
            "每段音频中，有两个人先后开始说话。\n\n"
            "请【仅关注首先开始说话的那个人】\n"
            "忽略后说话者的内容。\n\n"
            "音频结束后，请回答 2 道判断题。\n"
            "正确请按 T 键，错误请按 F 键。\n\n"
            "按 空格键 开始实验",
            font_size=36,
        )

        # ── Session 开始 Marker ──
        trigger.send_and_log(MARKER_TABLE["S4_AAD_START"], "S4_AAD_START")
        append_event(events, "session_start", 0, "", MARKER_TABLE["S4_AAD_START"],
                     note=f"n_trials={n_actual}, difficulty={difficulty}, speed={speed_mult}x")

        for trial_idx, trial_info in enumerate(trials, start=1):
            trial_id = trial_info["trial_id"]
            condition = trial_info["condition"]
            audio_path = trial_info["path"]
            audio_file = trial_info["filename"]
            questions = QUESTIONS_DB.get(trial_id, [])

            print(f"\n[Trial {trial_idx}/{n_actual}] {trial_id}  condition={condition}  file={audio_file}")

            # ── 注视十字 ──
            trigger.send_and_log(MARKER_TABLE["S4_AAD_BASELINE"],
                                f"S4_AAD_BASELINE (trial {trial_idx})")
            append_event(events, "baseline", trial_idx, condition,
                        MARKER_TABLE["S4_AAD_BASELINE"],
                        note="fixation", trial_id=trial_id, audio_file=audio_file)
            run_fixation_interval(win, kb, fixation_duration)

            # ── 加载 + 处理 + 播放音频 ──
            audio_marker = (
                MARKER_TABLE["S4_AAD_AUDIO_LEFT"] if condition == "Left"
                else MARKER_TABLE["S4_AAD_AUDIO_RIGHT"]
            )
            audio_marker_name = f"S4_AAD_AUDIO_{condition.upper()}"

            try:
                audio_arr, fs = _load_and_process_audio(
                    audio_path, condition, difficulty, speed_mult
                )
            except Exception as exc:
                print(f"  [!] 音频加载失败: {exc}")
                append_event(events, "audio_failed", trial_idx, condition, audio_marker,
                            note=str(exc), trial_id=trial_id, audio_file=audio_file)
                continue

            trigger.send_and_log(audio_marker,
                                f"{audio_marker_name} (trial {trial_idx}/{n_actual})")
            append_event(events, "audio_start", trial_idx, condition, audio_marker,
                        note="audio_playing", trial_id=trial_id, audio_file=audio_file)

            actual_duration = _play_audio_and_wait(
                audio_arr, fs, trigger, audio_marker, audio_marker_name
            )
            append_event(events, "audio_end", trial_idx, condition, audio_marker,
                        note=f"duration={actual_duration:.1f}s", trial_id=trial_id,
                        audio_duration_s=round(actual_duration, 2))

            # 短暂黑屏过渡
            win.flip()
            core.wait(0.3)

            # ── 答题阶段 ──
            trigger.send_and_log(MARKER_TABLE["S4_AAD_QUESTION"],
                                f"S4_AAD_QUESTION (trial {trial_idx})")
            append_event(events, "question_start", trial_idx, condition,
                        MARKER_TABLE["S4_AAD_QUESTION"],
                        trial_id=trial_id)

            # 随机化题目顺序
            q_order = list(range(len(questions)))
            random.shuffle(q_order)

            q1_result = _present_question(
                win, kb, questions[q_order[0]]["q"], trial_idx, 1
            )
            q1_correct = (q1_result["response"] == questions[q_order[0]]["ans"])
            if q1_correct:
                correct_count += 1
            total_questions += 1

            win.flip()
            core.wait(0.2)

            q2_result = _present_question(
                win, kb, questions[q_order[1]]["q"], trial_idx, 2
            )
            q2_correct = (q2_result["response"] == questions[q_order[1]]["ans"])
            if q2_correct:
                correct_count += 1
            total_questions += 1

            append_event(events, "question_end", trial_idx, condition,
                        MARKER_TABLE["S4_AAD_QUESTION"],
                        trial_id=trial_id,
                        q1=q1_result, q1_correct=q1_correct,
                        q2=q2_result, q2_correct=q2_correct,
                        question_order=q_order)

            trial_results.append({
                "trial_index": trial_idx,
                "trial_id": trial_id,
                "condition": condition,
                "audio_file": audio_file,
                "audio_duration_s": round(actual_duration, 2),
                "question_order": q_order,
                "q1_response": q1_result["response"],
                "q1_correct": q1_correct,
                "q1_rt": q1_result["rt"],
                "q2_response": q2_result["response"],
                "q2_correct": q2_correct,
                "q2_rt": q2_result["rt"],
            })

            # ── 休息 ──
            if trial_idx < n_actual:
                trigger.send_and_log(MARKER_TABLE["S4_AAD_REST"],
                                    f"S4_AAD_REST (trial {trial_idx})")
                append_event(events, "rest", trial_idx, condition,
                            MARKER_TABLE["S4_AAD_REST"])

                # 每 4 个 trial 显示休息提示
                if trial_idx % 4 == 0:
                    show_message_and_wait(
                        win, kb,
                        "您可以稍作休息。\n\n准备好后，请按 空格键 继续。",
                        font_size=40,
                    )
                else:
                    rest_start = core.getTime()
                    while core.getTime() - rest_start < rest_duration:
                        win.flip()
                        _drain_escape(kb)

            if trial_idx % 6 == 0:
                acc = correct_count / total_questions if total_questions > 0 else 0
                print(f"  [进度] {trial_idx}/{n_actual} trials, 当前答题准确率: {acc:.1%}")

        # ── Session 结束 ──
        trigger.send_and_log(MARKER_TABLE["S4_AAD_END"], "S4_AAD_END")
        append_event(events, "session_end", n_actual, "", MARKER_TABLE["S4_AAD_END"])

        overall_acc = correct_count / total_questions if total_questions > 0 else 0
        print(f"\n[Session 4 听觉注意力] 完成: {n_actual} trials")
        print(f"  答题准确率: {correct_count}/{total_questions} = {overall_acc:.1%}")

        show_message_and_wait(
            win, kb,
            "听觉注意力实验完成！\n\n"
            f"共 {n_actual} 个试次\n"
            f"答题准确率: {correct_count}/{total_questions} = {overall_acc:.1%}\n\n"
            "按 空格键 退出",
            font_size=40,
        )

        saved_path = save_data(
            cfg,
            {
                "events": events,
                "trial_results": trial_results,
                "session": "4",
                "task": "auditory_attention",
                "n_trials": n_actual,
                "total_questions": total_questions,
                "correct_count": correct_count,
                "overall_accuracy": overall_acc,
                "difficulty": difficulty,
                "speed_multiplier": speed_mult,
                "fixation_duration_s": fixation_duration,
                "rest_duration_s": rest_duration,
                "audio_dir": audio_dir,
                "random_seed": seed,
                "quick_test": _is_quick_test(cfg),
            },
            suffix="session4_auditory",
        )
        print("[Session 4 听觉注意力] 数据已保存。")
        return saved_path

    except SystemExit:
        raise
    except Exception as exc:
        print(f"\nSession 4 异常: {exc}")
        traceback.print_exc()
        raise
    finally:
        if kb is not None:
            kb.close()
        if trigger is not None:
            trigger.close()
        cleanup_all()
