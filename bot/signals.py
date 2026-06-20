"""
Signal aggregator — evaluasi semua filter dan return signal dict atau None.

Entry diizinkan pada dua kondisi struktur M15:
  BOS   (Break of Structure)  → tren sudah terkonfirmasi, entry lebih aman
  CHoCH (Change of Character) → awal tren baru, entry lebih awal tapi ADX threshold lebih tinggi
"""
import pandas as pd
import config
from bot.trend import get_trend, TREND_BULLISH, TREND_BEARISH, NO_TRADE
from bot.pullback import has_pullback
from bot.structure import (
    get_market_structure,
    is_bullish_structure, is_bearish_structure,
    structure_strength,
    BULLISH_BOS, BULLISH_CHOCH, BEARISH_BOS, BEARISH_CHOCH, NO_STRUCTURE,
)
from bot.candlestick import (
    check_pattern,
    BULLISH_PIN_BAR, BULLISH_ENGULFING,
    BEARISH_PIN_BAR, BEARISH_ENGULFING,
)
from bot.session import is_trading_session
from bot.news_filter import is_news_lock
from bot.logger import log_console

# CHoCH memerlukan ADX lebih tinggi karena sinyal lebih awal (lebih berisiko)
_ADX_CHOCH_BONUS = 5   # threshold ADX untuk CHoCH = ADX_MIN + bonus ini


def evaluate(df_h4: pd.DataFrame, df_h1: pd.DataFrame, df_m15: pd.DataFrame) -> dict | None:
    """
    Returns signal dict atau None.

    Signal dict keys:
      direction, trend, structure, structure_strength,
      adx, atr, pattern
    """

    # ── Pre-checks ────────────────────────────────────────────────
    if not is_trading_session():
        log_console("[SIG] Outside trading session — skip")
        return None

    if is_news_lock():
        log_console("[SIG] NEWS_LOCK active — skip")
        return None

    # ── Trend (H4) ───────────────────────────────────────────────
    trend = get_trend(df_h4)
    if trend == NO_TRADE:
        log_console("[SIG] No clear H4 trend — skip")
        return None

    direction = "BUY" if trend == TREND_BULLISH else "SELL"

    # ── Market Structure M15 ─────────────────────────────────────
    structure = get_market_structure(df_m15)

    if direction == "BUY" and not is_bullish_structure(structure):
        log_console(f"[SIG] No bullish structure on M15 ({structure}) — skip")
        return None
    if direction == "SELL" and not is_bearish_structure(structure):
        log_console(f"[SIG] No bearish structure on M15 ({structure}) — skip")
        return None

    strength = structure_strength(structure)

    # ── ADX filter (H1) — threshold lebih tinggi untuk CHoCH ─────
    adx_val = df_h1.iloc[-1]["adx"]
    adx_threshold = config.ADX_MIN
    if strength == "MODERATE":   # CHoCH
        adx_threshold = config.ADX_MIN + _ADX_CHOCH_BONUS

    if adx_val < config.ADX_SKIP:
        log_console(f"[SIG] ADX terlalu rendah ({adx_val:.1f}) — skip")
        return None
    if adx_val < adx_threshold:
        log_console(f"[SIG] ADX {adx_val:.1f} < threshold {adx_threshold} ({structure}) — skip")
        return None

    # ── ATR filter (H1) ──────────────────────────────────────────
    last_h1 = df_h1.iloc[-1]
    atr_val    = last_h1["atr"]
    atr_ma_val = last_h1["atr_ma"]
    if pd.isna(atr_ma_val) or atr_val <= atr_ma_val:
        log_console(f"[SIG] ATR ({atr_val:.4f}) <= ATR_MA ({atr_ma_val:.4f}) — skip")
        return None

    # ── Pullback ke EMA H1 ────────────────────────────────────────
    if not has_pullback(df_h1, trend):
        log_console(f"[SIG] No {trend} pullback on H1 — skip")
        return None

    # ── Candlestick confirmation (M15) ───────────────────────────
    pattern = check_pattern(df_m15)
    bullish_ok = pattern in {BULLISH_PIN_BAR, BULLISH_ENGULFING}
    bearish_ok = pattern in {BEARISH_PIN_BAR, BEARISH_ENGULFING}

    if direction == "BUY" and not bullish_ok:
        log_console(f"[SIG] No bullish candle ({pattern}) — skip")
        return None
    if direction == "SELL" and not bearish_ok:
        log_console(f"[SIG] No bearish candle ({pattern}) — skip")
        return None

    log_console(
        f"[SIG] ✅ SIGNAL | {direction} | {structure} ({strength}) | "
        f"ADX={adx_val:.1f} | ATR={atr_val:.4f} | pattern={pattern}"
    )

    return {
        "direction":          direction,
        "trend":              trend,
        "structure":          structure,
        "structure_strength": strength,
        "adx":                adx_val,
        "atr":                atr_val,
        "pattern":            pattern,
    }
