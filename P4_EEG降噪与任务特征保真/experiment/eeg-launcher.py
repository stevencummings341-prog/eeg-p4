import sys

from launcher import main


if __name__ == "__main__":
    print("[EEG Launcher] 相机录制已并入 launcher.py，建议直接使用 python launcher.py")
    raise SystemExit(main())
