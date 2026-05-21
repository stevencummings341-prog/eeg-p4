@echo off
chcp 65001 >nul
cd /d "%~dp0\video_action_tool"

python -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Local venv created at video_action_tool\.venv
pause
