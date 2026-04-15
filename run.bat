@echo off
REM BACnet Bounty simulator — portable runner for Windows.
REM Creates a local venv on first run, installs dependencies, then launches
REM the simulator. Re-running is idempotent — venv is reused if it exists.
REM
REM Press Ctrl+C in this window to stop the simulator cleanly. All 28 BACnet
REM devices will disconnect and release their IPs before the process exits.
REM
REM Prerequisites (see README.md for full setup):
REM   1. Python 3.12 or later on PATH
REM   2. Loopback adapter with IPs 192.168.100.200-228 assigned
REM      (use scripts/add_loopback_ips.bat as reference — but note that
REM      script ships separately for dev; co-worker reads netsh block in README)

setlocal

REM Ensure console prints non-ASCII cleanly (em-dashes in banner, etc.)
set PYTHONIOENCODING=utf-8:replace

REM Locate Python — prefer "py" launcher, fall back to "python"
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PY=py
) else (
    where python >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Python not found on PATH.
        echo Install Python 3.12 from https://www.python.org/downloads/ then re-run.
        pause
        exit /b 1
    )
    set PY=python
)

REM Create venv if missing
if not exist .venv\Scripts\python.exe (
    echo Creating local virtual environment ^(.venv^)...
    %PY% -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo ERROR: venv creation failed.
        pause
        exit /b 1
    )
    echo Installing dependencies...
    .venv\Scripts\python.exe -m pip install --upgrade pip >nul
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo ERROR: dependency install failed.
        pause
        exit /b 1
    )
    echo Setup complete.
    echo.
)

REM Launch simulator. Keeps running until Ctrl+C.
.venv\Scripts\python.exe -m simulator

REM On exit (clean or error), keep window open so user can review output.
echo.
echo Simulator stopped. Press any key to close this window.
pause >nul
endlocal
