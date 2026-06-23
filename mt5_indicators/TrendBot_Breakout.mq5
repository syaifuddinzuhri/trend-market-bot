//+------------------------------------------------------------------+
//| TrendBot_Breakout.mq5                                            |
//| Deteksi pola kompresi + sinyal breakout                          |
//|                                                                  |
//| Pola: Descending Triangle, Ascending Triangle, Wedge, Range      |
//| Visual:                                                          |
//|   Kotak kuning  = zona kompresi aktif                            |
//|   Garis merah   = resistance                                     |
//|   Garis hijau   = support                                        |
//|   Panah biru ↑  = BUY breakout                                   |
//|   Panah merah ↓ = SELL breakdown                                 |
//+------------------------------------------------------------------+
#property copyright   ""
#property version     "1.00"
#property strict
#property indicator_chart_window
#property indicator_plots 0

//── Input ─────────────────────────────────────────────────────────
input int    InpLookback    = 30;    // Bar untuk scan kompresi
input int    InpMinBars     = 8;     // Min bar kompres sebelum valid
input double InpMaxRangePip = 35.0; // Max range zona (pip)
input double InpBodyRatio   = 0.45; // Body candle min (breakout)
input double InpAdxMin      = 18.0; // ADX minimum
input int    InpAdxPeriod   = 14;   // Period ADX
input color  InpColorBuy    = clrDodgerBlue;
input color  InpColorSell   = clrRed;
input color  InpColorZone   = clrGold;
input color  InpColorResist = clrOrangeRed;
input color  InpColorSupport= clrLimeGreen;
input bool   InpShowLabel   = true;
input bool   InpAlertOn     = true;

//── Global ────────────────────────────────────────────────────────
double   g_pip;
datetime g_last_buy  = 0;
datetime g_last_sell = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   g_pip = (point >= 0.01) ? 1.0 : point * 10.0;

   IndicatorSetString(INDICATOR_SHORTNAME,
      StringFormat("TrendBot Breakout (%d bar / %.0f pip)", InpLookback, InpMaxRangePip));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, "TBB_");
}

//+------------------------------------------------------------------+
int OnCalculate(const int      rates_total,
                const int      prev_calculated,
                const datetime &time[],
                const double   &open[],
                const double   &high[],
                const double   &low[],
                const double   &close[],
                const long     &tick_volume[],
                const long     &volume[],
                const int      &spread[])
{
   if (rates_total < InpLookback + 10)
      return 0;

   // Set sebagai series — index 0 = candle terbaru
   ArraySetAsSeries(time,  true);
   ArraySetAsSeries(open,  true);
   ArraySetAsSeries(high,  true);
   ArraySetAsSeries(low,   true);
   ArraySetAsSeries(close, true);

   // Hanya proses bar terbaru (real-time) + sedikit ke belakang
   int limit = (prev_calculated == 0) ? MathMin(rates_total - InpLookback - 5, 300) : 3;

   for (int i = 1; i <= limit; i++)
   {
      if (i + InpLookback >= rates_total) continue;

      // Kumpulkan swing high/low dalam window [i .. i+lookback]
      double res = 0, sup = 999999;
      double r_first = 0, r_last = 0, s_first = 0, s_last = 0;
      int    r_count = 0, s_count = 0;

      for (int j = i + 1; j < i + InpLookback - 2 && j + 2 < rates_total; j++)
      {
         // Swing high
         if (high[j] > high[j-1] && high[j] > high[j+1] &&
             high[j] > high[j-2] && high[j] > high[j+2])
         {
            if (r_count == 0) { r_first = high[j]; r_last = high[j]; }
            else              { r_last  = high[j]; }
            if (high[j] > res) res = high[j];
            r_count++;
         }
         // Swing low
         if (low[j] < low[j-1] && low[j] < low[j+1] &&
             low[j] < low[j-2] && low[j] < low[j+2])
         {
            if (s_count == 0) { s_first = low[j]; s_last = low[j]; }
            else              { s_last  = low[j]; }
            if (low[j] < sup) sup = low[j];
            s_count++;
         }
      }

      // Fallback jika swing tidak cukup
      if (r_count < 2 || s_count < 2)
      {
         res = 0; sup = 999999;
         for (int j = i; j < i + InpLookback && j < rates_total; j++)
         {
            if (high[j] > res) res = high[j];
            if (low[j]  < sup) sup = low[j];
         }
         r_first = r_last = res;
         s_first = s_last = sup;
      }

      if (res <= 0 || sup >= 999998) continue;

      double range_pip = (res - sup) / g_pip;
      if (range_pip > InpMaxRangePip || range_pip < 3.0) continue;

      // Deteksi pola
      double r_change = r_first - r_last;  // positif = resistance turun (first lebih baru)
      double s_change = s_first - s_last;  // negatif = support naik

      string pattern;
      if (r_change > g_pip * 2 && MathAbs(s_change) < g_pip * 3)
         pattern = "Descending Triangle";
      else if (s_change < -g_pip * 2 && MathAbs(r_change) < g_pip * 3)
         pattern = "Ascending Triangle";
      else if (r_change > g_pip && s_change < -g_pip)
         pattern = "Wedge";
      else
         pattern = "Range";

      // ADX
      double adx_val = CalcAdx(i, rates_total, high, low, close);
      if (adx_val < InpAdxMin) continue;

      // Gambar zona aktif (hanya di bar terbaru i=1)
      if (i == 1)
      {
         DrawZone(time[i + InpLookback - 1], time[i], res, sup, range_pip, pattern, adx_val);
      }

      // Cek breakout pada candle [i]
      double o_c = open[i], h_c = high[i], l_c = low[i], c_c = close[i];
      double body       = MathAbs(c_c - o_c);
      double full_range = h_c - l_c;
      if (full_range < 0.001) continue;
      bool   body_ok = (full_range > 0) && (body / full_range >= InpBodyRatio);

      // BUY breakout
      if (c_c > res + g_pip && body_ok && c_c > o_c)
      {
         string nm = StringFormat("TBB_BUY_%d", (int)time[i]);
         if (ObjectFind(0, nm) < 0)
         {
            DrawArrow(nm, time[i], l_c - g_pip * 4, true);
            if (InpShowLabel)
               DrawText(StringFormat("TBB_LBLB_%d", (int)time[i]),
                        time[i], l_c - g_pip * 8,
                        StringFormat("BUY %.1f pip | %s", range_pip, pattern),
                        InpColorBuy);
            if (InpAlertOn && time[i] > g_last_buy)
            {
               Alert(StringFormat("TrendBot BUY Breakout | %s | %s | Range=%.1f pip | ADX=%.1f",
                                  _Symbol, pattern, range_pip, adx_val));
               g_last_buy = time[i];
            }
         }
      }

      // SELL breakdown
      if (c_c < sup - g_pip && body_ok && c_c < o_c)
      {
         string nm = StringFormat("TBB_SELL_%d", (int)time[i]);
         if (ObjectFind(0, nm) < 0)
         {
            DrawArrow(nm, time[i], h_c + g_pip * 4, false);
            if (InpShowLabel)
               DrawText(StringFormat("TBB_LBLS_%d", (int)time[i]),
                        time[i], h_c + g_pip * 8,
                        StringFormat("SELL %.1f pip | %s", range_pip, pattern),
                        InpColorSell);
            if (InpAlertOn && time[i] > g_last_sell)
            {
               Alert(StringFormat("TrendBot SELL Breakdown | %s | %s | Range=%.1f pip | ADX=%.1f",
                                  _Symbol, pattern, range_pip, adx_val));
               g_last_sell = time[i];
            }
         }
      }
   }

   return rates_total;
}

//+------------------------------------------------------------------+
double CalcAdx(int bar, int total,
               const double &high[], const double &low[], const double &close[])
{
   int p = InpAdxPeriod;
   if (bar + p * 2 + 2 >= total) return 0;

   double tr_s = 0, dp_s = 0, dm_s = 0;
   for (int k = bar + 1; k <= bar + p; k++)
   {
      if (k + 1 >= total) break;
      double tr  = MathMax(high[k] - low[k],
                   MathMax(MathAbs(high[k] - close[k+1]),
                           MathAbs(low[k]  - close[k+1])));
      double dp  = (high[k] - high[k+1] > 0 && high[k] - high[k+1] > low[k+1] - low[k])
                   ? high[k] - high[k+1] : 0;
      double dm  = (low[k+1] - low[k] > 0 && low[k+1] - low[k] > high[k] - high[k+1])
                   ? low[k+1] - low[k] : 0;
      tr_s += tr; dp_s += dp; dm_s += dm;
   }
   if (tr_s < 0.0001) return 0;
   double dip = 100.0 * dp_s / tr_s;
   double dim = 100.0 * dm_s / tr_s;
   double sum = dip + dim;
   return (sum > 0) ? 100.0 * MathAbs(dip - dim) / sum : 0;
}

//+------------------------------------------------------------------+
void DrawZone(datetime t1, datetime t2,
              double res, double sup,
              double range_pip, string pattern, double adx)
{
   ObjectsDeleteAll(0, "TBB_ZONE");
   ObjectsDeleteAll(0, "TBB_RES");
   ObjectsDeleteAll(0, "TBB_SUP");
   ObjectsDeleteAll(0, "TBB_INFO");

   // Kotak zona
   string zn = "TBB_ZONE_box";
   if (ObjectCreate(0, zn, OBJ_RECTANGLE, 0, t1, res, t2, sup))
   {
      ObjectSetInteger(0, zn, OBJPROP_COLOR, InpColorZone);
      ObjectSetInteger(0, zn, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetInteger(0, zn, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, zn, OBJPROP_FILL,  true);
      ObjectSetInteger(0, zn, OBJPROP_BACK,  true);
   }

   // Garis resistance
   string rn = "TBB_RES_line";
   if (ObjectCreate(0, rn, OBJ_TREND, 0, t1, res, t2, res))
   {
      ObjectSetInteger(0, rn, OBJPROP_COLOR,     InpColorResist);
      ObjectSetInteger(0, rn, OBJPROP_WIDTH,     2);
      ObjectSetInteger(0, rn, OBJPROP_STYLE,     STYLE_SOLID);
      ObjectSetInteger(0, rn, OBJPROP_RAY_RIGHT, false);
   }

   // Garis support
   string sn = "TBB_SUP_line";
   if (ObjectCreate(0, sn, OBJ_TREND, 0, t1, sup, t2, sup))
   {
      ObjectSetInteger(0, sn, OBJPROP_COLOR,     InpColorSupport);
      ObjectSetInteger(0, sn, OBJPROP_WIDTH,     2);
      ObjectSetInteger(0, sn, OBJPROP_STYLE,     STYLE_SOLID);
      ObjectSetInteger(0, sn, OBJPROP_RAY_RIGHT, false);
   }

   // Label
   if (InpShowLabel)
   {
      string in = "TBB_INFO_txt";
      if (ObjectCreate(0, in, OBJ_TEXT, 0, t2, res + g_pip * 2))
      {
         ObjectSetString (0, in, OBJPROP_TEXT,
            StringFormat("%s | %.1f pip | ADX %.0f", pattern, range_pip, adx));
         ObjectSetInteger(0, in, OBJPROP_COLOR,    InpColorZone);
         ObjectSetInteger(0, in, OBJPROP_FONTSIZE,  9);
         ObjectSetString (0, in, OBJPROP_FONT,      "Arial Bold");
         ObjectSetInteger(0, in, OBJPROP_ANCHOR,    ANCHOR_LEFT_LOWER);
      }
   }
}

//+------------------------------------------------------------------+
void DrawArrow(string name, datetime t, double price, bool is_buy)
{
   if (ObjectCreate(0, name, OBJ_ARROW, 0, t, price))
   {
      ObjectSetInteger(0, name, OBJPROP_ARROWCODE, is_buy ? 233 : 234);
      ObjectSetInteger(0, name, OBJPROP_COLOR,     is_buy ? InpColorBuy : InpColorSell);
      ObjectSetInteger(0, name, OBJPROP_WIDTH,     3);
   }
}

//+------------------------------------------------------------------+
void DrawText(string name, datetime t, double price, string txt, color clr)
{
   if (ObjectCreate(0, name, OBJ_TEXT, 0, t, price))
   {
      ObjectSetString (0, name, OBJPROP_TEXT,     txt);
      ObjectSetInteger(0, name, OBJPROP_COLOR,    clr);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE,  8);
      ObjectSetString (0, name, OBJPROP_FONT,      "Arial Bold");
      ObjectSetInteger(0, name, OBJPROP_ANCHOR,    ANCHOR_LEFT_UPPER);
   }
}
