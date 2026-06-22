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


def notify_analysis(data: dict, positions: list, currency: str = "IDR"):
    """
    Kirim analisa market lengkap ke Telegram setiap 5 menit.
    data = dict dari signals.build_analysis()
    positions = list of dict: {direction, entry, sl, tp1, tp2, current, pnl, lot}
    """
    from datetime import datetime
    symbol    = data.get("symbol", "XAUUSD")
    direction = data.get("direction", "—")
    passed    = data.get("passed", 0)
    total     = data.get("total", 8)
    adx       = data.get("adx", 0)
    atr       = data.get("atr", 0)
    structure = data.get("structure", "")
    current   = data.get("current_price", 0)
    ema20     = data.get("ema20_h1", 0)
    ema50     = data.get("ema50_h1", 0)
    high20    = data.get("high_m15", 0)
    low20     = data.get("low_m15", 0)
    move      = data.get("move_label", "")
    rec       = data.get("recommendation", "")
    entry_z   = data.get("entry_zone", "")
    sl_l      = data.get("sl_level", "")
    tp1_l     = data.get("tp1_level", "")
    tp2_l     = data.get("tp2_level", "")
    missing   = data.get("missing_filters", [])

    arrow = "🟢 BUY" if direction == "BUY" else ("🔴 SELL" if direction == "SELL" else "⚪ SIDEWAYS")
    filter_icon = "🟢" if passed >= total else ("🔥" if passed >= 6 else ("⏳" if passed >= 4 else "💤"))
    struct_short = {
        "BULLISH_BOS": "BOS↑", "BEARISH_BOS": "BOS↓",
        "BULLISH_CHOCH": "CHoCH↑", "BEARISH_CHOCH": "CHoCH↓",
    }.get(structure, structure[:8] if structure else "—")

    now_str = datetime.now().strftime("%H:%M")

    lines = [
        f"📊 *Market Analysis — {symbol}* `{now_str}`",
        f"",
        f"*Trend H4*  : {arrow}",
        f"*Gerakan*   : {move}",
        f"*Struktur*  : `{struct_short}` | ADX `{adx:.1f}` | ATR `{atr:.2f}`",
        f"*Level EMA* : EMA20=`{ema20:.2f}` EMA50=`{ema50:.2f}`",
        f"*Range M15* : High `{high20:.2f}` — Low `{low20:.2f}`",
        f"*Filter*    : {filter_icon} `{passed}/{total}` lolos",
        f"",
        f"📌 *{rec}*",
    ]

    if missing:
        lines.append(f"❌ Belum lolos: `{'`, `'.join(missing)}`")

    if entry_z:
        lines += [
            f"",
            f"*Entry zona* : `{entry_z}`",
            f"*SL*         : `{sl_l}`",
            f"*TP1*        : `{tp1_l}`",
            f"*TP2*        : `{tp2_l}`",
        ]

    if positions:
        lines.append("")
        for p in positions:
            pnl_str    = f"{p['pnl']:+,.0f} {currency}"
            dist_tp1   = abs(p['tp1'] - p['current'])
            dist_sl    = abs(p['sl'] - p['current'])
            pos_icon   = "🟢" if p['pnl'] >= 0 else "🔴"
            lines += [
                f"─────────────────────",
                f"📍 *Posisi {p['direction']}* {pos_icon} `{pnl_str}`",
                f"Entry `{p['entry']:.2f}` → Sekarang `{p['current']:.2f}`",
                f"SL `{p['sl']:.2f}` ({dist_sl:.1f} buffer) | TP1 `{p['tp1']:.2f}` ({dist_tp1:.1f} lagi)",
                f"TP2 `{p['tp2']:.2f}` | Lot `{p['lot']}`",
            ]
    else:
        lines += ["", "📭 Tidak ada posisi terbuka"]

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
