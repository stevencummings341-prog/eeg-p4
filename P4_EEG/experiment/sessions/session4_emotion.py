"""
Session 4 — 情绪识别实验 (scheme="emotion")
────────────────────────────────────────────

每个 trial 流程：
    注视十字 (Marker 105 S4_EMOTION_BASELINE)
    → 播放视频 (Marker 101/102/103 = 负/中/正)
    → 休息 (Marker 106 S4_EMOTION_REST)

视频素材读取 experiment/stimuli/stimuli_config.json。
随机化由 cfg.emotion_random_seed 控制。

数据落点对齐 MI 标准：utils.save_data 自动写入
    <data_dir>/<scheme>/eeg-npz/P4_S4_<subject>_<ts>_session4_emotion.npz
其中 scheme = "emotion"。
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import traceback

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

# 本文件在 experiment/sessions/ 下，stimuli 放在 experiment/stimuli/
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STIMULI_DIR = os.path.join(SCRIPT_DIR, "stimuli")
STIMULI_CONFIG_PATH = os.path.join(STIMULI_DIR, "stimuli_config.json")
MAX_VIDEO_DURATION = 120.0

try:
    from psychopy.visual import MovieStim3 as MovieStimClass
    MOVIE_AVAILABLE = True
except ImportError:
    try:
        from psychopy.visual import MovieStim as MovieStimClass
        MOVIE_AVAILABLE = True
    except ImportError:
        MOVIE_AVAILABLE = False


def _is_quick_test(cfg: ExperimentConfig) -> bool:
    return bool(getattr(cfg, "quick_test", False))


def _effective_fixation_duration(cfg: ExperimentConfig) -> float:
    if _is_quick_test(cfg):
        return min(0.5, cfg.emotion_fixation_duration)
    return cfg.emotion_fixation_duration


def _effective_rest_duration(cfg: ExperimentConfig) -> float:
    if _is_quick_test(cfg):
        return min(0.5, cfg.emotion_rest_duration)
    return cfg.emotion_rest_duration


def _effective_trials_per_category(cfg: ExperimentConfig) -> int:
    # quick-test 模式：每类只跑 2 个，验证 Marker / 数据保存即可
    return 2 if _is_quick_test(cfg) else 6


def append_event(events: list, phase: str, trial_index: int, category: str,
                 marker: int, note: str = "", **extra) -> None:
    events.append(
        {
            "time": core.getTime(),
            "phase": phase,
            "trial_index": trial_index,
            "category": category,
            "marker": marker,
            "note": note,
            **extra,
        }
    )


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


def _get_video_info(video_path: str):
    width, height, duration = None, None, None

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,duration",
                "-of", "csv=p=0", video_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(",")
            if len(parts) >= 2:
                try:
                    width = int(parts[0])
                    height = int(parts[1])
                except ValueError:
                    pass
                if len(parts) >= 3 and parts[2]:
                    try:
                        duration = float(parts[2])
                    except ValueError:
                        pass
    except Exception:
        pass

    if width is None or height is None:
        try:
            from ffpyplayer.tools import get_metadata
            meta = get_metadata(video_path)
            src_size = meta.get("src_vid_size") if meta else None
            if src_size and len(src_size) == 2 and src_size[0] > 0:
                width, height = int(src_size[0]), int(src_size[1])
        except Exception:
            pass

    if duration is None:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", video_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
        except Exception:
            pass

    if duration is None:
        try:
            from ffpyplayer.player import MediaPlayer
            player = MediaPlayer(video_path)
            meta = player.get_metadata()
            if meta and "duration" in meta:
                duration = float(meta["duration"])
            player.close_player()
        except Exception:
            pass

    return width, height, duration


def _calc_video_display(vid_w, vid_h, screen_w, screen_h):
    if not vid_w or not vid_h:
        h = 0.70
        w = h * 16 / 9
        return w, h, 0, 0

    screen_aspect = screen_w / screen_h
    video_aspect = vid_w / vid_h
    max_w = screen_aspect * 0.80
    max_h = 0.80

    if video_aspect > max_w / max_h:
        w = max_w
        h = w / video_aspect
    else:
        h = max_h
        w = h * video_aspect
    return w, h, 0, 0


def load_stimuli(cfg: ExperimentConfig):
    """读取 stimuli_config.json，按类别挑出 N 个真实存在于磁盘上的视频。

    挑选策略：
        - 按 json 里 `videos` 列表的顺序，从前往后取
        - 遇到磁盘上缺失的文件时跳过，继续往后找候选
        - 直到该类别凑满 N 个 (target_trials_per_category) 为止
        - 多放几个候选是安全的（充当 backup）；少放会得到 < N 的实际 trial 数
    """
    if not os.path.exists(STIMULI_CONFIG_PATH):
        raise FileNotFoundError(
            f"刺激配置文件不存在: {STIMULI_CONFIG_PATH}\n"
            "请先创建 experiment/stimuli/stimuli_config.json 并放置视频素材"
        )

    with open(STIMULI_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    trials_by_category = {"negative": [], "neutral": [], "positive": []}
    target_trials_per_category = _effective_trials_per_category(cfg)

    for cat_name, cat_info in config["categories"].items():
        label = cat_info["label"]
        accepted = trials_by_category.setdefault(cat_name, [])
        missing_in_a_row: list[str] = []
        for rel_path in cat_info["videos"]:
            if len(accepted) >= target_trials_per_category:
                break
            video_path = os.path.join(STIMULI_DIR, rel_path)
            if os.path.exists(video_path):
                accepted.append((cat_name, label, video_path))
            else:
                missing_in_a_row.append(rel_path)
                print(f"  [!] 视频缺失，跳过: {rel_path}")
        if len(accepted) < target_trials_per_category:
            print(f"  [!] {cat_name} 仅找到 {len(accepted)}/{target_trials_per_category} 个可用视频"
                  f"; 缺失/跳过 {len(missing_in_a_row)} 个 → 此类别将以更少的 trial 数运行")

    rng = random.Random(cfg.emotion_random_seed)
    for cat_name in trials_by_category:
        rng.shuffle(trials_by_category[cat_name])

    trials = []
    max_per_cat = max(len(v) for v in trials_by_category.values())
    for i in range(max_per_cat):
        for cat_name in ["negative", "neutral", "positive"]:
            if i < len(trials_by_category[cat_name]):
                trials.append(trials_by_category[cat_name][i])

    if not trials:
        raise RuntimeError("没有找到任何可用视频。请检查 experiment/stimuli/ 目录。")

    print(f"[刺激] 共加载 {len(trials)} 个视频 (目标每类 {target_trials_per_category})")
    for cat_name in ["negative", "neutral", "positive"]:
        print(f"  {cat_name}: {len(trials_by_category[cat_name])}")
    return trials


def _play_video_trial(win, kb: KeyboardManager, video_path: str, video_start_time: float):
    vid_w, vid_h, vid_dur = _get_video_info(video_path)
    disp_w, disp_h, pos_x, pos_y = _calc_video_display(
        vid_w, vid_h, win.size[0], win.size[1]
    )
    watchdog = vid_dur + 3.0 if vid_dur else MAX_VIDEO_DURATION
    if vid_dur:
        print(f"  [播放] {vid_w}x{vid_h}, 显示 {disp_w:.2f}x{disp_h:.2f}, 时长约 {vid_dur:.1f}s")
    else:
        print(f"  [播放] {vid_w}x{vid_h}, 显示 {disp_w:.2f}x{disp_h:.2f}")

    movie = MovieStimClass(
        win, video_path,
        size=(disp_w, disp_h),
        pos=(pos_x, pos_y),
        units="height", loop=False,
    )
    while movie.status != visual.FINISHED:
        movie.draw()
        win.flip()
        if core.getTime() - video_start_time > watchdog:
            print("  [!] watchdog 触发, 强制结束播放")
            break
        _drain_escape(kb)

    movie.pause()
    movie.stop()
    del movie
    for _ in range(5):
        win.flip()
    core.wait(0.15)
    return core.getTime() - video_start_time, vid_w, vid_h, vid_dur


def run_session4(cfg: ExperimentConfig) -> str:
    trials = load_stimuli(cfg)
    fixation_duration = _effective_fixation_duration(cfg)
    rest_duration = _effective_rest_duration(cfg)

    win = None
    kb = None
    trigger = None
    saved_path = ""
    events = []
    successful_trials = 0
    failed_trials = 0
    category_counts = {"negative": 0, "neutral": 0, "positive": 0}

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

        show_message_and_wait(
            win, kb,
            "情绪识别实验\n\n"
            f"屏幕上将依次播放 {len(trials)} 段视频片段\n"
            "请认真观看每一段视频\n"
            "感受视频传递的情绪\n\n"
            "每个 trial 前会出现注视十字 (+)\n"
            "请在此期间保持静止、减少眨眼\n\n"
            "按 空格键 开始",
            font_size=36,
        )

        trigger.send_and_log(MARKER_TABLE["S4_EMOTION_START"], "S4_EMOTION_START")
        append_event(events, "session_start", 0, "", MARKER_TABLE["S4_EMOTION_START"],
                     note=f"total_trials={len(trials)}")

        for trial_index, (category, category_label, video_path) in enumerate(trials, start=1):
            marker = MARKER_TABLE[f"S4_EMOTION_{category.upper()}"]
            print(f"\n[Trial {trial_index}/{len(trials)}] {category_label} ({category}) 文件: {os.path.basename(video_path)}")

            trigger.send_and_log(MARKER_TABLE["S4_EMOTION_BASELINE"], f"S4_BASELINE (trial {trial_index})")
            append_event(events, "baseline", trial_index, category, MARKER_TABLE["S4_EMOTION_BASELINE"],
                         note=category_label, video_file=os.path.basename(video_path))
            run_fixation_interval(win, kb, fixation_duration)

            trigger.send_and_log(marker, f"S4_{category.upper()} (trial {trial_index}/{len(trials)}, {category_label})")
            append_event(events, "stimulus_start", trial_index, category, marker,
                         note=category_label, video_file=os.path.basename(video_path))

            video_start_time = core.getTime()
            video_played = False
            actual_duration = 0.0
            vid_w = vid_h = vid_dur = None

            if MOVIE_AVAILABLE:
                try:
                    actual_duration, vid_w, vid_h, vid_dur = _play_video_trial(win, kb, video_path, video_start_time)
                    video_played = True
                    print(f"  [OK] 实际播放 {actual_duration:.1f}s")
                except Exception as exc:
                    print(f"  [!] 视频播放失败, 跳过此 trial: {exc}")
                    append_event(events, "stimulus_failed", trial_index, category, marker,
                                 note=str(exc), video_file=os.path.basename(video_path),
                                 video_path=video_path)
            else:
                print("  [!] MovieStim 不可用")
                append_event(events, "stimulus_failed", trial_index, category, marker,
                             note="MovieStim unavailable", video_file=os.path.basename(video_path),
                             video_path=video_path)

            if not video_played:
                failed_trials += 1
                append_event(events, "trial_skipped", trial_index, category, marker,
                             note="video_play_failed", video_file=os.path.basename(video_path),
                             video_path=video_path)
                continue

            trigger.send_and_log(MARKER_TABLE["S4_EMOTION_REST"], f"S4_REST (trial {trial_index})")
            append_event(events, "rest", trial_index, category, MARKER_TABLE["S4_EMOTION_REST"],
                         note=category_label, video_file=os.path.basename(video_path),
                         video_path=video_path, video_width=vid_w, video_height=vid_h,
                         video_duration_s=round(actual_duration, 2), video_probe_duration_s=vid_dur)
            rest_start = core.getTime()
            while core.getTime() - rest_start < rest_duration:
                win.flip()
                _drain_escape(kb)

            successful_trials += 1
            category_counts[category] += 1
            if trial_index % 6 == 0:
                print(f"  [进度] {trial_index}/{len(trials)} trials 完成")

        trigger.send_and_log(MARKER_TABLE["S4_EMOTION_END"], "S4_EMOTION_END")
        append_event(events, "session_end", len(trials), "", MARKER_TABLE["S4_EMOTION_END"],
                     note=f"success={successful_trials}, failed={failed_trials}")

        print("\n[Session 4 情绪识别] 完成统计:")
        for category in ["negative", "neutral", "positive"]:
            print(f"  {category}: {category_counts.get(category, 0)} trials")
        print(f"  成功: {successful_trials} / 失败: {failed_trials} / 总计: {len(trials)}")

        show_message_and_wait(
            win, kb,
            "情绪识别实验完成！\n\n"
            f"成功播放 {successful_trials}/{len(trials)} 个试次\n"
            f"负性 {category_counts.get('negative', 0)} / "
            f"中性 {category_counts.get('neutral', 0)} / "
            f"正性 {category_counts.get('positive', 0)}\n\n"
            "按 空格键 退出",
            font_size=40,
        )

        saved_path = save_data(
            cfg,
            {
                "events": events,
                "session": "4",
                "task": "emotion_recognition",
                "n_categories": 3,
                "n_trials_per_category": _effective_trials_per_category(cfg),
                "total_trials": len(trials),
                "successful_trials": successful_trials,
                "failed_trials": failed_trials,
                "pre_stimulus_fixation_s": fixation_duration,
                "post_stimulus_rest_s": rest_duration,
                "quick_test": _is_quick_test(cfg),
                "category_counts": category_counts,
            },
            suffix="session4_emotion",
        )
        print("[Session 4 情绪识别] 数据已保存。")
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
