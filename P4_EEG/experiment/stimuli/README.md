# 情绪刺激视频素材目录

供 Session 4 情绪识别方案 (`scheme="emotion"`) 使用。所有视频必须放进
`negative/` / `neutral/` / `positive/` 三个子目录之一；不再支持直接把视频
平放在本目录根（旧的 `negativeN.mp4` / `positiveN.mp4` 已弃用）。

## 目录结构

```text
stimuli/
├── stimuli_config.json   # 三类视频候选清单（运行时被 session4_emotion.py 读取）
├── README.md
├── negative/             # 负性情绪视频（悲伤、愤怒、恐惧…）
├── neutral/              # 中性情绪视频（无明显情绪倾向）
└── positive/             # 正性情绪视频（高兴、愉悦、兴奋…）
```

## Marker 映射

|  类别       | 文件夹      | Trigger Marker | 在代码中的常量名         |
|:------------|:------------|:---------------|:-------------------------|
| 负性         | `negative/` | 101            | `S4_EMOTION_NEGATIVE`    |
| 中性         | `neutral/`  | 102            | `S4_EMOTION_NEUTRAL`     |
| 正性         | `positive/` | 103            | `S4_EMOTION_POSITIVE`    |

每个 trial 实际还会发送 `S4_EMOTION_BASELINE=105`（视频开始前的注视十字）
和 `S4_EMOTION_REST=106`（视频结束后的休息）；整个 Session 头尾发送
`S4_EMOTION_START=100` / `S4_EMOTION_END=104`。这些数值在
`experiment/config.py:MARKER_TABLE` 与 `processing/pipeline/constants.py:MARKERS`
里保持同步。

## 视频要求

- 格式：MP4（推荐，已验证可播放），AVI / MOV 也可
- 分辨率：建议 1280×720 或 1920×1080；过大或过小都会被代码按比例缩放（保持原宽高比）
- 时长：建议 4–10 秒；EEG 分析窗口默认取 (0.5 ~ 5.5 s) 后才稳定
- 音频：建议包含音频轨（增强情绪诱发效果）

## `stimuli_config.json` 是怎么用的

```json
{
  "categories": {
    "negative": {
      "label": "负性",
      "marker": 101,
      "videos": [ "negative/A.mp4", "negative/B.mp4", "..." ]
    },
    ...
  },
  "trial_settings": {
    "trials_per_category": 6,
    "pre_stimulus_fixation_s": 2.0,
    "post_stimulus_rest_s": 2.0,
    "randomize_order": true
  }
}
```

运行时 `session4_emotion.py` 会：

1. 按 `videos` 列表的顺序，从前往后挑选实际存在于磁盘上的文件
2. 凑够 `trials_per_category`（默认 6；`--quick-test` 模式下变成 2）就停
3. 如果某个文件缺失，会打印 `[!] 视频缺失，跳过: ...` 并自动用列表后面的候补
4. 在三个类别之间交错调度，按 `emotion_random_seed` 做类内随机化

因此你可以在 `videos` 列表里多放几个候选当 backup，不会被一次性全用掉。

## 注意事项

1. 每类至少要 6 个真实存在的视频文件，否则会得到少于 18 个 trial
2. 视频文件名必须与 `stimuli_config.json` 里的相对路径**一字不差**
3. 视频文件本身**不入 git**（已在根 `.gitignore` 里排除 `*.mp4`）；该目录通过 `experiment/data/` 同级的方式手动维护
4. 想换某段视频？把新文件放进对应子目录 → 在 json 的 `videos` 列表里加 / 改一行 → 重启 launcher 即可，**不需要改任何 Python 代码**
