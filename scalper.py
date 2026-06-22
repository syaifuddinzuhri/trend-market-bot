"""
TrendBot Scalper — Grid Entry M5
Jalan terpisah dari main.py (bot trend utama).

Run: python scalper.py
"""
import time
import sys
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd

import scalp_config as sc
from bot.logger import log_console
from bot.session import is_trading_session
from bot import telegram
from scalp.zones import find_sd_zones, nearest_zone
from scalp.grid import (
    place_grid, cancel_all_grid,
    get_grid_count, get_open_count,
    manage_grid_positions,
)

# Timeframe M5
TF_M5 = None

# Cooldown setelah grid dipasang (detik) — cegah pasang ulang terlalu cepat
_last_grid_placed: float = 0.0
GRID_COOLDOWN = 300  # 5 menit


def _connect() -> bool:
    if not mt5.initialize():
        log_console("[SCALP] MT5 initialize() gagal", level="ERROR")
        return False
    if not mt5.login(sc.MT5_LOGIN, sc.MT5_PASSWORD, sc.MT5_SERVER):
        log_console(f"[SCALP] MT5 login gagal: {mt5.last_error()}", level="ERROR")
        mt5.shutdown()
        return False
    info = mt5.account_info()
    log_console(f"[SCALP] Connected | {info.name} | Balance={info.balance:.2f}")
    return True


def _get_m5(symbol: str, bars: int = 200) -> pd.DataFrame | None:
    global TF_M5
    if TF_M5 is None:
        TF_M5 = mt5.TIMEFRAME_M5
    rates = mt5.copy_rates_from_pos(symbol, TF_M5, 0, bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def _get_adx(df: pd.DataFrame, period: int = 14) -> float:
    """Hitung ADX sederhana dari data M5."""
    try:
        high  = df["high"]
        low   = df["low"]
        close = df["close"]

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)

        dm_plus  = (high.diff()).clip(lower=0)
        dm_minus = (-low.diff()).clip(lower=0)
        dm_plus  = dm_plus.where(dm_plus > dm_minus, 0)
        dm_minus = dm_minus.where(dm_minus > dm_plus, 0)

        atr14   = tr.ewm(alpha=1/period, adjust=False).mean()
        dip14   = dm_plus.ewm(alpha=1/period, adjust=False).mean()
        dim14   = dm_minus.ewm(alpha=1/period, adjust=False).mean()

        di_plus  = 100 * dip14 / atr14.replace(0, 1e-9)
        di_minus = 100 * dim14 / atr14.replace(0, 1e-9)
        dx       = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, 1e-9)
        adx      = dx.ewm(alpha=1/period, adjust=False).mean()
        return float(adx.iloc[-1])
    except Exception:
        return 0.0


def _get_atr(df: pd.DataFrame, period: int = 14) -> float:
    try:
        high  = df["high"]
        low   = df["low"]
        close = df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return float(tr.ewm(alpha=1/period, adjust=False).mean().iloc[-1])
    except Exception:
        return 0.0


def _get_trend_direction(df: pd.DataFrame) -> str:
    """Trend M5 sederhana: EMA20 vs EMA50."""
    try:
        ema20 = df["close"].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        if ema20 > ema50:
            return "BUY"
        elif ema20 < ema50:
            return "SELL"
    except Exception:
        pass
    return "—"


def _run_cycle():
    global _last_grid_placed

    symbol = sc.SYMBOL

    # ── Session check ─────────────────────────────────────────────
    if not is_trading_session():
        log_console("[SCALP] Di luar sesi trading — skip")
        cancel_all_grid(symbol, "session tutup")
        return

    # ── Data M5 ───────────────────────────────────────────────────
    df = _get_m5(symbol, sc.SCALP_ZONE_LOOKBACK + 50)
    if df is None:
        log_console("[SCALP] Gagal ambil data M5", level="WARN")
        return

    # ── Filter ADX ────────────────────────────────────────────────
    adx = _get_adx(df)
    atr = _get_atr(df)

    if adx < sc.SCALP_ADX_MIN:
        log_console(f"[SCALP] ADX={adx:.1f} < {sc.SCALP_ADX_MIN} — momentum lemah, skip")
        return

    # ── Cek posisi & grid aktif ───────────────────────────────────
    manage_grid_positions(symbol)
    open_count  = get_open_count(symbol)
    grid_count  = get_grid_count(symbol)

    if open_count >= sc.SCALP_MAX_OPEN:
        log_console(f"[SCALP] Max posisi ({open_count}/{sc.SCALP_MAX_OPEN}) — skip")
        return

    if grid_count > 0:
        log_console(f"[SCALP] Grid sudah aktif ({grid_count} orders) — tunggu")
        return

    # ── Cooldown setelah grid terakhir ────────────────────────────
    if time.time() - _last_grid_placed < GRID_COOLDOWN:
        remaining = int(GRID_COOLDOWN - (time.time() - _last_grid_placed))
        log_console(f"[SCALP] Cooldown {remaining}s — skip")
        return

    # ── Trend M5 ──────────────────────────────────────────────────
    direction = _get_trend_direction(df)
    if direction == "—":
        log_console("[SCALP] Trend tidak jelas — skip")
        return

    # ── Deteksi zona S&D ─────────────────────────────────────────
    zones = find_sd_zones(
        df.tail(sc.SCALP_ZONE_LOOKBACK),
        max_zones=sc.SCALP_MAX_ZONES,
        show_mitigated=False,
    )

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return
    current = tick.ask if direction == "BUY" else tick.bid

    zone = nearest_zone(zones, current, direction)
    if zone is None:
        log_console(f"[SCALP] Tidak ada zona {direction} yang valid — skip")
        return

    # ── Filter jarak harga ke zona ───────────────────────────────
    sym_info = mt5.symbol_info(symbol)
    pip_size = (sym_info.point * 10) if sym_info else 0.1
    max_dist = sc.SCALP_MAX_ZONE_DISTANCE * pip_size

    if direction == "SELL":
        dist_to_zone = zone["bottom"] - current  # harga harus di bawah zona
    else:
        dist_to_zone = current - zone["top"]     # harga harus di atas zona

    if dist_to_zone < 0:
        log_console(f"[SCALP] Harga sudah masuk zona — skip")
        return
    if dist_to_zone > max_dist:
        log_console(
            f"[SCALP] Zona terlalu jauh ({dist_to_zone/pip_size:.1f} pip "
            f"> max {sc.SCALP_MAX_ZONE_DISTANCE} pip) — skip"
        )
        return

    log_console(
        f"[SCALP] {direction} | ADX={adx:.1f} | ATR={atr:.4f} | "
        f"Zona {zone['type']} {zone['bottom']:.3f}–{zone['top']:.3f} | "
        f"Jarak={dist_to_zone/pip_size:.1f} pip"
    )

    # ── Pasang grid ───────────────────────────────────────────────
    tickets = place_grid(
        symbol=symbol,
        direction=direction,
        zone_top=zone["top"],
        zone_bottom=zone["bottom"],
        atr=atr,
    )

    if tickets:
        _last_grid_placed = time.time()
        log_console(f"[SCALP] Grid dipasang: {len(tickets)} orders")
    else:
        log_console("[SCALP] Tidak ada order yang berhasil dipasang", level="WARN")


def _status_line():
    info = mt5.account_info()
    if info is None:
        return
    open_c = get_open_count(sc.SYMBOL)
    grid_c = get_grid_count(sc.SYMBOL)
    log_console(
        f"[SCALP STATUS] Balance={info.balance:,.0f} | "
        f"Equity={info.equity:,.0f} | "
        f"OpenPos={open_c} | GridPending={grid_c}"
    )


def main():
    log_console("=" * 55)
    log_console("  TrendBot Scalper  |  M5 Grid Entry")
    log_console("=" * 55)

    if not _connect():
        sys.exit(1)

    telegram.send(f"⚡ *TrendBot Scalper started* | {sc.SYMBOL} | Grid={sc.SCALP_GRID_COUNT} | Lot={sc.SCALP_LOT}")

    last_status = 0.0
    STATUS_INTERVAL = 30

    try:
        while True:
            now = time.time()

            if now - last_status >= STATUS_INTERVAL:
                _status_line()
                last_status = now

            try:
                _run_cycle()
            except Exception as e:
                log_console(f"[SCALP] Cycle error: {e}", level="ERROR")

            time.sleep(sc.SCALP_CHECK_INTERVAL)

    except KeyboardInterrupt:
        log_console("[SCALP] Dihentikan oleh user.")
        cancel_all_grid(sc.SYMBOL, "bot stop")
        telegram.send(f"⛔ *TrendBot Scalper stopped* | {sc.SYMBOL}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
