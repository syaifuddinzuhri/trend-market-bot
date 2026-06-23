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
    momentum  = data.get("momentum_label", "")
    narasi    = data.get("narasi", "")
    bounce    = data.get("bounce_zone", "")
    exhaustion= data.get("is_exhaustion", False)
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
        f"*Momentum*  : {momentum}",
        f"*Gerakan*   : {move}",
        f"*Struktur*  : `{struct_short}` | ATR `{atr:.2f}`",
        f"*Level EMA* : EMA20=`{ema20:.2f}` EMA50=`{ema50:.2f}`",
        f"*Range M15* : High `{high20:.2f}` — Low `{low20:.2f}`",
        f"*Filter*    : {filter_icon} `{passed}/{total}` lolos",
    ]

    if narasi:
        lines += ["", f"💬 {narasi}"]

    lines += ["", f"📌 *{rec}*"]

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
    tp3: float,
    missing: list[str],
    move_label: str = "",
    momentum_label: str = "",
    ema20: float = 0,
    ema50: float = 0,
    high_m15: float = 0,
    low_m15: float = 0,
):
    from datetime import datetime
    arrow      = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    now_str    = datetime.now().strftime("%H:%M")
    sl_dist    = abs(entry - sl)
    tp1_dist   = abs(tp1 - entry)
    tp2_dist   = abs(tp2 - entry)
    tp3_dist   = abs(tp3 - entry)
    rr1        = tp1_dist / sl_dist if sl_dist else 0
    rr2        = tp2_dist / sl_dist if sl_dist else 0
    filter_bar = "🟩" * passed + "⬜" * (total - passed)
    missing_str = "\n".join(f"  ⚠️ {m}" for m in missing) if missing else "  ✅ Semua filter lolos"

    lines = [
        f"⚡ *ALERT MANUAL — {symbol}* `{now_str}`",
        f"",
        f"*Arah*      : {arrow}  `{passed}/{total}` {filter_bar}",
        f"*Momentum*  : {momentum_label or '—'}",
        f"*Gerakan*   : {move_label or '—'}",
        f"*Struktur*  : `{struct_short}` | Candle `{candle_short}`",
        f"*ATR*       : `{atr_val:.2f}` / MA `{atr_ma:.2f}`",
    ]

    if ema20 or ema50:
        lines.append(f"*EMA H1*   : EMA20=`{ema20:.2f}` EMA50=`{ema50:.2f}`")
    if high_m15 or low_m15:
        lines.append(f"*Range M15*: High `{high_m15:.2f}` — Low `{low_m15:.2f}`")

    lines += [
        f"",
        f"*Entry*  : `{entry:.2f}`",
        f"*SL*     : `{sl:.2f}`  ({sl_dist:.1f} pip)",
        f"*TP1*    : `{tp1:.2f}`  (+{tp1_dist:.1f} pip | RR 1:{rr1:.1f})",
        f"*TP2*    : `{tp2:.2f}`  (+{tp2_dist:.1f} pip | RR 1:{rr2:.1f})",
        f"*TP3*    : `{tp3:.2f}`  (+{tp3_dist:.1f} pip | trailing)",
        f"",
        f"*Belum lolos:*",
        missing_str,
        f"",
        f"_Entry manual sekarang atau tunggu filter penuh_",
    ]
    send("\n".join(lines))


def notify_trail_exit(ticket: int, symbol: str, price: float, pnl: float):
    msg = (
        f"🏁 *Trail Exit — {symbol}*\n"
        f"Ticket  : `{ticket}`\n"
        f"Price   : `{price:.3f}`\n"
        f"PnL     : `{pnl:+.2f}`"
    )
    send(msg)
