"""P4 4-Session 实验脚本集合。

由 ``experiment/launcher.py`` 按 Session 号 + 实验方案 (scheme) 调度。
每个模块导出一个 ``run_*`` 函数：

- ``session1_resting.run_session1``        — S1 睁眼/闭眼静息态        (两套方案共用)
- ``session2_artifacts.run_session2``      — S2 8 类伪迹模板采集        (两套方案共用)
- ``session3_oddball.run_oddball``         — S3 视觉 Oddball (P300)     (两套方案共用)
- ``session3_ssvep.run_ssvep``             — S3 SSVEP (4 频率)          (两套方案共用)
- ``session4_mi.run_session4``             — S4 离线双手运动想象采集    (scheme="motor_imagery")
- ``session4_emotion.run_session4``        — S4 情绪识别 (音视频刺激)   (scheme="emotion")

S4 通过 ``cfg.scheme`` 切换：
    scheme="motor_imagery" → session4_mi
    scheme="emotion"        → session4_emotion

每个 Session 都通过同一份 ``config.ExperimentConfig`` 配置；Marker 编码与时长
口径以 ``config.MARKER_TABLE`` 为唯一权威来源。数据落点由 ``utils.save_data``
统一为 ``<data_dir>/<scheme>/eeg-npz/P4_S{n}_{subject}_{ts}_{suffix}.npz``。
"""
