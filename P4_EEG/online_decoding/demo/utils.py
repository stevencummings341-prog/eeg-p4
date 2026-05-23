"""
utils.py — 环形缓冲 + 信号处理工具
"""

import numpy as np
from scipy.signal import welch


class RingBuffer:
    """高效的环形缓冲：写入新数据（无 np.roll） + 按需取最新窗口"""

    def __init__(self, n_channels: int, capacity: int):
        self._buf = np.zeros((n_channels, capacity), dtype=np.float64)
        self.capacity = capacity
        self._pos = 0          # 下一个写入位置
        self._total = 0        # 累计写入样本数

    @property
    def total_samples(self) -> int:
        return self._total

    def push(self, data: np.ndarray):
        """data: (n_channels, n_samples)，不足 capacity 的通道自动截断"""
        n_ch = min(data.shape[0], self._buf.shape[0])
        n_new = data.shape[1]

        if n_new >= self.capacity:
            self._buf[:n_ch] = data[:n_ch, -self.capacity:]
            self._pos = 0
        else:
            end = self._pos + n_new
            if end <= self.capacity:
                self._buf[:n_ch, self._pos:end] = data[:n_ch]
            else:
                part1 = self.capacity - self._pos
                self._buf[:n_ch, self._pos:] = data[:n_ch, :part1]
                self._buf[:n_ch, :end - self.capacity] = data[:n_ch, part1:]
            self._pos = end % self.capacity

        self._total += n_new

    def get_recent(self, n: int | None = None) -> np.ndarray:
        """取最近 n 个样本（连续内存），n=None 返回全部"""
        if n is None:
            n = min(self._total, self.capacity)
        else:
            n = min(n, self._total, self.capacity)

        if self._total <= self.capacity:
            # 尚未绕回
            start = max(0, self._pos - n)
            return self._buf[:, start:self._pos].copy()

        # 已绕回
        if n <= self._pos:
            return self._buf[:, self._pos - n:self._pos].copy()

        # 跨绕回边界 → 拼接
        tail = self._buf[:, self._pos - n:]   # 负数索引从末尾取
        head = self._buf[:, :self._pos]
        return np.hstack([tail, head])


# ============================================================
# 频域分析
# ============================================================

def band_power(data: np.ndarray, fs: float, fmin: float = 8, fmax: float = 30) -> float:
    """Welch PSD → 指定频段积分功率"""
    nperseg = min(len(data), int(fs))
    if nperseg < 8:
        return 0.0
    f, pxx = welch(data, fs=fs, nperseg=nperseg)
    mask = (f >= fmin) & (f <= fmax)
    return float(np.trapz(pxx[mask], f[mask]))


def spectral_alpha_beta_ratio(data: np.ndarray, fs: float) -> dict:
    """一次性返回 alpha(8-13Hz) 和 beta(13-30Hz) 功率及比值"""
    nperseg = min(len(data), int(fs))
    if nperseg < 8:
        return {"alpha": 0.0, "beta": 0.0, "ratio": 0.0}
    f, pxx = welch(data, fs=fs, nperseg=nperseg)
    a = float(np.trapz(pxx[(f >= 8) & (f <= 13)], f[(f >= 8) & (f <= 13)]))
    b = float(np.trapz(pxx[(f >= 13) & (f <= 30)], f[(f >= 13) & (f <= 30)]))
    return {"alpha": a, "beta": b, "ratio": a / (b + 1e-9)}


# ============================================================
# AAD 决策（保留兼容）
# ============================================================

def decide_target_speaker(power_left: float, power_right: float):
    """T7 > T8 → Speaker A (1.0); 否则 → Speaker B (0.0)"""
    if power_left > power_right:
        return "A", 1.0
    return "B", 0.0
