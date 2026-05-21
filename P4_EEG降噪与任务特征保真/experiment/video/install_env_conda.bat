@echo off
chcp 65001 >nul
cd /d "%~dp0"

where conda >nul 2>nul
if errorlevel 1 (
    echo [ERROR] conda not found. Please install Anaconda or Miniconda first.
    pause
    exit /b 1
)

conda env create -f video_action_tool\environment.yml

echo.
echo If the environment already existed, run:
echo conda env update -n eeg-p4 -f video_action_tool\environment.yml
echo.
pause
