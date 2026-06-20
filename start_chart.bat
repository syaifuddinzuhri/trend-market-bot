@echo off
echo ============================================================
echo  TrendBot - Chart Generator
echo  Pastikan MT5 sudah dibuka dan login
echo ============================================================
call venv\Scripts\activate.bat

echo.
echo Pilih timeframe:
echo   1. M15 (default)
echo   2. H1
echo   3. H4
echo   4. D1
echo.
set /p TF_CHOICE="Pilihan (1-4) [1]: "
if "%TF_CHOICE%"=="2" set TF=H1
if "%TF_CHOICE%"=="3" set TF=H4
if "%TF_CHOICE%"=="4" set TF=D1
if not defined TF set TF=M15

set /p BARS="Jumlah bars [200]: "
if "%BARS%"=="" set BARS=200

echo.
echo Generating chart %TF% (%BARS% bars)...
python chart/run_chart.py --tf %TF% --bars %BARS%

echo.
pause
