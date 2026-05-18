"""
Session 3 — SSVEP 稳态视觉诱发电位 (窄带频谱 + 锁相精度验证)
────────────────────────────────────────────────────────
4 频率: 6Hz / 8.57Hz / 10Hz / 15Hz
正式版采用四宫格同时显示：
  左上 6Hz / 右上 8.57Hz / 左下 10Hz / 右下 15Hz
每个 trial 提前提示被试看哪一个方块，然后四个方块同时闪烁 4 秒。

Marker 体系 (8-bit):
  S3: 131=6Hz, 132=8.57Hz, 133=10Hz, 134=15Hz
  S4: 151=6Hz, 152=8.57Hz, 153=10Hz, 154=15Hz

依赖: config.py, utils.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import random
from psychopy import visual, core

from config import (
    ExperimentConfig, get_marker, config_from_args, ExperimentLauncher
)
from utils import (
    TriggerSender, KeyboardManager, draw_fixation,
    show_message_and_wait, save_data, cleanup_all
)


# ============================================================
# SSVEP 四频率参数 (60Hz 刷新率)
# ============================================================

N_TRIALS_PER_FREQ = 20     # 每个频率 20 trials
FLICKER_DURATION = 4.0     # 闪烁持续 4 秒
PRE_STIM_QUIET = 0.500     # 刺激前强制静息 500ms
CUE_DURATION = 1.0         # 目标提示 1 秒
EXPECTED_REFRESH_RATE = 60.0
REFRESH_TOLERANCE_HZ = 1.5   # 超过 ±1.5Hz 直接告警 (不再"自适应"模糊处理)
WARMUP_FRAMES = 60           # 正式闪烁前先 flip 60 帧, 让 vsync 进入稳态
FRAME_INTERVAL_THRESHOLD_S = 1.0 / EXPECTED_REFRESH_RATE + 0.004  # 丢帧检测阈值

ON_COLOR = (1.0, 1.0, 1.0)
OFF_COLOR = (0.05, 0.05, 0.05)

FORMAL_SQUARE_SIZE = 0.18
FORMAL_GRID_X = 0.28
FORMAL_GRID_Y = 0.20
FORMAL_LABEL_Y_OFFSET = 0.16
DEBUG_SQUARE_SIZE = 0.18
DEBUG_GRID_X = 0.28
DEBUG_GRID_Y = 0.20
LABEL_Y_OFFSET = 0.16

FREQ_SPECS = [
    {"hz": 6.0,   "label": "6Hz",    "marker_name": "SSVEP_6HZ",    "frames_on": 5, "frames_off": 5, "band": "Theta",      "position_label": "左上"},
    {"hz": 8.57,  "label": "8.57Hz", "marker_name": "SSVEP_8_57HZ", "frames_on": 3, "frames_off": 4, "band": "Alpha-low", "position_label": "右上"},
    {"hz": 10.0,  "label": "10Hz",   "marker_name": "SSVEP_10HZ",   "frames_on": 3, "frames_off": 3, "band": "Alpha",      "position_label": "左下"},
    {"hz": 15.0,  "label": "15Hz",   "marker_name": "SSVEP_15HZ",   "frames_on": 2, "frames_off": 2, "band": "Beta",       "position_label": "右下"},
]

FORMAL_POSITIONS = {
    "6Hz": (-FORMAL_GRID_X, FORMAL_GRID_Y),
    "8.57Hz": (FORMAL_GRID_X, FORMAL_GRID_Y),
    "10Hz": (-FORMAL_GRID_X, -FORMAL_GRID_Y),
    "15Hz": (FORMAL_GRID_X, -FORMAL_GRID_Y),
}

DEBUG_POSITIONS = {
    "6Hz": (-DEBUG_GRID_X, DEBUG_GRID_Y),
    "8.57Hz": (DEBUG_GRID_X, DEBUG_GRID_Y),
    "10Hz": (-DEBUG_GRID_X, -DEBUG_GRID_Y),
    "15Hz": (DEBUG_GRID_X, -DEBUG_GRID_Y),
}

N_TOTAL = N_TRIALS_PER_FREQ * len(FREQ_SPECS)  # 80


def _build_grid_stimuli(win, positions, square_size, label_offset):
    squares = {}
    labels = {}
    for spec in FREQ_SPECS:
        pos = positions[spec["label"]]
        squares[spec["label"]] = visual.Rect(
            win, width=square_size, height=square_size,
            pos=pos, fillColor=OFF_COLOR, lineColor=None
        )
        labels[spec["label"]] = visual.TextStim(
            win,
            text=spec['position_label'],
            font="Microsoft YaHei",
            pos=(pos[0], pos[1] + label_offset),
            height=0.04,
            color=(1, 1, 1),
            bold=True,
        )
    return squares, labels


def _compute_runtime_specs(actual_fps):
    runtime_specs = []
    for spec in FREQ_SPECS:
        total_frames = max(2, int(round(actual_fps / spec["hz"])))
        frames_on = max(1, total_frames // 2)
        frames_off = max(1, total_frames - frames_on)
        actual_hz = actual_fps / total_frames
        runtime_specs.append({
            **spec,
            "runtime_total_frames": total_frames,
            "runtime_frames_on": frames_on,
            "runtime_frames_off": frames_off,
            "runtime_actual_hz": actual_hz,
            "runtime_error_pct": abs(actual_hz - spec["hz"]) / spec["hz"] * 100,
        })
    return runtime_specs


def _get_refresh_rate(win, nIdentical=10, nMaxFrames=200, nWarmUpFrames=10, threshold=0.5):
    """多次测量取稳定值。

    PsychoPy 的 `getActualFrameRate` 默认只看 10 连续帧的中位数, 在 Windows
    动态刷新率 / VRR 启用时会返回 90/120 之类的杂乱值。这里把 nIdentical
    放宽、加 warm-up, 同时连测两次取最接近 60Hz 的一次, 提高稳定性。
    """
    candidates = []
    for _ in range(2):
        m = win.getActualFrameRate(
            nIdentical=nIdentical,
            nMaxFrames=nMaxFrames,
            nWarmUpFrames=nWarmUpFrames,
            threshold=threshold,
        )
        if m is not None:
            candidates.append(m)

    fps_warning = ""
    if not candidates:
        actual_fps = EXPECTED_REFRESH_RATE
        fps_warning = (
            "无法测得实际刷新率。将按 60Hz 强制运行；"
            "正式采集前必须在 Windows 显示设置中确认外接屏稳定在 60Hz。"
        )
    else:
        # 取最接近 60Hz 的一次测量
        actual_fps = min(candidates, key=lambda f: abs(f - EXPECTED_REFRESH_RATE))
        if abs(actual_fps - EXPECTED_REFRESH_RATE) > REFRESH_TOLERANCE_HZ:
            fps_warning = (
                f"当前刺激屏刷新率测得为 {actual_fps:.2f}Hz，偏离 60Hz 超过 "
                f"{REFRESH_TOLERANCE_HZ}Hz。SSVEP 实际频率会偏离设计值。\n\n"
                "请打开 Windows 设置 → 系统 → 屏幕 → 高级显示器设置，把刷新率"
                "固定为 60Hz，并关闭可变刷新率 (VRR) / 动态刷新率 / 游戏增强 / "
                "Freesync / G-Sync。\n\n正式采集请勿继续。"
            )
        else:
            # 在容忍范围内, 直接按 60Hz 计算, 避免微小偏差导致 frame 数跳变
            actual_fps = EXPECTED_REFRESH_RATE
    return actual_fps, fps_warning


def _show_refresh_warning(win, kb, fps_warning, debug_mode=False):
    if not fps_warning:
        return
    mode_title = "SSVEP 四宫格调试" if debug_mode else "SSVEP 刷新率警告"
    show_message_and_wait(
        win, kb,
        f"{mode_title}\n\n{fps_warning}\n\n"
        "如果只是无硬件测试，可以按空格继续；\n正式采集前请先修正刷新率。",
        font_size=30
    )


def run_ssvep_grid_debug(cfg: ExperimentConfig):
    """在指定 screen 上同时显示 4 个频率的持续闪烁方块，用于肉眼调试。"""
    win = visual.Window(
        size=(cfg.screen_width, cfg.screen_height),
        screen=cfg.screen_id, fullscr=cfg.full_screen,
        color=cfg.background_color, units="height",
        allowGUI=False
    )
    from utils import register_resource
    register_resource("window", win)

    kb = KeyboardManager()
    actual_fps, fps_warning = _get_refresh_rate(win)
    runtime_specs = _compute_runtime_specs(actual_fps)
    for spec in runtime_specs:
        status = "✓" if spec["runtime_error_pct"] < 1.0 else "⚠"
        print(
            f"  [{status}] {spec['label']}: {spec['runtime_total_frames']} 帧/周期 "
            f"(ON {spec['runtime_frames_on']} / OFF {spec['runtime_frames_off']}) → "
            f"{spec['runtime_actual_hz']:.2f} Hz (误差 {spec['runtime_error_pct']:.1f}%)"
        )

    _show_refresh_warning(win, kb, fps_warning, debug_mode=True)

    show_message_and_wait(
        win, kb,
        "SSVEP 四宫格调试\n\n"
        "屏幕上将同时显示 4 个频率的闪烁方块\n"
        "左上 6Hz，右上 8.57Hz，左下 10Hz，右下 15Hz\n"
        "按 空格键 开始，按 ESC 退出",
        font_size=30
    )

    squares, labels = _build_grid_stimuli(win, DEBUG_POSITIONS, DEBUG_SQUARE_SIZE, LABEL_Y_OFFSET)
    counters = {spec["label"]: 0 for spec in runtime_specs}

    while True:
        keys = kb.kb.getKeys(["escape"], waitRelease=False, clear=True)
        for k in keys:
            if k.name == "escape":
                raise SystemExit(0)

        for spec in runtime_specs:
            label = spec["label"]
            total_frames = spec["runtime_total_frames"]
            cycle_frame = counters[label] % total_frames
            counters[label] += 1
            if cycle_frame < spec["runtime_frames_on"]:
                squares[label].fillColor = ON_COLOR
            else:
                squares[label].fillColor = OFF_COLOR

        for spec in FREQ_SPECS:
            label = spec["label"]
            labels[label].draw()
            squares[label].draw()
        win.flip()


def run_ssvep(cfg: ExperimentConfig):
    """运行正式四宫格 SSVEP 任务 (Session 3 或 Session 4)"""
    is_natural = cfg.natural_mode
    session_label = "S4 (自然态)" if is_natural else "S3 (银标准)"

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

    # 开启丢帧记录与 vsync 强同步, 让闪烁速率受显卡 vsync 约束, 不受 wall clock 影响
    win.recordFrameIntervals = True
    win.refreshThreshold = FRAME_INTERVAL_THRESHOLD_S
    win.setMouseVisible(False)

    actual_fps, fps_warning = _get_refresh_rate(win)
    frame_interval_ms = 1000.0 / actual_fps
    print(f"[SSVEP] 实际帧率: {actual_fps:.2f} Hz, 帧间隔: {frame_interval_ms:.2f} ms")
    if fps_warning:
        print(f"⚠ [SSVEP] {fps_warning}")

    runtime_specs = _compute_runtime_specs(actual_fps)
    for spec in runtime_specs:
        status = "✓" if spec["runtime_error_pct"] < 1.0 else "⚠"
        print(
            f"  [{status}] {spec['label']}: {spec['runtime_total_frames']} 帧/周期 "
            f"(ON {spec['runtime_frames_on']} / OFF {spec['runtime_frames_off']}) → "
            f"{spec['runtime_actual_hz']:.2f} Hz (误差 {spec['runtime_error_pct']:.1f}%)"
        )

    _show_refresh_warning(win, kb, fps_warning)

    squares, labels = _build_grid_stimuli(win, FORMAL_POSITIONS, FORMAL_SQUARE_SIZE, FORMAL_LABEL_Y_OFFSET)

    # 在首个 trial 前做 warm-up: 连续 flip WARMUP_FRAMES 帧并丢弃, 让 vsync 进入稳态
    print(f"[SSVEP] warm-up {WARMUP_FRAMES} 帧 (让 vsync 进入稳态) ...")
    for _ in range(WARMUP_FRAMES):
        win.flip()
    win.nDroppedFrames = 0  # 重置统计

    trials = []
    for spec in runtime_specs:
        for _ in range(N_TRIALS_PER_FREQ):
            trials.append(spec)
    random.shuffle(trials)

    freq_list_str = " / ".join(s["label"] for s in FREQ_SPECS)
    if is_natural:
        instruction_text = (
            f"SSVEP 任务（自然态）\n\n"
            f"屏幕上会同时显示 4 个频率方块：{freq_list_str}\n"
            f"每个 trial 会提前告诉你要看哪个位置\n"
            f"四个方块会同时闪烁 4 秒\n"
            f"共 {N_TOTAL} 个试次\n\n"
            f"你可以完全放松，不需要控制眨眼\n"
            f"每次休息可以久一点，准备好再按空格继续\n\n"
            f"按 空格键 开始"
        )
    else:
        instruction_text = (
            f"SSVEP 任务\n\n"
            f"屏幕上会同时显示 4 个频率方块：{freq_list_str}\n"
            f"每个 trial 会提前告诉你要看哪个位置\n"
            f"四个方块会同时闪烁 4 秒\n"
            f"共 {N_TOTAL} 个试次\n\n"
            f"⚠ 闪烁过程中绝对禁止眨眼\n"
            f"⚠ 只有屏幕显示休息时才能眨眼\n"
            f"每次休息可以久一点，准备好再按空格继续\n\n"
            f"按 空格键 开始"
        )
    show_message_and_wait(win, kb, instruction_text, font_size=30)

    trial_events = []

    for trial_i, spec in enumerate(trials):
        freq_label = spec["label"]
        marker = get_marker(spec["marker_name"], natural_mode=is_natural)
        counters = {s["label"]: 0 for s in runtime_specs}

        cue_text = f"请看：{spec['position_label']}"
        cue_start = core.getTime()
        while core.getTime() - cue_start < CUE_DURATION:
            for s in runtime_specs:
                label = s["label"]
                labels[label].draw()
                squares[label].fillColor = OFF_COLOR
                squares[label].draw()
            cue = visual.TextStim(
                win,
                text=cue_text,
                font="Microsoft YaHei",
                pos=(0, 0),
                height=0.06,
                color=(1, 1, 1),
                bold=True,
            )
            cue.draw()
            win.flip()

        quiet_start = core.getTime()
        while core.getTime() - quiet_start < PRE_STIM_QUIET:
            draw_fixation(win, size=0.02, color=(0.25, 0.25, 0.25))
            win.flip()

        trigger.send_and_log(
            marker,
            f"{spec['position_label']} (trial {trial_i + 1}/{N_TOTAL})"
        )

        # 关键: 按帧循环 (而不是 wall-clock), 确保各方块按各自周期严格闪烁。
        # vsync 阻塞 win.flip(), 因此每次循环耗时 ≈ 16.67ms; counters 严格
        # 与实际渲染帧绑定, 4 个方块的频率独立、不会因 GPU 卡顿被错速。
        total_flicker_frames = int(round(FLICKER_DURATION * actual_fps))
        dropped_before = win.nDroppedFrames
        for _frame_i in range(total_flicker_frames):
            for s in runtime_specs:
                label = s["label"]
                total_frames = s["runtime_total_frames"]
                cycle_frame = counters[label] % total_frames
                counters[label] += 1
                if cycle_frame < s["runtime_frames_on"]:
                    squares[label].fillColor = ON_COLOR
                else:
                    squares[label].fillColor = OFF_COLOR
                labels[label].draw()
                squares[label].draw()
            win.flip()

        dropped_this_trial = win.nDroppedFrames - dropped_before
        if dropped_this_trial > 0:
            print(f"  ⚠ [SSVEP] trial {trial_i + 1} 丢帧 {dropped_this_trial} 帧, "
                  f"该 trial 实际频率会略有偏差, 建议后处理时剔除")

        rest_text = "休息，可以眨眼和放松\n\n准备好后按 空格键 进入下一试次"
        show_message_and_wait(win, kb, rest_text, font_size=32)

        print(f"[Session {'4' if is_natural else '3'} SSVEP] {spec['position_label']} {trial_i + 1}/{N_TOTAL}")

        trial_events.append({
            "trial": trial_i + 1,
            "target_frequency_hz": round(spec["hz"], 2),
            "target_frequency_label": freq_label,
            "target_position": spec["position_label"],
            "marker": marker,
            "band": spec["band"],
            "dropped_frames": int(dropped_this_trial),
            "total_flicker_frames": int(total_flicker_frames),
        })

        if (trial_i + 1) % 15 == 0:
            print(f"  [SSVEP {session_label}] {trial_i + 1}/{N_TOTAL} trials")

    freq_counts = {}
    for evt in trial_events:
        label = evt["target_frequency_label"]
        freq_counts[label] = freq_counts.get(label, 0) + 1

    print(f"\n[SSVEP {session_label}] 完成统计:")
    for label, cnt in sorted(freq_counts.items()):
        print(f"  {label}: {cnt} trials")

    show_message_and_wait(
        win, kb,
        f"SSVEP 任务完成！\n\n"
        f"共 {N_TOTAL} 个试次（{len(FREQ_SPECS)} 个频率 × {N_TRIALS_PER_FREQ} 次）\n\n"
        f"按 空格键 退出",
        font_size=40
    )

    # frame interval 诊断信息: 用于后处理时排除丢帧 trial / 计算实际刺激频率漂移
    try:
        frame_intervals = list(win.frameIntervals) if win.frameIntervals else []
    except Exception:
        frame_intervals = []
    total_dropped_frames = int(getattr(win, "nDroppedFrames", 0))

    suffix = "session4_ssvep" if is_natural else "session3_ssvep"
    session_data = {
        "session": "4" if is_natural else "3",
        "natural_mode": is_natural,
        "layout": "four-quadrant",
        "n_frequencies": len(FREQ_SPECS),
        "n_trials_per_freq": N_TRIALS_PER_FREQ,
        "total_trials": N_TOTAL,
        "flicker_duration_s": FLICKER_DURATION,
        "rest_mode": "self_paced_space",
        "actual_refresh_rate_hz": round(actual_fps, 2),
        "refresh_warning": fps_warning,
        "total_dropped_frames": total_dropped_frames,
        "frame_interval_threshold_s": FRAME_INTERVAL_THRESHOLD_S,
        "frame_intervals_s": frame_intervals,
        "frequencies": [
            {
                "hz": s["hz"],
                "label": s["label"],
                "band": s["band"],
                "position": s["position_label"],
                "marker": get_marker(s["marker_name"], natural_mode=is_natural),
            }
            for s in FREQ_SPECS
        ],
        "freq_counts": freq_counts,
        "events": trial_events,
    }
    save_data(cfg, session_data, suffix=suffix)

    print(f"[SSVEP {session_label}] 数据已保存。")
    kb.close()
    cleanup_all()


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

        if getattr(cfg, "ssvep_grid_debug", False):
            run_ssvep_grid_debug(cfg)
        else:
            run_ssvep(cfg)

    except SystemExit:
        pass
    except Exception as e:
        print(f"\n❌ 实验异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup_all()
