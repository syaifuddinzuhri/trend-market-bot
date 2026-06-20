import requests
import config
from bot.logger import log_console

_BASE = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"


def send(message: str):
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    try:
        resp = requests.post(
            _BASE,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
        if not resp.ok:
            log_console(f"[TG] Send failed: {resp.text}", level="WARN")
    except Exception as e:
        log_console(f"[TG] Exception: {e}", level="WARN")


def notify_signal(
    direction: str, symbol: str, entry: float, sl: float,
    tp1: float, tp2: float, lot: float, pattern: str,
    structure: str = "", strength: str = "",
):
    arrow = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    struct_label = ""
    if structure:
        icon = "💪" if strength == "STRONG" else "⚡"
        struct_label = f"\nStruktur: `{structure}` {icon}"
    msg = (
        f"*{arrow} SIGNAL — {symbol}*"
        f"{struct_label}\n"
        f"Pattern : `{pattern}`\n"
        f"Entry   : `{entry}`\n"
        f"SL      : `{sl}`\n"
        f"TP1     : `{tp1}`\n"
        f"TP2     : `{tp2}`\n"
        f"Lot     : `{lot}`"
    )
    send(msg)


def notify_tp(ticket: int, symbol: str, tp_level: str, price: float, pnl: float):
    msg = (
        f"✅ *TP HIT — {symbol}*\n"
        f"Ticket  : `{ticket}`\n"
        f"Level   : `{tp_level}`\n"
        f"Price   : `{price}`\n"
        f"PnL     : `{pnl:+.2f} USD`"
    )
    send(msg)


def notify_sl(ticket: int, symbol: str, price: float, pnl: float):
    msg = (
        f"❌ *SL HIT — {symbol}*\n"
        f"Ticket  : `{ticket}`\n"
        f"Price   : `{price}`\n"
        f"PnL     : `{pnl:+.2f} USD`"
    )
    send(msg)


def notify_breakeven(ticket: int, symbol: str):
    msg = f"🔁 *Breakeven set — {symbol}* | Ticket `{ticket}`"
    send(msg)


def notify_continuation(signal_type: str, direction: str, symbol: str, entry: float, sl: float, tp1: float, tp2: float, lot: float):
    arrow = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    label = "EMA RETEST" if signal_type == "EMA_RETEST" else "HLC CONTINUATION"
    msg = (
        f"🔄 *{arrow} {label} — {symbol}*\n"
        f"Entry   : `{entry}`\n"
        f"SL      : `{sl}`\n"
        f"TP1     : `{tp1}`\n"
        f"TP2     : `{tp2}`\n"
        f"Lot     : `{lot}`"
    )
    send(msg)


def notify_pyramid(direction: str, symbol: str, entry: float, sl: float, tp1: float, tp2: float, lot: float, parent_ticket: int):
    arrow = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    msg = (
        f"📐 *PYRAMID {arrow} — {symbol}*\n"
        f"Parent  : `#{parent_ticket}`\n"
        f"Entry   : `{entry}`\n"
        f"SL      : `{sl}`\n"
        f"TP1     : `{tp1}`\n"
        f"TP2     : `{tp2}`\n"
        f"Lot     : `{lot}`"
    )
    send(msg)


def notify_trail_exit(ticket: int, symbol: str, price: float, pnl: float):
    msg = (
        f"🏁 *Trail Exit — {symbol}*\n"
        f"Ticket  : `{ticket}`\n"
        f"Price   : `{price}`\n"
        f"PnL     : `{pnl:+.2f}`"
    )
    send(msg)
