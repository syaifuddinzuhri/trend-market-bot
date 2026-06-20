# TrendBot — XAUUSD Trend Following Bot

> **v1.3.1** — [Lihat CHANGELOG](CHANGELOG.md)

Bot trading otomatis untuk **XAUUSD** berbasis trend following multi-timeframe.
Dijalankan di **MetaTrader 5** (Windows), notifikasi via **Telegram**.

---

## Arsitektur Timeframe

| Timeframe | Fungsi |
|-----------|--------|
| H4 | Filter arah tren utama |
| H1 | Konfirmasi pullback + momentum (ADX, ATR) |
| M15 | Entry trigger (BOS / CHoCH + candlestick) |

---

## Cara Kerja Lengkap

### Step 1 — Filter Tren H4
```
BULLISH : EMA50 > EMA200  DAN  Close > EMA200
BEARISH : EMA50 < EMA200  DAN  Close < EMA200
NO_TRADE: salah satu syarat tidak terpenuhi → skip
```

### Step 2 — Filter Momentum H1
```
ADX ≥ 25  (BOS setup)   — tren sudah terkonfirmasi
ADX ≥ 30  (CHoCH setup) — threshold lebih tinggi karena sinyal lebih awal
ATR > ATR_MA            — volatilitas cukup untuk entry
```

### Step 3 — Pullback H1
```
Harga menyentuh atau mendekati EMA20 / EMA50
(toleransi = 0.3 × ATR)
```

### Step 4 — Market Structure M15 (BOS & CHoCH)
```
BULLISH_BOS   : Uptrend (HH+HL) → harga break above swing HH terakhir    [STRONG]
BULLISH_CHoCH : Downtrend (LH+LL) → harga break above swing LH terakhir  [MODERATE]
BEARISH_BOS   : Downtrend (LH+LL) → harga break below swing LL terakhir  [STRONG]
BEARISH_CHoCH : Uptrend (HH+HL) → harga break below swing HL terakhir    [MODERATE]
```

### Step 5 — Konfirmasi Candlestick M15
```
BUY  : Bullish Engulfing  atau  Bullish Pin Bar
SELL : Bearish Engulfing  atau  Bearish Pin Bar

Pin Bar  : wick minimal 2× body, close di 30% area terjauh
Engulfing: body candle saat ini menelan body candle sebelumnya
```

### Step 6 — Pre-checks
```
✅ Jam trading aktif    : 13:00 – 01:00 WIB
✅ Tidak ada news lock  : ±30 menit dari FOMC / NFP / CPI / GDP
✅ Daily trade limit    : belum mencapai MAX_TRADES_PER_DAY
✅ Tidak ada posisi induk yang sedang terbuka
```

---

## Multi-Entry Mid-Session

Setelah entry pertama, bot bisa membuka posisi tambahan selama tren masih valid.

### Alur Logika

```
Tidak ada posisi?
  → Cari PRIMARY signal (setup lengkap multi-TF)

Ada posisi < MAX_CONCURRENT_POSITIONS?
  → Tunggu MIN_ENTRY_INTERVAL menit sejak entry terakhir
  → Cek jarak harga MIN_ENTRY_DISTANCE_ATR dari posisi yang ada
  → Cari CONTINUATION signal (harus searah posisi yang ada)

Sudah MAX_CONCURRENT_POSITIONS?
  → Skip pencarian signal, kelola posisi yang ada saja
```

### Dua Jenis Continuation Signal

**EMA Retest M15**
```
1. BOS sudah terkonfirmasi dalam 20 candle M15 terakhir
2. Harga pullback menyentuh EMA20 M15
3. Terbentuk Pin Bar atau Engulfing
→ Lot: 80% dari lot normal
```

**HLC Continuation** (Higher Low / Lower High)
```
1. Swing Low baru di H1 lebih tinggi dari sebelumnya (Higher Low)
   atau Swing High baru lebih rendah (Lower High)
2. Struktur M15 masih bullish/bearish (CHoCH cukup)
3. Candle konfirmasi M15
→ Lot: 80% dari lot normal
```

### Guard Anti-Overtrading

| Parameter | Default | Fungsi |
|-----------|---------|--------|
| `MAX_CONCURRENT_POSITIONS` | 2 | Max posisi induk bersamaan |
| `MIN_ENTRY_INTERVAL` | 30 mnt | Cooldown antar entry baru |
| `MIN_ENTRY_DISTANCE_ATR` | 1.0× | Jarak harga min dari posisi lain |

---

## Money Management

### SL Dinamis (ATR-based)
```
BUY  → SL = Swing Low H1  − (ATR_H1 × 1.5)
SELL → SL = Swing High H1 + (ATR_H1 × 1.5)

Buffer adaptif: makin volatile → SL makin jauh secara otomatis
```

### TP 3-Tier + Trailing
```
Entry    → buka 100% posisi
TP1 (1R) → tutup 30% | SL pindah ke entry (risk = 0)
TP2 (2R) → tutup 40% | aktifkan trailing stop
TP3      → sisa 30% exit saat candle H1 close cross EMA20
```

### Pyramid Entry
```
Kondisi  : BE sudah set + TP1 sudah hit + ADX masih kuat + pullback baru H1
Lot      : 50% dari lot posisi induk
SL       : entry posisi induk (risk = 0 di posisi induk)
Max      : 1 pyramid per trade induk
```

### Lot Size
```
FIXED_LOT > 0 → pakai lot tetap (misal 0.02)
FIXED_LOT = 0 → auto hitung dari RISK_PERCENT % balance
```

---

## Estimasi Frekuensi Entry

| Kondisi Pasar | Entry per Session |
|---------------|------------------|
| Trending kuat (ADX > 35) | 2–3x |
| Trending normal | 1–2x |
| Sideways / choppy | 0x (semua filter block) |

---

## Struktur Project

```
trendbot/
├── main.py                    Entry point utama bot
├── config.py                  Semua konfigurasi dari .env
├── .env                       Konfigurasi akun & parameter trading
├── .env.example               Template konfigurasi
├── requirements.txt           Dependencies Python
│
├── bot/
│   ├── connector.py           Koneksi & reconnect MT5
│   ├── indicators.py          EMA, ADX, ATR — fetch candle H4/H1/M15
│   ├── trend.py               Filter tren H4 (EMA50 vs EMA200)
│   ├── pullback.py            Deteksi pullback ke EMA20/50 H1
│   ├── structure.py           BOS & CHoCH — HH/HL/LH/LL detection
│   ├── candlestick.py         Pin Bar & Engulfing detection
│   ├── signals.py             Agregasi semua filter → signal dict
│   ├── risk.py                Lot size & SL calculation (ATR-based)
│   ├── trade.py               Open/modify/partial close + pyramid + trailing
│   ├── session.py             Filter jam WIB (13:00 – 01:00)
│   ├── news_filter.py         News lock — calendar otomatis + manual override
│   ├── calendar.py            Fetch ForexFactory, cache JSON, upcoming events
│   ├── logger.py              Logging ke CSV + SQLite
│   └── telegram.py            Notifikasi signal/TP/SL/BE/pyramid/trail
│
├── backtest/
│   ├── engine.py              Backtesting bar-by-bar dari data MT5
│   ├── report.py              Generate laporan HTML + CSV
│   └── run_backtest.py        CLI entry point backtest
│
├── dashboard/
│   └── app.py                 Dashboard web Flask (localhost:5000)
│
├── logs/
│   ├── trades.db              SQLite — semua aktivitas trade
│   ├── trades.csv             CSV — backup log
│   └── calendar_cache.json    Cache jadwal news (auto-refresh tiap 6 jam)
│
├── chart/
│   ├── plotter.py             Builder chart Plotly (candlestick, EMA, trendline, markers)
│   ├── trendlines.py          Swing detection, trendline builder, S/R cluster
│   ├── run_chart.py           CLI chart generator
│   └── output/                File HTML chart (tidak di-commit)
│
├── setup.bat                  Install dependencies (jalankan sekali)
├── start_bot.bat              Jalankan bot trading
├── start_chart.bat            Wizard chart interaktif
├── start_dashboard.bat        Jalankan dashboard monitoring
└── run_backtest.bat           Wizard interaktif backtest
```

---

## Konfigurasi `.env`

```env
# Salin .env.example → .env lalu isi nilai yang kosong

# ── MT5 Account ──────────────────────────────────────────────────
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=Broker-Server

# ── Trading Settings ─────────────────────────────────────────────
SYMBOL=XAUUSD
ACCOUNT_CURRENCY=IDR          # atau USD
RISK_PERCENT=1.0              # % balance per trade (jika FIXED_LOT=0)
FIXED_LOT=0.02                # lot tetap; 0 = auto dari RISK_PERCENT
MAGIC_NUMBER=202406
SLIPPAGE=20

# ── Session Filter (WIB / UTC+7) ─────────────────────────────────
SESSION_START_WIB=13          # 13:00 WIB
SESSION_END_WIB=1             # 01:00 WIB

# ── Telegram ─────────────────────────────────────────────────────
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# ── SL Dinamis ───────────────────────────────────────────────────
ATR_SL_MULTIPLIER=1.5         # SL = swing H1 ± ATR × multiplier

# ── TP 3-Tier ────────────────────────────────────────────────────
TP1_R=1.0                     # tutup 30% di 1R
TP1_PCT=0.30
TP2_R=2.0                     # tutup 40% di 2R, sisa trailing
TP2_PCT=0.40
BREAKEVEN_R=1.0               # pindah SL ke entry saat profit = 1R

# ── Pyramid ──────────────────────────────────────────────────────
PYRAMID_ENABLED=true
PYRAMID_LOT_RATIO=0.5         # lot pyramid = lot_awal × 0.5
MAX_PYRAMID=1

# ── Multi-Entry Mid-Session ──────────────────────────────────────
MAX_CONCURRENT_POSITIONS=2    # max posisi induk bersamaan
MIN_ENTRY_INTERVAL=30         # cooldown antar entry (menit)
MIN_ENTRY_DISTANCE_ATR=1.0    # jarak harga min antar entry (× ATR H1)

# ── Trade Limits ─────────────────────────────────────────────────
MAX_TRADES_PER_DAY=5          # 0 = unlimited
ADX_MIN=25                    # threshold ADX untuk BOS entry
```

---

## Cara Install & Jalankan (Windows)

### Setup Awal (sekali saja)
```batch
1. Jalankan setup.bat
2. Isi .env dengan data akun MT5 dan Telegram
```

### Chart Visualisasi
```batch
start_chart.bat
→ Pilih timeframe (M15 / H1 / H4 / D1)
→ Input jumlah bars
→ Browser otomatis buka chart interaktif

# Atau via CLI:
python chart/run_chart.py --tf H1 --bars 300
python chart/run_chart.py --tf M15 --bars 150 --no-bos
```

**Isi chart:**
- Candlestick + EMA Ribbon (20/50/100/200)
- Trendline otomatis dari swing high & low
- Label HH / HL / LH / LL di setiap swing point
- Marker BOS & CHoCH
- S/R level horizontal (cluster swing points)
- Entry/Exit dari trade log (▲ BUY, ▼ SELL, ★ TP, ✕ SL)
- Panel ADX + panel ATR vs ATR_MA
- Draw mode aktif — bisa gambar garis manual di browser

### Jalankan Bot
```batch
1. Buka MT5 → login dengan akun yang sama di .env
2. Jalankan start_bot.bat
```

### Dashboard Monitoring
```batch
start_dashboard.bat
→ Browser otomatis buka http://localhost:5000
```

### Backtest
```batch
run_backtest.bat
→ Input tanggal start & end
→ Laporan HTML otomatis terbuka di browser
```

---

## Notifikasi Telegram

| Event | Isi Notifikasi |
|-------|----------------|
| 🟢/🔴 Signal | Direction, struktur (BOS/CHoCH), pattern, entry, SL, TP1, TP2, lot |
| ✅ TP1 hit | Partial close 30%, info breakeven aktif |
| ✅ TP2 hit | Partial close 40%, trailing aktif |
| 🏁 Trail exit | Sisa 30% exit via EMA20 H1 |
| ❌ SL hit | Loss notification + PnL |
| 🔄 Continuation | EMA Retest / HLC signal, lot 80%, searah posisi yang ada |
| 📐 Pyramid | Posisi ke-2 dibuka, info parent ticket |
| 🔁 Breakeven | SL dipindah ke entry |

---

## Economic Calendar Otomatis

Bot fetch jadwal news **High-Impact USD** dari ForexFactory setiap 6 jam.

```
Events yang difilter:
  FOMC, Federal Funds Rate, Non-Farm Payroll, CPI,
  PPI, GDP, Unemployment Rate, Interest Rate, Jackson Hole

Cache   : logs/calendar_cache.json
Refresh : maksimal sekali per jam (hard rate-limit — sesuai kebijakan ForexFactory)
Fallback: jika internet mati → pakai cache terakhir
Manual  : tambahkan event di bot/news_filter.py (NEWS_EVENTS_UTC)
```

---

## Backtesting

Engine menggunakan data historis langsung dari MT5 — tidak perlu file eksternal.

```batch
# Via wizard interaktif
run_backtest.bat

# Via command line
python backtest/run_backtest.py --from 2024-01-01 --to 2024-12-31 --balance 15000000
```

Output:
```
Total Trades  : 47
Win Rate      : 57.4%
Total R       : +38.2R
Profit Factor : 1.87
Max Drawdown  : 8.3R
Expectancy    : 0.81R/trade

→ logs/backtest_report.html   (equity curve + trade list)
→ logs/backtest_trades.csv    (raw data)
```

> MT5 harus dibuka saat backtest karena data diambil langsung dari terminal.

---

## Dashboard Monitoring

Buka `http://localhost:5000` — auto-refresh setiap 10 detik.

```
┌─ Account ──────────────────────────────────┐
│ Balance | Equity | Margin | Open Trades    │
└────────────────────────────────────────────┘

[Session: ON]  [News: OK]

┌─ Equity Curve ─────────────────────────────┐
│ Grafik cumulative PnL dari trade history   │
└────────────────────────────────────────────┘

┌─ Posisi Terbuka ────────────────────────────┐
│ Ticket | Dir | Lot | Entry | SL | TP | PnL │
└─────────────────────────────────────────────┘

┌─ Trade Hari Ini ────────────────────────────┐
│ Waktu | Dir | Entry | Result | PnL          │
└─────────────────────────────────────────────┘

┌─ Upcoming News (±60 menit) ────────────────┐
│ +15m — CPI (2025-07-10 12:30)             │
└────────────────────────────────────────────┘
```

---

## Target Performa

| Metrik | Target |
|--------|--------|
| Win Rate | 45–60% |
| Risk per trade | 1% balance |
| Risk Reward | 1:2 minimum (TP2), unlimited trailing |
| Max Drawdown | < 15% |
| Profit Factor | > 1.5 |
| Expectancy | > 0.5R per trade |

---

## Catatan Penting

- MT5 **harus dibuka** dan login sebelum bot dijalankan
- Bot mencoba **reconnect otomatis** jika koneksi MT5 terputus
- Untuk **prop firm**: sesuaikan `RISK_PERCENT` dan `MAX_TRADES_PER_DAY` dengan aturan challenge
- `FIXED_LOT` disarankan untuk prop firm agar lot konsisten
- News filter berjalan otomatis — tidak perlu isi manual kecuali ada event darurat
- Pyramid entry **tidak menambah risk** karena SL di entry posisi induk (sudah breakeven)
