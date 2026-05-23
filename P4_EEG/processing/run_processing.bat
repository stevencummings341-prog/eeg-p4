@echo off
REM ===========================================================
REM  P4 EEG processing pipeline - one-click GUI launcher
REM
REM  Double-click this file to open the launcher. It will:
REM    1. activate the eeg-p4 conda env (or fall back to a python on PATH)
REM    2. open a Tkinter GUI to pick scheme / subject / date
REM    3. run pipeline.run_pipeline with the chosen options
REM
REM  This .bat is intentionally ASCII so it works on Chinese-Windows
REM  even without a UTF-8 BOM. Chinese strings live in the python GUI.
REM ===========================================================

setlocal

REM Move to the processing/ directory (where this .bat lives)
cd /d "%~dp0"

REM Make sure Python prints UTF-8 (Chinese log lines)
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

REM ---------- pick interpreter ----------
set "PY_EXE="

REM 1) prefer the eeg-p4 conda env
for %%P in (
    "%USERPROFILE%\miniconda3\envs\eeg-p4\python.exe"
    "%USERPROFILE%\anaconda3\envs\eeg-p4\python.exe"
    "C:\ProgramData\miniconda3\envs\eeg-p4\python.exe"
    "C:\ProgramData\anaconda3\envs\eeg-p4\python.exe"
) do (
    if exist %%P (
        set "PY_EXE=%%~P"
        goto :found_py
    )
)

REM 2) fall back to plain python on PATH
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY_EXE=python"
    goto :found_py
)

echo [fail] Cannot find a Python interpreter.
echo        Expected one of:
echo          %USERPROFILE%\miniconda3\envs\eeg-p4\python.exe
echo          %USERPROFILE%\anaconda3\envs\eeg-p4\python.exe
echo        Or a `python` on PATH.
echo.
echo        To create the conda env:
echo          conda env create -f environment.yml
echo          conda activate eeg-p4
pause
exit /b 1

:found_py
echo [run_processing] Using Python: %PY_EXE%
"%PY_EXE%" launch_processing.py
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
    echo.
    echo [run_processing] launcher exited with code %RC%
    pause
)

endlocal
exit /b %RC%
