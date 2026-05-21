"""
P8 离线运动想象实验工具模块。

提供：
- Trigger 发送
- 键盘管理
- 窗口/文本/注视十字辅助函数
- 数据保存与资源清理
"""

import atexit
import json
import os
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Optional

import numpy as np

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    serial = None


_global_resources = {
    "serial_port": None,
    "window": None,
    "keyboard": None,
}


def register_resource(name: str, obj: Any) -> None:
    _global_resources[name] = obj


class TriggerSender:
    """串口 Trigger 发送器。"""

    def __init__(self, port_name: str = "COM5", baud_rate: int = 115200, no_hardware: bool = False):
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.no_hardware = no_hardware
        self.serial_port = None

        if self.no_hardware:
            print("[Trigger] 无硬件模式，Marker 仅记录不发送。")
            return
        if not HAS_SERIAL:
            print("[Trigger] pyserial 未安装，自动降级为无硬件模式。")
            self.no_hardware = True
            return

        try:
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=baud_rate,
                parity=serial.PARITY_NONE,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0,
            )
            register_resource("serial_port", self.serial_port)
            print(f"[Trigger] 串口 {port_name} 打开成功。")
        except Exception as exc:
            print(f"[Trigger] 串口 {port_name} 打开失败：{exc}")
            print("[Trigger] 自动降级为无硬件模式。")
            self.serial_port = None
            self.no_hardware = True

    def send(self, marker: int, duration_ms: float = 5.0) -> None:
        if self.no_hardware or self.serial_port is None:
            return
        try:
            marker = int(marker) & 0xFF
            frame = bytes([marker, 0x55, 0x66, 0x0D])
            self.serial_port.write(frame)
            self.serial_port.flush()
            time.sleep(duration_ms / 1000.0)
            zero_frame = bytes([0, 0x55, 0x66, 0x0D])
            self.serial_port.write(zero_frame)
            self.serial_port.flush()
        except Exception as exc:
            print(f"[Trigger] 发送 marker={marker} 失败：{exc}")

    def send_and_log(self, marker: int, name: str = "") -> None:
        label = f"{name} (={marker})" if name else str(marker)
        print(f"[Marker] {label}")
        self.send(marker)

    def close(self) -> None:
        if self.serial_port is not None:
            try:
                if self.serial_port.is_open:
                    self.serial_port.close()
                    print(f"[Trigger] 串口 {self.port_name} 已关闭。")
            except Exception as exc:
                print(f"[Trigger] 关闭串口时出错：{exc}")
            finally:
                if _global_resources.get("serial_port") is self.serial_port:
                    _global_resources["serial_port"] = None
                self.serial_port = None


class KeyboardManager:
    """基于 PsychoPy keyboard.Keyboard 的按键管理。"""

    def __init__(self, escape_key: str = "escape"):
        from psychopy.hardware import keyboard

        self.kb = keyboard.Keyboard()
        self.escape_key = escape_key
        register_resource("keyboard", self.kb)

    def wait_for_key(self, target_keys, timeout: Optional[float] = None, exit_on_esc: bool = True) -> Optional[str]:
        if isinstance(target_keys, str):
            target_keys = [target_keys]
        listen_keys = list(target_keys)
        if exit_on_esc and self.escape_key not in listen_keys:
            listen_keys.append(self.escape_key)

        self.kb.clearEvents()
        start = time.perf_counter()
        while True:
            keys = self.kb.getKeys(listen_keys, waitRelease=False, clear=True)
            for key in keys:
                if exit_on_esc and key.name == self.escape_key:
                    print("\n>>> 实验被用户终止 (ESC) <<<")
                    raise SystemExit(0)
                if key.name in target_keys:
                    return key.name
            if timeout is not None and (time.perf_counter() - start) > timeout:
                return None
            time.sleep(0.005)

    def wait_for_space(self, timeout: Optional[float] = None) -> Optional[str]:
        return self.wait_for_key("space", timeout=timeout)

    def clear(self) -> None:
        self.kb.clearEvents()



def create_window(cfg):
    from psychopy import visual

    win = visual.Window(
        size=(cfg.screen_width, cfg.screen_height),
        screen=cfg.screen_id,
        fullscr=cfg.full_screen,
        color=cfg.background_color,
        units="height",
        allowGUI=False,
    )
    register_resource("window", win)
    return win


def draw_text(win, text: str, font_size: int = 42, color=(1.0, 1.0, 1.0), pos=(0, 0), wrap_width: float = 1.6, bold: bool = False):
    from psychopy import visual

    stim = visual.TextStim(
        win,
        text=text,
        font="Microsoft YaHei",
        pos=pos,
        height=font_size / win.size[1],
        color=color,
        wrapWidth=wrap_width,
        bold=bold,
        languageStyle="LTR",
    )
    stim.draw()



def show_message(win, text: str, font_size: int = 42, color=(1.0, 1.0, 1.0)) -> None:
    draw_text(win, text, font_size=font_size, color=color)
    win.flip()



def show_message_and_wait(win, kb: KeyboardManager, text: str, font_size: int = 42, wait_keys="space") -> str:
    show_message(win, text, font_size=font_size)
    return kb.wait_for_key(wait_keys)



def draw_fixation(win, size: float = 0.03, color=(0.55, 0.55, 0.55), line_width: float = 3.0) -> None:
    from psychopy import visual

    visual.Line(win, start=(-size, 0), end=(size, 0), lineColor=color, lineWidth=line_width).draw()
    visual.Line(win, start=(0, -size), end=(0, size), lineColor=color, lineWidth=line_width).draw()



def save_data(cfg, session_data: dict, suffix: str = "offline_mi") -> str:
    os.makedirs(cfg.data_dir, exist_ok=True)
    filepath = os.path.join(cfg.data_dir, cfg.make_filename(suffix) + ".npz")

    config_dict = asdict(cfg) if is_dataclass(cfg) else dict(cfg)
    save_dict = {"config_json": json.dumps(config_dict, ensure_ascii=False)}

    for key, value in session_data.items():
        if isinstance(value, list):
            save_dict[key] = np.array(value, dtype=object)
        else:
            save_dict[key] = value

    np.savez_compressed(filepath, **save_dict)
    print(f"[保存] 数据已保存至: {filepath}")
    return filepath



def cleanup_all() -> None:
    kb = _global_resources.get("keyboard")
    if kb is not None:
        try:
            kb.clearEvents()
        except Exception:
            pass
        _global_resources["keyboard"] = None

    serial_port = _global_resources.get("serial_port")
    if serial_port is not None:
        try:
            if serial_port.is_open:
                serial_port.close()
                print("[清理] 串口已释放。")
        except Exception:
            pass
        _global_resources["serial_port"] = None

    win = _global_resources.get("window")
    if win is not None:
        try:
            win.close()
            print("[清理] 窗口已关闭。")
        except Exception:
            pass
        _global_resources["window"] = None


atexit.register(cleanup_all)
