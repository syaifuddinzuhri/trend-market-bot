@echo off
echo ============================================================
echo  TrendBot - Backtest
echo  Pastikan MT5 sudah dibuka dan login
echo ============================================================
call venv\Scripts\activate.bat
set /p FROM="Start date (YYYY-MM-DD) [2024-01-01]: "
if "%FROM%"=="" set FROM=2024-01-01
set /p TO="End date   (YYYY-MM-DD) [2024-12-31]: "
if "%TO%"=="" set TO=2024-12-31
python backtest/run_backtest.py --from %FROM% --to %TO%
echo.
echo Membuka report di browser...
start "" "logs\backtest_report.html"
pause
