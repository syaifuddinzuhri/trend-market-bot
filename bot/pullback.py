import pandas as pd


def _touched(price: float, ema_val: float, atr: float, tolerance_ratio: float = 0.3) -> bool:
    """Price is considered 'touching' EMA if within tolerance * ATR."""
    return abs(price - ema_val) <= atr * tolerance_ratio


def has_pullback(df_h1: pd.DataFrame, direction: str) -> bool:
    """
    Check if the last H1 candle touched EMA20 or EMA50.
    direction: 'BULLISH' | 'BEARISH'
    """
    last = df_h1.iloc[-1]
    close = last["close"]
    low = last["low"]
    high = last["high"]
    atr = last["atr"]
    ema20 = last["ema20"]
    ema50 = last["ema50"]

    if direction == "BULLISH":
        # Price dipped into EMA20 or EMA50 from above
        touch20 = low <= ema20 <= high or _touched(close, ema20, atr)
        touch50 = low <= ema50 <= high or _touched(close, ema50, atr)
        return touch20 or touch50

    if direction == "BEARISH":
        # Price bounced into EMA20 or EMA50 from below
        touch20 = low <= ema20 <= high or _touched(close, ema20, atr)
        touch50 = low <= ema50 <= high or _touched(close, ema50, atr)
        return touch20 or touch50

    return False
