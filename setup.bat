@echo off
echo ============================================================
echo  TrendBot - Setup (Windows)
echo ============================================================

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from python.org
    pause
    exit /b 1
)

echo Creating virtual environment...
python -m venv venv

echo Activating venv...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo ============================================================
echo  Setup complete!
echo  1. Edit .env with your MT5 account and Telegram details
echo  2. Make sure MT5 is open and logged in with the same account
echo  3. Run: start_bot.bat
echo ============================================================
pause
