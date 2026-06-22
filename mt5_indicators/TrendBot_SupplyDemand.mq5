//+------------------------------------------------------------------+
//| TrendBot_SupplyDemand.mq5                                        |
//| Supply & Demand zone otomatis — Rally/Drop Base Rally/Drop       |
//|                                                                  |
//| Pattern:                                                         |
//|  SUPPLY : Rally → Base (konsolidasi) → Drop besar               |
//|  DEMAND : Drop  → Base (konsolidasi) → Rally besar              |
//|                                                                  |
//| Bisa tampilkan banyak zona sekaligus (MaxZones)                 |
//+------------------------------------------------------------------+
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots   0

input int    LookbackBars     = 500;   // bar historis yang di-scan
input int    BaseBarsMin      = 1;     // min bar konsolidasi
input int    BaseBarsMax      = 6;     // max bar konsolidasi
input double ImpulseBodyRatio = 0.50;  // body/range impulse minimum
input double ImpulseBodyMult  = 1.5;   // body impulse >= N × rata-rata body base
input int    MaxZones         = 10;    // max zona per tipe (supply & demand masing-masing)
input bool   ShowMitigated    = true;  // tampilkan zona yang sudah ditembus (lebih gelap)
input color  DemandColor      = C'0,60,0';    // hijau (fresh demand)
input color  SupplyColor      = C'60,0,0';    // merah (fresh supply)
input color  DemandColorUsed  = C'0,25,0';    // hijau redup (demand mitigated)
input color  SupplyColorUsed  = C'25,0,0';    // merah redup (supply mitigated)
input ENUM_LINE_STYLE BorderStyle = STYLE_SOLID;

#define PREFIX "TBot_SD_"

struct SDZone
{
   string   name;
   double   top;
   double   bottom;
   datetime time_start;
   bool     is_demand;
   bool     mitigated;
};

SDZone zones[];
int    zone_count = 0;

int OnInit()
{
   IndicatorSetString(INDICATOR_SHORTNAME, "TrendBot S&D");
   _DeleteAllZones();
   zone_count = 0;
   ArrayResize(zones, MaxZones * 2);
   ChartRedraw();
   return INIT_SUCCEEDED;
}

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[], const double &close[],
                const long &tick_volume[], const long &volume[], const int &spread[])
{
   if (rates_total < LookbackBars + BaseBarsMax + 3) return rates_total;

   if (prev_calculated == 0 || zone_count == 0)
   {
      _DeleteAllZones();
      zone_count = 0;
      _ScanZones(rates_total, time, open, high, low, close);
      _DrawAllZones(time);
   }
   else
   {
      _CheckMitigation(close[rates_total - 1]);
      _RefreshZoneEndTime();
   }

   return rates_total;
}

//───────────────────────────────────────────────────────────────────
// Scan: cari pola Base + Impulse dari kiri ke kanan
//───────────────────────────────────────────────────────────────────
void _ScanZones(const int total, const datetime &time[],
                const double &open[], const double &high[],
                const double &low[], const double &close[])
{
   int demand_count = 0;
   int supply_count = 0;

   int start = MathMax(BaseBarsMax + 3, total - LookbackBars);

   for (int i = start; i < total - 1; i++)
   {
      if (demand_count >= MaxZones && supply_count >= MaxZones) break;

      // ── Candle impulse (candle i+1 setelah base) ─────────────
      int imp = i;
      double body_imp  = MathAbs(close[imp] - open[imp]);
      double range_imp = high[imp] - low[imp];
      if (range_imp < _Point * 5) continue;

      bool bull_imp = close[imp] > open[imp] && body_imp / range_imp >= ImpulseBodyRatio;
      bool bear_imp = close[imp] < open[imp] && body_imp / range_imp >= ImpulseBodyRatio;
      if (!bull_imp && !bear_imp) continue;

      // ── Cari base sebelum impulse ─────────────────────────────
      int    base_end   = imp - 1;
      int    base_start = -1;
      double base_body_sum = 0;
      int    base_count    = 0;

      for (int b = base_end; b >= MathMax(0, imp - BaseBarsMax - 1) && base_count <= BaseBarsMax; b--)
      {
         double body_b  = MathAbs(close[b] - open[b]);
         double range_b = high[b] - low[b];
         if (range_b < _Point * 2) continue;

         double ratio_b = (range_b > 0) ? body_b / range_b : 0;

         // Base: body relatif kecil dibanding range (konsolidasi/doji/small candle)
         if (ratio_b <= 0.70)
         {
            base_body_sum += body_b;
            base_count++;
            base_start = b;
         }
         else
         {
            if (base_count >= BaseBarsMin) break; // cukup base, stop
            else { base_count = 0; base_body_sum = 0; base_start = -1; } // reset
         }
      }

      if (base_count < BaseBarsMin || base_start < 0) continue;

      double avg_base_body = (base_count > 0) ? base_body_sum / base_count : 0;
      if (avg_base_body < _Point) avg_base_body = _Point * 3; // fallback untuk doji

      // Impulse harus lebih besar dari base
      if (body_imp < avg_base_body * ImpulseBodyMult) continue;

      // ── Zona = range seluruh base candle ─────────────────────
      double zone_top    = -DBL_MAX;
      double zone_bottom =  DBL_MAX;
      for (int b = base_start; b <= base_end; b++)
      {
         if (high[b] > zone_top)    zone_top    = high[b];
         if (low[b]  < zone_bottom) zone_bottom = low[b];
      }

      if (zone_top <= zone_bottom) continue;
      if (zone_top - zone_bottom < _Point * 2) continue;

      bool is_demand = bull_imp;

      // Skip jika kuota penuh untuk tipe ini
      if (is_demand && demand_count >= MaxZones) continue;
      if (!is_demand && supply_count >= MaxZones) continue;

      // ── Cek duplikat (zona tumpang tindih, semua tipe) ───────
      bool duplicate = false;
      for (int z = 0; z < zone_count; z++)
      {
         double overlap_top    = MathMin(zones[z].top,    zone_top);
         double overlap_bottom = MathMax(zones[z].bottom, zone_bottom);
         if (overlap_top > overlap_bottom) { duplicate = true; break; }
      }
      if (duplicate) continue;

      // ── Cek mitigation ────────────────────────────────────────
      bool mitigated = false;
      for (int k = imp + 1; k < total; k++)
      {
         if (is_demand && low[k]  <= zone_bottom) { mitigated = true; break; }
         if (!is_demand && high[k] >= zone_top)   { mitigated = true; break; }
      }

      if (mitigated && !ShowMitigated) continue;

      // ── Simpan zona ───────────────────────────────────────────
      string name = PREFIX + (is_demand ? "D_" : "S_") + IntegerToString(base_start);
      if (zone_count < ArraySize(zones))
      {
         zones[zone_count].name       = name;
         zones[zone_count].top        = zone_top;
         zones[zone_count].bottom     = zone_bottom;
         zones[zone_count].time_start = time[base_start];
         zones[zone_count].is_demand  = is_demand;
         zones[zone_count].mitigated  = mitigated;
         zone_count++;

         if (is_demand) demand_count++;
         else           supply_count++;
      }
   }

   PrintFormat("[S&D] Scan selesai: %d zona ditemukan (%d demand, %d supply)",
               zone_count, demand_count, supply_count);
}

//───────────────────────────────────────────────────────────────────
// Gambar semua zona
//───────────────────────────────────────────────────────────────────
void _DrawAllZones(const datetime &time[])
{
   for (int z = 0; z < zone_count; z++)
      _DrawZone(zones[z]);
}

void _DrawZone(SDZone &z)
{
   color col;
   string label;

   if (z.is_demand)
   {
      col   = z.mitigated ? DemandColorUsed : DemandColor;
      label = z.mitigated ? "Demand (used)" : "Demand";
   }
   else
   {
      col   = z.mitigated ? SupplyColorUsed : SupplyColor;
      label = z.mitigated ? "Supply (used)" : "Supply";
   }

   datetime t_end = TimeCurrent() + 86400 * 30;

   // Kotak — OBJPROP_COLOR adalah satu-satunya warna yang efektif untuk fill+border
   string rect = z.name + "_rect";
   if (ObjectFind(0, rect) < 0)
      ObjectCreate(0, rect, OBJ_RECTANGLE, 0, z.time_start, z.top, t_end, z.bottom);
   ObjectSetInteger(0, rect, OBJPROP_COLOR,      col);
   ObjectSetInteger(0, rect, OBJPROP_STYLE,      BorderStyle);
   ObjectSetInteger(0, rect, OBJPROP_WIDTH,      1);
   ObjectSetInteger(0, rect, OBJPROP_FILL,       true);
   ObjectSetInteger(0, rect, OBJPROP_BACK,       true);
   ObjectSetInteger(0, rect, OBJPROP_HIDDEN,     true);
   ObjectSetInteger(0, rect, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, rect, OBJPROP_TIME,  0, z.time_start);
   ObjectSetDouble(0,  rect, OBJPROP_PRICE, 0, z.top);
   ObjectSetInteger(0, rect, OBJPROP_TIME,  1, t_end);
   ObjectSetDouble(0,  rect, OBJPROP_PRICE, 1, z.bottom);
   ObjectSetString(0,  rect, OBJPROP_TOOLTIP,
                   label + " | " + DoubleToString(z.top, _Digits) +
                   " — " + DoubleToString(z.bottom, _Digits));

   // Label
   string lbl = z.name + "_lbl";
   if (ObjectFind(0, lbl) < 0)
      ObjectCreate(0, lbl, OBJ_TEXT, 0, z.time_start, z.top);
   ObjectSetString(0,  lbl, OBJPROP_TEXT,      " " + label);
   ObjectSetInteger(0, lbl, OBJPROP_COLOR,     col);
   ObjectSetInteger(0, lbl, OBJPROP_FONTSIZE,  8);
   ObjectSetString(0,  lbl, OBJPROP_FONT,      "Arial Bold");
   ObjectSetInteger(0, lbl, OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0, lbl, OBJPROP_BACK,      false);
}

//───────────────────────────────────────────────────────────────────
// Update: cek mitigation & perpanjang kotak ke kanan
//───────────────────────────────────────────────────────────────────
void _CheckMitigation(double current_price)
{
   for (int z = 0; z < zone_count; z++)
   {
      if (zones[z].mitigated) continue;

      bool hit = zones[z].is_demand
                 ? current_price <= zones[z].bottom
                 : current_price >= zones[z].top;
      if (!hit) continue;

      zones[z].mitigated = true;

      if (!ShowMitigated)
      {
         ObjectDelete(0, zones[z].name + "_rect");
         ObjectDelete(0, zones[z].name + "_lbl");
      }
      else
      {
         color col   = zones[z].is_demand ? DemandColorUsed : SupplyColorUsed;
         string label = zones[z].is_demand ? "Demand (used)" : "Supply (used)";
         ObjectSetInteger(0, zones[z].name + "_rect", OBJPROP_COLOR, col);
         ObjectSetString(0,  zones[z].name + "_lbl",  OBJPROP_TEXT,  " " + label);
         ObjectSetInteger(0, zones[z].name + "_lbl",  OBJPROP_COLOR, col);
      }
   }
}

void _RefreshZoneEndTime()
{
   datetime t_end = TimeCurrent() + 86400 * 30;
   for (int z = 0; z < zone_count; z++)
   {
      if (!zones[z].mitigated || ShowMitigated)
         ObjectSetInteger(0, zones[z].name + "_rect", OBJPROP_TIME, 1, t_end);
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
