@echo off
chcp 65001 >nul
cd /d "%~dp0"

set /p VIDEO_PATH=Drag or type video path here, then press Enter: 

conda run -n eeg-p4 python -m analysis.run_analysis --video "%VIDEO_PATH%" --duration 60 --save-preview

echo.
echo Done. Press any key to close.
pause >nul
