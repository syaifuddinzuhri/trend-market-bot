import numpy as np
import pandas as pd
import MetaTrader5 as mt5
import config
from bot.logger import log_console


def get_candles(symbol: str, timeframe, count: int = 300) -> pd.DataFrame | None:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        log_console(f"[IND] No rates for {symbol} tf={timeframe}", level="WARN")
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def add_emas(df: pd.DataFrame) -> pd.DataFrame:
    for p in config.EMA_PERIODS:
        df[f"ema{p}"] = ema(df["close"], p)
    return df


def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_s = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_s
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0)

    df["adx"] = dx.ewm(alpha=1 / period, adjust=False).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    return df


def add_atr(df: pd.DataFrame, period: int = 14, ma_period: int = 20) -> pd.DataFrame:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    df["atr"] = tr.ewm(span=period, adjust=False).mean()
    df["atr_ma"] = df["atr"].rolling(ma_period).mean()
    return df


def get_h4(symbol: str) -> pd.DataFrame | None:
    df = get_candles(symbol, config.TF_H4, 300)
    if df is None:
        return None
    df = add_emas(df)
    df = add_adx(df, config.ADX_PERIOD)
    df = add_atr(df, config.ATR_PERIOD, config.ATR_MA_PERIOD)
    return df


def get_h1(symbol: str) -> pd.DataFrame | None:
    df = get_candles(symbol, config.TF_H1, 300)
    if df is None:
        return None
    df = add_emas(df)
    df = add_adx(df, config.ADX_PERIOD)
    df = add_atr(df, config.ATR_PERIOD, config.ATR_MA_PERIOD)
    return df


def get_m15(symbol: str) -> pd.DataFrame | None:
    df = get_candles(symbol, config.TF_M15, 200)
    if df is None:
        return None
    df = add_emas(df)
    df = add_adx(df, config.ADX_PERIOD)
    df = add_atr(df, config.ATR_PERIOD, config.ATR_MA_PERIOD)
    return df
