"""
Konfigurasi khusus untuk Scalper M5.
Dibaca dari .env — semua key diawali SCALP_
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── MT5 (sama dengan bot utama) ───────────────────────────────────
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", 0))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "")
SYMBOL       = os.getenv("SYMBOL", "XAUUSD")

# ── Telegram ──────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Scalper identity ──────────────────────────────────────────────
SCALP_MAGIC           = int(os.getenv("SCALP_MAGIC", 202407))   # berbeda dari bot utama

# ── Grid settings ─────────────────────────────────────────────────
SCALP_ENABLED         = os.getenv("SCALP_ENABLED", "true").lower() == "true"
SCALP_GRID_COUNT      = int(os.getenv("SCALP_GRID_COUNT", 5))      # jumlah order per zona
SCALP_LOT             = float(os.getenv("SCALP_LOT", 0.05))         # total lot dibagi grid
SCALP_SL_PIPS         = float(os.getenv("SCALP_SL_PIPS", 8.0))     # SL dalam pip
SCALP_TP_PIPS         = float(os.getenv("SCALP_TP_PIPS", 15.0))    # TP dalam pip (default 1:1.8)
SCALP_EXPIRY_MINUTES  = int(os.getenv("SCALP_EXPIRY_MINUTES", 20)) # auto-cancel pending

# ── Zone detection ────────────────────────────────────────────────
SCALP_ZONE_LOOKBACK   = int(os.getenv("SCALP_ZONE_LOOKBACK", 100)) # bar M5 untuk scan zona
SCALP_MAX_ZONES       = int(os.getenv("SCALP_MAX_ZONES", 3))       # maks zona yang dicari

# ── Filter ────────────────────────────────────────────────────────
SCALP_ADX_MIN             = float(os.getenv("SCALP_ADX_MIN", 20.0))    # ADX minimum
SCALP_MAX_OPEN            = int(os.getenv("SCALP_MAX_OPEN", 10))        # maks posisi scalp terbuka
SCALP_CHECK_INTERVAL      = int(os.getenv("SCALP_CHECK_INTERVAL", 10)) # detik antar cycle
SCALP_MAX_ZONE_DISTANCE   = float(os.getenv("SCALP_MAX_ZONE_DISTANCE", 10.0))  # pip maks jarak harga ke zona

# ── Session (sama dengan bot utama) ───────────────────────────────
SESSION_START_WIB = int(os.getenv("SESSION_START_WIB", 13))
SESSION_END_WIB   = int(os.getenv("SESSION_END_WIB", 1))
