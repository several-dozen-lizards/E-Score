@echo off
REM === convo_metrics_launcher.bat ===
REM Launches the GUI (gui_convo_metrics.py) for Convo Metrics Analyzer
REM Ensure Python, pandas, and openpyxl are installed.

cd /d "%~dp0"

REM Optional: create virtual env activation if desired
REM call venv\Scripts\activate

REM Check Python installation
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python not found. Please install Python 3.9+ and ensure it's in PATH.
    pause
    exit /b 1
)

echo Launching Convo Metrics GUI...
python gui_convo_metrics.py

if %errorlevel% neq 0 (
    echo.
    echo [!] The program exited with an error code %errorlevel%.
    echo Check for missing dependencies (pip install pandas openpyxl tkinterdnd2).
)

echo.
echo Done.
pause
