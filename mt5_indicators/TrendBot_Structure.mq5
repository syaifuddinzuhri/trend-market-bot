//+------------------------------------------------------------------+
//| TrendBot_Structure.mq5                                           |
//| Swing HH/HL/LH/LL + BOS/CHoCH label — sama dengan bot/structure  |
//| Pasang di M15 (entry timeframe)                                  |
//|                                                                  |
//| Swing detection: left=5 bar, right=2 bar (sama dengan bot)       |
//| BOS  = Break of Structure  (searah trend)                        |
//| CHoCH = Change of Character (pembalikan)                         |
//+------------------------------------------------------------------+
#property indicator_chart_window
#property indicator_buffers 2
#property indicator_plots   2

#property indicator_label1  "Swing High"
#property indicator_type1   DRAW_ARROW
#property indicator_color1  clrRed
#property indicator_width1  2

#property indicator_label2  "Swing Low"
#property indicator_type2   DRAW_ARROW
#property indicator_color2  clrLime
#property indicator_width2  2

input int  SwingLeft  = 5;   // Bar kiri untuk konfirmasi swing
input int  SwingRight = 2;   // Bar kanan untuk konfirmasi swing
input bool ShowLabels = true; // Tampilkan label HH/HL/LH/LL
input bool ShowBOS    = true; // Tampilkan label BOS / CHoCH
input color ColorBOS  = clrDodgerBlue;
input color ColorCHoCH= clrOrangeRed;

double sh_buf[], sl_buf[];

// State tracking untuk klasifikasi swing
double last_sh = 0, prev_sh = 0;
double last_sl = 0, prev_sl = 0;
int    last_sh_bar = -1, last_sl_bar = -1;

int OnInit()
{
   SetIndexBuffer(0, sh_buf, INDICATOR_DATA);
   SetIndexBuffer(1, sl_buf, INDICATOR_DATA);

   PlotIndexSetInteger(0, PLOT_ARROW, 218); // panah bawah (▼) di atas candle
   PlotIndexSetInteger(1, PLOT_ARROW, 217); // panah atas  (▲) di bawah candle
   PlotIndexSetDouble(0, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   PlotIndexSetDouble(1, PLOT_EMPTY_VALUE, EMPTY_VALUE);

   ArrayInitialize(sh_buf, EMPTY_VALUE);
   ArrayInitialize(sl_buf, EMPTY_VALUE);

   IndicatorSetString(INDICATOR_SHORTNAME, "TrendBot Structure");
   return INIT_SUCCEEDED;
}

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{
   // Reset semua objek jika full recalc
   if (prev_calculated == 0)
   {
      ArrayInitialize(sh_buf, EMPTY_VALUE);
      ArrayInitialize(sl_buf, EMPTY_VALUE);
      _DeleteObjects();
      last_sh = 0; prev_sh = 0;
      last_sl = 0; prev_sl = 0;
      last_sh_bar = -1; last_sl_bar = -1;
   }

   int limit = MathMax(prev_calculated - 1, SwingLeft + SwingRight + 1);

   for (int i = limit; i < rates_total - SwingRight; i++)
   {
      // Cek swing high: bar i adalah tertinggi di antara left+right bar
      bool is_sh = true, is_sl = true;
      for (int k = 1; k <= SwingLeft; k++)
      {
         if (i - k < 0) { is_sh = false; is_sl = false; break; }
         if (high[i - k] >= high[i]) is_sh = false;
         if (low[i - k]  <= low[i])  is_sl = false;
      }
      for (int k = 1; k <= SwingRight; k++)
      {
         if (i + k >= rates_total) { is_sh = false; is_sl = false; break; }
         if (high[i + k] >= high[i]) is_sh = false;
         if (low[i + k]  <= low[i])  is_sl = false;
      }

      if (is_sh)
      {
         sh_buf[i] = high[i];
         string swing_type = "";
         if (prev_sh > 0) swing_type = (high[i] > prev_sh) ? "HH" : "LH";
         if (ShowLabels && swing_type != "")
         {
            string name = "SH_" + IntegerToString(i);
            _DrawLabel(name, time[i], high[i] + _Point * 15,
                       swing_type, clrRed, ANCHOR_LOWER);
         }
         // BOS / CHoCH detection (saat swing high terbentuk vs swing low sebelumnya)
         if (ShowBOS && last_sl > 0 && last_sl_bar > 0)
         {
            // Jika harga close melewati last swing low → CHoCH (bullish ke bearish)
            if (close[i] < last_sl)
            {
               string bname = "CHoCH_SH_" + IntegerToString(i);
               _DrawBOSLine(bname, time[last_sl_bar], time[i], last_sl, ColorCHoCH, "CHoCH↓");
            }
         }
         prev_sh = last_sh; last_sh = high[i]; last_sh_bar = i;
      }

      if (is_sl)
      {
         sl_buf[i] = low[i];
         string swing_type = "";
         if (prev_sl > 0) swing_type = (low[i] > prev_sl) ? "HL" : "LL";
         if (ShowLabels && swing_type != "")
         {
            string name = "SL_" + IntegerToString(i);
            _DrawLabel(name, time[i], low[i] - _Point * 15,
                       swing_type, clrLime, ANCHOR_UPPER);
         }
         // BOS bullish: harga close melewati last swing high
         if (ShowBOS && last_sh > 0 && last_sh_bar > 0)
         {
            if (close[i] > last_sh)
            {
               string bname = "BOS_SL_" + IntegerToString(i);
               _DrawBOSLine(bname, time[last_sh_bar], time[i], last_sh, ColorBOS, "BOS↑");
            }
         }
         prev_sl = last_sl; last_sl = low[i]; last_sl_bar = i;
      }
   }

   return rates_total;
}

void _DrawLabel(string name, datetime t, double price,
                string txt, color clr, ENUM_ANCHOR_POINT anchor)
{
   if (ObjectFind(0, name) >= 0) return;
   ObjectCreate(0, name, OBJ_TEXT, 0, t, price);
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, anchor);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
}

void _DrawBOSLine(string name, datetime t1, datetime t2,
                  double price, color clr, string label)
{
   if (ObjectFind(0, name) >= 0) return;
   // Garis horizontal di level BOS/CHoCH
   ObjectCreate(0, name, OBJ_TREND, 0, t1, price, t2, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
   ObjectSetString(0, name, OBJPROP_TOOLTIP, label);

   // Label teks di ujung kanan
   string lname = name + "_lbl";
   if (ObjectFind(0, lname) < 0)
   {
      ObjectCreate(0, lname, OBJ_TEXT, 0, t2, price);
      ObjectSetString(0, lname, OBJPROP_TEXT, " " + label);
      ObjectSetInteger(0, lname, OBJPROP_COLOR, clr);
      ObjectSetInteger(0, lname, OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, lname, OBJPROP_SELECTABLE, false);
   }
}

void _DeleteObjects()
{
   string prefixes[] = {"SH_","SL_","BOS_","CHoCH_"};
   for (int p = 0; p < 4; p++)
   {
      for (int i = ObjectsTotal(0, 0, -1) - 1; i >= 0; i--)
      {
         string name = ObjectName(0, i);
         if (StringFind(name, prefixes[p]) == 0)
            ObjectDelete(0, name);
      }
   }
}

void OnDeinit(const int reason)
{
   _DeleteObjects();
}
