//+------------------------------------------------------------------+
//| TrendBot_SupplyDemand.mq5                                        |
//| Supply & Demand zone otomatis — pola Base + Impulse              |
//|                                                                  |
//| Logika deteksi:                                                  |
//|  DEMAND zone: candle impulse bullish besar keluar dari base      |
//|               (beberapa candle kecil konsolidasi)               |
//|  SUPPLY zone: candle impulse bearish besar keluar dari base      |
//|                                                                  |
//| Pasang di H1 atau M15                                           |
//+------------------------------------------------------------------+
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots   0

input int    LookbackBars     = 300;   // bar historis yang di-scan
input int    BaseBars         = 3;     // min bar konsolidasi (base)
input double ImpulseBodyMult  = 2.5;   // body impulse >= N × rata-rata body base
input int    MaxZones         = 30;    // max zona yang ditampilkan
input bool   ShowMitigated    = false; // tampilkan zona yang sudah ditembus harga
input color  DemandColor      = C'0,60,0';    // hijau gelap
input color  SupplyColor      = C'80,0,0';    // merah gelap
input color  DemandBorder     = clrLime;
input color  SupplyBorder     = clrRed;
input int    ZoneAlpha        = 60;    // transparansi kotak (0-255)
input ENUM_LINE_STYLE BorderStyle = STYLE_SOLID;

#define PREFIX "TBot_SD_"

struct SDZone
{
   string   name;
   double   top;
   double   bottom;
   datetime time_start;
   datetime time_end;
   bool     is_demand;
   bool     mitigated;
};

SDZone zones[];
int    zone_count = 0;

int OnInit()
{
   IndicatorSetString(INDICATOR_SHORTNAME, "TrendBot S&D");
   ArrayResize(zones, MaxZones);
   return INIT_SUCCEEDED;
}

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{
   if (rates_total < LookbackBars + BaseBars + 2) return rates_total;

   // Full recalc hanya jika belum ada zone atau bar baru masuk
   if (prev_calculated == 0 || zone_count == 0)
   {
      _DeleteAllZones();
      zone_count = 0;
      _ScanZones(rates_total, time, open, high, low, close);
   }
   else
   {
      // Update mitigasi saja
      _CheckMitigation(close[rates_total - 1]);
   }

   return rates_total;
}

void _ScanZones(const int total, const datetime &time[],
                const double &open[], const double &high[],
                const double &low[], const double &close[])
{
   int start = MathMax(BaseBars + 2, total - LookbackBars);

   for (int i = start; i < total - 1 && zone_count < MaxZones; i++)
   {
      // ── Hitung body candle i ─────────────────────────────────
      double body_i = MathAbs(close[i] - open[i]);
      double range_i = high[i] - low[i];
      if (range_i == 0) continue;

      // Cek apakah candle i adalah impulse (body besar)
      bool bull_impulse = close[i] > open[i] && body_i / range_i >= 0.6;
      bool bear_impulse = close[i] < open[i] && body_i / range_i >= 0.6;
      if (!bull_impulse && !bear_impulse) continue;

      // ── Cari base sebelum impulse (BaseBars candle ke kiri) ──
      int base_start = -1, base_end = i - 1;
      double base_body_sum = 0;
      int    base_count    = 0;

      for (int b = i - 1; b >= MathMax(0, i - BaseBars - 4) && base_count < BaseBars + 3; b--)
      {
         double body_b  = MathAbs(close[b] - open[b]);
         double range_b = high[b] - low[b];
         if (range_b == 0) continue;

         // Base candle: body kecil (konsolidasi)
         if (body_b / range_b <= 0.55)
         {
            base_body_sum += body_b;
            base_count++;
            base_start = b;
         }
         else break; // keluar jika ketemu candle besar
      }

      if (base_count < BaseBars) continue;

      double avg_base_body = base_body_sum / base_count;
      if (avg_base_body == 0) continue;
      if (body_i < avg_base_body * ImpulseBodyMult) continue;

      // ── Tentukan zona (top & bottom dari range base) ──────────
      double zone_top = -DBL_MAX, zone_bottom = DBL_MAX;
      for (int b = base_start; b <= base_end; b++)
      {
         if (high[b] > zone_top)    zone_top    = high[b];
         if (low[b]  < zone_bottom) zone_bottom = low[b];
      }

      bool is_demand = bull_impulse;

      // ── Cek mitigation (harga pernah kembali ke zona) ─────────
      bool mitigated = false;
      for (int k = i + 1; k < total; k++)
      {
         if (is_demand && low[k] <= zone_top)    { mitigated = true; break; }
         if (!is_demand && high[k] >= zone_bottom){ mitigated = true; break; }
      }

      if (mitigated && !ShowMitigated) continue;

      // ── Simpan & gambar zona ───────────────────────────────────
      string name = PREFIX + (is_demand ? "D_" : "S_") + IntegerToString(i);
      zones[zone_count].name       = name;
      zones[zone_count].top        = zone_top;
      zones[zone_count].bottom     = zone_bottom;
      zones[zone_count].time_start = time[base_start];
      zones[zone_count].time_end   = 0; // extend ke kanan
      zones[zone_count].is_demand  = is_demand;
      zones[zone_count].mitigated  = mitigated;
      zone_count++;

      _DrawZone(name, time[base_start], zone_top, zone_bottom, is_demand, mitigated);
   }
}

void _DrawZone(string name, datetime t_start,
               double top, double bottom,
               bool is_demand, bool mitigated)
{
   color fill   = is_demand ? DemandColor  : SupplyColor;
   color border = is_demand ? DemandBorder : SupplyBorder;
   string label = is_demand ? "Demand" : "Supply";

   if (mitigated)
   {
      fill   = clrDimGray;
      border = clrGray;
      label += " (used)";
   }

   // Kotak zona
   string rect_name = name + "_rect";
   if (ObjectFind(0, rect_name) < 0)
      ObjectCreate(0, rect_name, OBJ_RECTANGLE, 0, t_start, top, TimeCurrent() + 86400 * 30, bottom);
   ObjectSetInteger(0, rect_name, OBJPROP_COLOR,     border);
   ObjectSetInteger(0, rect_name, OBJPROP_STYLE,     BorderStyle);
   ObjectSetInteger(0, rect_name, OBJPROP_WIDTH,     1);
   ObjectSetInteger(0, rect_name, OBJPROP_FILL,      true);
   ObjectSetInteger(0, rect_name, OBJPROP_BACK,      true);
   ObjectSetInteger(0, rect_name, OBJPROP_BGCOLOR,   fill);
   ObjectSetString(0,  rect_name, OBJPROP_TOOLTIP,   label + " | " +
                   DoubleToString(top, _Digits) + " — " + DoubleToString(bottom, _Digits));
   ObjectSetInteger(0, rect_name, OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0, rect_name, OBJPROP_TIME,  0, t_start);
   ObjectSetDouble(0,  rect_name, OBJPROP_PRICE, 0, top);
   ObjectSetInteger(0, rect_name, OBJPROP_TIME,  1, TimeCurrent() + 86400 * 30);
   ObjectSetDouble(0,  rect_name, OBJPROP_PRICE, 1, bottom);

   // Label teks di tepi kiri zona
   string lbl_name = name + "_lbl";
   if (ObjectFind(0, lbl_name) < 0)
      ObjectCreate(0, lbl_name, OBJ_TEXT, 0, t_start, top);
   ObjectSetString(0,  lbl_name, OBJPROP_TEXT,     " " + label);
   ObjectSetInteger(0, lbl_name, OBJPROP_COLOR,    border);
   ObjectSetInteger(0, lbl_name, OBJPROP_FONTSIZE, 8);
   ObjectSetString(0,  lbl_name, OBJPROP_FONT,     "Arial Bold");
   ObjectSetInteger(0, lbl_name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, lbl_name, OBJPROP_BACK,     false);
}

void _CheckMitigation(double current_price)
{
   for (int z = 0; z < zone_count; z++)
   {
      if (zones[z].mitigated) continue;
      bool hit = zones[z].is_demand
                 ? current_price <= zones[z].top
                 : current_price >= zones[z].bottom;
      if (hit)
      {
         zones[z].mitigated = true;
         if (!ShowMitigated)
         {
            ObjectDelete(0, zones[z].name + "_rect");
            ObjectDelete(0, zones[z].name + "_lbl");
         }
         else
         {
            // Ubah warna jadi abu
            ObjectSetInteger(0, zones[z].name + "_rect", OBJPROP_COLOR,   clrGray);
            ObjectSetInteger(0, zones[z].name + "_rect", OBJPROP_BGCOLOR, clrDimGray);
         }
      }
   }
}

void _DeleteAllZones()
{
   for (int i = ObjectsTotal(0, 0, -1) - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, -1);
      if (StringFind(name, PREFIX) == 0)
         ObjectDelete(0, name);
   }
}

void OnDeinit(const int reason)
{
   _DeleteAllZones();
   ChartRedraw();
}
