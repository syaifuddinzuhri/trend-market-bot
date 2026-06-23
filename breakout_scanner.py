"""
TrendBot Breakout Scanner — Strategi Compression + Breakout

Strategi (berdasarkan metode trader):
  1. Deteksi zona kompresi: harga terjepit antara
     descending resistance (high makin turun) dan support flat/ascending
  2. Hitung range kompresi — makin sempit = makin siap breakout
  3. Tunggu candle CLOSE di luar zona:
     - Close > resistance → BUY breakout
     - Close < support   → SELL breakdown
  4. Konfirmasi tambahan: body candle kuat + ADX mulai naik
  5. Kirim alert Telegram dengan level entry, SL, TP

Run: python breakout_scanner.py
"""
import time
import sys
import os

import MetaTrader5 as mt5
import pandas as pd

from dotenv import load_dotenv
load_dotenv()

from bot.logger import log_console
from bot import telegram
from bot.risk import get_pip_size

# ── Konfigurasi ──────────────────────────────────────────────────────
SYMBOL            = os.getenv("SYMBOL", "XAUUSD")
MT5_LOGIN         = int(os.getenv("MT5_LOGIN", 0))
MT5_PASSWORD      = os.getenv("MT5_PASSWORD", "")
MT5_SERVER        = os.getenv("MT5_SERVER", "")

BO_LOOKBACK       = int(os.getenv("BO_LOOKBACK", 30))        # bar M5 untuk scan kompresi
BO_MIN_BARS       = int(os.getenv("BO_MIN_BARS", 8))         # min bar kompresi sebelum valid
BO_MAX_RANGE_PIP  = float(os.getenv("BO_MAX_RANGE_PIP", 35)) # max range pip = dianggap kompres
BO_TP1_PIPS       = float(os.getenv("BO_TP1_PIPS", 20))      # TP1 pip
BO_TP2_PIPS       = float(os.getenv("BO_TP2_PIPS", 35))      # TP2 pip
BO_SL_BUFFER_PIP  = float(os.getenv("BO_SL_BUFFER_PIP", 5))  # SL = sisi berlawanan zona + buffer
BO_BODY_RATIO     = float(os.getenv("BO_BODY_RATIO", 0.45))  # body candle min 45% range
BO_ADX_MIN        = float(os.getenv("BO_ADX_MIN", 18))       # ADX minimal (boleh rendah, sedang kompres)
BO_COOLDOWN_SEC   = int(os.getenv("BO_COOLDOWN_SEC", 300))   # 5 menit cooldown per arah
CHECK_INTERVAL    = 5                                          # detik antar cycle

_last_alert: dict[str, float] = {}   # "BUY"/"SELL" → epoch


def _connect() -> bool:
    if not mt5.initialize():
        log_console("[BO] MT5 initialize() gagal", level="ERROR")
        return False
    if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
        log_console(f"[BO] MT5 login gagal: {mt5.last_error()}", level="ERROR")
        mt5.shutdown()
        return False
    info = mt5.account_info()
    log_console(f"[BO] Connected | {info.name} | Balance={info.balance:,.0f}")
    return True


def _candles(tf, bars: int) -> pd.DataFrame | None:
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def _adx(df: pd.DataFrame, period: int = 14) -> float:
    try:
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        dm_p = high.diff().clip(lower=0)
        dm_m = (-low.diff()).clip(lower=0)
        dm_p = dm_p.where(dm_p > dm_m, 0)
        dm_m = dm_m.where(dm_m > dm_p, 0)
        atr14 = tr.ewm(alpha=1/period, adjust=False).mean()
        dip = 100 * dm_p.ewm(alpha=1/period, adjust=False).mean() / atr14.replace(0, 1e-9)
        dim = 100 * dm_m.ewm(alpha=1/period, adjust=False).mean() / atr14.replace(0, 1e-9)
        dx  = 100 * (dip - dim).abs() / (dip + dim).replace(0, 1e-9)
        return float(dx.ewm(alpha=1/period, adjust=False).mean().iloc[-1])
    except Exception:
        return 0.0


def _detect_compression(df: pd.DataFrame, pip_size: float) -> dict | None:
    """
    Deteksi pola kompresi (descending triangle / wedge / tight range).

    Return dict:
      resistance  — level resistance (rata-rata swing high yang makin turun)
      support     — level support (rata-rata swing low yang flat/naik)
      range_pip   — lebar zona dalam pip
      bars        — jumlah bar yang sudah kompres
      trend       — 'descending_triangle' | 'ascending_triangle' | 'wedge' | 'range'
    Atau None jika tidak terdeteksi.
    """
    if len(df) < BO_MIN_BARS + 5:
        return None

    window = df.tail(BO_LOOKBACK)

    highs = window["high"].values
    lows  = window["low"].values

    # Swing high: lokal maxima
    swing_highs = []
    swing_lows  = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append((i, highs[i]))
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append((i, lows[i]))

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        # Fallback: pakai simple high/low range
        resistance = window["high"].max()
        support    = window["low"].min()
        range_pip  = (resistance - support) / pip_size
        if range_pip <= BO_MAX_RANGE_PIP:
            return {
                "resistance": resistance,
                "support":    support,
                "range_pip":  range_pip,
                "bars":       len(window),
                "trend":      "range",
            }
        return None

    # Trend resistance (swing high): turun = descending, naik = ascending
    r_vals  = [v for _, v in swing_highs[-3:]]
    s_vals  = [v for _, v in swing_lows[-3:]]
    r_trend = r_vals[-1] - r_vals[0]   # negatif = resistance turun
    s_trend = s_vals[-1] - s_vals[0]   # positif = support naik

    resistance = r_vals[-1]   # level resistance terkini
    support    = s_vals[-1]   # level support terkini
    range_pip  = (resistance - support) / pip_size

    if range_pip > BO_MAX_RANGE_PIP:
        return None

    if r_trend < -pip_size * 2 and abs(s_trend) < pip_size * 3:
        pattern = "descending_triangle"   # seperti di chart trader
    elif s_trend > pip_size * 2 and abs(r_trend) < pip_size * 3:
        pattern = "ascending_triangle"
    elif r_trend < -pip_size and s_trend > pip_size:
        pattern = "wedge"
    else:
        pattern = "range"

    return {
        "resistance": resistance,
        "support":    support,
        "range_pip":  range_pip,
        "bars":       len(window),
        "trend":      pattern,
        "r_change":   r_trend / pip_size,  # pip perubahan resistance
        "s_change":   s_trend / pip_size,  # pip perubahan support
    }


def _check_breakout(df: pd.DataFrame, compression: dict, pip_size: float) -> str | None:
    """
    Cek apakah candle terbaru breakout dari zona kompresi.

    Syarat:
      - Close candle MELEWATI resistance / support (bukan hanya wick)
      - Body candle cukup besar (≥ BO_BODY_RATIO dari full range)
      - Close setidaknya 1 pip di luar zona

    Return 'BUY' | 'SELL' | None
    """
    cur = df.iloc[-1]
    o, h, l, c = cur["open"], cur["high"], cur["low"], cur["close"]
    body       = abs(c - o)
    full_range = h - l if h != l else 1e-9

    resistance = compression["resistance"]
    support    = compression["support"]
    min_close_outside = pip_size * 1.0   # minimal 1 pip di luar zona

    body_ok = body >= full_range * BO_BODY_RATIO

    # BUY breakout: close di atas resistance
    if c > resistance + min_close_outside and body_ok and c > o:
        return "BUY"

    # SELL breakdown: close di bawah support
    if c < support - min_close_outside and body_ok and c < o:
        return "SELL"

    return None


def _run_cycle():
    pip_size = get_pip_size(SYMBOL)

    # Ambil data M5
    df_m5 = _candles(mt5.TIMEFRAME_M5, BO_LOOKBACK + 20)
    if df_m5 is None or len(df_m5) < BO_MIN_BARS + 5:
        return

    # Deteksi kompresi
    compression = _detect_compression(df_m5, pip_size)
    if compression is None:
        log_console(
            f"[BO] Tidak ada pola kompresi "
            f"(range {(df_m5['high'].tail(BO_LOOKBACK).max() - df_m5['low'].tail(BO_LOOKBACK).min()) / pip_size:.0f} pip)"
        )
        return

    log_console(
        f"[BO] Kompresi terdeteksi: {compression['trend']} | "
        f"Resistance={compression['resistance']:.2f} | "
        f"Support={compression['support']:.2f} | "
        f"Range={compression['range_pip']:.1f} pip | "
        f"Bars={compression['bars']}"
    )

    # ADX — momentum mulai terbentuk?
    adx_val = _adx(df_m5)
    if adx_val < BO_ADX_MIN:
        log_console(f"[BO] ADX {adx_val:.1f} < {BO_ADX_MIN} — pasar masih diam, tunggu")
        return

    # Cek breakout
    direction = _check_breakout(df_m5, compression, pip_size)
    if direction is None:
        log_console(
            f"[BO] Belum ada breakout | "
            f"Harga={df_m5.iloc[-1]['close']:.2f} | "
            f"Resistance={compression['resistance']:.2f} | "
            f"Support={compression['support']:.2f} | "
            f"ADX={adx_val:.1f}"
        )
        return

    # Throttle
    now  = time.time()
    last = _last_alert.get(direction, 0)
    if now - last < BO_COOLDOWN_SEC:
        remaining = int(BO_COOLDOWN_SEC - (now - last))
        log_console(f"[BO] {direction} cooldown {remaining}s — skip")
        return

    # Hitung level
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        return
    entry = tick.ask if direction == "BUY" else tick.bid

    if direction == "BUY":
        sl   = compression["support"] - BO_SL_BUFFER_PIP * pip_size
        tp1  = entry + BO_TP1_PIPS * pip_size
        tp2  = entry + BO_TP2_PIPS * pip_size
    else:
        sl   = compression["resistance"] + BO_SL_BUFFER_PIP * pip_size
        tp1  = entry - BO_TP1_PIPS * pip_size
        tp2  = entry - BO_TP2_PIPS * pip_size

    sl_dist  = abs(entry - sl)
    tp1_dist = abs(tp1 - entry)
    tp2_dist = abs(tp2 - entry)
    rr1 = tp1_dist / sl_dist if sl_dist else 0
    rr2 = tp2_dist / sl_dist if sl_dist else 0

    # Pattern name dari tipe kompresi
    pattern_map = {
        "descending_triangle": "Descending Triangle Breakout",
        "ascending_triangle":  "Ascending Triangle Breakout",
        "wedge":               "Wedge Breakout",
        "range":               "Range Breakout",
    }
    pattern_name = pattern_map.get(compression["trend"], "Compression Breakout")

    log_console(
        f"[BO] ⚡ {direction} BREAKOUT | {pattern_name} | "
        f"Entry={entry:.2f} | SL={sl:.2f} | TP1={tp1:.2f} | TP2={tp2:.2f} | "
        f"ADX={adx_val:.1f} | Range kompres={compression['range_pip']:.1f} pip"
    )

    _send_alert(
        direction=direction,
        pattern=pattern_name,
        compression=compression,
        entry=entry,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        sl_dist=sl_dist,
        tp1_dist=tp1_dist,
        tp2_dist=tp2_dist,
        rr1=rr1,
        rr2=rr2,
        adx=adx_val,
        pip_size=pip_size,
    )
    _last_alert[direction] = now


def _send_alert(
    direction, pattern, compression,
    entry, sl, tp1, tp2,
    sl_dist, tp1_dist, tp2_dist,
    rr1, rr2, adx, pip_size,
):
    from datetime import datetime
    now_str   = datetime.now().strftime("%H:%M")
    arrow     = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
    bo_icon   = "📈" if direction == "BUY" else "📉"

    # Deskripsi pola
    trend = compression["trend"]
    if trend == "descending_triangle":
        pola_desc = (
            f"Resistance turun {abs(compression.get('r_change', 0)):.1f} pip | "
            f"Support flat → harga terjepit, breakout {direction}"
        )
    elif trend == "ascending_triangle":
        pola_desc = (
            f"Support naik {abs(compression.get('s_change', 0)):.1f} pip | "
            f"Resistance flat → harga terjepit, breakout {direction}"
        )
    elif trend == "wedge":
        pola_desc = "Resistance turun + Support naik → wedge, harga pecah keluar"
    else:
        pola_desc = f"Range {compression['range_pip']:.1f} pip, harga breakout {direction}"

    msg = (
        f"{bo_icon} *BREAKOUT {arrow} — {SYMBOL}* `{now_str}`\n"
        f"\n"
        f"*Pola*  : `{pattern}`\n"
        f"_{pola_desc}_\n"
        f"\n"
        f"*Zona Kompresi:*\n"
        f"Resistance : `{compression['resistance']:.2f}`\n"
        f"Support    : `{compression['support']:.2f}`\n"
        f"Range      : `{compression['range_pip']:.1f} pip` | ADX : `{adx:.1f}`\n"
        f"\n"
        f"*Entry* : `{entry:.2f}`\n"
        f"*SL*    : `{sl:.2f}`  ({sl_dist:.1f} pip) — sisi berlawanan zona\n"
        f"*TP1*   : `{tp1:.2f}`  (+{tp1_dist:.1f} pip | RR 1:{rr1:.1f})\n"
        f"*TP2*   : `{tp2:.2f}`  (+{tp2_dist:.1f} pip | RR 1:{rr2:.1f})\n"
        f"\n"
        f"⚡ _Breakout konfirmasi — candle close di luar zona_"
    )
    telegram.send(msg)


def _status():
    info = mt5.account_info()
    if info is None:
        return
    log_console(
        f"[BO STATUS] Balance={info.balance:,.0f} | "
        f"Equity={info.equity:,.0f} | "
        f"Symbol={SYMBOL} | "
        f"Lookback={BO_LOOKBACK}bar | MaxRange={BO_MAX_RANGE_PIP}pip"
    )


def main():
    log_console("=" * 60)
    log_console("  TrendBot Breakout Scanner  |  Compression + Breakout")
    log_console("=" * 60)
    log_console(f"  Lookback  : {BO_LOOKBACK} bar M5")
    log_console(f"  Max Range : {BO_MAX_RANGE_PIP} pip (zona kompres)")
    log_console(f"  TP1/TP2   : {BO_TP1_PIPS}/{BO_TP2_PIPS} pip")
    log_console(f"  SL Buffer : {BO_SL_BUFFER_PIP} pip dari sisi berlawanan zona")
    log_console("=" * 60)

    if not _connect():
        sys.exit(1)

    telegram.send(
        f"🔍 *Breakout Scanner started* | {SYMBOL}\n"
        f"Deteksi: Compression + Breakout konfirmasi\n"
        f"TP1={BO_TP1_PIPS}pip | TP2={BO_TP2_PIPS}pip | SLbuffer={BO_SL_BUFFER_PIP}pip"
    )

    last_status = 0.0
    try:
        while True:
            now = time.time()
            if now - last_status >= 60:
                _status()
                last_status = now
            try:
                _run_cycle()
            except Exception as e:
                log_console(f"[BO] Cycle error: {e}", level="ERROR")
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        log_console("[BO] Dihentikan oleh user.")
        telegram.send(f"⛔ *Breakout Scanner stopped* | {SYMBOL}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
