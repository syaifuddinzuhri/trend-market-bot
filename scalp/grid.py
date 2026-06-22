"""
Grid order management untuk scalper M5.
Pasang N pending limit order di dalam S&D zone.
"""
import time
import MetaTrader5 as mt5
from bot.logger import log_console
from bot import telegram
import scalp_config as sc


_grid_state: dict[int, dict] = {}  # ticket → {direction, level, sl, tp}


def place_grid(
    symbol: str,
    direction: str,
    zone_top: float,
    zone_bottom: float,
    atr: float,
) -> list[int]:
    """
    Pasang SCALP_GRID_COUNT pending order di dalam zona.
    Return list ticket yang berhasil dipasang.
    """
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return []

    digits  = sym_info.digits
    lot_per = _calc_lot_per_order()
    if lot_per < sym_info.volume_min:
        lot_per = sym_info.volume_min

    # Hitung SL & TP berdasarkan pip
    sl_pts = sc.SCALP_SL_PIPS * sym_info.point * 10
    tp_pts = sc.SCALP_TP_PIPS * sym_info.point * 10

    # Level grid: spread merata di dalam zona
    zone_range = zone_top - zone_bottom
    step = zone_range / max(sc.SCALP_GRID_COUNT, 1)

    order_type = mt5.ORDER_TYPE_SELL_LIMIT if direction == "SELL" else mt5.ORDER_TYPE_BUY_LIMIT
    expiry_sec = int(time.time()) + sc.SCALP_EXPIRY_MINUTES * 60

    tickets = []
    for i in range(sc.SCALP_GRID_COUNT):
        if direction == "SELL":
            # Dari bawah zona ke atas (level terdekat dulu)
            level = round(zone_bottom + step * (i + 0.5), digits)
            sl    = round(level + sl_pts, digits)
            tp    = round(level - tp_pts, digits)
            # Validasi: level harus di atas harga sekarang
            tick = mt5.symbol_info_tick(symbol)
            if tick and level <= tick.ask:
                continue
        else:
            # BUY LIMIT: dari atas zona ke bawah
            level = round(zone_top - step * (i + 0.5), digits)
            sl    = round(level - sl_pts, digits)
            tp    = round(level + tp_pts, digits)
            tick = mt5.symbol_info_tick(symbol)
            if tick and level >= tick.bid:
                continue

        request = {
            "action":       mt5.TRADE_ACTION_PENDING,
            "symbol":       symbol,
            "volume":       lot_per,
            "type":         order_type,
            "price":        level,
            "sl":           sl,
            "tp":           tp,
            "deviation":    20,
            "magic":        sc.SCALP_MAGIC,
            "comment":      f"scalp_grid_{i+1}",
            "type_time":    mt5.ORDER_TIME_SPECIFIED,
            "expiration":   expiry_sec,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            ticket = result.order
            tickets.append(ticket)
            _grid_state[ticket] = {
                "direction": direction,
                "level":     level,
                "sl":        sl,
                "tp":        tp,
                "lot":       lot_per,
                "placed_at": time.time(),
            }
            log_console(
                f"[SCALP] Grid #{i+1} {direction} LIMIT | "
                f"level={level:.3f} | SL={sl:.3f} | TP={tp:.3f} | lot={lot_per}"
            )
        else:
            code = result.retcode if result else "None"
            log_console(f"[SCALP] Grid #{i+1} FAILED retcode={code}", level="WARN")

    if tickets:
        _notify_grid(symbol, direction, tickets, zone_top, zone_bottom, lot_per)

    return tickets


def cancel_all_grid(symbol: str, reason: str = ""):
    """Cancel semua grid pending order bot scalper."""
    pending_types = {
        mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT,
        mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP,
    }
    orders = mt5.orders_get(symbol=symbol) or []
    for o in orders:
        if o.magic == sc.SCALP_MAGIC and o.type in pending_types:
            req = {"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket}
            result = mt5.order_send(req)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                _grid_state.pop(o.ticket, None)
                log_console(f"[SCALP] Cancelled grid ticket={o.ticket} | {reason}")


def get_grid_count(symbol: str) -> int:
    """Jumlah grid pending order aktif di MT5."""
    pending_types = {
        mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT,
        mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP,
    }
    return sum(
        1 for o in (mt5.orders_get(symbol=symbol) or [])
        if o.magic == sc.SCALP_MAGIC and o.type in pending_types
    )


def get_open_count(symbol: str) -> int:
    """Jumlah posisi scalp yang sedang terbuka."""
    return sum(
        1 for p in (mt5.positions_get(symbol=symbol) or [])
        if p.magic == sc.SCALP_MAGIC
    )


def manage_grid_positions(symbol: str):
    """
    Manage posisi scalp yang sudah filled:
    - Close semua jika salah satu SL hit (pelindung grid)
    - Sync _grid_state
    """
    pending_types = {
        mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT,
        mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP,
    }
    mt5_pending = {o.ticket for o in (mt5.orders_get(symbol=symbol) or [])
                   if o.magic == sc.SCALP_MAGIC and o.type in pending_types}
    mt5_pos     = {p.ticket for p in (mt5.positions_get(symbol=symbol) or [])
                   if p.magic == sc.SCALP_MAGIC}

    # Bersihkan state untuk order yang sudah tidak ada
    for ticket in list(_grid_state.keys()):
        if ticket not in mt5_pending and ticket not in mt5_pos:
            _grid_state.pop(ticket, None)


def _calc_lot_per_order() -> float:
    """Lot per order = total lot / jumlah grid."""
    total = sc.SCALP_LOT
    per   = round(total / max(sc.SCALP_GRID_COUNT, 1), 2)
    return max(per, 0.01)


def _notify_grid(symbol: str, direction: str, tickets: list, top: float, bottom: float, lot: float):
    arrow = "🔴 SELL" if direction == "SELL" else "🟢 BUY"
    telegram.send(
        f"⚡ *SCALP GRID {arrow} — {symbol}*\n"
        f"Zona     : `{bottom:.3f}` — `{top:.3f}`\n"
        f"Orders   : `{len(tickets)}/{sc.SCALP_GRID_COUNT}`\n"
        f"Lot/order: `{lot}` | Total: `{round(lot * len(tickets), 2)}`\n"
        f"SL/TP    : `{sc.SCALP_SL_PIPS}` pip / `{sc.SCALP_TP_PIPS}` pip\n"
        f"Expiry   : `{sc.SCALP_EXPIRY_MINUTES}` menit"
    )
