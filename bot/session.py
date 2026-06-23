from datetime import datetime, timezone, timedelta
import config

WIB = timezone(timedelta(hours=7))


def is_trading_session() -> bool:
    if not config.SESSION_ENABLED:
        return True

    now_wib = datetime.now(WIB)
    hour = now_wib.hour
    start = config.SESSION_START_WIB
    end   = config.SESSION_END_WIB

    if start > end:
        return hour >= start or hour < end
    return start <= hour < end
