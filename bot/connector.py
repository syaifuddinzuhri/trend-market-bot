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
