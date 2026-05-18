import sys
import traceback

from config import ExperimentLauncher, config_from_args
from launcher import run_full_experiment, run_session_safe, cleanup_all
from video.camera_recorder_controlled import FFmpegCameraRecorder


def load_config():
    if len(sys.argv) > 1:
        cfg = config_from_args()
    else:
        launcher = ExperimentLauncher()
        cfg = launcher.run()
        if cfg is None:
            print("实验被用户取消。")
            raise SystemExit(0)
    return cfg


def main():
    recorder = FFmpegCameraRecorder()
    camera_started = False

    try:
        cfg = load_config()

        print("\n" + "=" * 60)
        print("  EEG Launcher")
        print(f"  模式: {'全流程 Session 1 → 2 → 3 → 4' if cfg.session == 'all' else f'单独 Session {cfg.session}'}")
        print(f"  被试: {cfg.subject_id}")
        print(f"  串口: {'无硬件' if cfg.no_hardware else cfg.port_name}")
        print(f"  屏幕: {cfg.screen_id}")
        print("  相机: 自动录制")
        print("=" * 60 + "\n")

        print("[Camera] 正在启动相机录制...")
        video_path, timestamp_path, metadata_path = recorder.start()
        camera_started = True
        print(f"[Camera] 已开始录制: {video_path}")

        if cfg.session == "all":
            print("[EEG Launcher] 开始全流程 Session 1 → 2 → 3 → 4")
            run_full_experiment(cfg)
        else:
            print(f"[EEG Launcher] 开始单独 Session {cfg.session}")
            run_session_safe(cfg, cfg.session)

    except SystemExit:
        pass
    except KeyboardInterrupt:
        print("\n\n>>> 实验被用户中断 (Ctrl+C) <<<")
    except Exception as e:
        print(f"\n❌ EEG Launcher 异常: {e}")
        traceback.print_exc()
    finally:
        if camera_started:
            try:
                print("\n[Camera] 正在停止相机录制...")
                result = recorder.stop()
                print("[Camera] 录制已停止。")
                print(f"[Camera] 视频: {result['video_path']}")
                print(f"[Camera] 时间戳: {result['timestamp_path']}")
                print(f"[Camera] Metadata: {result['metadata_path']}")
            except Exception as camera_error:
                print(f"⚠️ [Camera] 停止录制失败: {camera_error}")
        cleanup_all()
        print("\nEEG Launcher 已退出。")


if __name__ == "__main__":
    main()
