//+------------------------------------------------------------------+
//| TrendBot_EMA_Ribbon.mq5                                          |
//| EMA 20 / 50 / 100 / 200 — sama persis dengan parameter bot       |
//| Pasang di H4 (trend filter) dan H1 (pullback monitor)            |
//+------------------------------------------------------------------+
#property indicator_chart_window
#property indicator_buffers 4
#property indicator_plots   4

#property indicator_label1  "EMA 20"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDodgerBlue
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

#property indicator_label2  "EMA 50"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrOrange
#property indicator_style2  STYLE_SOLID
#property indicator_width2  2

#property indicator_label3  "EMA 100"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrMagenta
#property indicator_style3  STYLE_SOLID
#property indicator_width3  1

#property indicator_label4  "EMA 200"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrRed
#property indicator_style4  STYLE_SOLID
#property indicator_width4  2

double ema20[], ema50[], ema100[], ema200[];
int h20, h50, h100, h200;

int OnInit()
{
   SetIndexBuffer(0, ema20,  INDICATOR_DATA);
   SetIndexBuffer(1, ema50,  INDICATOR_DATA);
   SetIndexBuffer(2, ema100, INDICATOR_DATA);
   SetIndexBuffer(3, ema200, INDICATOR_DATA);

   h20  = iMA(_Symbol, PERIOD_CURRENT, 20,  0, MODE_EMA, PRICE_CLOSE);
   h50  = iMA(_Symbol, PERIOD_CURRENT, 50,  0, MODE_EMA, PRICE_CLOSE);
   h100 = iMA(_Symbol, PERIOD_CURRENT, 100, 0, MODE_EMA, PRICE_CLOSE);
   h200 = iMA(_Symbol, PERIOD_CURRENT, 200, 0, MODE_EMA, PRICE_CLOSE);

   IndicatorSetString(INDICATOR_SHORTNAME, "TrendBot EMA Ribbon");
   return INIT_SUCCEEDED;
}

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{
   int start = prev_calculated == 0 ? 0 : prev_calculated - 1;

   for (int i = start; i < rates_total; i++)
   {
      ema20[i]  = iMAGet(h20,  i, rates_total);
      ema50[i]  = iMAGet(h50,  i, rates_total);
      ema100[i] = iMAGet(h100, i, rates_total);
      ema200[i] = iMAGet(h200, i, rates_total);
   }
   return rates_total;
}

double iMAGet(int handle, int i, int total)
{
   double buf[];
   int idx = total - 1 - i;
   if (CopyBuffer(handle, 0, idx, 1, buf) <= 0) return EMPTY_VALUE;
   return buf[0];
}

void OnDeinit(const int reason)
{
   IndicatorRelease(h20);
   IndicatorRelease(h50);
   IndicatorRelease(h100);
   IndicatorRelease(h200);
}
