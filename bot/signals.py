"""
Signal aggregator — dua jenis signal:

PRIMARY       : setup lengkap multi-TF (BOS/CHoCH + pullback H1 + candle M15)
CONTINUATION  : mid-session re-entry (EMA_RETEST atau HLC)
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

_ADX_CHOCH_BONUS = 5


def _ok(v: bool) -> str:
    return "✅" if v else "❌"


def scan_log(df_h4: pd.DataFrame, df_h1: pd.DataFrame, df_m15: pd.DataFrame, df_m5: pd.DataFrame | None = None):
    """
    Cetak status semua filter setiap cycle — membantu entry manual di akun lain.

    Format (semua filter lolos):
    [SCAN] BUY | Session✅ News✅ | Trend✅ | ADX=28.3✅ ATR=21.5✅ | Pullback✅ | Struct=BOS↑✅ | Candle=Engulf↑✅ → 🟢 SIAP ENTRY
    [SCAN]   ↳ Entry=3285.50 | SL=3271.30 (-14.20) | TP1=3299.70 (+14.20) | TP2=3313.90 (+28.40)
    """
    import MetaTrader5 as mt5
    from bot.risk import calc_sl

    session_ok = is_trading_session()
    news_ok    = not is_news_lock()

    # H4 trend
    trend = get_trend(df_h4)
    trend_ok = trend != NO_TRADE
    direction = "BUY" if trend == TREND_BULLISH else ("SELL" if trend == TREND_BEARISH else "—")

    # H1 filters
    last_h1    = df_h1.iloc[-1]
    adx_val    = last_h1["adx"]
    atr_val    = last_h1["atr"]
    atr_ma_val = last_h1.get("atr_ma", 0)
    adx_ok     = adx_val >= config.ADX_MIN
    atr_ok     = (not pd.isna(atr_ma_val)) and (atr_val > atr_ma_val)
    pullback_ok = has_pullback(df_h1, trend) if trend_ok else False

    # M15 structure & candle
    structure   = get_market_structure(df_m15)
    struct_ok   = (
        (direction == "BUY"  and is_bullish_structure(structure)) or
        (direction == "SELL" and is_bearish_structure(structure))
    ) if trend_ok else False

    # M5 untuk candle (lebih presisi), fallback M15
    entry_df  = df_m5 if df_m5 is not None else df_m15
    entry_tf  = "M5" if df_m5 is not None else "M15"
    pattern   = check_pattern(entry_df)
    bull_pat  = pattern in {BULLISH_PIN_BAR, BULLISH_ENGULFING}
    bear_pat  = pattern in {BEARISH_PIN_BAR, BEARISH_ENGULFING}
    candle_ok = (direction == "BUY" and bull_pat) or (direction == "SELL" and bear_pat) if trend_ok else False

    filters = [session_ok, news_ok, trend_ok, adx_ok, atr_ok, pullback_ok, struct_ok, candle_ok]
    passed  = sum(filters)
    total   = len(filters)
    all_ok  = all(filters)

    # Simbol struktur pendek
    struct_short = {
        "BULLISH_BOS":   "BOS↑", "BEARISH_BOS":   "BOS↓",
        "BULLISH_CHOCH": "CHoCH↑", "BEARISH_CHOCH": "CHoCH↓",
    }.get(structure, structure[:8] if structure else "—")

    candle_short = {
        BULLISH_PIN_BAR: "PinBar↑", BULLISH_ENGULFING: "Engulf↑",
        BEARISH_PIN_BAR: "PinBar↓", BEARISH_ENGULFING: "Engulf↓",
    }.get(pattern, "—") + f"[{entry_tf}]"

    if all_ok:
        status = "🟢 SIAP ENTRY"
    elif passed >= 6:
        status = f"🔥 HAMPIR ({passed}/{total})"
    elif passed >= 4:
        status = f"⏳ DEKAT ({passed}/{total})"
    else:
        status = f"💤 TUNGGU ({passed}/{total})"

    log_console(
        f"[SCAN] {direction} | "
        f"Session{_ok(session_ok)} News{_ok(news_ok)} | "
        f"Trend{_ok(trend_ok)} | "
        f"ADX={adx_val:.1f}{_ok(adx_ok)} "
        f"ATR={atr_val:.2f}{_ok(atr_ok)} | "
        f"Pullback{_ok(pullback_ok)} | "
        f"Struct={struct_short}{_ok(struct_ok)} | "
        f"Candle={candle_short}{_ok(candle_ok)} → {status}"
    )

    # Tampilkan proyeksi Entry / SL / TP jika 6+ filter lolos dan arah diketahui
    if passed >= 6 and direction in ("BUY", "SELL"):
        try:
            tick = mt5.symbol_info_tick(config.SYMBOL)
            if tick:
                entry = tick.ask if direction == "BUY" else tick.bid
                sl, sl_dist = calc_sl(df_h1, direction, entry)
                if sl_dist > 0:
                    tp1 = entry + sl_dist * config.TP1_R if direction == "BUY" else entry - sl_dist * config.TP1_R
                    tp2 = entry + sl_dist * config.TP2_R if direction == "BUY" else entry - sl_dist * config.TP2_R
                    sl_diff  = sl   - entry  # negatif untuk BUY
                    tp1_diff = tp1  - entry  # positif untuk BUY
                    tp2_diff = tp2  - entry
                    log_console(
                        f"[SCAN]   ↳ Entry={entry:.2f} | "
                        f"SL={sl:.2f} ({sl_diff:+.2f}) | "
                        f"TP1={tp1:.2f} ({tp1_diff:+.2f}) | "
                        f"TP2={tp2:.2f} ({tp2_diff:+.2f})"
                    )
        except Exception:
            pass

    # Jika hampir entry, cetak filter mana yang belum terpenuhi
    if passed >= 6 and not all_ok:
        missing = []
        if not struct_ok:   missing.append(f"Tunggu {direction} structure di M15")
        if not candle_ok:   missing.append(f"Tunggu candle konfirmasi ({direction})")
        if not pullback_ok: missing.append(f"Tunggu pullback ke EMA20/50 H1")
        if not atr_ok:      missing.append(f"Tunggu ATR naik (skrg {atr_val:.2f} < MA {atr_ma_val:.2f})")
        if not adx_ok:      missing.append(f"Tunggu ADX naik (skrg {adx_val:.1f} < {config.ADX_MIN})")
        for m in missing:
            log_console(f"[SCAN]   ↳ {m}")

    return all_ok


def _base_filters(df_h4: pd.DataFrame, df_h1: pd.DataFrame) -> tuple[str | None, str, float, float]:
    if not is_trading_session():
        return None, "", 0, 0
    if is_news_lock():
        return None, "", 0, 0

    trend = get_trend(df_h4)
    if trend == NO_TRADE:
        return None, "", 0, 0

    direction = "BUY" if trend == TREND_BULLISH else "SELL"

    last_h1    = df_h1.iloc[-1]
    adx_val    = last_h1["adx"]
    atr_val    = last_h1["atr"]
    atr_ma_val = last_h1["atr_ma"]

    if adx_val < config.ADX_SKIP:
        return None, trend, adx_val, atr_val
    if pd.isna(atr_ma_val) or atr_val <= atr_ma_val:
        return None, trend, adx_val, atr_val

    return direction, trend, adx_val, atr_val


def _candle_ok(df_m15: pd.DataFrame, direction: str) -> str | None:
    pattern = check_pattern(df_m15)
    if direction == "BUY" and pattern in {BULLISH_PIN_BAR, BULLISH_ENGULFING}:
        return pattern
    if direction == "SELL" and pattern in {BEARISH_PIN_BAR, BEARISH_ENGULFING}:
        return pattern
    return None


def evaluate(
    df_h4: pd.DataFrame,
    df_h1: pd.DataFrame,
    df_m15: pd.DataFrame,
    df_m5: pd.DataFrame | None = None,
) -> dict | None:
    direction, trend, adx_val, atr_val = _base_filters(df_h4, df_h1)
    if direction is None:
        return None

    # M15 → konfirmasi struktur BOS/CHoCH
    structure = get_market_structure(df_m15)
    if direction == "BUY" and not is_bullish_structure(structure):
        log_console(f"[SIG] Struct M15={structure} tidak cocok arah {direction} — skip")
        return None
    if direction == "SELL" and not is_bearish_structure(structure):
        log_console(f"[SIG] Struct M15={structure} tidak cocok arah {direction} — skip")
        return None

    strength = structure_strength(structure)
    adx_threshold = config.ADX_MIN + (_ADX_CHOCH_BONUS if strength == "MODERATE" else 0)
    if adx_val < adx_threshold:
        return None

    if not has_pullback(df_h1, trend):
        return None

    # M5 → candle entry presisi (jika tersedia), fallback ke M15
    entry_df = df_m5 if df_m5 is not None else df_m15
    entry_tf  = "M5" if df_m5 is not None else "M15"
    pattern = _candle_ok(entry_df, direction)
    if not pattern:
        log_console(f"[SIG] Candle {entry_tf} tidak valid untuk {direction} — skip")
        return None

    log_console(
        f"[SIG] ✅ PRIMARY | {direction} | {structure} ({strength}) | "
        f"ADX={adx_val:.1f} | ATR={atr_val:.4f} | pattern={pattern} [{entry_tf}]"
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
        "entry_tf":           entry_tf,
    }


def evaluate_continuation(
    df_h4: pd.DataFrame,
    df_h1: pd.DataFrame,
    df_m15: pd.DataFrame,
    existing_direction: str,
    df_m5: pd.DataFrame | None = None,
) -> dict | None:
    direction, trend, adx_val, atr_val = _base_filters(df_h4, df_h1)
    if direction is None:
        return None
    if direction != existing_direction:
        return None
    if adx_val < config.ADX_MIN:
        return None

    # M5 untuk candle konfirmasi (lebih presisi), fallback M15
    entry_df = df_m5 if df_m5 is not None else df_m15
    entry_tf  = "M5" if df_m5 is not None else "M15"
    pattern = _candle_ok(entry_df, direction)
    if not pattern:
        return None

    if has_ema_retest_m15(df_m15, direction):
        log_console(f"[CONT] ✅ EMA_RETEST | {direction} | ADX={adx_val:.1f} | pattern={pattern} [{entry_tf}]")
        return {
            "signal_type": "EMA_RETEST", "direction": direction, "trend": trend,
            "structure": "EMA_RETEST_M15", "structure_strength": "MODERATE",
            "adx": adx_val, "atr": atr_val, "pattern": pattern, "entry_tf": entry_tf,
        }

    if has_hlc_continuation(df_h1, direction):
        structure = get_market_structure(df_m15)
        if direction == "BUY" and not is_bullish_structure(structure):
            return None
        if direction == "SELL" and not is_bearish_structure(structure):
            return None
        log_console(f"[CONT] ✅ HLC | {direction} | {structure} | ADX={adx_val:.1f} | pattern={pattern} [{entry_tf}]")
        return {
            "signal_type": "HLC", "direction": direction, "trend": trend,
            "structure": structure, "structure_strength": "MODERATE",
            "adx": adx_val, "atr": atr_val, "pattern": pattern, "entry_tf": entry_tf,
        }

    return None
