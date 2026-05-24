"""
实验工具模块 — Trigger 发送、键盘队列、资源清理、界面辅助函数
依赖: psychopy, pyserial, numpy
"""

import sys
import time
import atexit
import numpy as np
from typing import Optional, Any

# PsychoPy
from psychopy import visual, core, event, sound
from psychopy.hardware import keyboard

# 串口
try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    print("⚠️  pyserial 未安装，Trigger 功能不可用。安装: pip install pyserial")


# ============================================================
# 全局资源追踪 (用于 finally 清理)
# ============================================================

_global_resources = {
    "serial_port": None,
    "window": None,
    "kb": None,
    "audio": None,
}

def register_resource(name: str, obj: Any):
    """注册需要清理的全局资源"""
    _global_resources[name] = obj

def cleanup_all():
    """强力清理所有底层资源 (对齐 MATLAB try-catch 清理逻辑)"""
    # 1. 键盘
    try:
        kb = _global_resources.get("kb")
        if kb:
            kb.clearEvents()
    except:
        pass

    # 2. 串口
    try:
        sp = _global_resources.get("serial_port")
        if sp and sp.is_open:
            sp.close()
            print("[清理] 串口已释放")
            _global_resources["serial_port"] = None
            # 给 Windows COM 驱动留出 ~300ms 释放时间, 下一段实验立刻新建
            # TriggerSender 时不会撞 "Access denied"。
            time.sleep(0.3)
    except:
        pass

    # 3. 窗口
    try:
        win = _global_resources.get("window")
        if win:
            win.close()
            print("[清理] 窗口已关闭")
    except:
        pass

    # 4. 音频
    try:
        aud = _global_resources.get("audio")
        if aud:
            aud.stop()
    except:
        pass

    print("[清理] 全部资源已释放")


# 注册退出清理
atexit.register(cleanup_all)


# ============================================================
# Trigger / Marker 发送
# ============================================================

class TriggerSender:
    """脑电 Trigger 发送器 (串口协议)

    Windows 串口在被释放后通常需要 100-300ms 才能再次打开，全流程
    `python launcher.py --session all` 模式下相邻 Session 切换会撞上
    "PermissionError: Access is denied"。这里加入有限次重试，避免静默
    降级到 no_hardware 导致 SSVEP 全程没有 Marker。
    """

    OPEN_RETRY_COUNT = 5
    OPEN_RETRY_INTERVAL_S = 0.3

    def __init__(self, port_name: str = "COM3", baud_rate: int = 115200,
                 no_hardware: bool = False):
        self.no_hardware = no_hardware
        self.serial_port = None
        self.port_name = port_name
        self.baud_rate = baud_rate

        if no_hardware:
            print("⚠️ [Trigger] 无硬件模式 — 不会实际发送 Trigger")
            return

        if not HAS_SERIAL:
            print("⚠️ [Trigger] pyserial 未安装，降级为无硬件模式")
            self.no_hardware = True
            return

        last_exc = None
        for attempt in range(1, self.OPEN_RETRY_COUNT + 1):
            try:
                self.serial_port = serial.Serial(
                    port=port_name,
                    baudrate=baud_rate,
                    parity=serial.PARITY_NONE,
                    bytesize=serial.EIGHTBITS,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=1.0
                )
                register_resource("serial_port", self.serial_port)
                print(f"[Trigger] 串口 {port_name} 连接成功 (波特率 {baud_rate}, 第 {attempt} 次尝试)")
                return
            except Exception as e:
                last_exc = e
                if attempt < self.OPEN_RETRY_COUNT:
                    print(f"⚠️ [Trigger] 串口 {port_name} 第 {attempt} 次打开失败: {e}, "
                          f"{self.OPEN_RETRY_INTERVAL_S:.1f}s 后重试...")
                    time.sleep(self.OPEN_RETRY_INTERVAL_S)

        print(f"❌ [Trigger] 串口 {port_name} 连续 {self.OPEN_RETRY_COUNT} 次打开失败: {last_exc}")
        print("⚠️ [Trigger] 降级为无硬件模式 — EEG 软件不会收到 Marker！")
        self.no_hardware = True
        self.serial_port = None

    def send(self, marker: int, duration_ms: float = 5.0):
        """发送一个 Marker 脉冲 (标记 → 等待 → 归零)

        Args:
            marker: Marker 值 (0-255)
            duration_ms: 脉冲持续时间 (毫秒)
        """
        if self.no_hardware or self.serial_port is None:
            return

        try:
            marker = int(marker) & 0xFF
            self._write_marker_frame(marker)
            core.wait(duration_ms / 1000.0)
            self._write_marker_frame(0)

        except Exception as e:
            print(f"⚠️ [Trigger] 发送失败 (marker={marker}): {e}")

    def _write_marker_frame(self, marker: int):
        frame = bytes([marker, 0x55, 0x66, 0x0D])
        self.serial_port.write(frame)
        self.serial_port.flush()

    def send_and_log(self, marker: int, marker_name: str = "",
                     duration_ms: float = 5.0):
        """发送 Marker 并打印日志"""
        label = f"{marker_name} (={marker})" if marker_name else str(marker)
        print(f"  [Marker] {label}")
        self.send(marker, duration_ms)

    def close(self):
        if self.serial_port is not None:
            try:
                if self.serial_port.is_open:
                    self.serial_port.close()
                    print(f"[Trigger] 串口 {self.port_name} 已关闭")
            except Exception as e:
                print(f"⚠️ [Trigger] 关闭串口时报错 (可忽略): {e}")
            finally:
                # 清掉全局引用, 避免 cleanup_all 重复关闭
                if _global_resources.get("serial_port") is self.serial_port:
                    _global_resources["serial_port"] = None
                self.serial_port = None


# ============================================================
# 键盘队列 (对齐 MATLAB KbQueue)
# ============================================================

class KeyboardManager:
    """基于 PsychoPy keyboard.Keyboard 的键盘管理器

    提供与 MATLAB KbQueue 等价的可靠按键检测：
    - 队列模式 (不丢键)
    - 等待指定按键
    - ESC 全局终止
    """

    def __init__(self, escape_key: str = "escape"):
        self.kb = keyboard.Keyboard()
        self.escape_key = escape_key
        register_resource("kb", self.kb)

    def wait_for_key(self, target_keys, timeout: float = None,
                     exit_on_esc: bool = True) -> Optional[str]:
        """等待指定的按键 (阻塞)，返回按下的键名

        Args:
            target_keys: 目标按键或按键列表，如 "space" 或 ["t", "f"]
            timeout: 超时时间 (秒)，None = 无限等待
            exit_on_esc: True 时按 ESC 抛出 SystemExit

        Returns:
            按下的键名，超时返回 None
        """
        if isinstance(target_keys, str):
            target_keys = [target_keys]

        self.kb.clearEvents()
        clock = core.Clock()

        while True:
            keys = self.kb.getKeys(target_keys + (["escape"] if exit_on_esc else []),
                                  waitRelease=False, clear=True)

            for k in keys:
                if exit_on_esc and k.name == "escape":
                    print("\n>>> 实验被用户终止 (ESC) <<<")
                    raise SystemExit(0)
                if k.name in target_keys:
                    return k.name

            if timeout is not None and clock.getTime() > timeout:
                return None

            core.wait(0.005)  # 5ms 轮询间隔

    def wait_for_space(self, timeout: float = None) -> Optional[str]:
        """等待空格键"""
        return self.wait_for_key("space", timeout=timeout)

    def get_choice(self, options: dict) -> str:
        """等待按键选择，返回选中的选项

        Args:
            options: 键名 → 返回值的映射，如 {"t": "True", "f": "False"}
        """
        target = list(options.keys())
        key = self.wait_for_key(target)
        return options[key]

    def flush(self):
        """清空键盘队列"""
        self.kb.clearEvents()

    def close(self):
        try:
            self.kb.clearEvents()
        except:
            pass


# ============================================================
# 文本渲染辅助 (中文)
# ============================================================

def draw_text(win: visual.Window, text: str, font_size: int = 50,
              color: tuple = (1.0, 1.0, 1.0), pos: tuple = (0, 0),
              bold: bool = False, wrap_width: float = None):
    """在窗口中央绘制中文文本

    Args:
        win: PsychoPy 窗口
        text: 文本内容
        font_size: 字号
        color: RGB 颜色 (0-1 归一化), 默认白色
        pos: 位置 (x, y), 默认居中
        bold: 是否加粗
        wrap_width: 自动换行宽度 (归一化单位)
    """
    stim = visual.TextStim(
        win,
        text=text,
        font="Microsoft YaHei",
        pos=pos,
        height=font_size / win.size[1],  # 转换为归一化单位
        color=color,
        bold=bold,
        wrapWidth=wrap_width,
        languageStyle="LTR"
    )
    stim.draw()


def draw_text_centered(win: visual.Window, text: str, font_size: int = 50,
                       color: tuple = (1.0, 1.0, 1.0),
                       wrap_width: float = None, y_offset: float = 0):
    """居中绘制文本 (带可选的垂直偏移)"""
    draw_text(win, text, font_size=font_size, color=color,
              pos=(0, y_offset), wrap_width=wrap_width)


def show_message(win: visual.Window, text: str, font_size: int = 50,
                 color: tuple = (1.0, 1.0, 1.0), duration: float = None):
    """显示一条消息 (立即翻屏)

    Args:
        win: 窗口
        text: 消息文本
        font_size: 字号
        color: 颜色
        duration: 显示时长 (秒), None = 不自动消失
    """
    draw_text_centered(win, text, font_size=font_size, color=color)
    win.flip()

    if duration is not None:
        core.wait(duration)


def show_message_and_wait(win: visual.Window, kb: KeyboardManager,
                          text: str, font_size: int = 50,
                          wait_key: str = "space") -> str:
    """显示消息并等待按键

    Returns:
        按下的键名
    """
    show_message(win, text, font_size=font_size)
    return kb.wait_for_key(wait_key)


# ============================================================
# 注视十字
# ============================================================

def draw_fixation(win: visual.Window, color: tuple = (0.5, 0.5, 0.5),
                  size: float = 0.03, line_width: float = 3.0):
    """绘制注视十字 "+"

    Args:
        win: 窗口
        color: 十字颜色 (0-1 RGB)
        size: 十字臂长 (归一化单位)
        line_width: 线宽 (像素)
    """
    # 水平线
    h_line = visual.Line(win, start=(-size, 0), end=(size, 0),
                        lineColor=color, lineWidth=line_width)
    h_line.draw()
    # 竖直线
    v_line = visual.Line(win, start=(0, -size), end=(0, size),
                        lineColor=color, lineWidth=line_width)
    v_line.draw()


# ============================================================
# 音频提示 (滴声)
# ============================================================

def create_beep(frequency: float = 1000.0, duration: float = 0.1,
                sample_rate: int = 44100) -> np.ndarray:
    """生成短促滴声波形

    Args:
        frequency: 频率 (Hz)
        duration: 时长 (秒)
        sample_rate: 采样率

    Returns:
        单声道音频波形
    """
    t = np.arange(0, duration, 1.0 / sample_rate)
    # 带指数衰减包络
    envelope = np.exp(-3.0 * t / duration)  # 避免咔嗒声
    waveform = np.sin(2 * np.pi * frequency * t) * envelope
    return waveform.astype(np.float32)


# ============================================================
# 数据保存
# ============================================================

def get_scheme_dir(cfg) -> str:
    """返回当前 scheme 对应的数据根目录： <data_dir>/<scheme>。

    两套方案共用同一份 data_dir，但通过 scheme 子目录隔离：
        <data_dir>/motor_imagery/{eeg-bdf,eeg-npz,video_records,experiment_logs}
        <data_dir>/emotion/{eeg-bdf,eeg-npz,video_records,experiment_logs}
    """
    import os
    scheme = getattr(cfg, "scheme", "motor_imagery") or "motor_imagery"
    return os.path.join(cfg.data_dir, scheme)


def save_data(cfg, session_data: dict, suffix: str = ""):
    """保存实验数据为 .npz 文件

    Args:
        cfg: ExperimentConfig 对象
        session_data: 要保存的数据字典
        suffix: 文件名后缀
    """
    import os
    import json

    npz_dir = os.path.join(get_scheme_dir(cfg), "eeg-npz")
    os.makedirs(npz_dir, exist_ok=True)
    filename = cfg.make_filename(suffix) + ".npz"
    filepath = os.path.join(npz_dir, filename)

    # 将配置序列化为 JSON 字符串存入。
    # 同时记录 scheme 和两套方案各自的参数，避免下游分析时丢失上下文。
    config_json = json.dumps({
        "scheme": getattr(cfg, "scheme", "motor_imagery"),
        "subject_id": cfg.subject_id,
        "session": cfg.session,
        "session_order": getattr(cfg, "session_order", None),
        "exp_timestamp": cfg.exp_timestamp,
        "quick_test": getattr(cfg, "quick_test", None),
        "screen_id": getattr(cfg, "screen_id", None),
        "full_screen": getattr(cfg, "full_screen", None),
        "screen_width": getattr(cfg, "screen_width", None),
        "screen_height": getattr(cfg, "screen_height", None),
        "camera_enabled": getattr(cfg, "camera_enabled", None),
        "camera_device_name": getattr(cfg, "camera_device_name", None),
        "camera_width": getattr(cfg, "camera_width", None),
        "camera_height": getattr(cfg, "camera_height", None),
        "camera_fps": getattr(cfg, "camera_fps", None),
        # MI scheme
        "mi_baseline_duration": getattr(cfg, "mi_baseline_duration", None),
        "mi_cue_duration": getattr(cfg, "mi_cue_duration", None),
        "mi_imagery_duration": getattr(cfg, "mi_imagery_duration", None),
        "mi_rest_duration": getattr(cfg, "mi_rest_duration", None),
        "mi_demo_trials_per_class": getattr(cfg, "mi_demo_trials_per_class", None),
        "mi_practice_trials_per_class": getattr(cfg, "mi_practice_trials_per_class", None),
        "mi_formal_trials_per_class": getattr(cfg, "mi_formal_trials_per_class", None),
        "mi_formal_blocks": getattr(cfg, "mi_formal_blocks", None),
        "mi_random_seed": getattr(cfg, "mi_random_seed", None),
        # Emotion scheme
        "emotion_fixation_duration": getattr(cfg, "emotion_fixation_duration", None),
        "emotion_rest_duration": getattr(cfg, "emotion_rest_duration", None),
        "emotion_random_seed": getattr(cfg, "emotion_random_seed", None),
        # Auditory Attention scheme
        "aad_audio_dir": getattr(cfg, "aad_audio_dir", None),
        "aad_difficulty": getattr(cfg, "aad_difficulty", None),
        "aad_speed_multiplier": getattr(cfg, "aad_speed_multiplier", None),
        "aad_trials": getattr(cfg, "aad_trials", None),
        "aad_random_seed": getattr(cfg, "aad_random_seed", None),
        "aad_fixation_duration": getattr(cfg, "aad_fixation_duration", None),
        "aad_rest_duration": getattr(cfg, "aad_rest_duration", None),
    }, ensure_ascii=False)

    save_dict = {"config_json": config_json}
    save_dict.update(session_data)

    np.savez_compressed(filepath, **save_dict)
    print(f"[保存] 数据已保存至: {filepath}")
    return filepath
