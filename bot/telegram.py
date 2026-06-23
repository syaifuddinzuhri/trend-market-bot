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
    Kirim analisa market terstruktur ke Telegram setiap 5 menit.
    Format: Header | Situasi M15 | Situasi M5 | Rekomendasi | Yang Perlu Dipantau | Posisi
    """
    from datetime import datetime
    symbol     = data.get("symbol", "XAUUSD")
    direction  = data.get("direction", "—")
    passed     = data.get("passed", 0)
    total      = data.get("total", 8)
    adx        = data.get("adx", 0)
    atr        = data.get("atr", 0)
    structure  = data.get("structure", "")
    current    = data.get("current_price", 0)
    ema20      = data.get("ema20_h1", 0)
    ema50      = data.get("ema50_h1", 0)
    high20     = data.get("high_m15", 0)
    low20      = data.get("low_m15", 0)
    momentum   = data.get("momentum_label", "")
    is_sideways= data.get("is_sideways", False)
    exhaustion = data.get("is_exhaustion", False)
    avg_body   = data.get("avg_body_pip", 0)
    move_from_high = data.get("move_from_high", 0)
    move_from_low  = data.get("move_from_low", 0)
    pullback_pips  = data.get("pullback_pips", 0)
    pullback_size  = data.get("pullback_size", "")
    bounce_zone    = data.get("bounce_zone", "")
    entry_z    = data.get("entry_zone", "")
    sl_l       = data.get("sl_level", "")
    tp1_l      = data.get("tp1_level", "")
    tp2_l      = data.get("tp2_level", "")
    tp3_l      = data.get("tp3_level", "")
    missing    = data.get("missing_filters", [])
    pantau     = data.get("pantau", [])

    arrow = "🟢 BUY" if direction == "BUY" else ("🔴 SELL" if direction == "SELL" else "⚪ SIDEWAYS")
    filter_icon = "✅" if passed >= total else ("🔥" if passed >= 6 else ("⏳" if passed >= 4 else "💤"))
    struct_short = {
        "BULLISH_BOS": "BOS↑", "BEARISH_BOS": "BOS↓",
        "BULLISH_CHOCH": "CHoCH↑", "BEARISH_CHOCH": "CHoCH↓",
    }.get(structure, structure[:8] if structure else "NO_STRUC")
    now_str = datetime.now().strftime("%H:%M")

    lines = [f"📊 *Analisa {symbol}* `{now_str}` — {arrow} {filter_icon} `{passed}/{total}`", ""]

    # ── Situasi M15 ────────────────────────────────────────────────
    lines.append("*📈 Situasi M15:*")
    if direction == "SELL":
        lines.append(f"Downtrend — harga turun *{move_from_high:.0f} pip* dari high `{high20:.2f}`")
    elif direction == "BUY":
        lines.append(f"Uptrend — harga naik *{move_from_low:.0f} pip* dari low `{low20:.2f}`")
    else:
        lines.append("Ranging — belum ada trend jelas")

    lines.append(f"Struktur: `{struct_short}` | {momentum}")
    lines.append(f"EMA20=`{ema20:.2f}` EMA50=`{ema50:.2f}` | ATR=`{atr:.2f}`")
    lines.append(f"Range: `{low20:.2f}` — `{high20:.2f}`")

    if pullback_pips > 10:
        pb_icon = "⚠️" if pullback_size == "besar" else "↩️"
        lines.append(f"{pb_icon} Pullback *{pullback_size}* {pullback_pips:.0f} pip dari low")

    # ── Situasi M5 ─────────────────────────────────────────────────
    lines += ["", "*📉 Situasi M5:*"]
    if exhaustion:
        lines.append(f"Candle kecil — konsolidasi/exhaustion (avg body {avg_body:.1f} pip)")
    else:
        lines.append(f"Candle aktif — momentum masih berjalan (avg body {avg_body:.1f} pip)")

    if is_sideways:
        lines.append("⚪ ADX lemah — pasar ranging di M5")
    elif adx >= 45:
        lines.append(f"🔴 Momentum sangat kuat (ADX {adx:.1f}) — strong trend mode aktif")
    elif adx >= 25:
        lines.append(f"🟢 Momentum trending (ADX {adx:.1f})")

    # ── Rekomendasi ────────────────────────────────────────────────
    lines += ["", "*📌 Rekomendasi:*"]
    if is_sideways:
        lines.append(f"TUNGGU — pasar ranging, hindari entry")
        lines.append(f"Pantau breakout dari range `{low20:.2f}`–`{high20:.2f}`")
    elif entry_z:
        if passed >= 7:
            lines.append(f"✅ *SIAP ENTRY {arrow}* di `{entry_z}`")
        elif passed == 6:
            lines.append(f"⚡ *POTENSI ENTRY {arrow}* di `{entry_z}` — pertimbangkan entry manual")
        elif pullback_size == "besar" and direction:
            opp = "BUY" if direction == "SELL" else "SELL"
            lines.append(f"⚠️ Pullback besar — bisa scalp *{opp}* counter-trend ke `{entry_z}`")
            lines.append(f"ATAU tunggu rejection di zona lalu *{direction}* ulang")
        elif bounce_zone:
            lines.append(f"⏳ Tunggu *{direction}* — harga pullback, zona entry: `{bounce_zone}`")
            lines.append(f"Cari rejection candle di zona tersebut")
        lines += [
            f"SL  : `{sl_l}`",
            f"TP1 : `{tp1_l}` | TP2 : `{tp2_l}`" + (f" | TP3 : `{tp3_l}`" if tp3_l else ""),
        ]
    else:
        if direction == "SELL":
            lines.append(f"MONITOR — tunggu pullback ke EMA20 `{ema20:.2f}` lalu cari rejection → SELL")
        elif direction == "BUY":
            lines.append(f"MONITOR — tunggu pullback ke EMA20 `{ema20:.2f}` lalu cari bounce → BUY")
        else:
            lines.append("TUNGGU — trend H4 belum jelas")

    if missing:
        lines.append(f"❌ Filter belum lolos: `{'`, `'.join(missing)}`")

    # ── Yang perlu dipantau ────────────────────────────────────────
    if pantau:
        lines += ["", "*👁 Yang perlu dipantau:*"]
        for p in pantau:
            lines.append(f"• {p}")

    # ── Posisi aktif ───────────────────────────────────────────────
    if positions:
        lines.append("")
        for p in positions:
            pnl_str  = f"{p['pnl']:+,.0f} {currency}"
            dist_tp1 = abs(p['tp1'] - p['current'])
            dist_sl  = abs(p['sl'] - p['current'])
            pos_icon = "🟢" if p['pnl'] >= 0 else "🔴"
            lines += [
                "─────────────────────",
                f"📍 *Posisi {p['direction']}* {pos_icon} `{pnl_str}`",
                f"Entry `{p['entry']:.2f}` → Kini `{p['current']:.2f}`",
                f"SL `{p['sl']:.2f}` ({dist_sl:.1f} buffer) | TP1 `{p['tp1']:.2f}` ({dist_tp1:.1f} lagi)",
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
    adverse_warning: str = "",
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

    if adverse_warning:
        lines += ["", adverse_warning]

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


def notify_counter_trend(
    direction: str,
    main_direction: str,
    symbol: str,
    pullback_pips: float,
    structure: str,
    pattern: str,
    entry: float,
    sl: float,
    tp1: float,
    adx: float,
):
    """Alert peluang scalp counter-trend saat pullback besar."""
    from datetime import datetime
    arrow      = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    main_arrow = "🟢 BUY" if main_direction == "BUY" else "🔴 SELL"
    sl_dist    = abs(entry - sl)
    tp1_dist   = abs(tp1 - entry)
    rr         = tp1_dist / sl_dist if sl_dist else 0
    now_str    = datetime.now().strftime("%H:%M")
    msg = (
        f"↩️ *SCALP COUNTER-TREND — {symbol}* `{now_str}`\n"
        f"\n"
        f"Trend utama : {main_arrow} | Pullback : *{pullback_pips:.0f} pip*\n"
        f"Peluang     : {arrow} _(berlawanan trend utama)_\n"
        f"\n"
        f"Struktur M15 : `{structure}` | Candle : `{pattern}`\n"
        f"ADX          : `{adx:.1f}`\n"
        f"\n"
        f"Entry : `{entry:.2f}`\n"
        f"SL    : `{sl:.2f}`  ({sl_dist:.1f} pip)\n"
        f"TP1   : `{tp1:.2f}`  (+{tp1_dist:.1f} pip | RR 1:{rr:.1f})\n"
        f"\n"
        f"⚠️ _Counter-trend — resiko lebih tinggi, gunakan lot kecil_"
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
