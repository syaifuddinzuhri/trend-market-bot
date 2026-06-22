//+------------------------------------------------------------------+
//| TrendBot_Dashboard.mq5                                           |
//| Panel overlay di chart — menampilkan status semua 8 filter bot   |
//| + proyeksi Entry / SL / TP1 / TP2 saat 6+ filter lolos          |
//|                                                                  |
//| Pasang di chart M15 XAUUSD.                                      |
//| Set timeframe input sesuai chart yang digunakan (M15 default).   |
//+------------------------------------------------------------------+
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots   0

input double ADX_MIN       = 25.0;
input double ADX_SKIP      = 20.0;
input double ATR_Period    = 14;
input double ATR_MA_Period = 20;
input double ATR_SL_Mult   = 1.5;   // ATR_SL_MULTIPLIER dari .env
input double TP1_R         = 1.0;   // TP1_R dari .env
input double TP2_R         = 2.0;   // TP2_R dari .env
input int    SwingLookback = 20;    // bar untuk cari swing SL
input int    PanelX        = 15;    // posisi panel dari kanan (px)
input int    PanelY        = 30;    // posisi panel dari atas (px)

// Handle indicator
int h_ema20_h1, h_ema50_h1, h_ema200_h4;
int h_adx_h1, h_atr_h1;

#define PREFIX "TBot_Dash_"

int OnInit()
{
   // EMA handles — multi-TF
   h_ema20_h1  = iMA(_Symbol, PERIOD_H1,  20,  0, MODE_EMA, PRICE_CLOSE);
   h_ema50_h1  = iMA(_Symbol, PERIOD_H1,  50,  0, MODE_EMA, PRICE_CLOSE);
   h_ema200_h4 = iMA(_Symbol, PERIOD_H4, 200, 0, MODE_EMA, PRICE_CLOSE);
   h_adx_h1   = iADX(_Symbol, PERIOD_H1, (int)ATR_Period);
   h_atr_h1   = iATR(_Symbol, PERIOD_H1, (int)ATR_Period);

   IndicatorSetString(INDICATOR_SHORTNAME, "TrendBot Dashboard");
   EventSetTimer(5); // update setiap 5 detik (sama dengan heartbeat bot)
   _UpdatePanel();
   return INIT_SUCCEEDED;
}

void OnTimer() { _UpdatePanel(); }

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{
   _UpdatePanel();
   return rates_total;
}

void _UpdatePanel()
{
   // ── 1. Session filter (WIB 13:00–01:00 = UTC 06:00–18:00) ──────
   MqlDateTime dt; TimeToStruct(TimeGMT(), dt);
   int hour_utc = dt.hour;
   bool session_ok = (hour_utc >= 6 && hour_utc < 18);

   // ── 2. H4 Trend filter ─────────────────────────────────────────
   double ema200_h4[], close_h4[];
   bool trend_bull = false, trend_bear = false;
   if (CopyBuffer(h_ema200_h4, 0, 0, 1, ema200_h4) > 0 &&
       CopyClose(_Symbol, PERIOD_H4, 0, 1, close_h4) > 0)
   {
      double c = close_h4[0];
      trend_bull = c > ema200_h4[0];
      trend_bear = c < ema200_h4[0];
   }
   bool trend_ok = trend_bull || trend_bear;
   string direction = trend_bull ? "BUY" : (trend_bear ? "SELL" : "—");

   // ── 3. ADX ─────────────────────────────────────────────────────
   double adx_buf[];
   double adx_val = 0;
   if (CopyBuffer(h_adx_h1, 0, 0, 1, adx_buf) > 0) adx_val = adx_buf[0];
   bool adx_ok = adx_val >= ADX_MIN;

   // ── 4. ATR vs ATR_MA ───────────────────────────────────────────
   double atr_raw[];
   double atr_val = 0;
   if (CopyBuffer(h_atr_h1, 0, 0, (int)ATR_MA_Period, atr_raw) > 0)
      atr_val = atr_raw[0];

   double atr_ma = 0;
   if (ArraySize(atr_raw) >= (int)ATR_MA_Period)
   {
      double s = 0;
      for (int k = 0; k < (int)ATR_MA_Period; k++) s += atr_raw[k];
      atr_ma = s / ATR_MA_Period;
   }
   bool atr_ok = atr_val > atr_ma && atr_ma > 0;

   // ── 5. Pullback ke EMA20 atau EMA50 H1 ─────────────────────────
   double ema20_h1[], ema50_h1[], close_h1[];
   bool pullback_ok = false;
   if (CopyBuffer(h_ema20_h1, 0, 0, 3, ema20_h1) > 0 &&
       CopyBuffer(h_ema50_h1, 0, 0, 3, ema50_h1) > 0 &&
       CopyClose(_Symbol, PERIOD_H1, 0, 3, close_h1) > 0)
   {
      double c0 = close_h1[0], c1 = close_h1[1];
      double e20 = ema20_h1[0], e50 = ema50_h1[0];
      if (trend_bull)
         pullback_ok = (c1 <= e20 && c0 > e20) || (c1 <= e50 && c0 > e50);
      else if (trend_bear)
         pullback_ok = (c1 >= e20 && c0 < e20) || (c1 >= e50 && c0 < e50);
   }

   // ── 6. Structure M15 (swing break) ─────────────────────────────
   double high_m15[], low_m15[], close_m15[];
   bool struct_ok = false;
   string struct_label = "—";
   int lookback = SwingLookback;
   if (CopyHigh(_Symbol, PERIOD_M15, 0, lookback, high_m15) > 0 &&
       CopyLow(_Symbol,  PERIOD_M15, 0, lookback, low_m15)  > 0 &&
       CopyClose(_Symbol,PERIOD_M15, 0, lookback, close_m15) > 0)
   {
      double swing_h = high_m15[ArrayMaximum(high_m15, 1, lookback - 1)];
      double swing_l = low_m15[ArrayMinimum(low_m15,  1, lookback - 1)];
      double last_c  = close_m15[0];

      if (trend_bull && last_c > swing_h) { struct_ok = true; struct_label = "BOS↑"; }
      else if (trend_bear && last_c < swing_l) { struct_ok = true; struct_label = "BOS↓"; }
      else if (trend_bull && last_c < swing_l) { struct_ok = true; struct_label = "CHoCH↓"; }
      else if (trend_bear && last_c > swing_h) { struct_ok = true; struct_label = "CHoCH↑"; }
      else struct_label = "WAIT";
   }

   // ── 7. Candle Pattern M15 ──────────────────────────────────────
   double o_m15[], h_m15_c[], l_m15_c[], c_m15_c[];
   bool candle_ok = false;
   string candle_label = "—";
   if (CopyOpen(_Symbol, PERIOD_M15, 0, 3, o_m15) > 0 &&
       CopyHigh(_Symbol, PERIOD_M15, 0, 3, h_m15_c) > 0 &&
       CopyLow(_Symbol,  PERIOD_M15, 0, 3, l_m15_c) > 0 &&
       CopyClose(_Symbol,PERIOD_M15, 0, 3, c_m15_c) > 0)
   {
      double o1 = o_m15[1], c1_c = c_m15_c[1], h1 = h_m15_c[1], l1 = l_m15_c[1];
      double o0 = o_m15[0], c0_c = c_m15_c[0];
      double body1 = MathAbs(c1_c - o1);
      double range1 = h1 - l1;

      // Pin Bar
      bool bull_pin = (c1_c > o1) && ((o1 - l1) >= 2 * body1) && (range1 > 0);
      bool bear_pin = (c1_c < o1) && ((h1 - o1) >= 2 * body1) && (range1 > 0);
      // Engulfing
      bool bull_eng = (c1_c > o1) && (o1 < c_m15_c[2]) && (c1_c > o_m15[2]);
      bool bear_eng = (c1_c < o1) && (o1 > c_m15_c[2]) && (c1_c < o_m15[2]);

      if (trend_bull && (bull_pin || bull_eng))
      {
         candle_ok = true;
         candle_label = bull_pin ? "PinBar↑" : "Engulf↑";
      }
      else if (trend_bear && (bear_pin || bear_eng))
      {
         candle_ok = true;
         candle_label = bear_pin ? "PinBar↓" : "Engulf↓";
      }
   }

   // ── Hitung skor ────────────────────────────────────────────────
   bool filters[8];
   filters[0] = session_ok; filters[1] = true; // news manual
   filters[2] = trend_ok;   filters[3] = adx_ok;
   filters[4] = atr_ok;     filters[5] = pullback_ok;
   filters[6] = struct_ok;  filters[7] = candle_ok;
   int passed = 0;
   for (int i = 0; i < 8; i++) if (filters[i]) passed++;
   bool all_ok = (passed == 8);

   string status_str = "";
   color  status_clr;
   if (all_ok)        { status_str = "🟢 SIAP ENTRY";           status_clr = clrLime; }
   else if (passed>=6){ status_str = "🔥 HAMPIR (" + (string)passed + "/8)"; status_clr = clrOrange; }
   else if (passed>=4){ status_str = "⏳ DEKAT ("  + (string)passed + "/8)"; status_clr = clrYellow; }
   else               { status_str = "💤 TUNGGU (" + (string)passed + "/8)"; status_clr = clrGray; }

   // ── Proyeksi Entry/SL/TP ───────────────────────────────────────
   string entry_str = "", sl_str = "", tp1_str = "", tp2_str = "";
   if (passed >= 6 && trend_ok)
   {
      MqlTick tick; SymbolInfoTick(_Symbol, tick);
      double entry = (direction == "BUY") ? tick.ask : tick.bid;

      // Swing-based SL (sama dengan bot/risk.py calc_sl)
      double sl_price = 0;
      double h1_high[], h1_low[];
      if (CopyHigh(_Symbol, PERIOD_H1, 0, SwingLookback, h1_high) > 0 &&
          CopyLow(_Symbol,  PERIOD_H1, 0, SwingLookback, h1_low)  > 0)
      {
         double atr_h1_buf[];
         double atr_h1_val = atr_val;
         double buffer = atr_h1_val * ATR_SL_Mult;
         if (direction == "BUY")
         {
            double swing = h1_low[ArrayMinimum(h1_low, 0, SwingLookback)];
            sl_price = swing - buffer;
         }
         else
         {
            double swing = h1_high[ArrayMaximum(h1_high, 0, SwingLookback)];
            sl_price = swing + buffer;
         }
         double sl_dist = MathAbs(entry - sl_price);
         double tp1 = (direction == "BUY") ? entry + sl_dist * TP1_R : entry - sl_dist * TP1_R;
         double tp2 = (direction == "BUY") ? entry + sl_dist * TP2_R : entry - sl_dist * TP2_R;

         int dig = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
         entry_str = DoubleToString(entry, dig);
         sl_str    = DoubleToString(sl_price, dig) +
                     " (" + DoubleToString(sl_price - entry, dig) + ")";
         tp1_str   = DoubleToString(tp1, dig) +
                     " (+" + DoubleToString(MathAbs(tp1 - entry), dig) + ")";
         tp2_str   = DoubleToString(tp2, dig) +
                     " (+" + DoubleToString(MathAbs(tp2 - entry), dig) + ")";
      }
   }

   // ── Render panel ───────────────────────────────────────────────
   string ok1 = session_ok ? "✓" : "✗";
   string ok2 = trend_ok   ? "✓" : "✗";
   string ok3 = adx_ok     ? "✓" : "✗";
   string ok4 = atr_ok     ? "✓" : "✗";
   string ok5 = pullback_ok? "✓" : "✗";
   string ok6 = struct_ok  ? "✓" : "✗";
   string ok7 = candle_ok  ? "✓" : "✗";

   string lines[];
   ArrayResize(lines, 14);
   lines[0]  = "━━ TrendBot Scanner ━━━━━━━━━━━━━━";
   lines[1]  = "Arah    : " + direction;
   lines[2]  = "Status  : " + status_str;
   lines[3]  = "─────────────────────────────────";
   lines[4]  = "[" + ok1 + "] Session (WIB 13:00-01:00)";
   lines[5]  = "[" + ok2 + "] Trend H4 (Close vs EMA200)  " + (trend_bull?"BULL":"BEAR");
   lines[6]  = "[" + ok3 + "] ADX H1 = " + DoubleToString(adx_val,1) + " (min " + DoubleToString(ADX_MIN,0) + ")";
   lines[7]  = "[" + ok4 + "] ATR H1 = " + DoubleToString(atr_val,2) + " | MA=" + DoubleToString(atr_ma,2);
   lines[8]  = "[" + ok5 + "] Pullback ke EMA20/50 H1";
   lines[9]  = "[" + ok6 + "] Structure M15: " + struct_label;
   lines[10] = "[" + ok7 + "] Candle M15:   " + candle_label;
   lines[11] = "─────────────────────────────────";
   if (entry_str != "")
   {
      lines[12] = "Entry  : " + entry_str;
      lines[13] = "SL     : " + sl_str;
      ArrayResize(lines, 16);
      lines[14] = "TP1    : " + tp1_str;
      lines[15] = "TP2    : " + tp2_str;
   }
   else
   {
      lines[12] = "Entry/SL/TP: —";
      lines[13] = "(butuh 6+ filter lolos)";
   }

   _RenderLines(lines, status_clr, passed);
   ChartRedraw();
}

void _RenderLines(string &lines[], color status_clr, int passed)
{
   int n = ArraySize(lines);
   for (int i = 0; i < n; i++)
   {
      string name = PREFIX + "L" + IntegerToString(i);
      if (ObjectFind(0, name) < 0)
      {
         ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
         ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_LOWER);
         ObjectSetInteger(0, name, OBJPROP_XDISTANCE, PanelX);
         ObjectSetInteger(0, name, OBJPROP_YDISTANCE, PanelY + (n - 1 - i) * 16);
         ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
         ObjectSetString(0, name, OBJPROP_FONT, "Courier New");
         ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, name, OBJPROP_BACK, false);
      }
      ObjectSetString(0, name, OBJPROP_TEXT, lines[i]);

      // Warna baris
      color clr = clrSilver;
      if (i == 2) clr = status_clr;           // baris status
      else if (StringFind(lines[i], "[✓]") >= 0) clr = clrLime;
      else if (StringFind(lines[i], "[✗]") >= 0) clr = clrOrangeRed;
      else if (i == 0 || i == 3 || i == 11)   clr = clrGray;
      else if (StringFind(lines[i], "Entry") >= 0 ||
               StringFind(lines[i], "SL") >= 0  ||
               StringFind(lines[i], "TP") >= 0)  clr = clrGold;
      ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   }

   // Hapus baris lama yang melebihi jumlah lines saat ini
   for (int i = n; i < 20; i++)
   {
      string name = PREFIX + "L" + IntegerToString(i);
      if (ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   }
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   for (int i = 0; i < 20; i++)
      ObjectDelete(0, PREFIX + "L" + IntegerToString(i));
   IndicatorRelease(h_ema20_h1);
   IndicatorRelease(h_ema50_h1);
   IndicatorRelease(h_ema200_h4);
   IndicatorRelease(h_adx_h1);
   IndicatorRelease(h_atr_h1);
   ChartRedraw();
}
