@echo off
echo =============================================
echo   TrendBot Scalper  ^|  M5 Grid Entry
echo =============================================
cd /d "%~dp0"
call venv\Scripts\activate
python scalper.py
pause
