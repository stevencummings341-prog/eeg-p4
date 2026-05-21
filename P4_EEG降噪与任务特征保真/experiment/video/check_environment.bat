@echo off
chcp 65001 >nul
cd /d "%~dp0\video_action_tool"

where conda >nul 2>nul
if %errorlevel%==0 (
    conda run -n eeg-p4 python check_environment.py
) else (
    if exist ".venv\Scripts\python.exe" (
        ".venv\Scripts\python.exe" check_environment.py
    ) else (
        python check_environment.py
    )
)

echo.
pause
