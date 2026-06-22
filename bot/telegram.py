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
        f"Entry   : `{entry:.3f}`\n"
        f"SL      : `{sl:.3f}`\n"
        f"TP1     : `{tp1:.3f}`\n"
        f"TP2     : `{tp2:.3f}`\n"
        f"Lot     : `{lot}`"
    )
    send(msg)


def notify_tp(ticket: int, symbol: str, tp_level: str, price: float, pnl: float):
    msg = (
        f"✅ *TP HIT — {symbol}*\n"
        f"Ticket  : `{ticket}`\n"
        f"Level   : `{tp_level}`\n"
        f"Price   : `{price:.3f}`\n"
        f"PnL     : `{pnl:+.2f} USD`"
    )
    send(msg)


def notify_sl(ticket: int, symbol: str, price: float, pnl: float):
    msg = (
        f"❌ *SL HIT — {symbol}*\n"
        f"Ticket  : `{ticket}`\n"
        f"Price   : `{price:.3f}`\n"
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
        f"Entry   : `{entry:.3f}`\n"
        f"SL      : `{sl:.3f}`\n"
        f"TP1     : `{tp1:.3f}`\n"
        f"TP2     : `{tp2:.3f}`\n"
        f"Lot     : `{lot}`"
    )
    send(msg)


def notify_pyramid(direction: str, symbol: str, entry: float, sl: float, tp1: float, tp2: float, lot: float, parent_ticket: int):
    arrow = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    msg = (
        f"📐 *PYRAMID {arrow} — {symbol}*\n"
        f"Parent  : `#{parent_ticket}`\n"
        f"Entry   : `{entry:.3f}`\n"
        f"SL      : `{sl:.3f}`\n"
        f"TP1     : `{tp1:.3f}`\n"
        f"TP2     : `{tp2:.3f}`\n"
        f"Lot     : `{lot}`"
    )
    send(msg)


def notify_analysis(
    symbol: str,
    direction: str,
    trend_label: str,
    adx: float,
    atr: float,
    structure: str,
    passed: int,
    total: int,
    positions: list,
    currency: str = "IDR",
):
    """
    Kirim analisa market ke Telegram setiap 30 menit.
    positions = list of dict: {direction, entry, sl, tp1, tp2, current, pnl, lot}
    """
    arrow = "🟢 BUY" if direction == "BUY" else ("🔴 SELL" if direction == "SELL" else "⚪ SIDEWAYS")
    status_icon = "🟢" if passed == total else ("🔥" if passed >= 6 else ("⏳" if passed >= 4 else "💤"))

    struct_short = {
        "BULLISH_BOS": "BOS↑", "BEARISH_BOS": "BOS↓",
        "BULLISH_CHOCH": "CHoCH↑", "BEARISH_CHOCH": "CHoCH↓",
    }.get(structure, structure[:8] if structure else "—")

    lines = [
        f"📊 *Analisa {symbol}*",
        f"",
        f"Trend    : {arrow}",
        f"ADX      : `{adx:.1f}` | ATR : `{atr:.2f}`",
        f"Struktur : `{struct_short}`",
        f"Filter   : {status_icon} `{passed}/{total}`",
    ]

    if positions:
        for p in positions:
            pnl_str = f"{p['pnl']:+,.0f} {currency}"
            pip_to_tp1 = abs(p['tp1'] - p['current'])
            pip_to_sl  = abs(p['sl']  - p['current'])
            pos_arrow  = "🟢" if p['pnl'] >= 0 else "🔴"
            lines += [
                f"",
                f"📍 *Posisi {p['direction']} aktif* {pos_arrow}",
                f"Entry    : `{p['entry']:.3f}`",
                f"Sekarang : `{p['current']:.3f}` ({pnl_str})",
                f"SL       : `{p['sl']:.3f}` ({pip_to_sl:.2f} pip buffer)",
                f"TP1      : `{p['tp1']:.3f}` (~{pip_to_tp1:.2f} pip lagi)",
                f"TP2      : `{p['tp2']:.3f}`",
                f"Lot      : `{p['lot']}`",
            ]
    else:
        lines += ["", "📭 *Tidak ada posisi terbuka*"]

    send("\n".join(lines))


def notify_alert_manual(
    direction: str,
    symbol: str,
    passed: int,
    total: int,
    adx: float,
    atr_val: float,
    atr_ma: float,
    struct_short: str,
    candle_short: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    missing: list[str],
):
    """
    Notif manual entry alert — dikirim saat filter >= 7/8.
    Hanya dikirim sekali per kondisi (throttle di scan_log).
    """
    arrow = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    missing_str = "\n".join(f"  ⚠️ {m}" for m in missing) if missing else "  ✅ Semua filter lolos"
    msg = (
        f"⚡ *ALERT MANUAL — {symbol}* ({passed}/{total})\n"
        f"\n"
        f"Arah     : {arrow}\n"
        f"ADX      : `{adx:.1f}` | ATR: `{atr_val:.2f}` / MA `{atr_ma:.2f}`\n"
        f"Struktur : `{struct_short}` | Candle: `{candle_short}`\n"
        f"\n"
        f"Entry    : `{entry:.2f}`\n"
        f"SL       : `{sl:.2f}`\n"
        f"TP1      : `{tp1:.2f}`\n"
        f"TP2      : `{tp2:.2f}`\n"
        f"\n"
        f"*Belum lolos:*\n{missing_str}\n"
        f"\n"
        f"_Entry manual jika filter terpenuhi_"
    )
    send(msg)


def notify_trail_exit(ticket: int, symbol: str, price: float, pnl: float):
    msg = (
        f"🏁 *Trail Exit — {symbol}*\n"
        f"Ticket  : `{ticket}`\n"
        f"Price   : `{price:.3f}`\n"
        f"PnL     : `{pnl:+.2f}`"
    )
    send(msg)
