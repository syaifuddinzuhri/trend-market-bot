"""
Signal aggregator — dua jenis signal:

PRIMARY       : setup lengkap multi-TF (BOS/CHoCH + pullback H1 + candle M15)
CONTINUATION  : mid-session re-entry (EMA_RETEST atau HLC)
"""
import pandas as pd
import config
from bot.trend import get_trend, TREND_BULLISH, TREND_BEARISH, NO_TRADE
from bot.pullback import has_pullback
from bot.structure import (
    get_market_structure,
    is_bullish_structure, is_bearish_structure,
    structure_strength,
    has_ema_retest_m15, has_hlc_continuation,
    BULLISH_BOS, BULLISH_CHOCH, BEARISH_BOS, BEARISH_CHOCH,
)
from bot.candlestick import (
    check_pattern,
    BULLISH_PIN_BAR, BULLISH_ENGULFING,
    BEARISH_PIN_BAR, BEARISH_ENGULFING,
)
from bot.session import is_trading_session
from bot.news_filter import is_news_lock
from bot.logger import log_console
from bot import telegram
from bot.mt5_zones import load_zones, price_in_zone, zones_summary, nearest_zones

_ADX_CHOCH_BONUS = 5

# Throttle alert manual — cegah spam Telegram tiap 5 menit
_alert_sent_at:    dict[tuple, float] = {}   # key: (symbol, direction) → epoch
_alert_last_price: dict[tuple, float] = {}   # key: (symbol, direction) → entry price terakhir
ALERT_MIN_FILTERS = 6          # kirim jika lolos >= N filter
ALERT_ADVERSE_PIP = 5          # warning jika harga sudah bergerak >5 pip berlawanan


def _ok(v: bool) -> str:
    return "✅" if v else "❌"


def _momentum_label(adx: float) -> tuple[str, bool]:
    """Return (label_string, is_sideways)."""
    if adx < 20:
        return f"⚪ SIDEWAYS (ADX {adx:.1f}) — hindari entry", True
    elif adx < 25:
        return f"🟡 LEMAH (ADX {adx:.1f}) — hati-hati", False
    elif adx < 40:
        return f"🟢 TRENDING (ADX {adx:.1f})", False
    else:
        return f"🔴 TRENDING KUAT (ADX {adx:.1f})", False


def scan_log(df_h4: pd.DataFrame, df_h1: pd.DataFrame, df_m15: pd.DataFrame, df_m5: pd.DataFrame | None = None):
    """
    Cetak status semua filter setiap cycle — membantu entry manual di akun lain.

    Format (semua filter lolos):
    [SCAN] BUY | Session✅ News✅ | Trend✅ | ADX=28.3✅ ATR=21.5✅ | Pullback✅ | Struct=BOS↑✅ | Candle=Engulf↑✅ → 🟢 SIAP ENTRY
    [SCAN]   ↳ Entry=3285.50 | SL=3271.30 (-14.20) | TP1=3299.70 (+14.20) | TP2=3313.90 (+28.40)
    """
    import MetaTrader5 as mt5
    from bot.risk import calc_sl

    session_ok = is_trading_session()
    news_ok    = not is_news_lock()

    # H4 trend
    trend = get_trend(df_h4)
    trend_ok = trend != NO_TRADE
    direction = "BUY" if trend == TREND_BULLISH else ("SELL" if trend == TREND_BEARISH else "—")

    # H1 filters
    last_h1    = df_h1.iloc[-1]
    adx_val    = last_h1["adx"]
    atr_val    = last_h1["atr"]
    atr_ma_val = last_h1.get("atr_ma", 0)
    adx_ok     = adx_val >= config.ADX_MIN
    atr_ok     = (not pd.isna(atr_ma_val)) and (atr_val >= atr_ma_val * config.ATR_MA_RATIO)
    pullback_ok = has_pullback(df_h1, trend) if trend_ok else False

    # M15 structure & candle
    structure   = get_market_structure(df_m15)
    struct_ok   = (
        (direction == "BUY"  and is_bullish_structure(structure)) or
        (direction == "SELL" and is_bearish_structure(structure))
    ) if trend_ok else False

    # M5 untuk candle (lebih presisi), fallback M15
    entry_df  = df_m5 if df_m5 is not None else df_m15
    entry_tf  = "M5" if df_m5 is not None else "M15"
    pattern   = check_pattern(entry_df)
    bull_pat  = pattern in {BULLISH_PIN_BAR, BULLISH_ENGULFING}
    bear_pat  = pattern in {BEARISH_PIN_BAR, BEARISH_ENGULFING}
    candle_ok = (direction == "BUY" and bull_pat) or (direction == "SELL" and bear_pat) if trend_ok else False

    filters = [session_ok, news_ok, trend_ok, adx_ok, atr_ok, pullback_ok, struct_ok, candle_ok]
    passed  = sum(filters)
    total   = len(filters)
    all_ok  = all(filters)

    # Simbol struktur pendek
    struct_short = {
        "BULLISH_BOS":   "BOS↑", "BEARISH_BOS":   "BOS↓",
        "BULLISH_CHOCH": "CHoCH↑", "BEARISH_CHOCH": "CHoCH↓",
    }.get(structure, structure[:8] if structure else "—")

    candle_short = {
        BULLISH_PIN_BAR: "PinBar↑", BULLISH_ENGULFING: "Engulf↑",
        BEARISH_PIN_BAR: "PinBar↓", BEARISH_ENGULFING: "Engulf↓",
    }.get(pattern, "—") + f"[{entry_tf}]"

    if all_ok:
        status = "🟢 SIAP ENTRY"
    elif passed >= 6:
        status = f"🔥 HAMPIR ({passed}/{total})"
    elif passed >= 4:
        status = f"⏳ DEKAT ({passed}/{total})"
    else:
        status = f"💤 TUNGGU ({passed}/{total})"

    log_console(
        f"[SCAN] {direction} | "
        f"Session{_ok(session_ok)} News{_ok(news_ok)} | "
        f"Trend{_ok(trend_ok)} | "
        f"ADX={adx_val:.1f}{_ok(adx_ok)} "
        f"ATR={atr_val:.2f}/MA={atr_ma_val:.2f}{_ok(atr_ok)} | "
        f"Pullback{_ok(pullback_ok)} | "
        f"Struct={struct_short}{_ok(struct_ok)} | "
        f"Candle={candle_short}{_ok(candle_ok)} → {status}"
    )

    # Tampilkan proyeksi Entry / SL / TP jika 6+ filter lolos dan arah diketahui
    if passed >= 6 and direction in ("BUY", "SELL"):
        try:
            tick = mt5.symbol_info_tick(config.SYMBOL)
            if tick:
                entry = tick.ask if direction == "BUY" else tick.bid
                sl, sl_dist = calc_sl(df_h1, direction, entry)
                if sl_dist > 0:
                    tp1 = entry + sl_dist * config.TP1_R if direction == "BUY" else entry - sl_dist * config.TP1_R
                    tp2 = entry + sl_dist * config.TP2_R if direction == "BUY" else entry - sl_dist * config.TP2_R
                    sl_diff  = sl   - entry  # negatif untuk BUY
                    tp1_diff = tp1  - entry  # positif untuk BUY
                    tp2_diff = tp2  - entry
                    log_console(
                        f"[SCAN]   ↳ Entry={entry:.2f} | "
                        f"SL={sl:.2f} ({sl_diff:+.2f}) | "
                        f"TP1={tp1:.2f} ({tp1_diff:+.2f}) | "
                        f"TP2={tp2:.2f} ({tp2_diff:+.2f})"
                    )
        except Exception:
            pass

    # Jika hampir entry, cetak filter mana yang belum terpenuhi
    missing = []
    if passed >= 6 and not all_ok:
        if not struct_ok:   missing.append(f"Tunggu {direction} structure di M15")
        if not candle_ok:   missing.append(f"Tunggu candle konfirmasi ({direction})")
        if not pullback_ok: missing.append(f"Tunggu pullback ke EMA20/50 H1")
        if not atr_ok:      missing.append(f"Tunggu ATR naik (skrg {atr_val:.2f} < MA {atr_ma_val:.2f})")
        if not adx_ok:      missing.append(f"Tunggu ADX naik (skrg {adx_val:.1f} < {config.ADX_MIN})")
        for m in missing:
            log_console(f"[SCAN]   ↳ {m}")

    # ── Cek zona S/R yang di-draw di MT5 ─────────────────────────
    mt5_zones = load_zones()
    zone_hit  = None
    zone_info = ""
    if mt5_zones and direction in ("BUY", "SELL"):
        try:
            tick_z = mt5.symbol_info_tick(config.SYMBOL)
            if tick_z:
                from bot.risk import get_pip_size as _gpz
                _pz = _gpz(config.SYMBOL)
                _cp = tick_z.bid
                zone_hit = price_in_zone(mt5_zones, _cp, direction, tolerance=_pz * 2)
                if zone_hit:
                    zone_info = (
                        f"📦 Zona S/R: *{zone_hit.get('label') or zone_hit['zone_type']}* "
                        f"`{zone_hit['low']:.2f}`–`{zone_hit['high']:.2f}`"
                    )
                    log_console(
                        f"[SCAN] 📦 Harga di zona {zone_hit['zone_type']} "
                        f"{zone_hit['low']:.2f}–{zone_hit['high']:.2f} "
                        f"({zone_hit.get('label', '')})"
                    )
        except Exception:
            pass

    # ── Alert manual ke Telegram jika >= ALERT_MIN_FILTERS ───────
    if passed >= ALERT_MIN_FILTERS and direction in ("BUY", "SELL"):
        import time as _t
        key = (config.SYMBOL, direction)
        now = _t.time()
        last = _alert_sent_at.get(key, 0)
        if now - last >= config.ALERT_COOLDOWN_SECONDS:
            try:
                from bot.risk import calc_sl, get_pip_size
                tick = mt5.symbol_info_tick(config.SYMBOL)
                entry_price = tick.ask if direction == "BUY" else tick.bid
                sl_price, sl_dist = calc_sl(df_h1, direction, entry_price)
                pip_size = get_pip_size(config.SYMBOL)

                if config.TP_MODE == "pips":
                    tp1_price = entry_price + config.TP1_PIPS * pip_size if direction == "BUY" else entry_price - config.TP1_PIPS * pip_size
                    tp2_price = entry_price + config.TP2_PIPS * pip_size if direction == "BUY" else entry_price - config.TP2_PIPS * pip_size
                    tp3_price = entry_price + config.TP3_PIPS * pip_size if direction == "BUY" else entry_price - config.TP3_PIPS * pip_size
                else:
                    tp1_price = entry_price + sl_dist * config.TP1_R if direction == "BUY" else entry_price - sl_dist * config.TP1_R
                    tp2_price = entry_price + sl_dist * config.TP2_R if direction == "BUY" else entry_price - sl_dist * config.TP2_R
                    tp3_price = tp2_price

                # Deteksi apakah harga sudah bergerak berlawanan sejak alert terakhir
                last_price = _alert_last_price.get(key, 0)
                adverse_warning = ""
                if last_price > 0:
                    if direction == "SELL":
                        adverse_pips = (entry_price - last_price) / pip_size
                    else:
                        adverse_pips = (last_price - entry_price) / pip_size
                    if adverse_pips >= ALERT_ADVERSE_PIP:
                        adverse_warning = (
                            f"⚠️ Harga bergerak {adverse_pips:.0f} pip berlawanan "
                            f"sejak alert terakhir ({last_price:.2f} → {entry_price:.2f})"
                        )

                ema20_h1 = last_h1.get("ema20", 0)
                ema50_h1 = last_h1.get("ema50", 0)
                if direction == "SELL":
                    move_label = "Pullback naik (retracement)" if entry_price > ema50_h1 else "Lanjut turun"
                else:
                    move_label = "Pullback turun (retracement)" if entry_price < ema50_h1 else "Lanjut naik"

                high_m15 = df_m15["high"].tail(20).max() if df_m15 is not None else 0
                low_m15  = df_m15["low"].tail(20).min()  if df_m15 is not None else 0

                telegram.notify_alert_manual(
                    direction=direction,
                    symbol=config.SYMBOL,
                    passed=passed,
                    total=total,
                    adx=adx_val,
                    atr_val=atr_val,
                    atr_ma=atr_ma_val,
                    struct_short=struct_short,
                    candle_short=candle_short,
                    entry=entry_price,
                    sl=sl_price,
                    tp1=tp1_price,
                    tp2=tp2_price,
                    tp3=tp3_price,
                    missing=missing,
                    move_label=move_label,
                    momentum_label=_momentum_label(adx_val)[0],
                    ema20=ema20_h1,
                    ema50=ema50_h1,
                    high_m15=high_m15,
                    low_m15=low_m15,
                    adverse_warning=adverse_warning,
                    zone_info=zone_info,
                )
                _alert_sent_at[key]    = now
                _alert_last_price[key] = entry_price
                log_console(f"[SCAN] ⚡ Alert manual dikirim ke Telegram ({passed}/{total})")
            except Exception as e:
                log_console(f"[SCAN] Alert gagal dikirim: {e}", level="WARN")

    # ── Counter-trend opportunity check ──────────────────────────────
    # Jika pullback besar (>= 30 pip) dari low/high dan M15 tunjukkan
    # struktur berlawanan + candle konfirmasi → kirim alert scalp counter-trend
    if direction in ("BUY", "SELL") and trend_ok and adx_ok:
        import time as _ct
        try:
            tick_ct = mt5.symbol_info_tick(config.SYMBOL)
            if tick_ct:
                from bot.risk import get_pip_size as _gps
                _pip = _gps(config.SYMBOL)
                _cp  = tick_ct.bid
                _h20 = df_m15["high"].tail(20).max()
                _l20 = df_m15["low"].tail(20).min()
                pb_pips = (_cp - _l20) / _pip if direction == "SELL" else (_h20 - _cp) / _pip

                if pb_pips >= 30:
                    opp_dir = "BUY" if direction == "SELL" else "SELL"
                    opp_struct = get_market_structure(df_m15)
                    opp_struct_ok = (
                        (opp_dir == "BUY"  and is_bullish_structure(opp_struct)) or
                        (opp_dir == "SELL" and is_bearish_structure(opp_struct))
                    )
                    opp_pat = check_pattern(entry_df)
                    opp_candle_ok = (
                        (opp_dir == "BUY"  and opp_pat in {BULLISH_PIN_BAR, BULLISH_ENGULFING}) or
                        (opp_dir == "SELL" and opp_pat in {BEARISH_PIN_BAR, BEARISH_ENGULFING})
                    )
                    if opp_struct_ok and opp_candle_ok:
                        ct_key  = (config.SYMBOL, f"CT_{opp_dir}")
                        ct_now  = _ct.time()
                        ct_last = _alert_sent_at.get(ct_key, 0)
                        if ct_now - ct_last >= config.ALERT_COOLDOWN_SECONDS:
                            from bot.risk import calc_sl as _csl
                            _entry = tick_ct.ask if opp_dir == "BUY" else tick_ct.bid
                            _sl, _sl_dist = _csl(df_h1, opp_dir, _entry)
                            if _sl_dist > 0:
                                from bot.risk import get_pip_size as _gps2
                                _ps = _gps2(config.SYMBOL)
                                _tp1 = (_entry + config.TP1_PIPS * _ps if opp_dir == "BUY"
                                        else _entry - config.TP1_PIPS * _ps)
                                struct_lbl = {
                                    "BULLISH_BOS": "BOS↑", "BEARISH_BOS": "BOS↓",
                                    "BULLISH_CHOCH": "CHoCH↑", "BEARISH_CHOCH": "CHoCH↓",
                                }.get(opp_struct, opp_struct[:8] if opp_struct else "—")
                                telegram.notify_counter_trend(
                                    direction=opp_dir,
                                    main_direction=direction,
                                    symbol=config.SYMBOL,
                                    pullback_pips=pb_pips,
                                    structure=struct_lbl,
                                    pattern=opp_pat,
                                    entry=_entry,
                                    sl=_sl,
                                    tp1=_tp1,
                                    adx=adx_val,
                                )
                                _alert_sent_at[ct_key] = ct_now
                                log_console(
                                    f"[SCAN] ↩️ Counter-trend {opp_dir} alert — "
                                    f"pullback {pb_pips:.0f} pip | {struct_lbl} | {opp_pat}"
                                )
        except Exception as _e:
            log_console(f"[SCAN] Counter-trend check error: {_e}", level="WARN")

    return all_ok


def build_analysis(df_h4, df_h1, df_m15, df_m5=None) -> dict:
    """
    Kumpulkan data analisa market untuk dikirim ke Telegram.
    Return dict lengkap termasuk narasi kondisi & rekomendasi.
    """
    import MetaTrader5 as mt5

    session_ok  = is_trading_session()
    news_ok     = not is_news_lock()
    trend       = get_trend(df_h4)
    trend_ok    = trend != NO_TRADE
    direction   = "BUY" if trend == TREND_BULLISH else ("SELL" if trend == TREND_BEARISH else "—")

    last_h4     = df_h4.iloc[-1]
    last_h1     = df_h1.iloc[-1]
    last_m15    = df_m15.iloc[-1]

    adx_val     = last_h1["adx"]
    atr_val     = last_h1["atr"]
    atr_ma_val  = last_h1.get("atr_ma", 0)
    adx_ok      = adx_val >= config.ADX_MIN
    atr_ok      = (not pd.isna(atr_ma_val)) and (atr_val >= atr_ma_val * config.ATR_MA_RATIO)
    pullback_ok = has_pullback(df_h1, trend) if trend_ok else False

    structure   = get_market_structure(df_m15)
    struct_ok   = (
        (direction == "BUY"  and is_bullish_structure(structure)) or
        (direction == "SELL" and is_bearish_structure(structure))
    ) if trend_ok else False

    entry_df    = df_m5 if df_m5 is not None else df_m15
    pattern     = check_pattern(entry_df)
    bull_pat    = pattern in {BULLISH_PIN_BAR, BULLISH_ENGULFING}
    bear_pat    = pattern in {BEARISH_PIN_BAR, BEARISH_ENGULFING}
    candle_ok   = (direction == "BUY" and bull_pat) or (direction == "SELL" and bear_pat) if trend_ok else False

    filters = [session_ok, news_ok, trend_ok, adx_ok, atr_ok, pullback_ok, struct_ok, candle_ok]
    passed  = sum(filters)
    total   = len(filters)

    # ── Key levels ──────────────────────────────────────────────────
    ema20_h1  = last_h1.get("ema20", 0)
    ema50_h1  = last_h1.get("ema50", 0)
    ema200_h4 = last_h4.get("ema200", 0)
    close_m15 = last_m15["close"]
    high_m15  = df_m15["high"].tail(20).max()
    low_m15   = df_m15["low"].tail(20).min()

    # Harga sekarang
    tick = mt5.symbol_info_tick(config.SYMBOL)
    current_price = tick.bid if tick else close_m15

    from bot.risk import get_pip_size
    pip_size = get_pip_size(config.SYMBOL)

    # ── Deteksi kondisi sekarang ─────────────────────────────────────
    if direction == "SELL":
        is_pullback_now = current_price > ema50_h1
        move_label = "Pullback naik (retracement)" if is_pullback_now else "Lanjut turun"
    elif direction == "BUY":
        is_pullback_now = current_price < ema50_h1
        move_label = "Pullback turun (retracement)" if is_pullback_now else "Lanjut naik"
    else:
        move_label = "Ranging / tidak jelas"
        is_pullback_now = False

    # ── Seberapa jauh harga dari high/low 20-bar ─────────────────────
    move_from_high = (high_m15 - current_price) / pip_size   # pip turun dari high
    move_from_low  = (current_price - low_m15)  / pip_size   # pip naik dari low

    # ── Seberapa besar pullback saat ini ─────────────────────────────
    # Untuk SELL trend: pullback = pip naik dari low terakhir
    # Untuk BUY trend:  pullback = pip turun dari high terakhir
    if direction == "SELL":
        pullback_pips = move_from_low   # naik dari low = sedang pullback naik
    elif direction == "BUY":
        pullback_pips = move_from_high  # turun dari high = sedang pullback turun
    else:
        pullback_pips = 0

    if pullback_pips < 30:
        pullback_size = "kecil"
    elif pullback_pips < 70:
        pullback_size = "sedang"
    else:
        pullback_size = "besar"

    # ── Deteksi exhaustion (candle kecil) ────────────────────────────
    last5 = df_m15.tail(5)
    avg_body = (abs(last5["close"] - last5["open"]) / pip_size).mean()
    is_exhaustion = avg_body < atr_val / pip_size * 0.3   # body < 30% ATR = konsolidasi

    # ── Zona bounce/re-entry ──────────────────────────────────────────
    if direction == "SELL" and not is_pullback_now:
        bounce_low  = min(ema20_h1, current_price + atr_val * 0.5)
        bounce_high = max(ema20_h1, current_price + atr_val * 1.0)
        bounce_zone = f"{bounce_low:.2f}–{bounce_high:.2f}"
    elif direction == "BUY" and not is_pullback_now:
        bounce_low  = min(ema20_h1, current_price - atr_val * 1.0)
        bounce_high = max(ema20_h1, current_price - atr_val * 0.5)
        bounce_zone = f"{bounce_low:.2f}–{bounce_high:.2f}"
    else:
        bounce_zone = ""

    # ── Narasi situasi ────────────────────────────────────────────────
    narasi_parts = []

    # Konteks pergerakan utama
    if direction == "SELL":
        narasi_parts.append(f"Trend SELL — harga turun {move_from_high:.0f} pip dari high {high_m15:.2f}")
    elif direction == "BUY":
        narasi_parts.append(f"Trend BUY — harga naik {move_from_low:.0f} pip dari low {low_m15:.2f}")

    # Narasi pullback jika sedang terjadi
    if is_pullback_now and pullback_pips > 10:
        if direction == "SELL":
            if pullback_size == "kecil":
                narasi_parts.append(
                    f"Pullback naik {pullback_pips:.0f} pip (kecil) — normal retracement, "
                    f"tunggu rejection di EMA20 ({ema20_h1:.2f}) lalu SELL"
                )
            elif pullback_size == "sedang":
                narasi_parts.append(
                    f"Pullback naik {pullback_pips:.0f} pip (sedang) — waspada, "
                    f"cari rejection di EMA50 ({ema50_h1:.2f}) atau resistance {high_m15:.2f}"
                )
            else:  # besar
                narasi_parts.append(
                    f"⚠️ Pullback naik {pullback_pips:.0f} pip (BESAR) — "
                    f"bisa scalp BUY counter-trend ke resistance {ema50_h1:.2f}–{ema20_h1:.2f}, "
                    f"ATAU tunggu SELL di area EMA50 ({ema50_h1:.2f}) jika ada rejection"
                )
        elif direction == "BUY":
            if pullback_size == "kecil":
                narasi_parts.append(
                    f"Pullback turun {pullback_pips:.0f} pip (kecil) — normal retracement, "
                    f"tunggu bounce di EMA20 ({ema20_h1:.2f}) lalu BUY"
                )
            elif pullback_size == "sedang":
                narasi_parts.append(
                    f"Pullback turun {pullback_pips:.0f} pip (sedang) — waspada, "
                    f"cari bounce di EMA50 ({ema50_h1:.2f}) atau support {low_m15:.2f}"
                )
            else:  # besar
                narasi_parts.append(
                    f"⚠️ Pullback turun {pullback_pips:.0f} pip (BESAR) — "
                    f"bisa scalp SELL counter-trend ke support {ema50_h1:.2f}–{ema20_h1:.2f}, "
                    f"ATAU tunggu BUY di area EMA50 ({ema50_h1:.2f}) jika ada bounce"
                )

    # Exhaustion / momentum candle
    if is_exhaustion:
        narasi_parts.append(
            f"Candle kecil avg {avg_body:.1f} pip — konsolidasi/exhaustion"
            + (f", jika bounce ke {bounce_zone} → peluang {'SELL' if direction == 'SELL' else 'BUY'} ulang" if bounce_zone else "")
        )
    else:
        narasi_parts.append(f"Candle aktif avg {avg_body:.1f} pip — momentum masih jalan")

    narasi = "\n💬 ".join(narasi_parts)

    # ── Momentum / sideways detection ────────────────────────────────
    momentum_label, is_sideways = _momentum_label(adx_val)

    # ── Filter yang belum lolos ───────────────────────────────────────
    filter_names = ["Session", "News", "Trend H4", "ADX", "ATR", "Pullback H1", "Struktur M15", "Candle"]
    filter_vals  = [session_ok, news_ok, trend_ok, adx_ok, atr_ok, pullback_ok, struct_ok, candle_ok]
    missing_filters = [filter_names[i] for i, v in enumerate(filter_vals) if not v]

    # ── Rekomendasi ──────────────────────────────────────────────────
    entry_zone = sl_level = tp1_level = tp2_level = ""

    def _levels(ref, d):
        nonlocal entry_zone, sl_level, tp1_level, tp2_level
        if d == "SELL":
            entry_zone = f"{ref:.2f}"
            sl_level   = f"{ref + config.MAX_SL_POINTS * pip_size:.2f}"
            tp1_level  = f"{ref - config.TP1_PIPS * pip_size:.2f}"
            tp2_level  = f"{ref - config.TP2_PIPS * pip_size:.2f}"
        else:
            entry_zone = f"{ref:.2f}"
            sl_level   = f"{ref - config.MAX_SL_POINTS * pip_size:.2f}"
            tp1_level  = f"{ref + config.TP1_PIPS * pip_size:.2f}"
            tp2_level  = f"{ref + config.TP2_PIPS * pip_size:.2f}"

    if is_sideways:
        recommendation = (
            f"⚪ SIDEWAYS — pasar ranging, ADX {adx_val:.1f} terlalu lemah\n"
            f"Tunggu breakout dari range {low_m15:.2f}–{high_m15:.2f}"
        )

    elif not trend_ok:
        recommendation = "⏸ TUNGGU — Trend H4 belum jelas (EMA50 vs EMA200 belum silang)"

    elif passed >= 7:
        arrow_txt = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
        recommendation = f"✅ SIAP ENTRY {arrow_txt} — {passed}/{total} filter lolos — entry manual atau tunggu bot"
        _levels(current_price, direction)

    elif passed == 6:
        arrow_txt = "🟢 BUY" if direction == "BUY" else "🔴 SELL"
        recommendation = f"⚡ POTENSI ENTRY {arrow_txt} — 6/8 filter lolos, pertimbangkan entry manual"
        _levels(current_price, direction)

    elif is_pullback_now and direction == "SELL":
        target = max(ema20_h1, ema50_h1)
        recommendation = (
            f"⏳ TUNGGU SELL — sedang pullback naik ke EMA\n"
            f"Zona entry: `{target:.2f}–{target + atr_val * 0.3:.2f}` → tunggu rejection/pin bar"
        )
        _levels(target, "SELL")
        entry_zone = f"{target:.2f}–{target + atr_val * 0.3:.2f}"

    elif is_pullback_now and direction == "BUY":
        target = min(ema20_h1, ema50_h1)
        recommendation = (
            f"⏳ TUNGGU BUY — sedang pullback turun ke EMA\n"
            f"Zona entry: `{target - atr_val * 0.3:.2f}–{target:.2f}` → tunggu bounce/pin bar"
        )
        _levels(target, "BUY")
        entry_zone = f"{target - atr_val * 0.3:.2f}–{target:.2f}"

    else:
        if direction == "SELL":
            next_action = f"Pantau apakah harga naik dulu ke EMA20 ({ema20_h1:.2f}) lalu balik turun"
        else:
            next_action = f"Pantau apakah harga turun dulu ke EMA20 ({ema20_h1:.2f}) lalu balik naik"
        recommendation = f"👀 MONITOR — tunggu filter lengkap\n{next_action}"

    # ── TP3 level ─────────────────────────────────────────────────────
    if entry_zone and direction in ("BUY", "SELL"):
        try:
            ref = float(entry_zone.split("–")[0])
            if direction == "SELL":
                tp3_level = f"{ref - config.TP3_PIPS * pip_size:.2f}"
            else:
                tp3_level = f"{ref + config.TP3_PIPS * pip_size:.2f}"
        except Exception:
            tp3_level = ""
    else:
        tp3_level = ""

    # ── Zona S/R dari MT5 rectangle ──────────────────────────────────
    mt5_zones_data = load_zones()
    drawn_zone     = None
    nearby_zones   = []
    zones_str      = ""
    if mt5_zones_data:
        drawn_zone   = price_in_zone(mt5_zones_data, current_price, direction, tolerance=pip_size * 2)
        nearby_zones = nearest_zones(mt5_zones_data, current_price, n=3)
        zones_str    = zones_summary(mt5_zones_data, current_price, pip_size)

    # ── Yang perlu dipantau ────────────────────────────────────────────
    pantau = []
    if direction == "SELL":
        if is_pullback_now:
            pantau.append(f"Rejection di EMA20 `{ema20_h1:.2f}`–EMA50 `{ema50_h1:.2f}` → konfirmasi SELL")
        if not is_pullback_now and not is_exhaustion:
            pantau.append(f"Jika harga naik ke `{ema20_h1:.2f}` → cari pin bar/engulfing lalu SELL")
        if is_exhaustion and bounce_zone:
            pantau.append(f"Bounce ke `{bounce_zone}` → peluang SELL ulang")
        pantau.append(f"Jika tembus `{high_m15:.2f}` (high 20 bar) → tren SELL bisa berbalik")
    elif direction == "BUY":
        if is_pullback_now:
            pantau.append(f"Bounce di EMA20 `{ema20_h1:.2f}`–EMA50 `{ema50_h1:.2f}` → konfirmasi BUY")
        if is_exhaustion and bounce_zone:
            pantau.append(f"Pullback ke `{bounce_zone}` → peluang BUY ulang")
        pantau.append(f"Jika tembus `{low_m15:.2f}` (low 20 bar) → tren BUY bisa berbalik")

    if is_sideways:
        pantau = [
            f"Breakout naik dari `{high_m15:.2f}` → potensi BUY",
            f"Breakout turun dari `{low_m15:.2f}` → potensi SELL",
        ]

    return {
        "direction":        direction,
        "adx":              adx_val,
        "atr":              atr_val,
        "atr_ma":           atr_ma_val,
        "structure":        structure,
        "passed":           passed,
        "total":            total,
        "current_price":    current_price,
        "ema20_h1":         ema20_h1,
        "ema50_h1":         ema50_h1,
        "ema200_h4":        ema200_h4,
        "high_m15":         high_m15,
        "low_m15":          low_m15,
        "move_label":       move_label,
        "recommendation":   recommendation,
        "entry_zone":       entry_zone,
        "sl_level":         sl_level,
        "tp1_level":        tp1_level,
        "tp2_level":        tp2_level,
        "tp3_level":        tp3_level,
        "pullback_ok":      pullback_ok,
        "adx_ok":           adx_ok,
        "atr_ok":           atr_ok,
        "session_ok":       session_ok,
        "news_ok":          news_ok,
        "missing_filters":  missing_filters,
        "momentum_label":   momentum_label,
        "is_sideways":      is_sideways,
        "narasi":           narasi,
        "bounce_zone":      bounce_zone,
        "is_exhaustion":    is_exhaustion,
        "avg_body_pip":     avg_body,
        "move_from_high":   move_from_high,
        "move_from_low":    move_from_low,
        "pullback_pips":    pullback_pips,
        "pullback_size":    pullback_size,
        "pantau":           pantau,
        "drawn_zone":       drawn_zone,
        "nearby_zones":     nearby_zones,
        "zones_str":        zones_str,
    }


def evaluate_pending(
    df_h4: pd.DataFrame,
    df_h1: pd.DataFrame,
) -> dict | None:
    """
    Evaluasi apakah kondisi cukup untuk pasang pending limit order.
    Syarat: session OK + news OK + trend OK + ADX OK + ATR OK
    (Pullback, Struct, Candle belum wajib — pending order tunggu di level EMA)
    Returns dict dengan level, direction, dll — atau None.
    """
    if not is_trading_session():
        return None
    if is_news_lock():
        return None

    trend = get_trend(df_h4)
    if trend == NO_TRADE:
        return None
    direction = "BUY" if trend == TREND_BULLISH else "SELL"

    last_h1  = df_h1.iloc[-1]
    adx_val  = last_h1["adx"]
    atr_val  = last_h1["atr"]
    atr_ma   = last_h1.get("atr_ma", 0)

    if adx_val < config.ADX_MIN:
        return None
    if pd.isna(atr_ma) or atr_val < atr_ma * config.ATR_MA_RATIO:
        return None

    ema20  = last_h1.get("ema20",  0)
    ema50  = last_h1.get("ema50",  0)
    ema100 = last_h1.get("ema100", 0)
    if ema20 <= 0:
        return None

    # Ambil harga sekarang untuk validasi arah level
    import MetaTrader5 as _mt5
    tick = _mt5.symbol_info_tick(config.SYMBOL)
    if tick is None:
        return None
    current = tick.ask if direction == "BUY" else tick.bid

    # SELL LIMIT: level harus DI ATAS harga sekarang (harga naik ke sana lalu reject)
    # BUY  LIMIT: level harus DI BAWAH harga sekarang (harga turun ke sana lalu bounce)
    level = None
    if direction == "SELL":
        for candidate in [ema20, ema50, ema100]:
            if candidate > 0 and candidate > current:
                level = candidate
                break
    else:  # BUY
        for candidate in [ema20, ema50, ema100]:
            if candidate > 0 and candidate < current:
                level = candidate
                break

    if level is None:
        log_console(f"[PEND] Tidak ada level EMA yang valid untuk {direction} LIMIT (harga={current:.2f})")
        return None

    return {
        "direction": direction,
        "trend":     trend,
        "adx":       adx_val,
        "atr":       atr_val,
        "level":     level,
        "ema20_h1":  ema20,
        "ema50_h1":  ema50,
    }


def _base_filters(df_h4: pd.DataFrame, df_h1: pd.DataFrame) -> tuple[str | None, str, float, float]:
    if not is_trading_session():
        return None, "", 0, 0
    if is_news_lock():
        return None, "", 0, 0

    trend = get_trend(df_h4)
    if trend == NO_TRADE:
        return None, "", 0, 0

    direction = "BUY" if trend == TREND_BULLISH else "SELL"

    last_h1    = df_h1.iloc[-1]
    adx_val    = last_h1["adx"]
    atr_val    = last_h1["atr"]
    atr_ma_val = last_h1["atr_ma"]

    if adx_val < config.ADX_SKIP:
        return None, trend, adx_val, atr_val
    if pd.isna(atr_ma_val) or atr_val < atr_ma_val * config.ATR_MA_RATIO:
        log_console(
            f"[SIG] ATR ({atr_val:.4f}) < ATR_MA×{config.ATR_MA_RATIO} "
            f"({atr_ma_val * config.ATR_MA_RATIO:.4f}) — skip"
        )
        return None, trend, adx_val, atr_val

    return direction, trend, adx_val, atr_val


def _candle_ok(df_m15: pd.DataFrame, direction: str) -> str | None:
    pattern = check_pattern(df_m15)
    if direction == "BUY" and pattern in {BULLISH_PIN_BAR, BULLISH_ENGULFING}:
        return pattern
    if direction == "SELL" and pattern in {BEARISH_PIN_BAR, BEARISH_ENGULFING}:
        return pattern
    return None


def evaluate(
    df_h4: pd.DataFrame,
    df_h1: pd.DataFrame,
    df_m15: pd.DataFrame,
    df_m5: pd.DataFrame | None = None,
) -> dict | None:
    direction, trend, adx_val, atr_val = _base_filters(df_h4, df_h1)
    if direction is None:
        return None

    # M15 → konfirmasi struktur BOS/CHoCH
    structure = get_market_structure(df_m15)
    if direction == "BUY" and not is_bullish_structure(structure):
        log_console(f"[SIG] Struct M15={structure} tidak cocok arah {direction} — skip")
        return None
    if direction == "SELL" and not is_bearish_structure(structure):
        log_console(f"[SIG] Struct M15={structure} tidak cocok arah {direction} — skip")
        return None

    strength = structure_strength(structure)
    adx_threshold = config.ADX_MIN + (_ADX_CHOCH_BONUS if strength == "MODERATE" else 0)
    if adx_val < adx_threshold:
        return None

    # ── Pullback check — relaks jika ADX sangat kuat ─────────────────
    # ADX < 45: wajib pullback ke EMA50 H1 (strategi normal)
    # ADX ≥ 45: skip pullback — momentum terlalu kuat, harga jarang balik ke EMA
    strong_trend = adx_val >= config.ADX_STRONG_TREND
    pullback_ok  = has_pullback(df_h1, trend)

    if not pullback_ok and not strong_trend:
        log_console(
            f"[SIG] Pullback belum terjadi (ADX={adx_val:.1f} < {config.ADX_STRONG_TREND}) — skip"
        )
        return None

    if not pullback_ok and strong_trend:
        log_console(
            f"[SIG] Pullback skip — ADX={adx_val:.1f} ≥ {config.ADX_STRONG_TREND} (strong trend mode)"
        )

    # M5 → candle entry presisi (jika tersedia), fallback ke M15
    entry_df = df_m5 if df_m5 is not None else df_m15
    entry_tf  = "M5" if df_m5 is not None else "M15"
    pattern = _candle_ok(entry_df, direction)
    if not pattern:
        log_console(f"[SIG] Candle {entry_tf} tidak valid untuk {direction} — skip")
        return None

    mode_label = "STRONG-TREND" if (strong_trend and not pullback_ok) else "PRIMARY"
    log_console(
        f"[SIG] ✅ {mode_label} | {direction} | {structure} ({strength}) | "
        f"ADX={adx_val:.1f} | ATR={atr_val:.4f} | pattern={pattern} [{entry_tf}]"
    )
    return {
        "signal_type":        "PRIMARY",
        "direction":          direction,
        "trend":              trend,
        "structure":          structure,
        "structure_strength": strength,
        "adx":                adx_val,
        "atr":                atr_val,
        "pattern":            pattern,
        "entry_tf":           entry_tf,
    }


def evaluate_reentry(
    df_h4: pd.DataFrame,
    df_h1: pd.DataFrame,
    df_m15: pd.DataFrame,
    reentry_direction: str,
    df_m5: pd.DataFrame | None = None,
) -> dict | None:
    """
    Re-entry setelah TP hit — syarat lebih ringan dari PRIMARY:
    - Tidak butuh BOS/CHoCH ulang (tren sudah terkonfirmasi)
    - Cukup: session + news + trend H4 sama arah + ADX + ATR + pullback H1 + candle

    Dipanggil dari main.py saat n_open == 0 dan ada TP exit context.
    """
    if not is_trading_session():
        return None
    if is_news_lock():
        return None

    trend = get_trend(df_h4)
    if trend == NO_TRADE:
        return None

    direction = "BUY" if trend == TREND_BULLISH else "SELL"
    if direction != reentry_direction:
        log_console(f"[REENTRY] Tren H4 berbalik ({reentry_direction}→{direction}) — batal re-entry")
        return None

    last_h1    = df_h1.iloc[-1]
    adx_val    = last_h1["adx"]
    atr_val    = last_h1["atr"]
    atr_ma_val = last_h1.get("atr_ma", 0)

    if adx_val < config.ADX_MIN:
        log_console(f"[REENTRY] ADX={adx_val:.1f} < {config.ADX_MIN} — skip")
        return None
    if pd.isna(atr_ma_val) or atr_val < atr_ma_val * config.ATR_MA_RATIO:
        log_console(f"[REENTRY] ATR terlalu lemah — skip")
        return None

    if not has_pullback(df_h1, trend):
        log_console(f"[REENTRY] Belum ada pullback ke EMA H1 — tunggu")
        return None

    entry_df = df_m5 if df_m5 is not None else df_m15
    entry_tf  = "M5" if df_m5 is not None else "M15"
    pattern = _candle_ok(entry_df, direction)
    if not pattern:
        log_console(f"[REENTRY] Belum ada candle konfirmasi [{entry_tf}] — tunggu")
        return None

    log_console(
        f"[REENTRY] ✅ RE-ENTRY | {direction} | "
        f"ADX={adx_val:.1f} | ATR={atr_val:.4f} | pattern={pattern} [{entry_tf}]"
    )
    return {
        "signal_type":        "REENTRY",
        "direction":          direction,
        "trend":              trend,
        "structure":          "REENTRY_PULLBACK",
        "structure_strength": "MODERATE",
        "adx":                adx_val,
        "atr":                atr_val,
        "pattern":            pattern,
        "entry_tf":           entry_tf,
    }


def evaluate_continuation(
    df_h4: pd.DataFrame,
    df_h1: pd.DataFrame,
    df_m15: pd.DataFrame,
    existing_direction: str,
    df_m5: pd.DataFrame | None = None,
) -> dict | None:
    direction, trend, adx_val, atr_val = _base_filters(df_h4, df_h1)
    if direction is None:
        return None
    if direction != existing_direction:
        return None
    if adx_val < config.ADX_MIN:
        return None

    # M5 untuk candle konfirmasi (lebih presisi), fallback M15
    entry_df = df_m5 if df_m5 is not None else df_m15
    entry_tf  = "M5" if df_m5 is not None else "M15"
    pattern = _candle_ok(entry_df, direction)
    if not pattern:
        return None

    if has_ema_retest_m15(df_m15, direction):
        log_console(f"[CONT] ✅ EMA_RETEST | {direction} | ADX={adx_val:.1f} | pattern={pattern} [{entry_tf}]")
        return {
            "signal_type": "EMA_RETEST", "direction": direction, "trend": trend,
            "structure": "EMA_RETEST_M15", "structure_strength": "MODERATE",
            "adx": adx_val, "atr": atr_val, "pattern": pattern, "entry_tf": entry_tf,
        }

    if has_hlc_continuation(df_h1, direction):
        structure = get_market_structure(df_m15)
        if direction == "BUY" and not is_bullish_structure(structure):
            return None
        if direction == "SELL" and not is_bearish_structure(structure):
            return None
        log_console(f"[CONT] ✅ HLC | {direction} | {structure} | ADX={adx_val:.1f} | pattern={pattern} [{entry_tf}]")
        return {
            "signal_type": "HLC", "direction": direction, "trend": trend,
            "structure": structure, "structure_strength": "MODERATE",
            "adx": adx_val, "atr": atr_val, "pattern": pattern, "entry_tf": entry_tf,
        }

    return None
