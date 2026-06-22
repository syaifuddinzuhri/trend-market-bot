# Changelog

Semua perubahan signifikan pada project ini didokumentasikan di sini.
Format mengacu pada [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
