"""
Signal aggregator — dua jenis signal:

PRIMARY       : setup lengkap multi-TF (BOS/CHoCH + pullback H1 + candle M15)
                → dipakai untuk entry pertama di sesi

CONTINUATION  : setup mid-session untuk re-entry tambahan
                → EMA_RETEST  : pullback ke EMA20 M15 setelah BOS
                → HLC         : Higher Low / Lower High baru di H1 + candle M15

Kedua jenis signal menggunakan filter H4 trend, ADX, ATR, dan session yang sama.
Perbedaan: CONTINUATION tidak wajib lewat pullback H1 ke EMA (karena sudah di area tren).
"""
import pandas as pd
import config
from bot.trend import get_trend, TREND_BULLISH, TREND_BEARISH, NO_TRADE
from bot.pullback import has_pullback
from bot.structure import (
    get_market_structure,
    is_bullish_structure, is_bearish_structure,
    structure_strength,
    has_ema_retest_m15, has_hlc_continuation,
    BULLISH_BOS, BULLISH_CHOCH, BEARISH_BOS, BEARISH_CHOCH,
)
from bot.candlestick import (
    check_pattern,
    BULLISH_PIN_BAR, BULLISH_ENGULFING,
    BEARISH_PIN_BAR, BEARISH_ENGULFING,
)
from bot.session import is_trading_session
from bot.news_filter import is_news_lock
from bot.logger import log_console

_ADX_CHOCH_BONUS = 5   # ADX threshold lebih tinggi untuk CHoCH


def _base_filters(df_h4: pd.DataFrame, df_h1: pd.DataFrame) -> tuple[str | None, str, float, float]:
    """
    Filter bersama H4 + H1.
    Returns (direction, trend, adx_val, atr_val) atau (None, ...) jika gagal.
    """
    if not is_trading_session():
        log_console("[SIG] Outside trading session — skip")
        return None, "", 0, 0

    if is_news_lock():
        log_console("[SIG] NEWS_LOCK active — skip")
        return None, "", 0, 0

    trend = get_trend(df_h4)
    if trend == NO_TRADE:
        log_console("[SIG] No clear H4 trend — skip")
        return None, "", 0, 0

    direction = "BUY" if trend == TREND_BULLISH else "SELL"

    last_h1 = df_h1.iloc[-1]
    adx_val    = last_h1["adx"]
    atr_val    = last_h1["atr"]
    atr_ma_val = last_h1["atr_ma"]

    if adx_val < config.ADX_SKIP:
        log_console(f"[SIG] ADX terlalu rendah ({adx_val:.1f}) — skip")
        return None, trend, adx_val, atr_val

    if pd.isna(atr_ma_val) or atr_val <= atr_ma_val:
        log_console(f"[SIG] ATR ({atr_val:.4f}) <= ATR_MA ({atr_ma_val:.4f}) — skip")
        return None, trend, adx_val, atr_val

    return direction, trend, adx_val, atr_val


def _candle_ok(df_m15: pd.DataFrame, direction: str) -> str | None:
    """Cek pola candle M15. Return nama pattern atau None."""
    pattern = check_pattern(df_m15)
    if direction == "BUY" and pattern in {BULLISH_PIN_BAR, BULLISH_ENGULFING}:
        return pattern
    if direction == "SELL" and pattern in {BEARISH_PIN_BAR, BEARISH_ENGULFING}:
        return pattern
    return None


# ── Signal PRIMARY ────────────────────────────────────────────────

def evaluate(df_h4: pd.DataFrame, df_h1: pd.DataFrame, df_m15: pd.DataFrame) -> dict | None:
    """
    Setup PRIMARY: filter lengkap multi-TF.
    Dipakai untuk entry pertama di sesi (posisi induk = 0).
    """
    direction, trend, adx_val, atr_val = _base_filters(df_h4, df_h1)
    if direction is None:
        return None

    # Structure M15
    structure = get_market_structure(df_m15)
    if direction == "BUY" and not is_bullish_structure(structure):
        log_console(f"[SIG] No bullish M15 structure ({structure}) — skip")
        return None
    if direction == "SELL" and not is_bearish_structure(structure):
        log_console(f"[SIG] No bearish M15 structure ({structure}) — skip")
        return None

    strength = structure_strength(structure)
    adx_threshold = config.ADX_MIN + (_ADX_CHOCH_BONUS if strength == "MODERATE" else 0)
    if adx_val < adx_threshold:
        log_console(f"[SIG] ADX {adx_val:.1f} < {adx_threshold} ({structure}) — skip")
        return None

    # Pullback H1 wajib untuk PRIMARY
    if not has_pullback(df_h1, trend):
        log_console(f"[SIG] No {trend} pullback H1 — skip")
        return None

    pattern = _candle_ok(df_m15, direction)
    if not pattern:
        log_console(f"[SIG] No {direction} candle pattern — skip")
        return None

    log_console(
        f"[SIG] ✅ PRIMARY | {direction} | {structure} ({strength}) | "
        f"ADX={adx_val:.1f} | ATR={atr_val:.4f} | pattern={pattern}"
    )
    return {
        "signal_type":        "PRIMARY",
        "direction":          direction,
        "trend":              trend,
        "structure":          structure,
        "structure_strength": strength,
        "adx":                adx_val,
        "atr":                atr_val,
        "pattern":            pattern,
    }


# ── Signal CONTINUATION ───────────────────────────────────────────

def evaluate_continuation(
    df_h4: pd.DataFrame,
    df_h1: pd.DataFrame,
    df_m15: pd.DataFrame,
    existing_direction: str,
) -> dict | None:
    """
    Setup CONTINUATION: mid-session re-entry.

    Dua sub-tipe:
      EMA_RETEST  — pullback ke EMA20 M15 setelah BOS terkonfirmasi
      HLC         — Higher Low / Lower High baru di H1 + candle M15

    existing_direction: arah posisi yang sudah terbuka ('BUY'/'SELL')
    Hanya boleh entry ke arah yang SAMA dengan posisi yang ada.
    """
    direction, trend, adx_val, atr_val = _base_filters(df_h4, df_h1)
    if direction is None:
        return None

    # Harus searah dengan posisi yang ada
    if direction != existing_direction:
        log_console(f"[CONT] Arah berbeda ({direction} vs existing {existing_direction}) — skip")
        return None

    # ADX minimal sama untuk continuation
    if adx_val < config.ADX_MIN:
        log_console(f"[CONT] ADX {adx_val:.1f} < {config.ADX_MIN} — skip")
        return None

    pattern = _candle_ok(df_m15, direction)
    if not pattern:
        log_console(f"[CONT] No {direction} candle pattern M15 — skip")
        return None

    # ── Sub-tipe 1: EMA Retest M15 ───────────────────────────────
    if has_ema_retest_m15(df_m15, direction):
        log_console(
            f"[CONT] ✅ EMA_RETEST | {direction} | ADX={adx_val:.1f} | pattern={pattern}"
        )
        return {
            "signal_type":        "EMA_RETEST",
            "direction":          direction,
            "trend":              trend,
            "structure":          "EMA_RETEST_M15",
            "structure_strength": "MODERATE",
            "adx":                adx_val,
            "atr":                atr_val,
            "pattern":            pattern,
        }

    # ── Sub-tipe 2: HLC Continuation ─────────────────────────────
    if has_hlc_continuation(df_h1, direction):
        # Tetap butuh struktur M15 minimal (CHoCH cukup)
        structure = get_market_structure(df_m15)
        if direction == "BUY" and not is_bullish_structure(structure):
            log_console(f"[CONT] HLC tapi no bullish M15 structure — skip")
            return None
        if direction == "SELL" and not is_bearish_structure(structure):
            log_console(f"[CONT] HLC tapi no bearish M15 structure — skip")
            return None

        log_console(
            f"[CONT] ✅ HLC | {direction} | {structure} | ADX={adx_val:.1f} | pattern={pattern}"
        )
        return {
            "signal_type":        "HLC",
            "direction":          direction,
            "trend":              trend,
            "structure":          structure,
            "structure_strength": "MODERATE",
            "adx":                adx_val,
            "atr":                atr_val,
            "pattern":            pattern,
        }

    log_console(f"[CONT] No continuation setup found — skip")
    return None
