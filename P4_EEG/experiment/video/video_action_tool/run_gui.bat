@echo off
chcp 65001 >nul
cd /d "%~dp0"

where conda >nul 2>nul
if %errorlevel%==0 (
    conda run -n eeg-p4 python -m analysis.gui
) else (
    if exist ".venv\Scripts\python.exe" (
        ".venv\Scripts\python.exe" -m analysis.gui
    ) else (
        python -m analysis.gui
    )
)

if errorlevel 1 (
    echo.
    echo GUI exited with an error. Press any key to close.
    pause >nul
)
