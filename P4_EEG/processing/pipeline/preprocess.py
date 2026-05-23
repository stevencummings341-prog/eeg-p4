"""通用预处理：高通 / 低通 / 工频陷波 / montage / 重参考。

这里**不做** ICA / 自动伪迹剔除 —— 那会模糊「降噪模型该干什么」的研究问题。
本 pipeline 的定位是「给降噪模型 + 任务特征计算提供一份可复现的 baseline」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

import numpy as np

from . import constants as C


@dataclass
class PreprocConfig:
    hp_hz: Optional[float] = C.HP_FILTER_HZ
    lp_hz: Optional[float] = C.LP_FILTER_HZ
    notch_hz: Optional[Iterable[float]] = field(default_factory=lambda: list(C.NOTCH_FREQS))
    reference: Optional[str] = C.REFERENCE   # "average" / "mastoids" / None
    montage: Optional[str] = C.MONTAGE
    drop_bads: bool = True


def apply_preprocessing(raw, cfg: PreprocConfig = PreprocConfig()):
    """原地修改 raw（先 load_data()），返回同一个对象。

    会跳过任何已经被设为 None 的步骤；MNE 警告全部按 ERROR 级别静默。
    """
    import mne
    raw.load_data()

    if cfg.montage:
        try:
            montage = mne.channels.make_standard_montage(cfg.montage)
            raw.set_montage(montage, match_case=False, on_missing="warn")
        except Exception as e:
            print(f"⚠ [preproc] set_montage({cfg.montage}) 失败: {e}")

    if cfg.notch_hz:
        try:
            raw.notch_filter(
                freqs=list(cfg.notch_hz),
                picks="eeg",
                verbose="ERROR",
            )
        except Exception as e:
            print(f"⚠ [preproc] notch_filter({list(cfg.notch_hz)}) 失败: {e}")

    if cfg.hp_hz or cfg.lp_hz:
        raw.filter(
            l_freq=cfg.hp_hz,
            h_freq=cfg.lp_hz,
            picks="eeg",
            method="fir",
            phase="zero",
            verbose="ERROR",
        )

    if cfg.reference == "average":
        raw.set_eeg_reference("average", projection=False, verbose="ERROR")
    elif cfg.reference == "mastoids":
        mastoids = [ch for ch in ("M1", "M2", "TP9", "TP10") if ch in raw.ch_names]
        if mastoids:
            raw.set_eeg_reference(mastoids, projection=False, verbose="ERROR")
        else:
            print("⚠ [preproc] 找不到 mastoid 通道，回退到 average 参考")
            raw.set_eeg_reference("average", projection=False, verbose="ERROR")

    if cfg.drop_bads and raw.info.get("bads"):
        raw.drop_channels(raw.info["bads"])

    return raw


def get_eeg_picks(raw) -> List[int]:
    import mne
    return mne.pick_types(raw.info, eeg=True, exclude="bads")
