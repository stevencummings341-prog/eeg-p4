#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path


def norm(value):
    if not value:
        return ""
    return str(value).replace("\\", "/")


def is_data_path(path):
    p = norm(path).strip().strip('"\'')
    if not p:
        return False
    parts = [part.lower() for part in Path(p).parts]
    slash = p.lower()
    return "data" in parts or "/data/" in slash or slash.endswith("/data")


def blocks_bash(command):
    cmd = norm(command).lower()
    if not cmd:
        return False
    mentions_data = re.search(r"(^|[\s'\"./\\])data([\s'\"/\\]|$)", cmd) or "/data/" in cmd or "\\data\\" in cmd
    if not mentions_data:
        return False
    modifying_patterns = [
        r"\brm\b", r"\bmv\b", r"\bcp\b", r"\bmkdir\b", r"\btouch\b", r"\bpython\b.*open\(",
        r">", r"\btee\b", r"\bgit\s+add\b", r"\bgit\s+rm\b", r"\bgit\s+clean\b",
        r"\bdel\b", r"\berase\b", r"\bmove\b", r"\bcopy\b", r"\bremove-item\b",
    ]
    return any(re.search(pattern, cmd) for pattern in modifying_patterns)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool in {"Write", "Edit"}:
        if is_data_path(tool_input.get("file_path")):
            deny("项目规则禁止 Claude 修改 data 目录或任何 **/data/** 下的文件。")
            return

    if tool == "NotebookEdit":
        if is_data_path(tool_input.get("notebook_path")):
            deny("项目规则禁止 Claude 修改 data 目录或任何 **/data/** 下的 notebook。")
            return

    if tool == "Bash":
        if blocks_bash(tool_input.get("command", "")):
            deny("项目规则禁止通过 Bash 对 data 目录执行写入、移动、删除、git add 等修改性操作。")
            return


if __name__ == "__main__":
    main()
