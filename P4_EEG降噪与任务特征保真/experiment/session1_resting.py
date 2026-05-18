"""
Session 1 — 纯净静息态基线采集
────────────────────────────────
睁眼静息 (2 min) → 过渡 (30s) → 闭眼静息 (2 min)

Marker 体系:
  11 = 睁眼开始    12 = 睁眼结束
  21 = 闭眼开始    22 = 闭眼结束

依赖: config.py, utils.py
用法: python session1_resting.py
      python session1_resting.py --subject Sub_01 --windowed
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
from psychopy import visual, core, sound

from config import ExperimentConfig, MARKER_TABLE, config_from_args, ExperimentLauncher
from utils import (
    TriggerSender, KeyboardManager, draw_fixation, draw_text_centered,
    show_message, show_message_and_wait, create_beep, save_data, cleanup_all
)


# ============================================================
# Session 1 主流程
# ============================================================

def run_session1(cfg: ExperimentConfig):
    """运行 Session 1 — 纯净静息态基线采集"""

    # ---- 初始化 ----
    trigger = TriggerSender(cfg.port_name, cfg.baud_rate, cfg.no_hardware)

    win = visual.Window(
        size=(cfg.screen_width, cfg.screen_height),
        screen=cfg.screen_id, fullscr=cfg.full_screen,
        color=cfg.background_color, units="height",
        allowGUI=False
    )
    # 注册到全局清理
    from utils import register_resource
    register_resource("window", win)

    kb = KeyboardManager()

    beep_wave = create_beep(cfg.beep_frequency, cfg.beep_duration)
    beep_sound = sound.Sound(beep_wave, sampleRate=44100)

    # ---- 开始界面 ----
    show_message_and_wait(
        win, kb,
        "脑电静息态采集\n\n请保持安静，按 空格键 开始",
        font_size=45
    )

    # ==========================================
    # 阶段 1: 睁眼静息 (2 分钟)
    # ==========================================
    show_message(win,
        "请盯住屏幕中央的十字\n\n"
        "尽量不要眨眼\n"
        "禁止咬牙、咽口水或活动身体\n\n"
        "按 空格键 开始睁眼静息",
        font_size=40
    )
    kb.wait_for_space()

    beep_sound.play()
    trigger.send_and_log(MARKER_TABLE["S1_EO_START"], "S1_EO_START")

    print("[Session 1] 睁眼静息开始 0/120s")
    eo_duration = 2 * 60  # 2 分钟
    eo_start = core.getTime()
    eo_last_report = -1

    while core.getTime() - eo_start < eo_duration:
        elapsed = int(core.getTime() - eo_start)
        if elapsed // 30 > eo_last_report:
            eo_last_report = elapsed // 30
            print(f"[Session 1] 睁眼静息 {min(elapsed, eo_duration)}/{eo_duration}s")
        draw_fixation(win)
        win.flip()
        # ESC 安全退出: 被试不适或主试看到嗜睡需立刻中止时, ESC 即时响应
        keys = kb.kb.getKeys(["escape"], waitRelease=False, clear=True)
        for k in keys:
            if k.name == "escape":
                print("\n>>> 实验被用户终止 (ESC) <<<")
                raise SystemExit(0)

    print("[Session 1] 睁眼静息完成")

    beep_sound.play()
    trigger.send_and_log(MARKER_TABLE["S1_EO_END"], "S1_EO_END")

    # ---- 过渡期 (30 秒, ESC 可中断) ----
    # 用循环 + win.flip 替代 core.wait(30.0), 否则被试不舒服时主试按 ESC 无效
    transition_duration = 30.0
    transition_start = core.getTime()
    while core.getTime() - transition_start < transition_duration:
        remaining = int(transition_duration - (core.getTime() - transition_start)) + 1
        from utils import draw_text_centered
        draw_text_centered(
            win,
            f"请闭眼休息\n\n可以自由活动一下面部\n\n{remaining} 秒",
            font_size=40,
        )
        win.flip()
        # 检测 ESC, 不阻塞键盘队列
        keys = kb.kb.getKeys(["escape"], waitRelease=False, clear=True)
        for k in keys:
            if k.name == "escape":
                print("\n>>> 实验被用户终止 (ESC) <<<")
                raise SystemExit(0)

    # ==========================================
    # 阶段 2: 闭眼静息 (2 分钟)
    # ==========================================
    show_message(win,
        "请闭上眼睛\n"
        "保持清醒，脑子里什么都不要想\n\n"
        "按 空格键 开始闭眼静息",
        font_size=40
    )
    kb.wait_for_space()

    beep_sound.play()
    trigger.send_and_log(MARKER_TABLE["S1_EC_START"], "S1_EC_START")

    print("[Session 1] 闭眼静息开始 0/120s")
    ec_duration = 2 * 60  # 2 分钟
    ec_start = core.getTime()
    ec_last_report = -1

    while core.getTime() - ec_start < ec_duration:
        elapsed = int(core.getTime() - ec_start)
        if elapsed // 30 > ec_last_report:
            ec_last_report = elapsed // 30
            print(f"[Session 1] 闭眼静息 {min(elapsed, ec_duration)}/{ec_duration}s")
        # 闭眼期间显示黑屏
        win.flip()
        # ESC 安全退出: 主试发现被试嗜睡时立刻中止, 避免污染 Alpha 阻断基线
        keys = kb.kb.getKeys(["escape"], waitRelease=False, clear=True)
        for k in keys:
            if k.name == "escape":
                print("\n>>> 实验被用户终止 (ESC) <<<")
                raise SystemExit(0)

    print("[Session 1] 闭眼静息完成")

    beep_sound.play()
    trigger.send_and_log(MARKER_TABLE["S1_EC_END"], "S1_EC_END")

    # ---- 结束 ----
    show_message_and_wait(
        win, kb,
        "Session 1 完成！\n\n按 空格键 退出",
        font_size=45
    )

    # ---- 保存 ----
    session_data = {
        "eo_duration_s": eo_duration,
        "ec_duration_s": ec_duration,
        "boundary_beep_enabled": True,
        "beep_frequency_hz": cfg.beep_frequency,
        "beep_duration_s": cfg.beep_duration,
        "markers_sent": [
            ("S1_EO_START",  MARKER_TABLE["S1_EO_START"]),
            ("S1_EO_END",    MARKER_TABLE["S1_EO_END"]),
            ("S1_EC_START",  MARKER_TABLE["S1_EC_START"]),
            ("S1_EC_END",    MARKER_TABLE["S1_EC_END"]),
        ]
    }
    save_data(cfg, session_data, suffix="session1")

    print("Session 1 数据已保存。")

    # ---- 清理 ----
    kb.close()
    cleanup_all()


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    try:
        # 优先使用 GUI，也支持命令行参数
        if len(sys.argv) > 1:
            cfg = config_from_args()
        else:
            launcher = ExperimentLauncher()
            cfg = launcher.run()
            if cfg is None:
                print("实验被用户取消。")
                sys.exit(0)

        run_session1(cfg)

    except SystemExit:
        pass
    except Exception as e:
        print(f"\n❌ 实验异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保资源清理 (对齐 MATLAB try-catch-finally 模式)
        cleanup_all()
