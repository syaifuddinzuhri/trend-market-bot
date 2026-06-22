"""
TrendBot Scalper Trend — M5 Candle Entry searah H1

Strategi:
  1. Konfirmasi tren H1: EMA50 < EMA200 → SELL, EMA50 > EMA200 → BUY
  2. Candle konfirmasi M5: Bearish Pin Bar atau Bearish Engulfing (untuk SELL)
  3. Entry market order, TP fixed pip, SL swing high/low M5 + buffer

Run: python scalper_trend.py
"""
import time
import sys

import MetaTrader5 as mt5
import pandas as pd

import scalp_config as sc
from bot.logger import log_console
from bot.session import is_trading_session
from bot import telegram

# ── Config scalper trend ──────────────────────────────────────────
TREND_TP_PIPS    = float(__import__('os').getenv("TREND_TP_PIPS",   12.0))  # TP pip (10-15)
TREND_SL_PIPS    = float(__import__('os').getenv("TREND_SL_PIPS",   15.0))  # SL pip
TREND_LOT        = float(__import__('os').getenv("TREND_LOT",        0.01))  # lot per trade
TREND_MAX_OPEN   = int(__import__('os').getenv("TREND_MAX_OPEN",       3))   # max posisi scalp
TREND_COOLDOWN   = int(__import__('os').getenv("TREND_COOLDOWN",      60))   # detik antar entry
TREND_MAGIC      = int(__import__('os').getenv("TREND_MAGIC",      202408))  # magic number
TREND_ADX_MIN    = float(__import__('os').getenv("TREND_ADX_MIN",    20.0))  # ADX minimum M5
CHECK_INTERVAL   = 5   # detik antar cycle

_last_entry_time: float = 0.0


def _connect() -> bool:
    if not mt5.initialize():
        log_console("[STREND] MT5 initialize() gagal", level="ERROR")
        return False
    if not mt5.login(sc.MT5_LOGIN, sc.MT5_PASSWORD, sc.MT5_SERVER):
        log_console(f"[STREND] MT5 login gagal: {mt5.last_error()}", level="ERROR")
        mt5.shutdown()
        return False
    info = mt5.account_info()
    log_console(f"[STREND] Connected | {info.name} | Balance={info.balance:,.0f}")
    return True


def _get_candles(timeframe, bars: int) -> pd.DataFrame | None:
    rates = mt5.copy_rates_from_pos(sc.SYMBOL, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _get_trend_h1() -> str:
    """
    Trend H1: EMA50 vs EMA200.
    Return 'SELL', 'BUY', atau '' jika tidak jelas.
    """
    df = _get_candles(mt5.TIMEFRAME_H1, 250)
    if df is None or len(df) < 200:
        return ""
    ema50  = _ema(df["close"], 50).iloc[-1]
    ema200 = _ema(df["close"], 200).iloc[-1]
    close  = df["close"].iloc[-1]
    if ema50 < ema200 and close < ema200:
        return "SELL"
    if ema50 > ema200 and close > ema200:
        return "BUY"
    return ""


def _get_adx_m5(df: pd.DataFrame, period: int = 14) -> float:
    try:
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        dm_p = (high.diff()).clip(lower=0)
        dm_m = (-low.diff()).clip(lower=0)
        dm_p = dm_p.where(dm_p > dm_m, 0)
        dm_m = dm_m.where(dm_m > dm_p, 0)
        atr14 = tr.ewm(alpha=1/period, adjust=False).mean()
        dip   = 100 * dm_p.ewm(alpha=1/period, adjust=False).mean() / atr14.replace(0, 1e-9)
        dim   = 100 * dm_m.ewm(alpha=1/period, adjust=False).mean() / atr14.replace(0, 1e-9)
        dx    = 100 * (dip - dim).abs() / (dip + dim).replace(0, 1e-9)
        return float(dx.ewm(alpha=1/period, adjust=False).mean().iloc[-1])
    except Exception:
        return 0.0


def _check_candle(df: pd.DataFrame, direction: str) -> str | None:
    """
    Cek candle konfirmasi di 2 candle terakhir.
    Return nama pattern atau None.
    """
    if len(df) < 2:
        return None
    cur  = df.iloc[-1]
    prev = df.iloc[-2]

    o, h, l, c = cur["open"], cur["high"], cur["low"], cur["close"]
    body        = abs(c - o)
    full_range  = h - l if h != l else 1e-10
    upper_wick  = h - max(o, c)
    lower_wick  = min(o, c) - l

    po, _, _, pc = prev["open"], prev["high"], prev["low"], prev["close"]

    if direction == "SELL":
        # Bearish Pin Bar: upper wick >= 2x body, close di bawah 30%
        if body > 0 and upper_wick >= 2 * body and (h - c) / full_range >= 0.70:
            return "BEARISH_PIN_BAR"
        # Bearish Engulfing: prev bullish, cur bearish dan engulf prev body
        if pc > po and c < o and o > pc and c < po:
            return "BEARISH_ENGULFING"

    if direction == "BUY":
        # Bullish Pin Bar: lower wick >= 2x body, close di atas 70%
        if body > 0 and lower_wick >= 2 * body and (c - l) / full_range >= 0.70:
            return "BULLISH_PIN_BAR"
        # Bullish Engulfing: prev bearish, cur bullish dan engulf prev body
        if pc < po and c > o and o < pc and c > po:
            return "BULLISH_ENGULFING"

    return None


def _get_swing(df: pd.DataFrame, direction: str, lookback: int = 10) -> float:
    """Swing high (SELL) atau swing low (BUY) dari N candle terakhir."""
    window = df.iloc[-lookback:]
    return window["high"].max() if direction == "SELL" else window["low"].min()


def _open_count() -> int:
    positions = mt5.positions_get(symbol=sc.SYMBOL) or []
    return sum(1 for p in positions if p.magic == TREND_MAGIC)


def _open_trade(direction: str, entry: float, sl: float, tp: float) -> int | None:
    sym_info = mt5.symbol_info(sc.SYMBOL)
    if sym_info is None:
        return None

    order_type = mt5.ORDER_TYPE_SELL if direction == "SELL" else mt5.ORDER_TYPE_BUY
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       sc.SYMBOL,
        "volume":       TREND_LOT,
        "type":         order_type,
        "price":        entry,
        "sl":           round(sl, sym_info.digits),
        "tp":           round(tp, sym_info.digits),
        "deviation":    20,
        "magic":        TREND_MAGIC,
        "comment":      "strend_scalp",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code = result.retcode if result else "None"
        log_console(f"[STREND] order_send gagal retcode={code}", level="ERROR")
        return None
    return result.order


def _run_cycle():
    global _last_entry_time

    if not is_trading_session():
        return

    # ── Trend H1 ──────────────────────────────────────────────────
    direction = _get_trend_h1()
    if not direction:
        log_console("[STREND] Trend H1 tidak jelas — skip")
        return

    # ── Data M5 ───────────────────────────────────────────────────
    df_m5 = _get_candles(mt5.TIMEFRAME_M5, 100)
    if df_m5 is None:
        return

    # ── ADX filter ────────────────────────────────────────────────
    adx = _get_adx_m5(df_m5)
    if adx < TREND_ADX_MIN:
        log_console(f"[STREND] ADX M5={adx:.1f} < {TREND_ADX_MIN} — skip")
        return

    # ── Candle konfirmasi ─────────────────────────────────────────
    pattern = _check_candle(df_m5, direction)
    if not pattern:
        return

    # ── Max posisi ────────────────────────────────────────────────
    if _open_count() >= TREND_MAX_OPEN:
        log_console(f"[STREND] Max posisi ({TREND_MAX_OPEN}) — skip")
        return

    # ── Cooldown antar entry ──────────────────────────────────────
    if time.time() - _last_entry_time < TREND_COOLDOWN:
        remaining = int(TREND_COOLDOWN - (time.time() - _last_entry_time))
        log_console(f"[STREND] Cooldown {remaining}s — skip")
        return

    # ── Harga & level ─────────────────────────────────────────────
    tick = mt5.symbol_info_tick(sc.SYMBOL)
    if tick is None:
        return
    sym_info = mt5.symbol_info(sc.SYMBOL)
    pip_size = max(sym_info.point * 10, 0.1) if sym_info else 0.1

    entry = tick.bid if direction == "SELL" else tick.ask
    sl    = _get_swing(df_m5, direction, lookback=10)

    # Fallback ke fixed pip jika swing terlalu jauh
    swing_dist = abs(entry - sl)
    max_sl_dist = TREND_SL_PIPS * pip_size
    if swing_dist > max_sl_dist or swing_dist < pip_size:
        sl = entry + max_sl_dist if direction == "SELL" else entry - max_sl_dist

    tp_dist = TREND_TP_PIPS * pip_size
    tp = entry - tp_dist if direction == "SELL" else entry + tp_dist
    sl = round(sl, sym_info.digits if sym_info else 2)
    tp = round(tp, sym_info.digits if sym_info else 2)

    log_console(
        f"[STREND] {direction} | {pattern} | ADX={adx:.1f} | "
        f"Entry={entry:.2f} | SL={sl:.2f} | TP={tp:.2f}"
    )

    ticket = _open_trade(direction, entry, sl, tp)
    if ticket:
        _last_entry_time = time.time()
        sl_dist = abs(entry - sl)
        telegram.send(
            f"⚡ *SCALP {direction} — {sc.SYMBOL}*\n"
            f"Pattern : `{pattern}`\n"
            f"Entry   : `{entry:.2f}`\n"
            f"SL      : `{sl:.2f}` ({sl_dist:.2f})\n"
            f"TP      : `{tp:.2f}` ({tp_dist:.2f})\n"
            f"Lot     : `{TREND_LOT}` | ADX M5: `{adx:.1f}`"
        )
        log_console(f"[STREND] Opened ticket={ticket}")


def _status():
    info = mt5.account_info()
    if info is None:
        return
    n = _open_count()
    trend = _get_trend_h1()
    log_console(
        f"[STREND STATUS] Balance={info.balance:,.0f} IDR | "
        f"Equity={info.equity:,.0f} IDR | "
        f"OpenScalp={n}/{TREND_MAX_OPEN} | TrendH1={trend or '—'}"
    )


def main():
    log_console("=" * 55)
    log_console("  TrendBot Scalper Trend  |  M5 Candle Entry")
    log_console("=" * 55)
    log_console(f"  TP={TREND_TP_PIPS} pip | SL={TREND_SL_PIPS} pip | Lot={TREND_LOT}")
    log_console("=" * 55)

    if not _connect():
        sys.exit(1)

    telegram.send(
        f"⚡ *Scalper Trend started* | {sc.SYMBOL}\n"
        f"TP={TREND_TP_PIPS}pip | SL={TREND_SL_PIPS}pip | Lot={TREND_LOT}"
    )

    last_status = 0.0

    try:
        while True:
            now = time.time()
            if now - last_status >= 30:
                _status()
                last_status = now
            try:
                _run_cycle()
            except Exception as e:
                log_console(f"[STREND] Cycle error: {e}", level="ERROR")
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        log_console("[STREND] Dihentikan oleh user.")
        telegram.send(f"⛔ *Scalper Trend stopped* | {sc.SYMBOL}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
