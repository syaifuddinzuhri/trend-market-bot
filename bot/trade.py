"""
Order execution & position management.

State per posisi disimpan di _pos_state (dict keyed by ticket):
  original_lot   : lot saat open
  entry          : harga entry
  sl_dist        : jarak SL dalam harga (1R)
  direction      : BUY | SELL
  tp1_hit        : bool
  tp2_hit        : bool
  be_set         : bool
  pyramid_done   : bool
  pyramid_ticket : int | None
"""
import MetaTrader5 as mt5
import config
from bot.logger import log_console, log_trade
from bot import telegram

# ── Position state registry ───────────────────────────────────────
# Keyed by ticket (int)
_pos_state: dict[int, dict] = {}


def get_state(ticket: int) -> dict | None:
    return _pos_state.get(ticket)


def _send_order(request: dict):
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        code = result.retcode if result else "None"
        log_console(f"[TRADE] order_send failed retcode={code}", level="ERROR")
        return None
    return result


# ── Open position ─────────────────────────────────────────────────

def open_position(
    symbol: str,
    direction: str,
    lot: float,
    sl: float,
    tp: float,           # TP pada MT5 = TP2 (2R) — broker menutup otomatis
    pattern: str,
    adx: float,
    atr: float,
    trend_status: str,
    structure: str = "",
    structure_strength: str = "",
    parent_ticket: int | None = None,
) -> int | None:

    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return None

    tick = mt5.symbol_info_tick(symbol)
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": config.SLIPPAGE,
        "magic": config.MAGIC_NUMBER,
        "comment": f"trendbot_{pattern}" if not parent_ticket else f"pyramid_{parent_ticket}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = _send_order(request)
    if result is None:
        return None

    ticket = result.order
    sl_dist = abs(price - sl)
    tp1_price = price + sl_dist * config.TP1_R if direction == "BUY" else price - sl_dist * config.TP1_R
    tp2_price = tp

    label = "PYRAMID" if parent_ticket else "OPEN"
    log_console(
        f"[TRADE] {direction} {label} | ticket={ticket} | entry={price:.2f} | "
        f"SL={sl:.2f} | TP1={tp1_price:.2f} | TP2={tp2_price:.2f} | lot={lot}"
    )

    if parent_ticket:
        telegram.notify_pyramid(direction, symbol, price, sl, tp1_price, tp2_price, lot, parent_ticket)
    else:
        telegram.notify_signal(
            direction, symbol, price, sl, tp1_price, tp2_price, lot, pattern,
            structure=structure, strength=structure_strength,
        )

    log_trade({
        "symbol": symbol,
        "direction": direction,
        "trend_status": trend_status,
        "adx": round(adx, 2),
        "atr": round(atr, 5),
        "pattern": pattern,
        "entry_price": price,
        "stop_loss": sl,
        "take_profit": tp,
        "lot_size": lot,
        "ticket": ticket,
        "result": label,
        "pnl": "",
    })

    # Daftarkan state
    _pos_state[ticket] = {
        "original_lot": lot,
        "entry": price,
        "sl_dist": sl_dist,
        "direction": direction,
        "tp1_hit": False,
        "tp2_hit": False,
        "be_set": False,
        "pyramid_done": False,
        "pyramid_ticket": None,
        "parent_ticket": parent_ticket,
        "symbol": symbol,
        "pattern": pattern,
        "adx": adx,
        "atr": atr,
        "trend_status": trend_status,
        "structure": structure,
        "structure_strength": structure_strength,
    }
    return ticket


# ── Helpers ───────────────────────────────────────────────────────

def _modify_sl(ticket: int, new_sl: float) -> bool:
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False
    pos = positions[0]
    result = _send_order({
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": ticket,
        "sl": new_sl,
        "tp": pos.tp,
    })
    return result is not None


def _close_partial(ticket: int, close_lot: float, direction: str) -> bool:
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False
    pos = positions[0]
    sym_info = mt5.symbol_info(pos.symbol)
    lot_min = sym_info.volume_min if sym_info else 0.01

    # Jangan tutup jika sisa lot setelah partial < lot_min
    remaining = round(pos.volume - close_lot, 2)
    if remaining < lot_min:
        close_lot = pos.volume  # tutup semua kalau sisa terlalu kecil

    tick = mt5.symbol_info_tick(pos.symbol)
    price = tick.bid if direction == "BUY" else tick.ask
    order_type = mt5.ORDER_TYPE_SELL if direction == "BUY" else mt5.ORDER_TYPE_BUY

    result = _send_order({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": close_lot,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": config.SLIPPAGE,
        "magic": config.MAGIC_NUMBER,
        "comment": "partial_close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    })
    return result is not None


def _close_all(ticket: int, direction: str) -> bool:
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False
    return _close_partial(ticket, positions[0].volume, direction)


# ── Main management loop ──────────────────────────────────────────

def manage_open_positions(symbol: str, df_h1=None):
    """
    Dipanggil setiap cycle dari main.py.
    df_h1 dipakai untuk trailing stop TP3 (EMA20 H1).
    """
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return

    ema20_h1 = df_h1.iloc[-1]["ema20"] if df_h1 is not None else None

    for pos in positions:
        if pos.magic != config.MAGIC_NUMBER:
            continue

        ticket = pos.ticket
        direction = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"

        # Pastikan state ada (bisa hilang kalau bot restart)
        if ticket not in _pos_state:
            _pos_state[ticket] = {
                "original_lot": pos.volume,
                "entry": pos.price_open,
                "sl_dist": abs(pos.price_open - pos.sl) if pos.sl else 0,
                "direction": direction,
                "tp1_hit": False,
                "tp2_hit": False,
                "be_set": False,
                "pyramid_done": False,
                "pyramid_ticket": None,
                "parent_ticket": None,
                "symbol": symbol,
                "pattern": "unknown",
                "adx": 0, "atr": 0, "trend_status": "",
            }

        state = _pos_state[ticket]
        entry = state["entry"]
        sl_dist = state["sl_dist"]

        if sl_dist <= 0:
            continue

        tick = mt5.symbol_info_tick(symbol)
        cur = tick.bid if direction == "BUY" else tick.ask
        profit_dist = (cur - entry) if direction == "BUY" else (entry - cur)
        r = profit_dist / sl_dist

        # ── Breakeven @ 1R ───────────────────────────────────────
        if r >= config.BREAKEVEN_R and not state["be_set"]:
            if _modify_sl(ticket, entry):
                state["be_set"] = True
                log_console(f"[MGMT] BE set | ticket={ticket} | entry={entry:.2f}")
                telegram.notify_breakeven(ticket, symbol)

        # ── TP1 @ TP1_R: tutup TP1_PCT ───────────────────────────
        if r >= config.TP1_R and not state["tp1_hit"]:
            sym_info = mt5.symbol_info(symbol)
            lot_min = sym_info.volume_min if sym_info else 0.01
            lot_step = sym_info.volume_step if sym_info else 0.01
            close_lot = round(
                max(lot_min, round(pos.volume * config.TP1_PCT / lot_step) * lot_step), 2
            )
            if _close_partial(ticket, close_lot, direction):
                state["tp1_hit"] = True
                pnl_est = pos.profit * config.TP1_PCT
                log_console(f"[MGMT] TP1 hit | ticket={ticket} | closed={close_lot} lot")
                telegram.notify_tp(ticket, symbol, f"TP1 ({config.TP1_R}R)", cur, pnl_est)
                log_trade({
                    "symbol": symbol, "direction": direction,
                    "ticket": ticket, "result": "TP1", "pnl": round(pnl_est, 2),
                })

        # ── TP2 @ TP2_R: tutup TP2_PCT ───────────────────────────
        if r >= config.TP2_R and state["tp1_hit"] and not state["tp2_hit"]:
            # Re-fetch volume karena sudah partial close di TP1
            positions2 = mt5.positions_get(ticket=ticket)
            if positions2:
                cur_vol = positions2[0].volume
                sym_info = mt5.symbol_info(symbol)
                lot_min = sym_info.volume_min if sym_info else 0.01
                lot_step = sym_info.volume_step if sym_info else 0.01
                # TP2_PCT dari sisa setelah TP1, normalkan ke original
                close_lot = round(
                    max(lot_min, round(cur_vol * (config.TP2_PCT / (1 - config.TP1_PCT)) / lot_step) * lot_step), 2
                )
                close_lot = min(close_lot, cur_vol)
                if _close_partial(ticket, close_lot, direction):
                    state["tp2_hit"] = True
                    pnl_est = positions2[0].profit * (close_lot / cur_vol)
                    log_console(f"[MGMT] TP2 hit | ticket={ticket} | closed={close_lot} lot | trailing aktif untuk sisa")
                    telegram.notify_tp(ticket, symbol, f"TP2 ({config.TP2_R}R)", cur, pnl_est)
                    log_trade({
                        "symbol": symbol, "direction": direction,
                        "ticket": ticket, "result": "TP2", "pnl": round(pnl_est, 2),
                    })

        # ── TP3: Trailing stop via EMA20 H1 (sisa posisi) ────────
        if state["tp2_hit"] and ema20_h1 is not None:
            trail_exit = (direction == "BUY" and cur < ema20_h1) or \
                         (direction == "SELL" and cur > ema20_h1)
            if trail_exit:
                positions2 = mt5.positions_get(ticket=ticket)
                if positions2:
                    pnl_est = positions2[0].profit
                    if _close_all(ticket, direction):
                        log_console(f"[MGMT] Trail exit (EMA20 H1 cross) | ticket={ticket}")
                        telegram.notify_trail_exit(ticket, symbol, cur, pnl_est)
                        log_trade({
                            "symbol": symbol, "direction": direction,
                            "ticket": ticket, "result": "TRAIL_EXIT", "pnl": round(pnl_est, 2),
                        })
                        _pos_state.pop(ticket, None)

        # ── Pyramid entry setelah BE + TP1 ────────────────────────
        if (
            config.PYRAMID_ENABLED
            and state["be_set"]
            and state["tp1_hit"]
            and not state["pyramid_done"]
            and state["parent_ticket"] is None      # hanya dari posisi induk
            and state["pyramid_ticket"] is None
        ):
            _try_pyramid(ticket, state, symbol, df_h1)


def _try_pyramid(parent_ticket: int, state: dict, symbol: str, df_h1):
    """Coba buka pyramid entry jika kondisi terpenuhi."""
    if df_h1 is None:
        return

    from bot.pullback import has_pullback
    from bot.indicators import get_m15
    from bot.trend import get_trend, NO_TRADE
    from bot.indicators import get_h4

    direction = state["direction"]
    last_h1 = df_h1.iloc[-1]
    adx_ok = last_h1["adx"] >= config.ADX_MIN

    if not adx_ok:
        return

    if not has_pullback(df_h1, direction):
        return

    # Hitung lot pyramid
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return
    lot_min = sym_info.volume_min
    lot_step = sym_info.volume_step
    raw_lot = state["original_lot"] * config.PYRAMID_LOT_RATIO
    pyr_lot = round(max(lot_min, round(raw_lot / lot_step) * lot_step), 2)

    # SL = entry induk (sudah di BE)
    sl = state["entry"]
    entry_now = mt5.symbol_info_tick(symbol)
    if entry_now is None:
        return
    price = entry_now.ask if direction == "BUY" else entry_now.bid

    # TP = 2R dari entry pyramid
    sl_dist = abs(price - sl)
    if sl_dist <= 0:
        return
    tp = price + sl_dist * config.TP2_R if direction == "BUY" else price - sl_dist * config.TP2_R

    pyr_ticket = open_position(
        symbol=symbol,
        direction=direction,
        lot=pyr_lot,
        sl=sl,
        tp=tp,
        pattern=state.get("pattern", "pyramid"),
        adx=last_h1["adx"],
        atr=last_h1["atr"],
        trend_status=state.get("trend_status", ""),
        parent_ticket=parent_ticket,
    )

    if pyr_ticket:
        state["pyramid_done"] = True
        state["pyramid_ticket"] = pyr_ticket
        log_console(
            f"[PYRAMID] Opened | parent={parent_ticket} | ticket={pyr_ticket} | "
            f"lot={pyr_lot} | SL={sl:.2f} | TP={tp:.2f}"
        )


def cleanup_closed(symbol: str):
    """Hapus state untuk posisi yang sudah tidak ada di MT5."""
    current = {p.ticket for p in (mt5.positions_get(symbol=symbol) or [])}
    stale = [t for t in list(_pos_state) if t not in current]
    for t in stale:
        _pos_state.pop(t, None)


# ── Pending Order (Limit) ─────────────────────────────────────────
# Registry pending order yang dibuka bot: {ticket: {direction, placed_at, level}}
_pending_state: dict[int, dict] = {}


def place_pending_order(
    symbol: str,
    direction: str,
    level: float,
    lot: float,
    sl: float,
    tp: float,
    pattern: str = "limit",
) -> int | None:
    """
    Pasang Sell Limit atau Buy Limit di level EMA H1.
    Expiry = PENDING_EXPIRY_MINUTES menit dari sekarang.
    """
    import time as _time
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return None

    order_type = (
        mt5.ORDER_TYPE_BUY_LIMIT if direction == "BUY"
        else mt5.ORDER_TYPE_SELL_LIMIT
    )

    # Expiry time MT5 (epoch seconds)
    expiry_sec = int(_time.time()) + config.PENDING_EXPIRY_MINUTES * 60

    request = {
        "action":      mt5.TRADE_ACTION_PENDING,
        "symbol":      symbol,
        "volume":      lot,
        "type":        order_type,
        "price":       round(level, sym_info.digits),
        "sl":          round(sl, sym_info.digits),
        "tp":          round(tp, sym_info.digits),
        "deviation":   config.SLIPPAGE,
        "magic":       config.MAGIC_NUMBER,
        "comment":     f"trendbot_limit_{pattern}",
        "type_time":   mt5.ORDER_TIME_SPECIFIED,
        "expiration":  expiry_sec,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }

    result = _send_order(request)
    if result is None:
        return None

    ticket = result.order
    sl_dist = abs(level - sl)
    tp1 = level + sl_dist * config.TP1_R if direction == "BUY" else level - sl_dist * config.TP1_R

    _pending_state[ticket] = {
        "direction": direction,
        "level":     level,
        "sl":        sl,
        "tp":        tp,
        "lot":       lot,
        "placed_at": _time.time(),
        "symbol":    symbol,
    }

    log_console(
        f"[PEND] {direction} LIMIT | ticket={ticket} | "
        f"level={level:.2f} | SL={sl:.2f} | TP1={tp1:.2f} | TP2={tp:.2f} | lot={lot}"
    )
    telegram.notify_signal(
        direction, symbol, level, sl, tp1, tp, lot, f"LIMIT_{pattern}",
        structure="PENDING", strength="",
    )
    return ticket


def cancel_pending_order(ticket: int, reason: str = "") -> bool:
    """Cancel satu pending order berdasarkan ticket."""
    request = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order":  ticket,
    }
    result = mt5.order_send(request)
    ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
    if ok:
        _pending_state.pop(ticket, None)
        log_console(f"[PEND] Cancelled ticket={ticket} | {reason}")
    else:
        code = result.retcode if result else "None"
        log_console(f"[PEND] Cancel FAILED ticket={ticket} retcode={code}", level="WARN")
    return ok


def manage_pending_orders(symbol: str, direction_valid: str | None):
    """
    Dipanggil setiap cycle dari main.py.
    Cancel pending order jika:
    - Trend berbalik (direction berubah)
    - Session habis / news lock
    - Sudah expired (MT5 harusnya auto-cancel, ini sebagai fallback)
    - Harga sudah melewati level (tidak relevan lagi)
    """
    import time as _time
    from bot.session import is_trading_session
    from bot.news_filter import is_news_lock

    if not _pending_state:
        return

    # Ambil semua pending order aktif dari MT5
    mt5_orders = {o.ticket for o in (mt5.orders_get(symbol=symbol) or [])
                  if o.magic == config.MAGIC_NUMBER}

    tick = mt5.symbol_info_tick(symbol)
    current_price = tick.bid if tick else 0

    for ticket in list(_pending_state.keys()):
        state = _pending_state[ticket]

        # Sudah tidak ada di MT5 (filled atau expired)
        if ticket not in mt5_orders:
            log_console(f"[PEND] ticket={ticket} sudah tidak aktif (filled/expired)")
            _pending_state.pop(ticket, None)
            continue

        reason = None

        # Trend berbalik
        if direction_valid and state["direction"] != direction_valid:
            reason = f"trend berbalik → {direction_valid}"

        # Session habis atau news lock
        elif not is_trading_session():
            reason = "session tutup"
        elif is_news_lock():
            reason = "news lock"

        # Harga sudah melewati level (terlalu jauh, peluang tidak relevan)
        elif current_price > 0:
            dist = abs(current_price - state["level"])
            sym_info = mt5.symbol_info(symbol)
            atr_approx = (sym_info.point * 100) if sym_info else 0.5
            if dist > atr_approx * config.PENDING_MAX_DISTANCE_ATR:
                reason = f"harga jauh dari level ({dist:.2f})"

        if reason:
            cancel_pending_order(ticket, reason)


def get_pending_count(symbol: str) -> int:
    """Jumlah pending order bot yang aktif."""
    mt5_orders = {o.ticket for o in (mt5.orders_get(symbol=symbol) or [])
                  if o.magic == config.MAGIC_NUMBER}
    # Sync: hapus yang sudah tidak ada di MT5
    for t in list(_pending_state.keys()):
        if t not in mt5_orders:
            _pending_state.pop(t, None)
    return len(_pending_state)


def has_pending_for_direction(symbol: str, direction: str) -> bool:
    """Cek apakah sudah ada pending order untuk arah ini."""
    mt5_orders = {o.ticket for o in (mt5.orders_get(symbol=symbol) or [])
                  if o.magic == config.MAGIC_NUMBER}
    for ticket, state in _pending_state.items():
        if ticket in mt5_orders and state["direction"] == direction:
            return True
    return False
