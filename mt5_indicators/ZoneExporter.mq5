//+------------------------------------------------------------------+
//| ZoneExporter.mq5                                                 |
//| Baca semua Rectangle di chart → export ke Common\Files\zones.csv |
//| Install: copy ke MQL5/Experts, attach ke chart XAUUSD M5 atau M15|
//+------------------------------------------------------------------+
#property copyright ""
#property version   "1.00"
#property description "Export rectangle zones ke CSV untuk TrendBot Python"

input int    UpdateIntervalSec = 5;     // interval update (detik)
input string OutputFilename    = "zones.csv";  // nama file output

datetime _last_update = 0;

int OnInit()
{
   EventSetTimer(UpdateIntervalSec);
   ExportZones();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   ExportZones();
}

void OnTick()
{
   if (TimeCurrent() - _last_update >= UpdateIntervalSec)
   {
      ExportZones();
      _last_update = TimeCurrent();
   }
}

void ExportZones()
{
   int handle = FileOpen(OutputFilename, FILE_WRITE | FILE_CSV | FILE_COMMON, ',');
   if (handle == INVALID_HANDLE)
   {
      Print("ZoneExporter: Gagal buka file ", OutputFilename, " error=", GetLastError());
      return;
   }

   // Header
   FileWrite(handle, "name", "price_high", "price_low", "color_hex", "label", "symbol");

   int total = ObjectsTotal(0, -1, OBJ_RECTANGLE);
   int exported = 0;

   for (int i = 0; i < total; i++)
   {
      string name = ObjectName(0, i, -1, OBJ_RECTANGLE);

      double p1 = ObjectGetDouble(0, name, OBJPROP_PRICE, 0);
      double p2 = ObjectGetDouble(0, name, OBJPROP_PRICE, 1);

      if (p1 == 0 && p2 == 0) continue;

      double zone_high = MathMax(p1, p2);
      double zone_low  = MathMin(p1, p2);

      // Skip zona yang terlalu tipis (< 0.5 pip untuk XAUUSD)
      if (zone_high - zone_low < 0.05) continue;

      color  clr   = (color)ObjectGetInteger(0, name, OBJPROP_COLOR);
      string label = ObjectGetString(0, name, OBJPROP_TEXT);

      // Format warna ke hex string agar mudah dibaca Python
      string clr_hex = StringFormat("#%06X",
         (clr & 0xFF) << 16 | (clr >> 8 & 0xFF) << 8 | clr >> 16);

      FileWrite(handle,
         name,
         DoubleToString(zone_high, 5),
         DoubleToString(zone_low, 5),
         clr_hex,
         label,
         _Symbol
      );
      exported++;
   }

   FileClose(handle);
   // Print("ZoneExporter: ", exported, " zona di-export ke ", OutputFilename);
}
