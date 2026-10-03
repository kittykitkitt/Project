@echo off
REM Flood Ready Vehicle System - Windows 10 / 11 setup script
REM Creates a virtual environment, installs the runtime requirements and
REM starts the application. No administrator rights are required.

setlocal
cd /d "%~dp0"

echo ============================================================
echo  Flood Ready Vehicle System - setup
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on this computer.
    echo Install Python 3.11 or newer from https://www.python.org/downloads/
    echo and make sure "Add python.exe to PATH" is ticked during setup.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo The virtual environment could not be created.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing runtime requirements...
python -m pip install -r requirements.txt

echo.
echo Starting Flood Ready Vehicle System...
python main.py

endlocal
pause
