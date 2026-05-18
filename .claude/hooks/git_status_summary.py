#!/usr/bin/env python3
import json
import subprocess


def run(args):
    completed = subprocess.run(args, capture_output=True, text=True, timeout=10)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def main():
    code, out, err = run(["git", "status", "--short"])
    if code != 0:
        message = f"Git 状态检查失败：{err or out}"
    elif out:
        message = "版本管理提醒：当前仍有未提交变更。请审阅 git diff；需要提交时明确告诉 Claude commit。\\n" + out
    else:
        message = "版本管理提醒：工作区干净，没有未提交变更。"

    print(json.dumps({"systemMessage": message}))


if __name__ == "__main__":
    main()
