@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo ============================================================
    echo ERROR: Python not found.
    echo Please install Python from: https://www.python.org/downloads/
    echo During installation, check the box "Add Python to PATH".
    echo ============================================================
    pause
    exit /b 1
)

python launcher.py
pause
