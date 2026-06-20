import csv
import os
import sqlite3
from datetime import datetime

import config

_FIELDS = [
    "timestamp", "symbol", "direction", "trend_status",
    "adx", "atr", "pattern",
    "entry_price", "stop_loss", "take_profit",
    "lot_size", "ticket", "result", "pnl",
]


def log_console(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def _ensure_db():
    os.makedirs(os.path.dirname(config.LOG_DB), exist_ok=True)
    conn = sqlite3.connect(config.LOG_DB)
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS trades (
            {", ".join(f + " TEXT" for f in _FIELDS)}
        )"""
    )
    conn.commit()
    return conn


def _ensure_csv():
    os.makedirs(os.path.dirname(config.LOG_CSV), exist_ok=True)
    if not os.path.exists(config.LOG_CSV):
        with open(config.LOG_CSV, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_FIELDS).writeheader()


def log_trade(record: dict):
    record.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # SQLite
    try:
        conn = _ensure_db()
        placeholders = ", ".join("?" * len(_FIELDS))
        values = [str(record.get(f, "")) for f in _FIELDS]
        conn.execute(f"INSERT INTO trades VALUES ({placeholders})", values)
        conn.commit()
        conn.close()
    except Exception as e:
        log_console(f"[LOG] DB write error: {e}", level="ERROR")

    # CSV
    try:
        _ensure_csv()
        with open(config.LOG_CSV, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writerow({f: record.get(f, "") for f in _FIELDS})
    except Exception as e:
        log_console(f"[LOG] CSV write error: {e}", level="ERROR")
