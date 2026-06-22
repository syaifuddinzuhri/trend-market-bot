//+------------------------------------------------------------------+
//| TrendBot_ADX_ATR.mq5                                             |
//| ADX(14) + ATR(14) vs ATR_MA(20) — sama persis dengan parameter   |
//| bot. Pasang di sub-window H1.                                    |
//|                                                                  |
//| Warna ADX line:                                                  |
//|   < 20  = abu  (ADX_SKIP  — bot skip signal)                    |
//|   20-25 = kuning (zona lemah)                                    |
//|   >= 25 = hijau (ADX_MIN  — bot boleh entry)                    |
//|   >= 40 = biru  (STRONG   — momentum kuat)                      |
//+------------------------------------------------------------------+
#property indicator_separate_window
#property indicator_buffers 6
#property indicator_plots   4

// Plot 0 — ADX line
#property indicator_label1  "ADX(14)"
#property indicator_type1   DRAW_COLOR_LINE
#property indicator_color1  clrGray,clrYellow,clrLime,clrDodgerBlue
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

// Plot 1 — ATR line
#property indicator_label2  "ATR(14)"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrOrange
#property indicator_style2  STYLE_SOLID
#property indicator_width2  1

// Plot 2 — ATR MA(20) line
#property indicator_label3  "ATR MA(20)"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrRed
#property indicator_style3  STYLE_DOT
#property indicator_width3  1

// Plot 3 — ADX level reference (hidden, pakai OBJ_HLINE manual)
#property indicator_label4  "ADX Level"
#property indicator_type4   DRAW_NONE

input int    ADX_Period    = 14;
input int    ATR_Period    = 14;
input int    ATR_MA_Period = 20;
input double ADX_SKIP      = 20.0;   // bot skip di bawah ini
input double ADX_MIN       = 25.0;   // bot entry minimum
input double ADX_STRONG    = 40.0;   // momentum kuat

double adx_buf[], adx_color[], atr_buf[], atr_ma_buf[], dummy[];
int    h_adx, h_atr;

int OnInit()
{
   SetIndexBuffer(0, adx_buf,   INDICATOR_DATA);
   SetIndexBuffer(1, adx_color, INDICATOR_COLOR_INDEX);
   SetIndexBuffer(2, atr_buf,   INDICATOR_DATA);
   SetIndexBuffer(3, atr_ma_buf,INDICATOR_DATA);
   SetIndexBuffer(4, dummy,     INDICATOR_CALCULATIONS);
   SetIndexBuffer(5, dummy,     INDICATOR_CALCULATIONS);

   h_adx = iADX(_Symbol, PERIOD_CURRENT, ADX_Period);
   h_atr = iATR(_Symbol, PERIOD_CURRENT, ATR_Period);

   IndicatorSetString(INDICATOR_SHORTNAME, "TrendBot ADX+ATR");
   IndicatorSetInteger(INDICATOR_DIGITS, 2);

   // Garis level horizontal
   _DrawLevel("ADX_SKIP",   ADX_SKIP,   clrDimGray,   STYLE_DOT);
   _DrawLevel("ADX_MIN",    ADX_MIN,    clrYellow,    STYLE_DASH);
   _DrawLevel("ADX_STRONG", ADX_STRONG, clrDodgerBlue,STYLE_DOT);

   return INIT_SUCCEEDED;
}

void _DrawLevel(string name, double value, color clr, ENUM_LINE_STYLE sty)
{
   string objName = "TBot_ADX_" + name;
   if (ObjectFind(0, objName) < 0)
      ObjectCreate(0, objName, OBJ_HLINE, ChartWindowFind(), 0, value);
   ObjectSetDouble(0, objName, OBJPROP_PRICE, value);
   ObjectSetInteger(0, objName, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, objName, OBJPROP_STYLE, sty);
   ObjectSetInteger(0, objName, OBJPROP_WIDTH, 1);
   ObjectSetString(0, objName, OBJPROP_TOOLTIP, name + "=" + DoubleToString(value, 1));
}

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{
   int start = prev_calculated == 0 ? 0 : prev_calculated - 1;

   double adx_tmp[], atr_tmp[];

   for (int i = start; i < rates_total; i++)
   {
      int idx = rates_total - 1 - i;

      // ADX
      if (CopyBuffer(h_adx, 0, idx, 1, adx_tmp) > 0)
      {
         adx_buf[i] = adx_tmp[0];
         if (adx_tmp[0] >= ADX_STRONG)     adx_color[i] = 3; // biru
         else if (adx_tmp[0] >= ADX_MIN)   adx_color[i] = 2; // hijau
         else if (adx_tmp[0] >= ADX_SKIP)  adx_color[i] = 1; // kuning
         else                               adx_color[i] = 0; // abu
      }

      // ATR
      if (CopyBuffer(h_atr, 0, idx, 1, atr_tmp) > 0)
         atr_buf[i] = atr_tmp[0];
   }

   // ATR MA(20) — hitung manual dari atr_buf
   int ma_period = ATR_MA_Period;
   for (int i = start; i < rates_total; i++)
   {
      if (i < ma_period - 1) { atr_ma_buf[i] = EMPTY_VALUE; continue; }
      double sum = 0;
      for (int j = 0; j < ma_period; j++) sum += atr_buf[i - j];
      atr_ma_buf[i] = sum / ma_period;
   }

   return rates_total;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(h_adx);
   IndicatorRelease(h_atr);
   // Hapus level lines
   string names[] = {"ADX_SKIP","ADX_MIN","ADX_STRONG"};
   for (int i = 0; i < 3; i++)
      ObjectDelete(0, "TBot_ADX_" + names[i]);
}
