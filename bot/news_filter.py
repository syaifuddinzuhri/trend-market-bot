"""
News filter — dua lapis:
  1. Calendar otomatis (ForexFactory via bot/calendar.py)
  2. Manual override di NEWS_EVENTS_UTC (untuk event yang tidak ada di feed)
"""
from datetime import datetime, timezone, timedelta
import config
from bot.logger import log_console

# ── Manual override (opsional, untuk event darurat) ───────────────
NEWS_EVENTS_UTC = [
    # "2025-07-30 18:00",  # FOMC manual
]

_BUFFER = timedelta(minutes=config.NEWS_BUFFER_MINUTES)


def _manual_lock() -> bool:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for event_str in NEWS_EVENTS_UTC:
        event_time = datetime.strptime(event_str, "%Y-%m-%d %H:%M")
        if event_time - _BUFFER <= now <= event_time + _BUFFER:
            return True
    return False


def is_news_lock() -> bool:
    """
    Cek news lock dari dua sumber:
    1. Calendar otomatis (ForexFactory)
    2. Manual list NEWS_EVENTS_UTC
    """
    # Coba calendar otomatis dulu
    try:
        from bot.calendar import is_news_lock_calendar, get_upcoming_events
        if is_news_lock_calendar():
            events = get_upcoming_events(config.NEWS_BUFFER_MINUTES)
            titles = ", ".join(e["title"] for e in events)
            log_console(f"[NEWS] LOCK — event: {titles}")
            return True
    except Exception as e:
        log_console(f"[NEWS] Calendar check error: {e} — fallback ke manual", level="WARN")

    # Fallback ke manual
    return _manual_lock()
