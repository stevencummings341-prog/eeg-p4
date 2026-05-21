"""
P8 离线双手运动想象实验启动入口。
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ExperimentLauncher, config_from_args


def main() -> int:
    try:
        if len(sys.argv) > 1:
            cfg = config_from_args()
            sys.argv = [sys.argv[0]]
        else:
            launcher = ExperimentLauncher()
            cfg = launcher.run()
            if cfg is None:
                print("实验被用户取消。")
                return 0

        from session4a_mi import run_session4a

        print("\n" + "=" * 60)
        print("  P8 离线双手运动想象采集")
        print(f"  被试: {cfg.subject_id}")
        print(f"  串口: {'无硬件' if cfg.no_hardware else cfg.port_name}")
        print(f"  数据目录: {cfg.data_dir}")
        print(f"  正式采集: 每类 {cfg.formal_trials_per_class} trials / {cfg.formal_blocks} blocks")
        print("=" * 60 + "\n")

        saved_path = run_session4a(cfg)
        if saved_path:
            print(f"\n采集完成，数据保存在: {saved_path}")
        return 0

    except SystemExit:
        return 0
    except KeyboardInterrupt:
        print("\n\n>>> 实验被用户中断 (Ctrl+C) <<<")
        return 1
    except Exception as exc:
        print(f"\n启动器异常: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
