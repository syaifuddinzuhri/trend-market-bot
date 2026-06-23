import os
from dotenv import load_dotenv

load_dotenv()

# MT5
MT5_LOGIN = int(os.getenv("MT5_LOGIN", 0))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

# Trading
SYMBOL = os.getenv("SYMBOL", "XAUUSD")
ACCOUNT_CURRENCY = os.getenv("ACCOUNT_CURRENCY", "USD")
RISK_PERCENT = float(os.getenv("RISK_PERCENT", 1.0))
FIXED_LOT = float(os.getenv("FIXED_LOT", 0.0))       # 0 = gunakan RISK_PERCENT
MAGIC_NUMBER = int(os.getenv("MAGIC_NUMBER", 202406))
SLIPPAGE = int(os.getenv("SLIPPAGE", 20))

# Session (WIB = UTC+7)
SESSION_ENABLED   = os.getenv("SESSION_ENABLED", "true").lower() == "true"
SESSION_START_WIB = int(os.getenv("SESSION_START_WIB", 13))
SESSION_END_WIB   = int(os.getenv("SESSION_END_WIB", 1))

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", ""))
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Logging
LOG_DB = os.getenv("LOG_DB", "logs/trades.db")
LOG_CSV = os.getenv("LOG_CSV", "logs/trades.csv")

# Indicator params
EMA_PERIODS = [20, 50, 100, 200]
ADX_PERIOD = 14
ADX_MIN = int(os.getenv("ADX_MIN", 25))
ADX_SKIP = 20
ATR_PERIOD = 14
ATR_MA_PERIOD = 20
# ATR filter: ATR harus >= ATR_MA × ATR_MA_RATIO (0.85 = toleransi 15% di bawah MA)
ATR_MA_RATIO = float(os.getenv("ATR_MA_RATIO", 0.85))

# ── SL: dinamis berbasis ATR H1 ───────────────────────────────────
# SL = swing H1 ± (ATR_H1 × ATR_SL_MULTIPLIER)
ATR_SL_MULTIPLIER    = float(os.getenv("ATR_SL_MULTIPLIER", 1.5))
MAX_SL_POINTS        = float(os.getenv("MAX_SL_POINTS", 30.0))   # 0 = tidak di-cap
SWING_LOOKBACK_M5    = int(os.getenv("SWING_LOOKBACK_M5", 10))   # lookback swing untuk M5

# ── TP 3-tier ─────────────────────────────────────────────────────
# Mode: "pips" = fixed pip target | "r_multiple" = kelipatan SL distance
TP_MODE = os.getenv("TP_MODE", "pips")        # "pips" atau "r_multiple"

# Mode pips (default aktif)
TP1_PIPS = float(os.getenv("TP1_PIPS", 50.0))   # pip ke TP1
TP2_PIPS = float(os.getenv("TP2_PIPS", 80.0))   # pip ke TP2
TP3_PIPS = float(os.getenv("TP3_PIPS", 120.0))  # pip ke TP3 (trailing mulai di sini)

# Mode R-multiple (fallback jika TP_MODE=r_multiple)
TP1_R   = float(os.getenv("TP1_R",   1.0))   # 1R
TP2_R   = float(os.getenv("TP2_R",   2.0))   # 2R

# Persentase close per tier (berlaku di kedua mode)
TP1_PCT = float(os.getenv("TP1_PCT", 0.30))  # tutup 30% di TP1
TP2_PCT = float(os.getenv("TP2_PCT", 0.40))  # tutup 40% di TP2, sisa 30% trailing

# ── Breakeven ─────────────────────────────────────────────────────
BREAKEVEN_R = float(os.getenv("BREAKEVEN_R", 1.0))

# ── Pyramid entry ─────────────────────────────────────────────────
# Dibuka setelah TP1 hit + SL sudah di BE pada posisi induk
# Lot pyramid = original_lot × PYRAMID_LOT_RATIO
PYRAMID_ENABLED   = os.getenv("PYRAMID_ENABLED", "true").lower() == "true"
PYRAMID_LOT_RATIO = float(os.getenv("PYRAMID_LOT_RATIO", 0.5))  # 50% dari lot awal
MAX_PYRAMID       = int(os.getenv("MAX_PYRAMID", 1))             # max 1 pyramid per trade

# ── Multi-entry mid-session ───────────────────────────────────────
# Posisi induk yang boleh berjalan bersamaan (bukan pyramid)
MAX_CONCURRENT_POSITIONS  = int(os.getenv("MAX_CONCURRENT_POSITIONS", 2))
# Jarak waktu minimum antar entry baru (menit)
MIN_ENTRY_INTERVAL        = int(os.getenv("MIN_ENTRY_INTERVAL", 30))
# Jarak harga minimum antar entry (× ATR H1) — cegah entry terlalu berdekatan
MIN_ENTRY_DISTANCE_ATR    = float(os.getenv("MIN_ENTRY_DISTANCE_ATR", 1.0))

# Trade limits
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", 5))    # 0 = unlimited

# News filter minutes
NEWS_BUFFER_MINUTES = 30

# Swing lookback bars (dipakai di H1 sekarang)
SWING_LOOKBACK = 20

# ── Re-entry after TP ─────────────────────────────────────────────
# Setelah posisi tutup profit, bot boleh re-entry searah jika harga
# pullback ke EMA — tanpa butuh BOS/CHoCH ulang.
REENTRY_ENABLED         = os.getenv("REENTRY_ENABLED", "true").lower() == "true"
REENTRY_WINDOW_MINUTES  = int(os.getenv("REENTRY_WINDOW_MINUTES", 90))   # window setelah TP
REENTRY_MAX_COUNT       = int(os.getenv("REENTRY_MAX_COUNT", 2))          # max re-entry per sesi tren

# ── Alert manual Telegram ─────────────────────────────────────────
ALERT_COOLDOWN_SECONDS  = int(os.getenv("ALERT_COOLDOWN_SECONDS", 300))  # cooldown antar alert (detik)

# ── Pending Order (Limit) ─────────────────────────────────────────
PENDING_ENABLED             = os.getenv("PENDING_ENABLED", "true").lower() == "true"
PENDING_MIN_FILTERS         = int(os.getenv("PENDING_MIN_FILTERS", 5))    # min filter lolos untuk pasang limit
PENDING_EXPIRY_MINUTES      = int(os.getenv("PENDING_EXPIRY_MINUTES", 120))  # auto-expire setelah N menit
PENDING_MAX_DISTANCE_ATR    = float(os.getenv("PENDING_MAX_DISTANCE_ATR", 3.0))  # cancel jika harga > N×ATR dari level

# Timeframes (MT5 constants loaded lazily)
TF_H4  = None
TF_H1  = None
TF_M15 = None
TF_M5  = None
