# Changelog

Semua perubahan signifikan pada project ini didokumentasikan di sini.
Format mengacu pada [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.9.5] — 2026-06-22

### Fixed
- TP1/TP2 di alert manual salah (terlalu kecil) — pip_size dihitung dari `point * 10` tanpa floor, untuk XAUUSDm (point=0.001) hasilnya 0.01 bukan 0.1. Sekarang pakai `max(point * 10, 0.1)`

---

## [1.9.4] — 2026-06-22

### Fixed
- Alert manual spam — cooldown key menyertakan `passed` sehingga dianggap berbeda saat nilai berubah (6→7→6). Key sekarang hanya `(symbol, direction)` — satu alert per arah per 5 menit

---

## [1.9.3] — 2026-06-22

### Changed
- `ALERT_COOLDOWN_SECONDS` dipindah ke `.env` — bisa diubah tanpa restart bot (default 300 detik)
- Set `ALERT_COOLDOWN_SECONDS=0` di `.env` lalu restart untuk reset cooldown instan

---

## [1.9.2] — 2026-06-22

### Fixed
- Alert manual Telegram tidak pernah terkirim — `telegram` module tidak diimport di `bot/signals.py`
- Cooldown `_alert_sent_at` sekarang hanya di-set setelah notif berhasil terkirim (sebelumnya di-set dulu sehingga cooldown jalan meski kirim gagal)

---

## [1.9.1] — 2026-06-22

### Changed
- Alert manual Telegram dikirim mulai **6/8 filter** (sebelumnya 7/8)

---

## [1.9.0] — 2026-06-22

### Added
- **Alert manual entry via Telegram** — notif otomatis saat filter >= 7/8
  - Dikirim saat `scan_log()` mendeteksi 7 atau 8 filter lolos
  - Isi notif: arah, ADX, ATR, struktur, candle, proyeksi entry/SL/TP1/TP2, dan filter yang belum lolos
  - Throttle 5 menit (`ALERT_COOLDOWN_SECONDS=300`) — tidak spam tiap cycle
  - Threshold dapat disesuaikan via `ALERT_MIN_FILTERS` (default 7) di `bot/signals.py`
- `bot/telegram.py`: fungsi `notify_alert_manual()`
- `bot/signals.py`: variabel `_alert_sent_at`, `ALERT_COOLDOWN_SECONDS`, `ALERT_MIN_FILTERS`

---

## [1.8.0] — 2026-06-22

### Added
- **Re-entry after TP** — bot otomatis re-entry searah setelah posisi tutup profit
  - Setelah TP hit, `record_tp_exit()` menyimpan konteks (arah, harga, waktu)
  - Pada cycle berikutnya (posisi kosong), `evaluate_reentry()` dievaluasi sebelum pending order
  - Syarat lebih ringan dari PRIMARY: tidak butuh BOS/CHoCH — cukup trend H4 + ADX + ATR + pullback H1 + candle M5/M15
  - Window re-entry: `REENTRY_WINDOW_MINUTES` (default 90 menit)
  - Batas re-entry per sesi tren: `REENTRY_MAX_COUNT` (default 2)
  - Jika SL hit (bukan TP), `clear_reentry()` dipanggil — tren dianggap berbalik, re-entry dibatalkan
  - Toggle via `REENTRY_ENABLED=true/false` di `.env`
- `bot/trade.py`: fungsi `record_tp_exit()`, `get_reentry_context()`, `clear_reentry()`
- `bot/signals.py`: fungsi `evaluate_reentry()`
- `config.py`: parameter `REENTRY_ENABLED`, `REENTRY_WINDOW_MINUTES`, `REENTRY_MAX_COUNT`

### Notes
- Strategi PRIMARY, CONTINUATION, dan pending order tidak berubah
- Re-entry hanya aktif jika PRIMARY signal tidak ditemukan (prioritas tetap PRIMARY)

---

## [1.7.0] — 2026-06-22

### Added
- **TrendBot Scalper** — bot terpisah (`scalper.py`) untuk grid entry M5
  - Deteksi S&D zone otomatis dari data M5 (Python, tanpa MT5 indicator)
  - Pasang `SCALP_GRID_COUNT` pending order (Sell/Buy Limit) di dalam zona sekaligus
  - Total lot dibagi rata: `SCALP_LOT / SCALP_GRID_COUNT` per order
  - SL & TP dalam pip: `SCALP_SL_PIPS` dan `SCALP_TP_PIPS` (default 8:8, 1:1)
  - Auto-cancel pending setelah `SCALP_EXPIRY_MINUTES` menit (default 20)
  - Filter ADX M5 minimum (`SCALP_ADX_MIN=20`)
  - Cooldown 5 menit setelah grid dipasang
  - Magic number terpisah (`SCALP_MAGIC=202407`) — tidak konflik dengan bot utama
  - Notif Telegram saat grid dipasang: zona, jumlah order, lot, SL/TP, expiry
- `scalp/zones.py` — deteksi S&D zone dari OHLC Python
- `scalp/grid.py` — place/cancel/manage grid pending orders
- `scalp_config.py` — konfigurasi scalper dari `.env`
- `start_scalper.bat` — launcher Windows untuk scalper
- Parameter `.env` baru: `SCALP_*` (lihat `.env.example`)

---

## [1.6.0] — 2026-06-22

### Added
- **Analisa market otomatis ke Telegram setiap 30 menit** — format lengkap:
  - Trend H4 (BUY/SELL/SIDEWAYS)
  - ADX + ATR H1
  - Struktur M15 (BOS↑/BOS↓/CHoCH)
  - Status filter `X/8` dengan emoji status (🟢/🔥/⏳/💤)
  - Jika ada posisi terbuka: Entry / Sekarang / PnL floating / SL buffer / pip ke TP1 / TP2 / Lot
- `notify_analysis()` di `bot/telegram.py`
- `build_analysis()` di `bot/signals.py` — kumpulkan semua data analisa tanpa side effect
- `_send_analysis()` di `main.py` — dipanggil setiap `ANALYSIS_INTERVAL=1800` detik
- **Notifikasi LIMIT FILLED** — ketika pending order ter-fill, bot kirim notif `✅ LIMIT FILLED BUY/SELL` dengan Entry/SL/TP1/TP2/Lot

---

## [1.5.5] — 2026-06-22

### Added
- **Notifikasi LIMIT FILLED** — ketika pending order ter-fill (masuk posisi), bot kirim notif Telegram `✅ LIMIT FILLED BUY/SELL` dengan Entry/SL/TP1/TP2/Lot. Sebelumnya tidak ada notif sama sekali saat pending order jadi market order.

---

## [1.5.4] — 2026-06-22

### Fixed
- **Spam pending order (root cause ke-2)** — `manage_pending_orders()` sebelumnya early-return jika `_pending_state` kosong (misal setelah restart), sehingga tidak bisa detect pending yang sudah ada di MT5. Sekarang function query langsung ke MT5 (`orders_get()`), tidak bergantung in-memory state. Juga menambah recovery: pending order yang ditemukan di MT5 tapi tidak ada di `_pending_state` langsung di-sync otomatis.
- **Debug logging `get_pending_count()`** — tambah log `[PEND] orders_get() → N total, M bot pending` agar mudah diagnosa masalah koneksi MT5

---

## [1.5.3] — 2026-06-22

### Fixed
- **Spam pending order** — `has_pending_for_direction()` dan `get_pending_count()` sekarang cek langsung ke MT5 orders (bukan hanya `_pending_state` in-memory yang hilang saat restart). Mencegah bot pasang pending order duplikat setiap cycle.

---

## [1.5.2] — 2026-06-22

### Fixed
- **Spam Telegram pending order** — notif Telegram pending hanya dikirim sekali saat order benar-benar terpasang di MT5, tidak dikirim ulang setiap cycle
- **SL terlalu lebar** — tiga perbaikan sekaligus:
  1. `ATR_SL_MULTIPLIER` diturunkan default `1.5 → 1.0`
  2. SL dihitung dari swing **M5** (bukan H1) jika `df_m5` tersedia → jarak lebih ketat
  3. `MAX_SL_POINTS=30.0` — cap maksimal SL distance, lindungi margin pada modal kecil
- `SWING_LOOKBACK_M5` parameter baru untuk mengatur lookback swing M5

---

## [1.5.1] — 2026-06-22

### Fixed
- **Pending order level salah** — SELL LIMIT dipasang di bawah harga (tidak valid di MT5). Sekarang bot memilih EMA pertama yang VALID: untuk SELL LIMIT harus di atas harga, untuk BUY LIMIT harus di bawah harga. Urutan coba: EMA20 → EMA50 → EMA100 H1
- Jika tidak ada EMA yang valid, bot log info dan tidak pasang pending

---

## [1.5.0] — 2026-06-22

### Added
- **Pending Order otomatis (Buy Limit / Sell Limit)** — bot pasang limit order di level EMA20 H1 saat 5+ filter lolos tapi market signal belum terpenuhi
- `place_pending_order()` di `bot/trade.py` — kirim ORDER_TYPE_BUY_LIMIT / SELL_LIMIT ke MT5 dengan expiry otomatis
- `cancel_pending_order()` — cancel satu pending order dan hapus dari registry
- `manage_pending_orders()` — dipanggil setiap cycle, auto-cancel jika:
  - Trend berbalik arah
  - Session tutup
  - News lock aktif
  - Harga sudah terlalu jauh dari level (> PENDING_MAX_DISTANCE_ATR × ATR)
- `has_pending_for_direction()` — cegah duplikasi pending order
- `evaluate_pending()` di `bot/signals.py` — evaluasi kondisi untuk pending (session + news + trend + ADX + ATR)
- `_place_pending()` di `main.py` — hitung SL/TP/lot dan pasang limit
- Parameter baru di `.env`: `PENDING_ENABLED`, `PENDING_EXPIRY_MINUTES`, `PENDING_MAX_DISTANCE_ATR`

### Changed
- `_run_signal_cycle()`: jika tidak ada market signal dan no open positions → coba pasang pending limit
- Jika market signal muncul saat ada pending → cancel pending dulu, lalu market order

---

## [1.4.2] — 2026-06-22

### Changed
- **scan_log** tampilkan ATR_MA di samping ATR: `ATR=19.76/MA=23.10❌` agar mudah debug kenapa filter gagal

---

## [1.4.1] — 2026-06-22

### Changed
- **ATR filter dilonggarkan** — kondisi sebelumnya `ATR > ATR_MA` (ketat), sekarang `ATR >= ATR_MA × ATR_MA_RATIO`
- Default `ATR_MA_RATIO=0.85` → ATR boleh hingga 15% di bawah MA, menangkap setup post-impulse yang sebelumnya di-skip
- Parameter `ATR_MA_RATIO` bisa diatur via `.env` (0.0 = nonaktifkan filter, 1.0 = ketat seperti semula)
- Log skip ATR lebih informatif: `ATR (4.15) < ATR_MA×0.85 (4.07) — skip`

---

## [1.4.0] — 2026-06-22

### Added
- **M5 entry trigger** — timeframe M5 ditambah sebagai candle konfirmasi entry (PinBar/Engulfing), menggantikan M15 untuk trigger akhir
- Flow baru: H4 trend → H1 pullback+ADX+ATR → M15 BOS/CHoCH struktur → **M5 candle entry**
- `get_m5()` di `bot/indicators.py` (EMA + ATR, tanpa ADX)
- `TF_M5` ditambah di `config.py` dan `bot/connector.py`
- `signals.evaluate()` dan `evaluate_continuation()` terima parameter `df_m5`, fallback ke M15 jika M5 tidak tersedia
- `scan_log()` tampilkan label `[M5]` atau `[M15]` di status candle

### Changed
- `SIGNAL_CHECK_INTERVAL` turun dari **15 detik → 5 detik** agar responsif terhadap candle M5

---

## [1.3.2] — 2026-06-22

### Added
- **Scan log real-time** — `bot/signals.py` kini memiliki fungsi `scan_log()` yang dipanggil setiap signal cycle (15 detik) dari `main.py`
- Format log: `[SCAN] BUY | Session✅ News✅ | Trend✅ | ADX=28.3✅ ATR=21.5✅ | Pullback✅ | Struct=BOS↑✅ | Candle=Engulf↑✅ → 🟢 SIAP ENTRY`
- Status level: 🟢 SIAP ENTRY / 🔥 HAMPIR (6-7/8) / ⏳ DEKAT (4-5/8) / 💤 TUNGGU (<4/8)
- Ketika 6+ filter lolos, cetak hint spesifik filter mana yang belum terpenuhi (membantu entry manual di akun lain)

---

## [1.3.1] — 2026-06-20

### Fixed
- **Dashboard infinite scroll** — canvas equity curve di-wrap dalam `<div style="height:220px">` agar Chart.js tidak expand unbounded
- **Dashboard scroll reset** — ganti `<meta http-equiv="refresh">` dengan `setInterval(load, 10000)` sehingga posisi scroll tidak kembali ke atas setiap 10 detik
- **ForexFactory rate limit (429)** — `bot/calendar.py` kini menerapkan hard cooldown 1 jam untuk *semua* fetch (sukses maupun gagal); timestamp disimpan ke `calendar_cache.json` sehingga cooldown bertahan saat restart
- **Dependency build error** — `pandas` dinaikkan ke `2.2.3` dan `numpy` ke `2.1.3` yang menyediakan wheel prebuilt untuk Python 3.13 (mencegah error Meson / MSVC saat `setup.bat`)

---

## [1.3.0] — 2026-06-20

### Added
- **Chart interaktif** — visualisasi HTML berbasis Plotly, buka di browser
- Candlestick chart dengan tema gelap
- EMA Ribbon (20/50/100/200) dengan warna berbeda
- Trendline otomatis dari swing high dan swing low
- Support & Resistance level horizontal (cluster swing points)
- Label swing: HH / HL / LH / LL di setiap swing point
- Marker BOS / CHoCH (segitiga + teks) dari scan M15
- Marker entry/exit dari trade log (▲ BUY, ▼ SELL, ★ TP, ✕ SL)
- Garis SL dan TP dari setiap trade entry (transparan)
- Panel ADX dengan threshold line (MIN, SKIP 20, STRONG 40)
- Panel ATR vs ATR_MA dengan fill zona entry diizinkan
- `chart/plotter.py` — builder utama chart Plotly
- `chart/trendlines.py` — swing detection, trendline builder, S/R cluster
- `chart/run_chart.py` — CLI dengan argumen `--tf`, `--bars`, `--no-trades`, dll
- `start_chart.bat` — wizard interaktif pilih TF dan bars
- Output disimpan ke `chart/output/chart_XAUUSD_M15.html`
- Draw mode aktif di toolbar browser (bisa gambar garis manual)
- `plotly==5.22.0` di requirements.txt

### Changed
- `.gitignore` — tambah `chart/output/` dan `logs/*.json`
- `README.md` — tambah section Chart Visualisasi

---

## [1.2.0] — 2026-06-20

### Added
- **Multi-entry mid-session** — bot kini bisa membuka posisi tambahan di tengah sesi selama tren masih valid
- **EMA Retest M15** — continuation signal: setelah BOS terkonfirmasi, pullback ke EMA20 M15 + candle konfirmasi
- **HLC Continuation** — continuation signal: Higher Low / Lower High baru di H1 + struktur M15 + candle konfirmasi
- `MAX_CONCURRENT_POSITIONS` — batas maksimal posisi induk yang boleh berjalan bersamaan
- `MIN_ENTRY_INTERVAL` — cooldown antar entry baru (menit) untuk hindari overtrading
- `MIN_ENTRY_DISTANCE_ATR` — jarak harga minimum antar entry (× ATR H1)
- `evaluate_continuation()` di `signals.py` — evaluator khusus continuation setup
- `has_ema_retest_m15()` dan `has_hlc_continuation()` di `structure.py`
- Notifikasi Telegram `notify_continuation()` khusus untuk signal EMA Retest dan HLC
- Status console sekarang menampilkan `Positions=1/2` dan `NextEntry=18m`
- Lot continuation otomatis dikurangi 80% dari normal untuk batasi exposure

### Changed
- `main.py` — `_run_signal_cycle()` direfaktor menjadi dua kasus: PRIMARY (no position) dan CONTINUATION (has position)
- `_status_line()` — tambah info `Positions=N/MAX` dan countdown interval

### Fixed
- Guard anti-overlap: entry baru tidak diizinkan jika harga terlalu dekat posisi yang ada

---

## [1.1.0] — 2026-06-20

### Added
- **BOS & CHoCH detection** — deteksi market structure proper: HH/HL/LH/LL dengan konfirmasi N bar kiri-kanan
- **SL dinamis ATR-based** — `SL = swing_H1 ± (ATR_H1 × ATR_SL_MULTIPLIER)`, menggantikan fixed 100 points
- **TP 3-tier + trailing** — TP1 tutup 30%, TP2 tutup 40%, sisa 30% trail via EMA20 H1
- **Pyramid entry** — posisi ke-2 (50% lot) setelah BE + TP1 hit pada posisi induk
- **Economic calendar otomatis** — fetch ForexFactory setiap 6 jam, cache ke `logs/calendar_cache.json`
- **Backtesting engine** — replay bar-by-bar dari data MT5, output HTML + CSV
- **Dashboard monitoring** — Flask web app di `localhost:5000`, auto-refresh 10 detik
- `ATR_SL_MULTIPLIER`, `TP1_R`, `TP1_PCT`, `TP2_R`, `TP2_PCT`, `BREAKEVEN_R` di `.env`
- `PYRAMID_ENABLED`, `PYRAMID_LOT_RATIO`, `MAX_PYRAMID` di `.env`
- `ADX_MIN` configurable via `.env`
- ADX threshold lebih tinggi untuk CHoCH entry (+5 dari `ADX_MIN`)
- Script `start_dashboard.bat` dan `run_backtest.bat`
- `bot/calendar.py` — ForexFactory integration dengan auto-refresh dan fallback cache
- `backtest/engine.py`, `backtest/report.py`, `backtest/run_backtest.py`
- `dashboard/app.py` — equity curve, open positions, today trades, upcoming news

### Changed
- `bot/structure.py` — tulis ulang dengan deteksi BOS/CHoCH yang proper (HH/HL/LH/LL)
- `bot/signals.py` — ADX threshold dinamis berdasarkan strength (BOS vs CHoCH)
- `bot/news_filter.py` — dua lapis: calendar otomatis + manual override
- `bot/trade.py` — position state registry (`_pos_state`) untuk tracking TP1/TP2/trail/pyramid
- `main.py` — versi v1.1, calendar refresh setiap 6 jam
- `requirements.txt` — tambah `flask==3.0.3`

### Removed
- Fixed SL buffer 100 points (diganti SL dinamis ATR)
- Simple partial close 50% (diganti 3-tier TP)

---

## [1.0.0] — 2026-06-20

### Added
- **Initial release** — XAUUSD Trend Following Bot berbasis multi-timeframe
- Filter tren H4 via EMA50 vs EMA200
- Filter momentum H1: ADX ≥ 25, ATR > ATR_MA
- Pullback detection H1 ke EMA20/50
- Market structure M15 (Higher Low + Break High / Lower High + Break Low)
- Candlestick confirmation: Bullish/Bearish Pin Bar & Engulfing
- Session filter 13:00–01:00 WIB
- News filter manual (FOMC, NFP, CPI) di `bot/news_filter.py`
- Risk management: 1% balance, SL di swing + 100 points, TP 1:2
- Breakeven otomatis di 1R
- Partial close 50% di TP1
- `FIXED_LOT` dan `RISK_PERCENT` di `.env`
- `ACCOUNT_CURRENCY` — support IDR dengan format balance `15,000,000 IDR`
- `MAX_TRADES_PER_DAY` — batas entry per hari
- Telegram notifikasi: signal, TP, SL, breakeven
- Logging ke SQLite (`logs/trades.db`) dan CSV (`logs/trades.csv`)
- `setup.bat` dan `start_bot.bat` untuk Windows
- `.gitignore` — `.env` tidak ikut commit
