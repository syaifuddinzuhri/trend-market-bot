import time
import MetaTrader5 as mt5
import config
from bot.logger import log_console


def connect() -> bool:
    """Initialize and login to MT5. Returns True on success."""
    if not mt5.initialize():
        log_console(f"[MT5] initialize() failed: {mt5.last_error()}", level="ERROR")
        return False

    authorized = mt5.login(
        login=config.MT5_LOGIN,
        password=config.MT5_PASSWORD,
        server=config.MT5_SERVER,
    )
    if not authorized:
        log_console(f"[MT5] login failed: {mt5.last_error()}", level="ERROR")
        mt5.shutdown()
        return False

    info = mt5.account_info()
    log_console(
        f"[MT5] Connected | Account: {info.login} | Balance: {info.balance:.2f} {info.currency} | Server: {info.server}"
    )

    # Resolve timeframe constants once connected
    config.TF_H4  = mt5.TIMEFRAME_H4
    config.TF_H1  = mt5.TIMEFRAME_H1
    config.TF_M15 = mt5.TIMEFRAME_M15
    config.TF_M5  = mt5.TIMEFRAME_M5

    # Enable symbol agar MT5 mau load data historis
    if not mt5.symbol_select(config.SYMBOL, True):
        log_console(f"[MT5] symbol_select({config.SYMBOL}) gagal — coba lanjut", level="WARN")
    else:
        log_console(f"[MT5] Symbol {config.SYMBOL} enabled")

    # Warm-up: request satu bar per timeframe agar MT5 mulai load data
    for tf, label in [
        (mt5.TIMEFRAME_H4, "H4"), (mt5.TIMEFRAME_H1, "H1"),
        (mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_M5, "M5"),
    ]:
        rates = mt5.copy_rates_from_pos(config.SYMBOL, tf, 0, 1)
        if rates is None or len(rates) == 0:
            log_console(f"[MT5] Warm-up {label} belum ada data — MT5 sedang load", level="WARN")
        else:
            log_console(f"[MT5] Warm-up {label} OK")

    return True


def disconnect():
    mt5.shutdown()
    log_console("[MT5] Disconnected.")


def reconnect(retries: int = 5, delay: int = 10) -> bool:
    for attempt in range(1, retries + 1):
        log_console(f"[MT5] Reconnect attempt {attempt}/{retries}...")
        if connect():
            return True
        time.sleep(delay)
    return False


def account_info():
    return mt5.account_info()


def get_balance() -> float:
    info = mt5.account_info()
    return info.balance if info else 0.0
