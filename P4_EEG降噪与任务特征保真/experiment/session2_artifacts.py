"""
Session 2 — 纯粹伪迹模板采集
────────────────────────────
8 类伪迹: 单次眨眼 / 连续眨眼 / 水平眼动 / 轻度咬牙 / 吞咽口水 / 向左摇头 / 向右摇头 / 上下点头

单个 Trial 时序 (三段式):
  T=0s      屏幕"准备" → 被试按空格键 → Marker 30
  T=0~2s    强制静息等待 (让按键运动电位平息)
  T=2s      系统"滴"声 → Marker 31 (伪迹起始)
  T=2~3s    被试执行伪迹动作
  T=3~5s    休息

Marker 体系:
  30=按键, 31=伪迹开始
  41=单眨眼, 42=连眨, 43=水平眼动, 44=咬牙, 45=吞咽
  46=向左摇头, 47=向右摇头, 48=上下点头

依赖: config.py, utils.py
用法: python session2_artifacts.py
      python session2_artifacts.py --subject Sub_01 --windowed
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import random
from psychopy import visual, core, sound

from config import ExperimentConfig, MARKER_TABLE, config_from_args, ExperimentLauncher
from utils import (
    TriggerSender, KeyboardManager, draw_fixation, draw_text_centered,
    show_message, show_message_and_wait, create_beep, save_data, cleanup_all
)


# ============================================================
# 伪迹类型定义
# ============================================================

QUIET_DURATION = 2.0
ACTION_DURATION = 1.0
REST_DURATION = 2.0

# 水平眼动小球: 单独配置, 让运动更明显, 给被试更明确的视觉跟随线索。
# - 振幅: ±SACCADE_BALL_AMPLITUDE (height 单位; 0.42 ≈ 全屏 84% 宽度)
# - 时长: SACCADE_DURATION 秒 (更长, 避免被试反应不过来)
# - 半径: SACCADE_BALL_RADIUS (更大, 视觉锚点更明显)
SACCADE_DURATION = 2.0
SACCADE_BALL_AMPLITUDE = 0.42
SACCADE_BALL_RADIUS = 0.028

ARTIFACT_TYPES = [
    {
        "name": "单次眨眼",
        "marker": MARKER_TABLE["S2_BLINK_SINGLE"],
        "count": 20,
        "instruction": "听到滴声后\n用力眨一下眼睛",
        "cue_symbol": "👁",
    },
    {
        "name": "连续眨眼",
        "marker": MARKER_TABLE["S2_BLINK_MULTI"],
        "count": 10,
        "instruction": "听到滴声后\n快速连眨三下\n(像眼睛里进了沙子)",
        "cue_symbol": "👁👁👁",
    },
    {
        "name": "水平眼动",
        "marker": MARKER_TABLE["S2_SACCADE"],
        "count": 30,
        "instruction": "听到滴声后\n眼睛跟随红球向左或向右移动\n(头绝对不能动)",
        "cue_symbol": "●",
    },
    {
        "name": "轻度咬牙",
        "marker": MARKER_TABLE["S2_JAW_CLENCH"],
        "count": 30,
        "instruction": "听到滴声后\n轻轻咬紧后槽牙\n持续 1 秒后放松",
        "cue_symbol": "🦷",
    },
    {
        "name": "吞咽口水",
        "marker": MARKER_TABLE["S2_SWALLOW"],
        "count": 10,
        "instruction": "听到滴声后\n自然地吞咽一下",
        "cue_symbol": "💧",
    },
    {
        "name": "向左摇头",
        "marker": MARKER_TABLE["S2_HEAD_LEFT"],
        "count": 10,
        "instruction": "听到滴声后\n中等幅度把头向左摇一下",
        "cue_symbol": "↖",
    },
    {
        "name": "向右摇头",
        "marker": MARKER_TABLE["S2_HEAD_RIGHT"],
        "count": 10,
        "instruction": "听到滴声后\n中等幅度把头向右摇一下",
        "cue_symbol": "↗",
    },
    {
        "name": "上下点头",
        "marker": MARKER_TABLE["S2_HEAD_NOD"],
        "count": 10,
        "instruction": "听到滴声后\n中等幅度上下点一下头",
        "cue_symbol": "↕",
    },
]

# 让水平眼动逻辑也跟 MARKER_TABLE 绑定, 防止改 marker 时漏改
SACCADE_MARKER = MARKER_TABLE["S2_SACCADE"]


# ============================================================
# Main
# ============================================================

def run_session2(cfg: ExperimentConfig):
    """运行 Session 2 — 伪迹模板采集"""

    trigger = TriggerSender(cfg.port_name, cfg.baud_rate, cfg.no_hardware)

    win = visual.Window(
        size=(cfg.screen_width, cfg.screen_height),
        screen=cfg.screen_id,
        fullscr=cfg.full_screen,
        color=cfg.background_color,
        units="height",
        allowGUI=False,
    )
    from utils import register_resource
    register_resource("window", win)

    kb = KeyboardManager()

    beep_wave = create_beep(cfg.beep_frequency, cfg.beep_duration)
    beep_sound = sound.Sound(beep_wave, sampleRate=44100)

    show_message_and_wait(
        win, kb,
        "伪迹模板采集\n\n"
        "本阶段将引导您执行 8 种常见的动作\n"
        "每种动作会产生不同类型的信号模板\n\n"
        "按 空格键 开始",
        font_size=40,
    )

    show_message_and_wait(
        win, kb,
        "每个试次的流程:\n\n"
        "1. 屏幕出现「准备」→ 按 空格键\n"
        "2. 保持静止 2 秒钟\n"
        "3. 听到「滴」声后 → 执行动作\n"
        "4. 休息 → 下一试次\n\n"
        "按 空格键 继续",
        font_size=38,
    )

    all_events = []

    for art_idx, art_type in enumerate(ARTIFACT_TYPES):
        art_name = art_type["name"]
        art_marker = art_type["marker"]
        n_trials = art_type["count"]
        instruction = art_type["instruction"]
        is_last_type = (art_idx == len(ARTIFACT_TYPES) - 1)

        show_message(
            win,
            f"下一个动作: {art_name}\n\n"
            f"{instruction}\n\n"
            f"共 {n_trials} 个试次\n\n"
            f"按 空格键 开始此类",
            font_size=42,
        )
        kb.wait_for_space()

        movement_directions = []
        if art_marker == SACCADE_MARKER:
            movement_directions = ["left"] * (n_trials // 2) + ["right"] * (n_trials - n_trials // 2)
            random.shuffle(movement_directions)

        for trial_i in range(n_trials):
            direction = movement_directions[trial_i] if movement_directions else ""
            direction_text = "向左" if direction == "left" else "向右" if direction == "right" else ""
            progress_label = f"{art_name}-{direction_text}" if direction_text else art_name

            if direction_text:
                show_message(
                    win,
                    f"准备\n\n本试次: 跟随红球{direction_text}移动\n头部保持不动",
                    font_size=42,
                )
            else:
                show_message(win, "准备", font_size=60)
            kb.wait_for_space()
            trigger.send_and_log(MARKER_TABLE["S2_KEYPRESS"], "S2_KEYPRESS")

            quiet_start = core.getTime()
            while core.getTime() - quiet_start < QUIET_DURATION:
                draw_fixation(win)
                win.flip()

            beep_sound.play()
            trigger.send_and_log(MARKER_TABLE["S2_ARTIFACT_ON"], "S2_ARTIFACT_ON")
            trigger.send_and_log(art_marker, f"S2_{progress_label}")

            # 水平眼动: 用更长的动作时长 + 更大的振幅, 避免运动太短被试反应不过来
            is_saccade = (art_marker == SACCADE_MARKER)
            this_action_duration = SACCADE_DURATION if is_saccade else ACTION_DURATION

            action_start = core.getTime()
            while core.getTime() - action_start < this_action_duration:
                if is_saccade:
                    elapsed = core.getTime() - action_start
                    progress = min(elapsed / this_action_duration, 1.0)
                    if direction == "left":
                        x_pos = SACCADE_BALL_AMPLITUDE - 2 * SACCADE_BALL_AMPLITUDE * progress
                    else:
                        x_pos = -SACCADE_BALL_AMPLITUDE + 2 * SACCADE_BALL_AMPLITUDE * progress
                    red_ball = visual.Circle(
                        win,
                        radius=SACCADE_BALL_RADIUS,
                        pos=(x_pos, 0),
                        fillColor=(1, 0, 0),
                        lineColor=None,
                    )
                    red_ball.draw()
                else:
                    draw_text_centered(win, art_type["cue_symbol"], font_size=80)
                win.flip()

            rest_start = core.getTime()
            while core.getTime() - rest_start < REST_DURATION:
                draw_text_centered(win, "休息...", font_size=30, color=(0.3, 0.3, 0.3))
                win.flip()

            all_events.append({
                "trial": trial_i + 1,
                "artifact": progress_label,
                "marker_type": art_marker,
                "movement_direction": direction or "none",
            })

            print(f"[Session 2] {progress_label} {trial_i + 1}/{n_trials}")

        print(f"[{art_name}] 全部 {n_trials} 个试次完成")
        if not is_last_type:
            show_message_and_wait(
                win,
                kb,
                f"「{art_name}」完成\n\n休息一下\n按 空格键 继续下一类",
                font_size=42,
            )

    show_message_and_wait(
        win,
        kb,
        "Session 2 完成！\n\n所有伪迹模板已采集完毕\n按 空格键 退出",
        font_size=45,
    )

    session_data = {
        "n_artifact_types": len(ARTIFACT_TYPES),
        "total_trials": sum(a["count"] for a in ARTIFACT_TYPES),
        "quiet_duration_s": QUIET_DURATION,
        "action_duration_s": ACTION_DURATION,
        "saccade_action_duration_s": SACCADE_DURATION,
        "saccade_ball_amplitude_height_units": SACCADE_BALL_AMPLITUDE,
        "saccade_ball_radius_height_units": SACCADE_BALL_RADIUS,
        "rest_duration_s": REST_DURATION,
        "events": all_events,
    }
    save_data(cfg, session_data, suffix="session2")

    print("Session 2 数据已保存。")

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

        run_session2(cfg)

    except SystemExit:
        pass
    except Exception as e:
        print(f"\n❌ 实验异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup_all()
