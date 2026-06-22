@echo off
echo ============================================================
echo  TrendBot Scalper Trend - Starting...
echo  Mode: Oscillation M15 + S^&D Zone Filter
echo ============================================================

call venv\Scripts\activate.bat
python scalper_trend.py

echo.
echo Scalper Trend exited. Press any key to close.
pause
