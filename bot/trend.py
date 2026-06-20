import pandas as pd

TREND_BULLISH = "BULLISH"
TREND_BEARISH = "BEARISH"
NO_TRADE = "NO_TRADE"


def get_trend(df_h4: pd.DataFrame) -> str:
    """
    Bullish : EMA50 > EMA200 AND Close > EMA200
    Bearish : EMA50 < EMA200 AND Close < EMA200
    """
    last = df_h4.iloc[-1]
    ema50 = last["ema50"]
    ema200 = last["ema200"]
    close = last["close"]

    if ema50 > ema200 and close > ema200:
        return TREND_BULLISH
    if ema50 < ema200 and close < ema200:
        return TREND_BEARISH
    return NO_TRADE
