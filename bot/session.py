from datetime import datetime, timezone, timedelta
import config

WIB = timezone(timedelta(hours=7))


def is_trading_session() -> bool:
    """
    Allowed window: SESSION_START_WIB (13:00) to SESSION_END_WIB (01:00 next day) WIB.
    Blocked window: 01:00 – 10:00 WIB.
    """
    now_wib = datetime.now(WIB)
    hour = now_wib.hour

    start = config.SESSION_START_WIB   # 13
    end = config.SESSION_END_WIB       # 1

    # Session spans midnight: valid hours are 13–23 and 0–1
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end
