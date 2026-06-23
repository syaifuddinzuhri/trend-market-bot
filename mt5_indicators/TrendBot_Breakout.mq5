//+------------------------------------------------------------------+
//| TrendBot_Breakout.mq5                                            |
//| Deteksi pola kompresi + sinyal breakout                          |
//|                                                                  |
//| Pola yang dideteksi:                                             |
//|   - Descending Triangle : resistance turun, support flat         |
//|   - Ascending Triangle  : support naik, resistance flat          |
//|   - Wedge               : resistance turun + support naik        |
//|   - Range               : sideways sempit                        |
//|                                                                  |
//| Visual:                                                          |
//|   - Kotak kuning = zona kompresi aktif                           |
//|   - Garis merah  = resistance (bisa miring)                      |
//|   - Garis hijau  = support (bisa miring)                         |
//|   - Panah BIRU ↑ = BUY breakout konfirmasi                      |
//|   - Panah MERAH↓ = SELL breakdown konfirmasi                     |
//|   - Label teks   = nama pola + range pip                         |
//+------------------------------------------------------------------+
#property copyright   ""
#property version     "1.00"
#property indicator_chart_window
#property indicator_plots 0

//── Input ────────────────────────────────────────────────────────────
input int    InpLookback      = 30;     // Bar untuk scan kompresi
input int    InpMinBars       = 8;      // Min bar kompres sebelum valid
input double InpMaxRangePip   = 35.0;  // Max range zona (pip)
input double InpBodyRatio     = 0.45;  // Body candle min untuk breakout
input double InpAdxMin        = 18.0;  // ADX minimum
input int    InpAdxPeriod     = 14;    // Period ADX
input color  InpColorBuy      = clrDodgerBlue;   // Warna sinyal BUY
input color  InpColorSell     = clrRed;           // Warna sinyal SELL
input color  InpColorZone     = clrGold;          // Warna kotak kompresi
input color  InpColorResist   = clrOrangeRed;     // Warna garis resistance
input color  InpColorSupport  = clrLimeGreen;     // Warna garis support
input bool   InpShowLabel     = true;             // Tampilkan label pola
input bool   InpAlertOn       = true;             // Alert popup saat breakout

//── Variabel global ──────────────────────────────────────────────────
double pip_size;
datetime _last_alert_buy  = 0;
datetime _last_alert_sell = 0;
int      _obj_counter     = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   // Deteksi pip size
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   pip_size = (point >= 0.01) ? 1.0 : point * 10.0;

   IndicatorSetString(INDICATOR_SHORTNAME,
      StringFormat("TrendBot Breakout (%d bar, max %.0f pip)", InpLookback, InpMaxRangePip));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, "TBB_");
}

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double   &open[],
                const double   &high[],
                const double   &low[],
                const double   &close[],
                const long     &tick_volume[],
                const long     &volume[],
                const int      &spread[])
{
   if (rates_total < InpLookback + 10) return rates_total;

   int limit = (prev_calculated == 0) ? rates_total - InpLookback - 5 : rates_total - prev_calculated + 1;
   if (limit <= 0) limit = 1;

   for (int i = limit; i >= 1; i--)
   {
      int bar = i;  // candle yang sedang dievaluasi (1 = candle terakhir selesai)

      // Kumpulkan window
      int start = bar + InpLookback - 1;
      if (start >= rates_total) continue;

      // Cari swing high/low dalam window
      double swing_highs[];
      double swing_lows[];
      datetime swing_high_time[];
      datetime swing_low_time[];
      ArrayResize(swing_highs, 0);
      ArrayResize(swing_lows,  0);
      ArrayResize(swing_high_time, 0);
      ArrayResize(swing_low_time,  0);

      for (int j = start; j >= bar + 2; j--)
      {
         if (j + 2 >= rates_total || j - 2 < 0) continue;
         // Swing high
         if (high[j] > high[j+1] && high[j] > high[j+2] &&
             high[j] > high[j-1] && high[j] > high[j-2])
         {
            int sz = ArraySize(swing_highs);
            ArrayResize(swing_highs,    sz + 1);
            ArrayResize(swing_high_time, sz + 1);
            swing_highs[sz]     = high[j];
            swing_high_time[sz] = time[j];
         }
         // Swing low
         if (low[j] < low[j+1] && low[j] < low[j+2] &&
             low[j] < low[j-1] && low[j] < low[j-2])
         {
            int sz = ArraySize(swing_lows);
            ArrayResize(swing_lows,    sz + 1);
            ArrayResize(swing_low_time, sz + 1);
            swing_lows[sz]     = low[j];
            swing_low_time[sz] = time[j];
         }
      }

      // Butuh minimal 2 swing high dan 2 swing low
      int nh = ArraySize(swing_highs);
      int nl = ArraySize(swing_lows);

      double resistance, support, r_change, s_change;
      string pattern;

      if (nh >= 2 && nl >= 2)
      {
         resistance = swing_highs[0];    // swing high terbaru
         support    = swing_lows[0];     // swing low terbaru
         r_change   = swing_highs[0] - swing_highs[nh-1];  // negatif = turun
         s_change   = swing_lows[0]  - swing_lows[nl-1];   // positif = naik

         double range_pip = (resistance - support) / pip_size;
         if (range_pip > InpMaxRangePip) continue;

         if (r_change < -pip_size * 2 && MathAbs(s_change) < pip_size * 3)
            pattern = "Descending Triangle";
         else if (s_change > pip_size * 2 && MathAbs(r_change) < pip_size * 3)
            pattern = "Ascending Triangle";
         else if (r_change < -pip_size && s_change > pip_size)
            pattern = "Wedge";
         else
            pattern = "Range";
      }
      else
      {
         // Fallback: simple high/low range
         resistance = 0; support = 999999;
         for (int j = start; j >= bar; j--)
         {
            if (high[j] > resistance) resistance = high[j];
            if (low[j]  < support)   support    = low[j];
         }
         double range_pip = (resistance - support) / pip_size;
         if (range_pip > InpMaxRangePip) continue;
         pattern   = "Range";
         r_change  = 0;
         s_change  = 0;
      }

      double range_pip = (resistance - support) / pip_size;

      // Cek ADX pada bar ini
      double adx_val = _GetAdx(bar, rates_total, high, low, close);
      if (adx_val < InpAdxMin) continue;

      // Gambar zona kompresi (hanya sekali per zona)
      if (bar == 1)
      {
         _DrawZone(time[start], time[bar], resistance, support, range_pip, pattern);
      }

      // Cek breakout pada candle [bar]
      double o = open[bar], h = high[bar], l = low[bar], c = close[bar];
      double body      = MathAbs(c - o);
      double full_range = h - l;
      if (full_range < 0.001) continue;
      bool body_ok = (body / full_range) >= InpBodyRatio;

      // BUY breakout
      if (c > resistance + pip_size && body_ok && c > o)
      {
         string sig_name = StringFormat("TBB_BUY_%d", bar);
         if (ObjectFind(0, sig_name) < 0)
         {
            _DrawArrow(sig_name, time[bar], l - pip_size * 3, true);
            if (InpShowLabel)
               _DrawLabel(StringFormat("TBB_LBL_B_%d", bar),
                          time[bar], l - pip_size * 6,
                          StringFormat("BUY ↑ %.1f pip\n%s", range_pip, pattern),
                          InpColorBuy);
            if (InpAlertOn && time[bar] > _last_alert_buy)
            {
               Alert(StringFormat("TrendBot Breakout: BUY %s | %s | Range=%.1f pip | ADX=%.1f",
                     _Symbol, pattern, range_pip, adx_val));
               _last_alert_buy = time[bar];
            }
         }
      }

      // SELL breakdown
      if (c < support - pip_size && body_ok && c < o)
      {
         string sig_name = StringFormat("TBB_SELL_%d", bar);
         if (ObjectFind(0, sig_name) < 0)
         {
            _DrawArrow(sig_name, time[bar], h + pip_size * 3, false);
            if (InpShowLabel)
               _DrawLabel(StringFormat("TBB_LBL_S_%d", bar),
                          time[bar], h + pip_size * 7,
                          StringFormat("SELL ↓ %.1f pip\n%s", range_pip, pattern),
                          InpColorSell);
            if (InpAlertOn && time[bar] > _last_alert_sell)
            {
               Alert(StringFormat("TrendBot Breakout: SELL %s | %s | Range=%.1f pip | ADX=%.1f",
                     _Symbol, pattern, range_pip, adx_val));
               _last_alert_sell = time[bar];
            }
         }
      }
   }

   return rates_total;
}

//+------------------------------------------------------------------+
double _GetAdx(int bar, int rates_total,
               const double &high[], const double &low[], const double &close[])
{
   int period = InpAdxPeriod;
   if (bar + period * 2 >= rates_total) return 0;

   double tr_sum = 0, dmp_sum = 0, dmm_sum = 0;
   for (int i = bar + period; i > bar; i--)
   {
      double tr  = MathMax(high[i] - low[i],
                  MathMax(MathAbs(high[i] - close[i+1]),
                          MathAbs(low[i]  - close[i+1])));
      double dmp = (high[i] - high[i+1] > low[i+1] - low[i] && high[i] - high[i+1] > 0)
                   ? high[i] - high[i+1] : 0;
      double dmm = (low[i+1] - low[i] > high[i] - high[i+1] && low[i+1] - low[i] > 0)
                   ? low[i+1] - low[i] : 0;
      tr_sum  += tr;
      dmp_sum += dmp;
      dmm_sum += dmm;
   }
   if (tr_sum < 0.0001) return 0;
   double dip = 100 * dmp_sum / tr_sum;
   double dim = 100 * dmm_sum / tr_sum;
   double dx  = (dip + dim > 0) ? 100 * MathAbs(dip - dim) / (dip + dim) : 0;
   return dx;
}

//+------------------------------------------------------------------+
void _DrawZone(datetime t_start, datetime t_end,
               double resistance, double support,
               double range_pip, string pattern)
{
   // Hapus zona lama
   ObjectsDeleteAll(0, "TBB_ZONE_");
   ObjectsDeleteAll(0, "TBB_RES_");
   ObjectsDeleteAll(0, "TBB_SUP_");
   ObjectsDeleteAll(0, "TBB_INFO_");

   // Kotak kompresi
   string zname = "TBB_ZONE_box";
   ObjectCreate(0, zname, OBJ_RECTANGLE, 0, t_start, resistance, t_end, support);
   ObjectSetInteger(0, zname, OBJPROP_COLOR,   InpColorZone);
   ObjectSetInteger(0, zname, OBJPROP_STYLE,   STYLE_DOT);
   ObjectSetInteger(0, zname, OBJPROP_WIDTH,   1);
   ObjectSetInteger(0, zname, OBJPROP_FILL,    true);
   ObjectSetInteger(0, zname, OBJPROP_BACK,    true);
   ObjectSetDouble (0, zname, OBJPROP_PRICE, 0, resistance);
   ObjectSetDouble (0, zname, OBJPROP_PRICE, 1, support);
   // Transparansi — gunakan alpha via back color
   ObjectSetInteger(0, zname, OBJPROP_BGCOLOR,
      ColorToARGB(InpColorZone, 30));  // 30/255 opacity

   // Garis resistance
   string rname = "TBB_RES_line";
   ObjectCreate(0, rname, OBJ_TREND, 0, t_start, resistance, t_end, resistance);
   ObjectSetInteger(0, rname, OBJPROP_COLOR, InpColorResist);
   ObjectSetInteger(0, rname, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, rname, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, rname, OBJPROP_RAY_RIGHT, false);

   // Garis support
   string sname = "TBB_SUP_line";
   ObjectCreate(0, sname, OBJ_TREND, 0, t_start, support, t_end, support);
   ObjectSetInteger(0, sname, OBJPROP_COLOR, InpColorSupport);
   ObjectSetInteger(0, sname, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, sname, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, sname, OBJPROP_RAY_RIGHT, false);

   // Label info zona
   if (InpShowLabel)
   {
      string iname = "TBB_INFO_label";
      double mid   = (resistance + support) / 2.0;
      ObjectCreate(0, iname, OBJ_TEXT, 0, t_end, resistance + pip_size * 2);
      ObjectSetString (0, iname, OBJPROP_TEXT,
         StringFormat("%s | %.1f pip | ADX>%.0f", pattern, range_pip, InpAdxMin));
      ObjectSetInteger(0, iname, OBJPROP_COLOR,    InpColorZone);
      ObjectSetInteger(0, iname, OBJPROP_FONTSIZE,  8);
      ObjectSetString (0, iname, OBJPROP_FONT,      "Arial Bold");
      ObjectSetInteger(0, iname, OBJPROP_ANCHOR,    ANCHOR_LEFT_LOWER);
   }
}

//+------------------------------------------------------------------+
void _DrawArrow(string name, datetime t, double price, bool is_buy)
{
   ObjectCreate(0, name, OBJ_ARROW, 0, t, price);
   ObjectSetInteger(0, name, OBJPROP_ARROWCODE, is_buy ? 233 : 234);  // 233=↑, 234=↓
   ObjectSetInteger(0, name, OBJPROP_COLOR,  is_buy ? InpColorBuy : InpColorSell);
   ObjectSetInteger(0, name, OBJPROP_WIDTH,  3);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, is_buy ? ANCHOR_TOP : ANCHOR_BOTTOM);
}

//+------------------------------------------------------------------+
void _DrawLabel(string name, datetime t, double price, string txt, color clr)
{
   ObjectCreate(0, name, OBJ_TEXT, 0, t, price);
   ObjectSetString (0, name, OBJPROP_TEXT,     txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR,    clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,  8);
   ObjectSetString (0, name, OBJPROP_FONT,      "Arial Bold");
   ObjectSetInteger(0, name, OBJPROP_ANCHOR,    ANCHOR_LEFT_UPPER);
}
