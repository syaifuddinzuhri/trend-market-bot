"""
XAUUSD Trend Following Bot
Run: python main.py
Requires: MT5 terminal open and logged in with the same account as .env
"""
import time
import sys
from datetime import datetime, date as _date, timedelta

import MetaTrader5 as mt5

import config
from bot import connector, trade, telegram
from bot import signals
from bot.indicators import get_h4, get_h1, get_m15, get_m5
from bot.risk import get_lot_size, calc_sl
from bot.logger import log_console, log_trade
from bot.session import is_trading_session
from bot.news_filter import is_news_lock
from bot.calendar import refresh as calendar_refresh

HEARTBEAT_INTERVAL    = 5      # detik antara console status
SIGNAL_CHECK_INTERVAL = 5      # detik antara full signal check (M5 butuh respons cepat)
ANALYSIS_INTERVAL     = 300    # detik antara analisa Telegram (5 menit)

# Ticket yang dibuka bot session ini
_open_tickets: set[int] = set()
_last_signal_check  = 0.0
_last_analysis_sent = 0.0
_last_pending_placed = 0.0   # epoch seconds saat terakhir pasang pending
PENDING_COOLDOWN = 300        # 5 menit cooldown antar pending placement

# Daily trade counter (hanya posisi induk, bukan pyramid)
_trades_today: int = 0
_trade_count_date: _date | None = None

# Waktu entry terakhir untuk MIN_ENTRY_INTERVAL
_last_entry_time: datetime | None = None


def _daily_limit_reached() -> bool:
    global _trades_today, _trade_count_date
    today = _date.today()
    if _trade_count_date != today:
        _trade_count_date = today
        _trades_today = 0
    if config.MAX_TRADES_PER_DAY == 0:
        return False
    return _trades_today >= config.MAX_TRADES_PER_DAY


def _increment_trade_count():
    global _trades_today, _trade_count_date, _last_entry_time
    today = _date.today()
    if _trade_count_date != today:
        _trade_count_date = today
        _trades_today = 0
    _trades_today += 1
    _last_entry_time = datetime.now()


def _interval_ok() -> bool:
    """Cek apakah sudah lewat MIN_ENTRY_INTERVAL menit sejak entry terakhir."""
    if _last_entry_time is None:
        return True
    elapsed = (datetime.now() - _last_entry_time).total_seconds() / 60
    if elapsed < config.MIN_ENTRY_INTERVAL:
        log_console(
            f"[BOT] Interval belum cukup ({elapsed:.0f}/{config.MIN_ENTRY_INTERVAL} menit) — skip"
        )
        return False
    return True


def _distance_ok(entry_price: float, direction: str, atr_h1: float) -> bool:
    """
    Cek jarak harga entry baru terhadap semua posisi terbuka.
    Entry baru tidak boleh terlalu dekat dengan posisi yang sudah ada.
    """
    min_dist = atr_h1 * config.MIN_ENTRY_DISTANCE_ATR
    positions = mt5.positions_get(symbol=config.SYMBOL) or []
    for p in positions:
        if p.magic != config.MAGIC_NUMBER:
            continue
        dist = abs(entry_price - p.price_open)
        if dist < min_dist:
            log_console(
                f"[BOT] Entry terlalu dekat posisi #{p.ticket} "
                f"(dist={dist:.2f} < min={min_dist:.2f}) — skip"
            )
            return False
    return True


def _get_parent_positions() -> list:
    """Return posisi induk (bukan pyramid) yang dibuka bot."""
    positions = mt5.positions_get(symbol=config.SYMBOL) or []
    return [
        p for p in positions
        if p.magic == config.MAGIC_NUMBER
        and (trade.get_state(p.ticket) is None
             or trade.get_state(p.ticket).get("parent_ticket") is None)
    ]


def _open_trade(sig: dict, df_h1, label: str = "", df_m5=None) -> bool:
    """Hitung SL/TP/lot dan buka order. Return True jika berhasil."""
    global _open_tickets

    direction = sig["direction"]
    tick = mt5.symbol_info_tick(config.SYMBOL)
    entry = tick.ask if direction == "BUY" else tick.bid

    atr_h1 = df_h1.iloc[-1]["atr"]

    # Cek jarak ke posisi lain
    if not _distance_ok(entry, direction, atr_h1):
        return False

    sl, sl_dist = calc_sl(df_h1, direction, entry, df_m5=df_m5)
    if sl_dist <= 0:
        log_console("[BOT] SL distance tidak valid — skip", level="WARN")
        return False

    sym_info = mt5.symbol_info(config.SYMBOL)
    pip_size = (sym_info.point * 10) if sym_info else 0.1

    if config.TP_MODE == "pips":
        tp1_dist = config.TP1_PIPS * pip_size
        tp2_dist = config.TP2_PIPS * pip_size
        tp3_dist = config.TP3_PIPS * pip_size
        tp1 = entry + tp1_dist if direction == "BUY" else entry - tp1_dist
        tp  = entry + tp2_dist if direction == "BUY" else entry - tp2_dist  # TP2 ke MT5
        tp3 = entry + tp3_dist if direction == "BUY" else entry - tp3_dist
    else:
        tp1 = entry + sl_dist * config.TP1_R if direction == "BUY" else entry - sl_dist * config.TP1_R
        tp  = entry + sl_dist * config.TP2_R if direction == "BUY" else entry - sl_dist * config.TP2_R
        tp3 = tp

    balance = connector.get_balance()
    lot = get_lot_size(config.SYMBOL, sl_dist, balance)

    # Untuk continuation: lot lebih kecil (80% dari normal) agar tidak over-expose
    signal_type = sig.get("signal_type", "PRIMARY")
    if signal_type in ("EMA_RETEST", "HLC"):
        sym_info = mt5.symbol_info(config.SYMBOL)
        lot_step = sym_info.volume_step if sym_info else 0.01
        lot_min  = sym_info.volume_min  if sym_info else 0.01
        lot = max(lot_min, round(round(lot * 0.8 / lot_step) * lot_step, 2))

    ticket = trade.open_position(
        symbol=config.SYMBOL,
        direction=direction,
        lot=lot,
        sl=sl,
        tp=tp,
        pattern=sig["pattern"],
        adx=sig["adx"],
        atr=sig["atr"],
        trend_status=sig["trend"],
        structure=sig.get("structure", ""),
        structure_strength=sig.get("structure_strength", ""),
    )

    if ticket:
        _open_tickets.add(ticket)
        _increment_trade_count()

        # Notif continuation terpisah
        if signal_type in ("EMA_RETEST", "HLC"):
            telegram.notify_continuation(signal_type, direction, config.SYMBOL, entry, sl, tp1, tp, lot)

        log_console(f"[BOT] {label} entry opened | ticket={ticket} | {direction} | lot={lot}")
        return True
    return False


def _place_pending(pend: dict, df_h1, df_m5=None) -> bool:
    """Pasang pending limit order di level EMA H1."""
    direction = pend["direction"]
    level     = pend["level"]

    # Cek tidak ada pending order yang sama arah
    if trade.has_pending_for_direction(config.SYMBOL, direction):
        log_console(f"[PEND] Sudah ada pending {direction} — skip")
        return False

    # Cek harga sekarang tidak sudah melewati level
    tick = mt5.symbol_info_tick(config.SYMBOL)
    if tick is None:
        return False
    current = tick.ask if direction == "BUY" else tick.bid
    if direction == "BUY" and current <= level:
        log_console(f"[PEND] Harga {current:.2f} sudah di bawah level BUY LIMIT {level:.2f} — skip")
        return False
    if direction == "SELL" and current >= level:
        log_console(f"[PEND] Harga {current:.2f} sudah di atas level SELL LIMIT {level:.2f} — skip")
        return False

    sl, sl_dist = calc_sl(df_h1, direction, level, df_m5=df_m5)
    if sl_dist <= 0:
        return False

    tp = (level + sl_dist * config.TP2_R if direction == "BUY"
          else level - sl_dist * config.TP2_R)

    balance = connector.get_balance()
    lot = get_lot_size(config.SYMBOL, sl_dist, balance)

    ticket = trade.place_pending_order(
        symbol=config.SYMBOL,
        direction=direction,
        level=level,
        lot=lot,
        sl=sl,
        tp=tp,
        pattern="ema_retest",
    )
    if ticket:
        log_console(
            f"[BOT] Pending {direction} LIMIT dipasang | "
            f"level={level:.2f} | SL={sl:.2f} | TP={tp:.2f} | lot={lot}"
        )
        return True
    return False


def _send_analysis(df_h4, df_h1, df_m15, df_m5=None):
    """Kirim analisa market + status posisi ke Telegram."""
    try:
        data = signals.build_analysis(df_h4, df_h1, df_m15, df_m5)

        # Kumpulkan posisi terbuka
        positions = []
        for pos in (mt5.positions_get(symbol=config.SYMBOL) or []):
            if pos.magic != config.MAGIC_NUMBER:
                continue
            direction = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
            tick = mt5.symbol_info_tick(config.SYMBOL)
            current = tick.bid if direction == "BUY" else tick.ask

            state = trade.get_state(pos.ticket)
            sl_dist = abs(pos.price_open - pos.sl) if pos.sl else 0
            tp1 = (pos.price_open + sl_dist * config.TP1_R if direction == "BUY"
                   else pos.price_open - sl_dist * config.TP1_R) if sl_dist else pos.tp
            positions.append({
                "direction": direction,
                "entry":     pos.price_open,
                "current":   current,
                "sl":        pos.sl,
                "tp1":       tp1,
                "tp2":       pos.tp,
                "lot":       pos.volume,
                "pnl":       pos.profit,
            })

        data["symbol"] = config.SYMBOL
        telegram.notify_analysis(data, positions, currency=config.ACCOUNT_CURRENCY)
        log_console("[BOT] Analisa dikirim ke Telegram")
    except Exception as e:
        log_console(f"[BOT] Gagal kirim analisa: {e}", level="WARN")


def _status_line():
    info = connector.account_info()
    if info is None:
        log_console("[STATUS] MT5 disconnected", level="WARN")
        return

    session_ok = is_trading_session()
    news_lock  = is_news_lock()
    parent_pos = _get_parent_positions()

    limit_str = (
        f"{_trades_today}/{config.MAX_TRADES_PER_DAY}"
        if config.MAX_TRADES_PER_DAY else f"{_trades_today}/∞"
    )
    currency = config.ACCOUNT_CURRENCY
    bal_fmt  = f"{info.balance:,.0f}" if currency == "IDR" else f"{info.balance:,.2f}"
    eq_fmt   = f"{info.equity:,.0f}"  if currency == "IDR" else f"{info.equity:,.2f}"
    interval_remaining = ""
    if _last_entry_time:
        elapsed = (datetime.now() - _last_entry_time).total_seconds() / 60
        remaining = max(0, config.MIN_ENTRY_INTERVAL - elapsed)
        if remaining > 0:
            interval_remaining = f" | NextEntry={remaining:.0f}m"

    log_console(
        f"[STATUS] Balance={bal_fmt} {currency} | "
        f"Equity={eq_fmt} {currency} | "
        f"Session={'ON' if session_ok else 'OFF'} | "
        f"News={'LOCK' if news_lock else 'OK'} | "
        f"Positions={len(parent_pos)}/{config.MAX_CONCURRENT_POSITIONS} | "
        f"TradesToday={limit_str}"
        f"{interval_remaining}"
    )


def _check_closed_positions():
    """Detect posisi yang sudah ditutup MT5 (SL/TP hit), log & notif."""
    if not _open_tickets:
        return
    current_tickets = {p.ticket for p in (mt5.positions_get(symbol=config.SYMBOL) or [])}
    closed = _open_tickets - current_tickets
    for ticket in closed:
        deals = mt5.history_deals_get(position=ticket)
        if deals:
            pnl   = sum(d.profit for d in deals)
            price = deals[-1].price
            reason = deals[-1].comment or "closed"
            log_console(f"[CLOSED] ticket={ticket} | {reason} | price={price} | PnL={pnl:+.2f}")
            if pnl < 0:
                telegram.notify_sl(ticket, config.SYMBOL, price, pnl)
                # Tren mungkin berbalik — bersihkan re-entry context
                state = trade.get_state(ticket)
                if state:
                    trade.clear_reentry(config.SYMBOL, state["direction"])
            else:
                telegram.notify_tp(ticket, config.SYMBOL, "FULL CLOSE", price, pnl)
                # Simpan konteks re-entry — posisi tutup profit
                if config.REENTRY_ENABLED:
                    state = trade.get_state(ticket)
                    if state and state.get("parent_ticket") is None:
                        trade.record_tp_exit(config.SYMBOL, state["direction"], price)
            log_trade({
                "symbol": config.SYMBOL, "ticket": ticket,
                "result": "SL" if pnl < 0 else "CLOSED", "pnl": round(pnl, 2),
            })
        _open_tickets.discard(ticket)
    trade.cleanup_closed(config.SYMBOL)


def _run_signal_cycle():
    global _last_pending_placed
    df_h4  = get_h4(config.SYMBOL)
    df_h1  = get_h1(config.SYMBOL)
    df_m15 = get_m15(config.SYMBOL)
    df_m5  = get_m5(config.SYMBOL)

    if df_h4 is None or df_h1 is None or df_m15 is None:
        log_console("[BOT] Gagal ambil data candle", level="WARN")
        return

    # ── Tampilkan status semua filter (untuk monitoring & manual entry) ──
    signals.scan_log(df_h4, df_h1, df_m15, df_m5)

    # ── Kelola posisi terbuka (TP1/TP2/Trail/Pyramid) ────────────
    trade.manage_open_positions(config.SYMBOL, df_h1=df_h1)

    # ── Kelola & validasi pending order ──────────────────────────
    existing_dir = None
    parent_positions = _get_parent_positions()
    if parent_positions:
        existing_dir = "BUY" if parent_positions[0].type == mt5.ORDER_TYPE_BUY else "SELL"
    trade.manage_pending_orders(config.SYMBOL, direction_valid=existing_dir)

    # Pre-checks umum
    if _daily_limit_reached():
        log_console(f"[BOT] Daily limit ({_trades_today}/{config.MAX_TRADES_PER_DAY}) — skip")
        return

    n_open = len(parent_positions)

    # ── KASUS 1: Belum ada posisi → cari PRIMARY signal ──────────
    if n_open == 0:
        sig = signals.evaluate(df_h4, df_h1, df_m15, df_m5)
        if sig:
            # Ada market signal → cancel semua pending dulu, lalu market order
            trade.manage_pending_orders(config.SYMBOL, direction_valid=None)
            _open_trade(sig, df_h1, label="PRIMARY", df_m5=df_m5)
            return

        # ── RE-ENTRY setelah TP ───────────────────────────────────
        # Cek apakah ada TP exit yang baru terjadi dan masih dalam window.
        # Evaluasi dengan syarat lebih ringan (tanpa BOS/CHoCH).
        if config.REENTRY_ENABLED and _interval_ok():
            for reentry_dir in ("SELL", "BUY"):
                ctx = trade.get_reentry_context(config.SYMBOL, reentry_dir)
                if ctx is None:
                    continue
                sig_re = signals.evaluate_reentry(df_h4, df_h1, df_m15, reentry_dir, df_m5)
                if sig_re:
                    trade.manage_pending_orders(config.SYMBOL, direction_valid=None)
                    _open_trade(sig_re, df_h1, label=f"REENTRY#{ctx['reentry_count']}", df_m5=df_m5)
                    return

        # Tidak ada market signal → coba pasang pending limit jika diaktifkan
        if config.PENDING_ENABLED and trade.get_pending_count(config.SYMBOL) == 0:
            # Reset cooldown jika tidak ada pending aktif — pending sudah cancel/expired
            if _last_pending_placed > 0 and (time.time() - _last_pending_placed) < PENDING_COOLDOWN:
                _last_pending_placed = 0.0
                log_console("[PEND] Cooldown direset — tidak ada pending aktif")
            elapsed = time.time() - _last_pending_placed
            if elapsed < PENDING_COOLDOWN:
                log_console(f"[PEND] Cooldown {int(PENDING_COOLDOWN - elapsed)}s — skip")
            else:
                pend = signals.evaluate_pending(df_h4, df_h1)
                if pend:
                    if _place_pending(pend, df_h1, df_m5=df_m5):
                        _last_pending_placed = time.time()
        return

    # ── KASUS 2: Ada posisi, belum capai MAX → cari CONTINUATION ─
    if n_open >= config.MAX_CONCURRENT_POSITIONS:
        log_console(
            f"[BOT] Max concurrent positions ({n_open}/{config.MAX_CONCURRENT_POSITIONS}) — skip"
        )
        return

    if not _interval_ok():
        return

    # Ambil arah dari posisi yang sudah ada (hanya boleh searah)
    existing_dir = "BUY" if parent_positions[0].type == mt5.ORDER_TYPE_BUY else "SELL"

    sig = signals.evaluate_continuation(df_h4, df_h1, df_m15, existing_dir, df_m5)
    if sig:
        _open_trade(sig, df_h1, label=f"CONTINUATION ({sig['signal_type']})")


def main():
    log_console("=" * 60)
    log_console("  XAUUSD Trend Following Bot  |  trendbot v1.2")
    log_console("=" * 60)

    if not connector.connect():
        log_console("[BOT] Tidak bisa connect ke MT5. Exit.", level="ERROR")
        sys.exit(1)

    telegram.send("🤖 *TrendBot v1.2 started* | XAUUSD")
    calendar_refresh()

    global _last_signal_check, _last_analysis_sent, _last_pending_placed
    last_heartbeat        = 0.0
    last_calendar_refresh = 0.0
    CALENDAR_REFRESH_INTERVAL = 6 * 3600

    try:
        while True:
            now = time.time()

            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                _status_line()
                _check_closed_positions()
                last_heartbeat = now

            if now - last_calendar_refresh >= CALENDAR_REFRESH_INTERVAL:
                calendar_refresh()
                last_calendar_refresh = now

            if now - _last_signal_check >= SIGNAL_CHECK_INTERVAL:
                try:
                    _run_signal_cycle()
                except Exception as e:
                    log_console(f"[BOT] Signal cycle error: {e}", level="ERROR")
                _last_signal_check = now

            if now - _last_analysis_sent >= ANALYSIS_INTERVAL:
                try:
                    df_h4  = get_h4(config.SYMBOL)
                    df_h1  = get_h1(config.SYMBOL)
                    df_m15 = get_m15(config.SYMBOL)
                    df_m5  = get_m5(config.SYMBOL)
                    if df_h4 is not None and df_h1 is not None and df_m15 is not None:
                        _send_analysis(df_h4, df_h1, df_m15, df_m5)
                except Exception as e:
                    log_console(f"[BOT] Analysis error: {e}", level="WARN")
                _last_analysis_sent = now

            time.sleep(1)

    except KeyboardInterrupt:
        log_console("[BOT] Dihentikan oleh user.")
        telegram.send("⛔ *TrendBot stopped* | XAUUSD")
    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
