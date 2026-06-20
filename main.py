"""
XAUUSD Trend Following Bot
Run: python main.py
Requires: MT5 terminal open and logged in with the same account as .env
"""
import time
import sys
from datetime import datetime, date as _date

import MetaTrader5 as mt5

import config
from bot import connector, signals, trade, telegram
from bot.indicators import get_h4, get_h1, get_m15
from bot.risk import get_lot_size, calc_sl
from bot.logger import log_console, log_trade
from bot.session import is_trading_session
from bot.news_filter import is_news_lock
from bot.calendar import refresh as calendar_refresh

HEARTBEAT_INTERVAL = 5       # detik antara console status
SIGNAL_CHECK_INTERVAL = 15   # detik antara full signal check

# Ticket yang dibuka bot session ini
_open_tickets: set[int] = set()
_last_signal_check = 0.0

# Daily trade counter (hanya posisi induk, bukan pyramid)
_trades_today: int = 0
_trade_count_date: _date | None = None


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
    global _trades_today, _trade_count_date
    today = _date.today()
    if _trade_count_date != today:
        _trade_count_date = today
        _trades_today = 0
    _trades_today += 1


def _status_line():
    info = connector.account_info()
    if info is None:
        log_console("[STATUS] MT5 disconnected", level="WARN")
        return

    session_ok = is_trading_session()
    news_lock = is_news_lock()
    positions = mt5.positions_get(symbol=config.SYMBOL) or []
    bot_positions = [p for p in positions if p.magic == config.MAGIC_NUMBER]

    limit_str = f"{_trades_today}/{config.MAX_TRADES_PER_DAY}" if config.MAX_TRADES_PER_DAY else f"{_trades_today}/∞"
    currency = config.ACCOUNT_CURRENCY
    bal_fmt = f"{info.balance:,.0f}" if currency == "IDR" else f"{info.balance:,.2f}"
    eq_fmt  = f"{info.equity:,.0f}"  if currency == "IDR" else f"{info.equity:,.2f}"

    log_console(
        f"[STATUS] Balance={bal_fmt} {currency} | "
        f"Equity={eq_fmt} {currency} | "
        f"Session={'ON' if session_ok else 'OFF'} | "
        f"News={'LOCK' if news_lock else 'OK'} | "
        f"OpenTrades={len(bot_positions)} | "
        f"TradesToday={limit_str}"
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
            pnl = sum(d.profit for d in deals)
            price = deals[-1].price
            reason = deals[-1].comment or "closed"
            log_console(f"[CLOSED] ticket={ticket} | {reason} | price={price} | PnL={pnl:+.2f}")
            if pnl < 0:
                telegram.notify_sl(ticket, config.SYMBOL, price, pnl)
            else:
                telegram.notify_tp(ticket, config.SYMBOL, "FULL CLOSE", price, pnl)
            log_trade({
                "symbol": config.SYMBOL, "ticket": ticket,
                "result": "SL" if pnl < 0 else "CLOSED", "pnl": round(pnl, 2),
            })
        _open_tickets.discard(ticket)

    # Bersihkan state posisi yang sudah tidak ada
    trade.cleanup_closed(config.SYMBOL)


def _run_signal_cycle():
    df_h4  = get_h4(config.SYMBOL)
    df_h1  = get_h1(config.SYMBOL)
    df_m15 = get_m15(config.SYMBOL)

    if df_h4 is None or df_h1 is None or df_m15 is None:
        log_console("[BOT] Gagal ambil data candle", level="WARN")
        return

    # ── Kelola posisi terbuka (TP1/TP2/Trail/Pyramid) ────────────
    trade.manage_open_positions(config.SYMBOL, df_h1=df_h1)

    # ── Cari sinyal baru hanya jika tidak ada posisi induk ───────
    positions = mt5.positions_get(symbol=config.SYMBOL) or []
    # Posisi induk = posisi bot yang bukan pyramid
    parent_positions = [
        p for p in positions
        if p.magic == config.MAGIC_NUMBER
        and (trade.get_state(p.ticket) is None
             or trade.get_state(p.ticket).get("parent_ticket") is None)
    ]
    if parent_positions:
        return

    if _daily_limit_reached():
        log_console(f"[BOT] Daily limit ({_trades_today}/{config.MAX_TRADES_PER_DAY}) — skip")
        return

    sig = signals.evaluate(df_h4, df_h1, df_m15)
    if sig is None:
        return

    direction = sig["direction"]

    # ── SL dinamis: swing H1 + ATR buffer ────────────────────────
    tick = mt5.symbol_info_tick(config.SYMBOL)
    entry = tick.ask if direction == "BUY" else tick.bid

    sl, sl_dist = calc_sl(df_h1, direction, entry)

    if sl_dist <= 0:
        log_console("[BOT] SL distance tidak valid — skip", level="WARN")
        return

    # ── TP2 sebagai TP di MT5 (broker auto-close) ────────────────
    tp = entry + sl_dist * config.TP2_R if direction == "BUY" else entry - sl_dist * config.TP2_R

    # ── Lot size ─────────────────────────────────────────────────
    balance = connector.get_balance()
    lot = get_lot_size(config.SYMBOL, sl_dist, balance)

    # ── Buka trade ───────────────────────────────────────────────
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


def main():
    log_console("=" * 60)
    log_console("  XAUUSD Trend Following Bot  |  trendbot v1.1")
    log_console("=" * 60)

    if not connector.connect():
        log_console("[BOT] Tidak bisa connect ke MT5. Exit.", level="ERROR")
        sys.exit(1)

    telegram.send("🤖 *TrendBot v1.1 started* | XAUUSD")

    # Fetch economic calendar saat startup
    calendar_refresh()

    global _last_signal_check
    last_heartbeat = 0.0
    last_calendar_refresh = 0.0
    CALENDAR_REFRESH_INTERVAL = 6 * 3600  # refresh setiap 6 jam

    try:
        while True:
            now = time.time()

            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                _status_line()
                _check_closed_positions()
                last_heartbeat = now

            # ── Refresh economic calendar setiap 6 jam ────────────
            if now - last_calendar_refresh >= CALENDAR_REFRESH_INTERVAL:
                calendar_refresh()
                last_calendar_refresh = now

            if now - _last_signal_check >= SIGNAL_CHECK_INTERVAL:
                try:
                    _run_signal_cycle()
                except Exception as e:
                    log_console(f"[BOT] Signal cycle error: {e}", level="ERROR")
                _last_signal_check = now

            time.sleep(1)

    except KeyboardInterrupt:
        log_console("[BOT] Dihentikan oleh user.")
        telegram.send("⛔ *TrendBot stopped* | XAUUSD")
    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
