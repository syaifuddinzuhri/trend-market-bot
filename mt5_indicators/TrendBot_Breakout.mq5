//+------------------------------------------------------------------+
//| TrendBot_Breakout.mq5                                            |
//| Deteksi kompresi (Triangle/Wedge/Range) + sinyal breakout        |
//+------------------------------------------------------------------+
#property copyright   ""
#property version     "1.10"
#property strict
#property indicator_chart_window
#property indicator_plots 0

input int    InpLookback    = 30;    // Bar untuk scan kompresi
input int    InpMinBars     = 8;     // Min bar kompres
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

double   g_pip;
datetime g_last_buy  = 0;
datetime g_last_sell = 0;
bool     g_initialized = false;

//+------------------------------------------------------------------+
int OnInit()
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   // XAUUSD: point=0.01 → pip=1.0 | Forex: point=0.00001 → pip=0.0001
   g_pip = (point >= 0.01) ? 1.0 : point * 10.0;
   g_initialized = false;

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

   ArraySetAsSeries(time,  true);
   ArraySetAsSeries(open,  true);
   ArraySetAsSeries(high,  true);
   ArraySetAsSeries(low,   true);
   ArraySetAsSeries(close, true);

   // Saat pertama kali load: scan histori untuk gambar visual saja (tanpa alert)
   // Setelah init selesai: hanya proses bar terbaru (real-time)
   bool first_run = !g_initialized;
   if (!g_initialized)
      g_initialized = true;

   int limit = first_run ? MathMin(rates_total - InpLookback - 5, 500) : 3;

   for (int i = 1; i <= limit; i++)
   {
      if (i + InpLookback + 2 >= rates_total) continue;

      // ── Cari swing high/low dalam window ──────────────────────
      double res = 0.0, sup = DBL_MAX;
      double r_recent = 0.0, r_old = 0.0;   // swing high terbaru dan terlama
      double s_recent = DBL_MAX, s_old = DBL_MAX;
      int    r_count = 0, s_count = 0;

      int j_start = i + 1;
      int j_end   = i + InpLookback - 2;

      for (int j = j_start; j <= j_end && j + 2 < rates_total; j++)
      {
         // Swing high: lokal maxima (dengan buffer 2 bar kiri/kanan)
         if (high[j] > high[j-1] && high[j] > high[j+1])
         {
            if (high[j] > res) res = high[j];
            if (r_count == 0) r_recent = high[j];
            r_old = high[j];
            r_count++;
         }
         // Swing low: lokal minima
         if (low[j] < low[j-1] && low[j] < low[j+1])
         {
            if (low[j] < sup) sup = low[j];
            if (s_count == 0) s_recent = low[j];
            s_old = low[j];
            s_count++;
         }
      }

      // Fallback: pakai high/low sederhana jika swing tidak cukup
      if (r_count < 2 || s_count < 2 || res <= 0 || sup >= DBL_MAX / 2)
      {
         res = 0.0; sup = DBL_MAX;
         for (int j = i; j <= i + InpLookback && j < rates_total; j++)
         {
            if (high[j] > res) res = high[j];
            if (low[j]  < sup) sup = low[j];
         }
         r_recent = r_old = res;
         s_recent = s_old = sup;
      }

      // Validasi dasar
      if (res <= 0 || sup >= DBL_MAX / 2 || res <= sup) continue;

      double range_pip = (res - sup) / g_pip;
      if (range_pip > InpMaxRangePip || range_pip < 2.0) continue;

      // ── Deteksi pola ──────────────────────────────────────────
      // r_recent = swing high paling baru, r_old = paling lama
      // Descending Triangle: resistance TURUN (r_recent < r_old)
      // Ascending Triangle : support NAIK   (s_recent > s_old)
      double r_diff = r_old - r_recent;  // positif = resistance turun
      double s_diff = s_recent - s_old;  // positif = support naik

      string pattern;
      if (r_diff > g_pip * 2 && MathAbs(s_diff) < g_pip * 3)
         pattern = "Descending Triangle";
      else if (s_diff > g_pip * 2 && MathAbs(r_diff) < g_pip * 3)
         pattern = "Ascending Triangle";
      else if (r_diff > g_pip && s_diff > g_pip)
         pattern = "Wedge";
      else
         pattern = "Range";

      // ── ADX ───────────────────────────────────────────────────
      double adx_val = CalcAdx(i, rates_total, high, low, close);
      if (adx_val < InpAdxMin) continue;

      // ── Gambar zona di bar terbaru ────────────────────────────
      if (i == 1)
         DrawZone(time[j_end], time[i], res, sup, range_pip, pattern, adx_val);

      // ── Cek breakout pada candle [i] ──────────────────────────
      double o_c = open[i], h_c = high[i], l_c = low[i], c_c = close[i];
      double body       = MathAbs(c_c - o_c);
      double full_range = h_c - l_c;
      if (full_range < g_pip * 0.5) continue;

      bool body_ok = (body / full_range >= InpBodyRatio);
      bool alert_ok = !first_run && InpAlertOn;  // TIDAK alert saat scan histori

      // BUY breakout
      if (c_c > res + g_pip && body_ok && c_c > o_c)
      {
         string nm = StringFormat("TBB_BUY_%d", (int)time[i]);
         if (ObjectFind(0, nm) < 0)
         {
            DrawArrow(nm, time[i], l_c - g_pip * 4, true);
            if (InpShowLabel)
               DrawText(StringFormat("TBB_LBLB_%d", (int)time[i]),
                        time[i], l_c - g_pip * 9,
                        StringFormat("BUY | %.1f pip\n%s", range_pip, pattern),
                        InpColorBuy);
            if (alert_ok && time[i] > g_last_buy)
            {
               Alert(StringFormat(
                  "TrendBot BUY Breakout | %s | %s\nRange=%.1f pip | ADX=%.1f",
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
                        time[i], h_c + g_pip * 9,
                        StringFormat("SELL | %.1f pip\n%s", range_pip, pattern),
                        InpColorSell);
            if (alert_ok && time[i] > g_last_sell)
            {
               Alert(StringFormat(
                  "TrendBot SELL Breakdown | %s | %s\nRange=%.1f pip | ADX=%.1f",
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
   for (int k = bar + 1; k <= bar + p && k + 1 < total; k++)
   {
      double tr = MathMax(high[k] - low[k],
                  MathMax(MathAbs(high[k] - close[k+1]),
                          MathAbs(low[k]  - close[k+1])));
      double dh = high[k] - high[k+1];
      double dl = low[k+1] - low[k];
      double dp = (dh > dl && dh > 0) ? dh : 0;
      double dm = (dl > dh && dl > 0) ? dl : 0;
      tr_s += tr; dp_s += dp; dm_s += dm;
   }
   if (tr_s < 0.0001) return 0;
   double dip = 100.0 * dp_s / tr_s;
   double dim = 100.0 * dm_s / tr_s;
   double sum = dip + dim;
   return (sum > 0.0001) ? 100.0 * MathAbs(dip - dim) / sum : 0;
}

//+------------------------------------------------------------------+
void DrawZone(datetime t1, datetime t2,
              double res, double sup,
              double range_pip, string pattern, double adx)
{
   // Hapus objek zona lama
   ObjectsDeleteAll(0, "TBB_ZONE");
   ObjectsDeleteAll(0, "TBB_RES");
   ObjectsDeleteAll(0, "TBB_SUP");
   ObjectsDeleteAll(0, "TBB_INFO");

   // Kotak kompresi
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

   // Label info
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
