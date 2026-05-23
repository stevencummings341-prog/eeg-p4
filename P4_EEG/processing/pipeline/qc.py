"""QC 报告：把每个被试每个 Session 的关键图/数字整合成一份 HTML。

设计哲学：HTML 自包含（图片用 base64 内嵌），方便把单个文件丢到
Obsidian / IM 群 / 邮件里都能直接看。不依赖 jinja2，纯字符串拼接
（脚本式实验代码的优先级是「可读 + 不报错」）。
"""

from __future__ import annotations

import base64
import datetime as dt
import io
from pathlib import Path
from typing import Dict, List, Optional


# --------------------------------------------------------------------------- #
# Figure → base64 png
# --------------------------------------------------------------------------- #
def fig_to_b64(fig) -> str:
    if fig is None:
        return ""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _kv_table(d: Dict, indent: int = 0) -> str:
    rows = []
    pad = "&nbsp;" * (indent * 4)
    for k, v in d.items():
        if isinstance(v, dict):
            rows.append(f'<tr><td>{pad}<b>{k}</b></td><td></td></tr>')
            rows.append(f'<tr><td colspan="2">{_kv_table(v, indent + 1)}</td></tr>')
        elif isinstance(v, list) and v and not isinstance(v[0], (int, float, str)):
            rows.append(f'<tr><td>{pad}{k}</td><td>[list len={len(v)}]</td></tr>')
        else:
            rows.append(f'<tr><td>{pad}{k}</td><td><code>{_fmt(v)}</code></td></tr>')
    return f'<table class="kv">{"".join(rows)}</table>'


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (list, tuple)):
        if len(v) > 8:
            return f"[{', '.join(_fmt(x) for x in v[:5])}, ..., len={len(v)}]"
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def _section(title: str, body: str, anchor: Optional[str] = None) -> str:
    a = f' id="{anchor}"' if anchor else ""
    return f'<section{a}><h2>{title}</h2>{body}</section>\n'


# --------------------------------------------------------------------------- #
# 单个 sub-session 的 HTML 片段
# --------------------------------------------------------------------------- #
def render_session_block(session_kind: str, feature_dict: Dict,
                         figures: List[tuple]) -> str:
    """figures: [(caption, b64_png), ...]"""
    blocks = []
    blocks.append(_kv_table(feature_dict))
    for caption, b64 in figures:
        if not b64:
            continue
        blocks.append(
            f'<figure><img src="data:image/png;base64,{b64}"/>'
            f'<figcaption>{caption}</figcaption></figure>'
        )
    return "".join(blocks)


# --------------------------------------------------------------------------- #
# 整份报告
# --------------------------------------------------------------------------- #
_HTML_HEADER = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>P4 EEG QC Report — __SUBJECT__</title>
<style>
  body { font-family: -apple-system, "Microsoft YaHei", Arial, sans-serif;
         max-width: 1100px; margin: 1.5em auto; padding: 0 1em;
         color: #222; line-height: 1.55; }
  h1 { color: #2c3e50; border-bottom: 3px solid #2c3e50; padding-bottom: .3em; }
  h2 { color: #1f77b4; margin-top: 1.6em; border-left: 4px solid #1f77b4; padding-left: .6em; }
  h3 { color: #444; }
  section { background: #fafafa; border: 1px solid #e1e1e1; border-radius: 6px;
            padding: 1em 1.4em; margin-bottom: 1.2em; }
  .meta { background: #eef6ff; padding: .6em 1em; border-radius: 6px; }
  table.kv { border-collapse: collapse; width: 100%; margin-bottom: 1em; }
  table.kv td { padding: 4px 8px; border-bottom: 1px solid #eee; font-size: 0.92em; }
  table.kv td:first-child { width: 38%; color: #555; }
  code { background: #f4f4f4; padding: 0 4px; border-radius: 3px; }
  figure { margin: 1em 0; text-align: center; }
  figure img { max-width: 100%; border: 1px solid #ddd; }
  figcaption { font-size: .9em; color: #666; margin-top: 4px; }
  .nav { background: #fff; padding: .6em 1em; border: 1px solid #ddd; border-radius: 6px; }
  .nav a { margin-right: 1em; }
  .warn { color: #c0392b; }
</style>
</head>
<body>
"""


def write_report(out_path, subject_id: str, sections: List[Dict]) -> Path:
    """sections: [{kind, html, anchor}]"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nav_links = " ".join(
        f'<a href="#{s["anchor"]}">{s["kind"]}</a>' for s in sections
    )
    html = _HTML_HEADER.replace("__SUBJECT__", subject_id)
    html += f"<h1>P4 EEG QC Report</h1>"
    html += (
        f'<div class="meta">'
        f'<b>被试</b>: {subject_id} &nbsp;|&nbsp;'
        f'<b>生成时间</b>: {dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} &nbsp;|&nbsp;'
        f'<b>章节数</b>: {len(sections)}'
        f"</div>"
    )
    html += f'<div class="nav">{nav_links}</div>'
    for s in sections:
        html += _section(s["kind"], s["html"], anchor=s["anchor"])
    html += "</body></html>"
    out_path.write_text(html, encoding="utf-8")
    return out_path
