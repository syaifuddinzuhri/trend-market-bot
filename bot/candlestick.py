import pandas as pd

BULLISH_PIN_BAR = "BULLISH_PIN_BAR"
BEARISH_PIN_BAR = "BEARISH_PIN_BAR"
BULLISH_ENGULFING = "BULLISH_ENGULFING"
BEARISH_ENGULFING = "BEARISH_ENGULFING"
NO_PATTERN = "NO_PATTERN"


def _candle_parts(row):
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    full_range = h - l if h != l else 1e-10
    return o, h, l, c, body, upper_wick, lower_wick, full_range


def check_pattern(df: pd.DataFrame) -> str:
    """Analyse the last two candles for entry pattern."""
    if len(df) < 2:
        return NO_PATTERN

    cur = df.iloc[-1]
    prev = df.iloc[-2]

    o, h, l, c, body, upper_wick, lower_wick, full_range = _candle_parts(cur)

    # ── Bullish Pin Bar ───────────────────────────────────────────
    # Lower wick >= 2x body, close in top 30% of candle range
    if body > 0 and lower_wick >= 2 * body and (c - l) / full_range >= 0.70:
        return BULLISH_PIN_BAR

    # ── Bearish Pin Bar ───────────────────────────────────────────
    # Upper wick >= 2x body, close in bottom 30% of candle range
    if body > 0 and upper_wick >= 2 * body and (h - c) / full_range >= 0.70:
        return BEARISH_PIN_BAR

    # ── Bullish Engulfing ─────────────────────────────────────────
    po, _, _, pc, pbody, *_ = _candle_parts(prev)
    if pc < po:  # prev candle is bearish
        if c > o and o < pc and c > po:  # current bullish engulfs prev body
            return BULLISH_ENGULFING

    # ── Bearish Engulfing ─────────────────────────────────────────
    if pc > po:  # prev candle is bullish
        if c < o and o > pc and c < po:  # current bearish engulfs prev body
            return BEARISH_ENGULFING

    return NO_PATTERN
