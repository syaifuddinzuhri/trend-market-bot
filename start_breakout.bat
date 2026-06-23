@echo off
echo ============================================================
echo  TrendBot Breakout Scanner
echo  Strategi: Compression (Triangle/Wedge/Range) + Breakout
echo ============================================================
echo.
echo  Pola yang dideteksi:
echo    - Descending Triangle: resistance turun, support flat
echo    - Ascending Triangle : support naik, resistance flat
echo    - Wedge              : resistance turun + support naik
echo    - Range              : harga sideways dalam range sempit
echo.
echo  Signal dikirim saat:
echo    - Candle CLOSE di atas resistance  -> BUY
echo    - Candle CLOSE di bawah support    -> SELL
echo    - Body candle minimal 45%% range
echo    - ADX mulai bergerak (>= 18)
echo ============================================================
echo.

call venv\Scripts\activate.bat
python breakout_scanner.py

echo.
echo Breakout Scanner exited. Press any key to close.
pause
