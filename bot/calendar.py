"""
Economic Calendar — fetch otomatis dari ForexFactory RSS.

Cara kerja:
  - Setiap hari refresh jadwal news high-impact untuk USD
  - Cache disimpan di logs/calendar_cache.json
  - is_news_lock() di news_filter.py menggunakan data ini
  - Refresh otomatis dipanggil dari main.py setiap hari 00:05 WIB
"""
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests

import config
from bot.logger import log_console

CACHE_FILE = "logs/calendar_cache.json"
FF_RSS_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Keyword event yang di-filter
HIGH_IMPACT_KEYWORDS = [
    "FOMC", "Federal Funds Rate", "Fed",
    "Non-Farm", "NFP",
    "CPI", "Consumer Price Index",
    "PCE", "Core PCE",
    "PPI", "GDP",
    "Unemployment",
    "Interest Rate",
    "Jackson Hole",
    "Retail Sales",
    "ISM",
]

WIB = timezone(timedelta(hours=7))
_cached_events: list[dict] = []
_last_fetch_date: str = ""
_last_fetch_ts: float = 0.0        # epoch seconds of last actual HTTP request
FETCH_COOLDOWN_SECONDS = 3600      # ForexFactory updates feed once per hour — never fetch more often


def _keyword_match(title: str) -> bool:
    title_up = title.upper()
    return any(kw.upper() in title_up for kw in HIGH_IMPACT_KEYWORDS)


def fetch_calendar() -> list[dict]:
    """
    Fetch weekly calendar dari ForexFactory JSON feed.
    Returns list of {'title': str, 'datetime_utc': datetime}
    """
    try:
        resp = requests.get(FF_RSS_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log_console(f"[CAL] Fetch error: {e}", level="WARN")
        return []

    events = []
    for item in data:
        # Hanya USD, impact High
        if item.get("country", "").upper() != "USD":
            continue
        if item.get("impact", "").lower() != "high":
            continue

        title = item.get("title", "")
        if not _keyword_match(title):
            continue

        date_str = item.get("date", "")      # "01-06-2025"
        time_str = item.get("time", "")      # "2:00pm"

        try:
            if time_str:
                dt = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p")
            else:
                dt = datetime.strptime(date_str, "%m-%d-%Y")
            # ForexFactory menggunakan ET (UTC-5 / UTC-4 DST) — kita simpan sebagai UTC naive
            # dan biarkan news_filter.py menggunakan buffer ±30 menit
            events.append({"title": title, "datetime_str": dt.strftime("%Y-%m-%d %H:%M")})
        except Exception:
            continue

    log_console(f"[CAL] Fetched {len(events)} high-impact USD events")
    return events


def refresh(force: bool = False):
    """Fetch calendar dari ForexFactory — maksimal sekali per jam."""
    global _cached_events, _last_fetch_date, _last_fetch_ts
    import time

    now_ts = time.time()

    # Hard rate-limit: never hit the API more than once per hour (success or failure)
    if not force and (now_ts - _last_fetch_ts) < FETCH_COOLDOWN_SECONDS:
        return

    os.makedirs("logs", exist_ok=True)
    _last_fetch_ts = now_ts  # stamp BEFORE the request so concurrent calls are blocked

    today = datetime.now(WIB).strftime("%Y-%m-%d")
    events = fetch_calendar()
    if events:
        _cached_events = events
        _last_fetch_date = today
        with open(CACHE_FILE, "w") as f:
            json.dump({"date": today, "events": events, "fetched_ts": now_ts}, f, indent=2)
        log_console(f"[CAL] Calendar cache updated — {len(events)} events")
    else:
        _load_cache()


def _load_cache():
    global _cached_events, _last_fetch_date, _last_fetch_ts
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                data = json.load(f)
            _cached_events = data.get("events", [])
            _last_fetch_date = data.get("date", "")
            _last_fetch_ts = float(data.get("fetched_ts", 0.0))
            log_console(f"[CAL] Loaded {len(_cached_events)} events from cache ({_last_fetch_date})")
        except Exception as e:
            log_console(f"[CAL] Cache load error: {e}", level="WARN")


def get_upcoming_events(within_minutes: int = 60) -> list[dict]:
    """Return events yang akan terjadi dalam N menit ke depan (UTC naive)."""
    now = datetime.utcnow()
    result = []
    for ev in _cached_events:
        try:
            ev_time = datetime.strptime(ev["datetime_str"], "%Y-%m-%d %H:%M")
            diff = (ev_time - now).total_seconds() / 60
            if -within_minutes <= diff <= within_minutes:
                result.append({**ev, "minutes_away": round(diff)})
        except Exception:
            continue
    return result


def is_news_lock_calendar() -> bool:
    """True jika ada event high-impact dalam buffer NEWS_BUFFER_MINUTES."""
    return len(get_upcoming_events(config.NEWS_BUFFER_MINUTES)) > 0


# Auto-load cache saat module diimport
_load_cache()
