@echo off
echo ============================================================
echo  TrendBot - Dashboard (http://localhost:5000)
echo ============================================================
call venv\Scripts\activate.bat
start "" "http://localhost:5000"
python dashboard/app.py
pause
