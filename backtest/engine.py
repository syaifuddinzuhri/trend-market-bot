"""
Backtesting Engine — menggunakan data historis dari MT5.

Cara kerja:
  - Fetch candle H4, H1, M15 dari MT5 untuk periode yang dipilih
  - Replay bar per bar simulasi logika bot
  - Hitung hasil setiap trade (SL/TP1/TP2/Trail)
  - Output: list of trade records

Keterbatasan:
  - Tidak ada slippage simulation (order fill diasumsikan di harga close/open)
  - Tidak ada spread dinamis
  - Trailing TP3 disederhanakan: exit saat close M15 cross EMA20
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

import config
from bot.indicators import add_emas, add_adx, add_atr
from bot.trend import get_trend, NO_TRADE
from bot.pullback import has_pullback
from bot.structure import get_market_structure, is_bullish_structure, is_bearish_structure
from bot.candlestick import check_pattern, BULLISH_PIN_BAR, BULLISH_ENGULFING, BEARISH_PIN_BAR, BEARISH_ENGULFING
from bot.session import WIB


class BacktestResult:
    def __init__(self):
        self.trades: list[dict] = []

    def add(self, trade: dict):
        self.trades.append(trade)

    def summary(self) -> dict:
        if not self.trades:
            return {}
        wins   = [t for t in self.trades if t["pnl_r"] > 0]
        losses = [t for t in self.trades if t["pnl_r"] <= 0]
        pnl_rs = [t["pnl_r"] for t in self.trades]
        gross_profit = sum(p for p in pnl_rs if p > 0)
        gross_loss   = abs(sum(p for p in pnl_rs if p < 0))

        # Equity curve
        equity = 0.0
        peak   = 0.0
        max_dd = 0.0
        for t in self.trades:
            equity += t["pnl_r"]
            peak    = max(peak, equity)
            dd      = peak - equity
            max_dd  = max(max_dd, dd)

        return {
            "total_trades":   len(self.trades),
            "wins":           len(wins),
            "losses":         len(losses),
            "win_rate":       round(len(wins) / len(self.trades) * 100, 1),
            "total_r":        round(sum(pnl_rs), 2),
            "avg_win_r":      round(np.mean([t["pnl_r"] for t in wins]), 2) if wins else 0,
            "avg_loss_r":     round(np.mean([t["pnl_r"] for t in losses]), 2) if losses else 0,
            "profit_factor":  round(gross_profit / gross_loss, 2) if gross_loss else float("inf"),
            "max_drawdown_r": round(max_dd, 2),
            "expectancy_r":   round(np.mean(pnl_rs), 3),
        }


def _fetch_all(symbol: str, date_from: datetime, date_to: datetime) -> tuple:
    """Fetch H4, H1, M15 candles dari MT5."""
    def fetch(tf, name):
        rates = mt5.copy_rates_range(symbol, tf, date_from, date_to)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"No data for {name}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = add_emas(df)
        df = add_adx(df, config.ADX_PERIOD)
        df = add_atr(df, config.ATR_PERIOD, config.ATR_MA_PERIOD)
        return df.reset_index(drop=True)

    h4  = fetch(mt5.TIMEFRAME_H4,  "H4")
    h1  = fetch(mt5.TIMEFRAME_H1,  "H1")
    m15 = fetch(mt5.TIMEFRAME_M15, "M15")
    return h4, h1, m15


def _session_ok(ts: pd.Timestamp) -> bool:
    dt_wib = ts.tz_localize("UTC").astimezone(WIB)
    hour = dt_wib.hour
    start, end = config.SESSION_START_WIB, config.SESSION_END_WIB
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


def run(
    symbol: str,
    date_from: datetime,
    date_to: datetime,
    initial_balance: float = 10_000_000,
) -> BacktestResult:
    print(f"\n[BT] Running backtest {symbol} | {date_from.date()} → {date_to.date()}")

    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    h4, h1, m15 = _fetch_all(symbol, date_from, date_to)
    print(f"[BT] Data: H4={len(h4)} bars | H1={len(h1)} bars | M15={len(m15)} bars")

    result = BacktestResult()
    balance = initial_balance
    WARMUP = 210  # candle warmup untuk indicator stabil

    # Iterasi per candle M15
    for i in range(WARMUP, len(m15)):
        candle = m15.iloc[i]
        ts = candle["time"]

        if not _session_ok(ts):
            continue

        # Slice data sampai candle saat ini (no lookahead)
        cur_m15 = m15.iloc[:i + 1]
        cur_h1  = h1[h1["time"] <= ts]
        cur_h4  = h4[h4["time"] <= ts]

        if len(cur_h1) < 50 or len(cur_h4) < 50:
            continue

        # ── Signal evaluation ─────────────────────────────────────
        trend = get_trend(cur_h4)
        if trend == NO_TRADE:
            continue

        direction = "BUY" if trend == "BULLISH" else "SELL"

        last_h1 = cur_h1.iloc[-1]
        adx_val = last_h1["adx"]
        atr_val = last_h1["atr"]
        atr_ma  = last_h1["atr_ma"]

        if adx_val < config.ADX_MIN:
            continue
        if pd.isna(atr_ma) or atr_val <= atr_ma:
            continue
        if not has_pullback(cur_h1, trend):
            continue

        structure = get_market_structure(cur_m15)
        if direction == "BUY" and not is_bullish_structure(structure):
            continue
        if direction == "SELL" and not is_bearish_structure(structure):
            continue

        pattern = check_pattern(cur_m15)
        if direction == "BUY" and pattern not in {BULLISH_PIN_BAR, BULLISH_ENGULFING}:
            continue
        if direction == "SELL" and pattern not in {BEARISH_PIN_BAR, BEARISH_ENGULFING}:
            continue

        # ── Entry price = open candle berikutnya ─────────────────
        if i + 1 >= len(m15):
            continue
        entry_candle = m15.iloc[i + 1]
        entry = entry_candle["open"]

        # ── SL: swing H1 + ATR buffer ────────────────────────────
        lookback = min(config.SWING_LOOKBACK, len(cur_h1) - 1)
        win_h1 = cur_h1.iloc[-lookback:]
        if direction == "BUY":
            swing = win_h1["low"].min()
            sl = swing - (atr_val * config.ATR_SL_MULTIPLIER)
            sl_dist = entry - sl
        else:
            swing = win_h1["high"].max()
            sl = swing + (atr_val * config.ATR_SL_MULTIPLIER)
            sl_dist = sl - entry

        if sl_dist <= 0:
            continue

        tp1 = entry + sl_dist * config.TP1_R if direction == "BUY" else entry - sl_dist * config.TP1_R
        tp2 = entry + sl_dist * config.TP2_R if direction == "BUY" else entry - sl_dist * config.TP2_R

        # ── Simulate forward ──────────────────────────────────────
        tp1_hit  = False
        tp2_hit  = False
        be_set   = False
        pnl_r    = 0.0
        exit_reason = ""
        exit_price  = entry
        remaining_r = 1.0      # 100% posisi dalam satuan R

        for j in range(i + 2, min(i + 200, len(m15))):
            fc = m15.iloc[j]
            hi, lo = fc["high"], fc["low"]

            if direction == "BUY":
                cur_sl = entry if be_set else sl
                # SL hit
                if lo <= cur_sl:
                    pnl_r += remaining_r * -1.0
                    exit_reason = "SL"
                    exit_price  = cur_sl
                    break
                # TP1
                if not tp1_hit and hi >= tp1:
                    pnl_r   += config.TP1_PCT * config.TP1_R
                    remaining_r -= config.TP1_PCT
                    tp1_hit  = True
                    be_set   = True
                # TP2
                if tp1_hit and not tp2_hit and hi >= tp2:
                    pnl_r   += config.TP2_PCT / (1 - config.TP1_PCT) * remaining_r * config.TP2_R
                    remaining_r -= config.TP2_PCT / (1 - config.TP1_PCT) * remaining_r
                    tp2_hit  = True
                # Trail: exit saat close < EMA20 H1
                if tp2_hit:
                    cur_h1_j = h1[h1["time"] <= fc["time"]]
                    if len(cur_h1_j) and fc["close"] < cur_h1_j.iloc[-1]["ema20"]:
                        trail_r = (fc["close"] - entry) / sl_dist
                        pnl_r  += remaining_r * trail_r
                        exit_reason = "TRAIL"
                        exit_price  = fc["close"]
                        break
            else:
                cur_sl = entry if be_set else sl
                if hi >= cur_sl:
                    pnl_r += remaining_r * -1.0
                    exit_reason = "SL"
                    exit_price  = cur_sl
                    break
                if not tp1_hit and lo <= tp1:
                    pnl_r   += config.TP1_PCT * config.TP1_R
                    remaining_r -= config.TP1_PCT
                    tp1_hit  = True
                    be_set   = True
                if tp1_hit and not tp2_hit and lo <= tp2:
                    pnl_r   += config.TP2_PCT / (1 - config.TP1_PCT) * remaining_r * config.TP2_R
                    remaining_r -= config.TP2_PCT / (1 - config.TP1_PCT) * remaining_r
                    tp2_hit  = True
                if tp2_hit:
                    cur_h1_j = h1[h1["time"] <= fc["time"]]
                    if len(cur_h1_j) and fc["close"] > cur_h1_j.iloc[-1]["ema20"]:
                        trail_r = (entry - fc["close"]) / sl_dist
                        pnl_r  += remaining_r * trail_r
                        exit_reason = "TRAIL"
                        exit_price  = fc["close"]
                        break
        else:
            # Timeout — tutup di harga terakhir
            last_close = m15.iloc[min(i + 200, len(m15) - 1)]["close"]
            if direction == "BUY":
                pnl_r += remaining_r * (last_close - entry) / sl_dist
            else:
                pnl_r += remaining_r * (entry - last_close) / sl_dist
            exit_reason = "TIMEOUT"
            exit_price  = last_close

        result.add({
            "time":          str(ts),
            "direction":     direction,
            "pattern":       pattern,
            "structure":     structure,
            "entry":         round(entry, 2),
            "sl":            round(sl, 2),
            "tp1":           round(tp1, 2),
            "tp2":           round(tp2, 2),
            "sl_dist":       round(sl_dist, 2),
            "exit_price":    round(exit_price, 2),
            "exit_reason":   exit_reason,
            "pnl_r":         round(pnl_r, 3),
            "tp1_hit":       tp1_hit,
            "tp2_hit":       tp2_hit,
        })

        # Skip forward sampai posisi selesai (hindari overlap trade)
        i = j if exit_reason else i

    mt5.shutdown()
    return result
