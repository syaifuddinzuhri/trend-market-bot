import MetaTrader5 as mt5
import config
from bot.logger import log_console


def get_lot_size(symbol: str, sl_points: float, balance: float) -> float:
    """
    Jika FIXED_LOT > 0 di .env → pakai lot tetap.
    Jika FIXED_LOT = 0       → hitung otomatis dari RISK_PERCENT % balance.
    """
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        log_console(f"[RISK] symbol_info({symbol}) is None", level="ERROR")
        return 0.01

    lot_min = sym_info.volume_min
    lot_max = sym_info.volume_max
    lot_step = sym_info.volume_step

    if config.FIXED_LOT > 0:
        lot = round(round(config.FIXED_LOT / lot_step) * lot_step, 2)
        lot = max(lot_min, min(lot_max, lot))
        log_console(f"[RISK] Fixed lot = {lot}")
        return lot

    # Dynamic — risk-based
    risk_amount = balance * (config.RISK_PERCENT / 100.0)

    # Konversi risk_amount ke USD jika akun bukan USD
    # MT5 tick_value selalu dalam currency akun, jadi tidak perlu konversi manual —
    # MT5 sudah menyesuaikan tick_value dengan currency akun broker.
    tick_value = sym_info.trade_tick_value          # sudah dalam currency akun
    tick_value_profit = sym_info.trade_tick_value   # alias lebih eksplisit
    tick_size = sym_info.trade_tick_size

    currency = config.ACCOUNT_CURRENCY.upper()
    if currency != "USD":
        # Cek apakah MT5 memberi tick_value dalam currency akun atau USD
        # Pada beberapa broker IDR, tick_value sudah dalam IDR — langsung pakai.
        # Validasi: tick_value harus > 0
        if tick_value <= 0:
            log_console(f"[RISK] tick_value tidak valid ({tick_value}) — pakai lot_min", level="WARN")
            return lot_min
        log_console(f"[RISK] Currency akun: {currency} | tick_value per lot = {tick_value:.2f} {currency}")

    if tick_size == 0 or sl_points == 0:
        return lot_min

    ticks_in_sl = sl_points / tick_size
    value_per_lot = ticks_in_sl * tick_value

    if value_per_lot == 0:
        return lot_min

    raw_lot = risk_amount / value_per_lot
    lot = round(raw_lot / lot_step) * lot_step
    lot = max(lot_min, min(lot_max, lot))
    log_console(
        f"[RISK] Dynamic lot = {lot:.2f} | risk {config.RISK_PERCENT}% of {balance:,.0f} {currency} "
        f"= {risk_amount:,.0f} {currency}"
    )
    return round(lot, 2)


def swing_stop(df, direction: str, lookback: int = None) -> float:
    """Return swing low (BUY) or swing high (SELL) from last N bars."""
    n = lookback or config.SWING_LOOKBACK
    window = df.iloc[-n:]
    if direction == "BUY":
        return window["low"].min()
    return window["high"].max()


def calc_sl(df_h1, direction: str, entry: float) -> tuple[float, float]:
    """
    SL berbasis swing H1 + buffer dinamis (ATR H1 × ATR_SL_MULTIPLIER).
    Returns (sl_price, sl_distance).
    """
    swing = swing_stop(df_h1, direction)
    atr_h1 = df_h1.iloc[-1]["atr"]
    buffer = atr_h1 * config.ATR_SL_MULTIPLIER

    if direction == "BUY":
        sl = swing - buffer
        sl_dist = entry - sl
    else:
        sl = swing + buffer
        sl_dist = sl - entry

    log_console(
        f"[RISK] SL={sl:.2f} | swing_H1={swing:.2f} | ATR_buf={buffer:.2f} | dist={sl_dist:.2f}"
    )
    return sl, max(sl_dist, 0.0)
