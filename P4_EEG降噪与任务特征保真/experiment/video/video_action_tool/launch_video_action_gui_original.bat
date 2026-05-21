@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "P4_PYTHON=D:\conda\envs\eeg-p4\python.exe"

if exist "%P4_PYTHON%" (
    "%P4_PYTHON%" -m analysis.gui
) else (
    echo [WARN] Cannot find %P4_PYTHON%
    echo [WARN] Falling back to python from PATH.
    python -m analysis.gui
)

if errorlevel 1 (
    echo.
    echo GUI exited with an error. Press any key to close this window.
    pause >nul
)
