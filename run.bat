@echo off
REM ============================================================================
REM Kromi Cabinet Planner - Windows launcher
REM
REM Double-click this file to start the application. On first launch the script
REM installs the Python dependencies listed in requirements.txt; on every
REM subsequent launch it skips straight to starting the app.
REM
REM Prerequisite: Python 3.10 or later, with "Add Python to PATH" enabled
REM during installation. Get Python at https://www.python.org/downloads/
REM ============================================================================

setlocal
cd /d "%~dp0"

REM --- 1. Confirm Python is available --------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python was not found on PATH.
    echo.
    echo Install Python 3.10 or later from https://www.python.org/downloads/
    echo During installation, tick "Add Python to PATH".
    echo Then double-click this file again.
    echo.
    pause
    exit /b 1
)

REM --- 2. Install or update dependencies when requirements.txt changed ----
REM tools\ensure_deps.py installs on first run, reinstalls whenever this
REM version's requirements.txt differs from the last successful install, and
REM never blocks a working installation if an update fails.
python tools\ensure_deps.py
if errorlevel 1 (
    echo.
    echo Dependency installation failed. See the messages above for the cause.
    echo.
    pause
    exit /b 1
)

REM --- 3. Notify if .env is missing (non-blocking) -------------------------
if not exist ".env" (
    echo.
    echo Note: no .env file found in the package root.
    echo The app will start, but AI classification fallback will be disabled.
    echo To enable it, copy .env.example to .env and fill in OPENAI_API_KEY.
    echo.
)

REM --- 4. Launch the app ---------------------------------------------------
echo Starting Kromi Cabinet Planner. The app will open in your default browser.
echo Close this window to stop the app.
echo.
python -m streamlit run Home.py

REM Keep the window open if Streamlit exits with an error
if errorlevel 1 pause
endlocal
