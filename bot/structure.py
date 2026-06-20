"""
Market Structure Detection — BOS & CHoCH

Swing detection menggunakan N-bar lookback di kiri dan kanan.
Karena kita tidak punya "kanan" untuk candle terbaru, swing
dikonfirmasi saat harga menutup di luar swing point sebelumnya.

Definisi:
  HH  = High lebih tinggi dari High sebelumnya
  HL  = Low lebih tinggi dari Low sebelumnya
  LH  = High lebih rendah dari High sebelumnya
  LL  = Low lebih rendah dari Low sebelumnya

  BOS    (Break of Structure)     = harga break swing terakhir searah tren → tren lanjut
  CHoCH  (Change of Character)    = harga break swing berlawanan arah → potensi reversal / awal tren baru
"""

import pandas as pd
import numpy as np
import config

# Return values
BULLISH_BOS    = "BULLISH_BOS"
BULLISH_CHOCH  = "BULLISH_CHOCH"
BEARISH_BOS    = "BEARISH_BOS"
BEARISH_CHOCH  = "BEARISH_CHOCH"
NO_STRUCTURE   = "NO_STRUCTURE"

# Legacy aliases untuk kompatibilitas signals.py
BULLISH_STRUCTURE = BULLISH_BOS
BEARISH_STRUCTURE = BEARISH_BOS


def _find_swings(df: pd.DataFrame, left: int = 5, right: int = 2) -> tuple[list, list]:
    """
    Cari swing high dan swing low.
    Swing high: candle ke-i lebih tinggi dari `left` candle di kiri dan `right` di kanan.
    right=2 cukup untuk konfirmasi tanpa terlalu delay.
    """
    highs = df["high"].values
    lows  = df["low"].values
    n     = len(df)

    swing_highs = []   # list of (index, price)
    swing_lows  = []

    for i in range(left, n - right):
        # Swing High
        if highs[i] == max(highs[i - left: i + right + 1]):
            swing_highs.append((i, highs[i]))
        # Swing Low
        if lows[i] == min(lows[i - left: i + right + 1]):
            swing_lows.append((i, lows[i]))

    return swing_highs, swing_lows


def _classify_swings(swing_highs: list, swing_lows: list) -> dict:
    """
    Klasifikasi urutan swing: HH/LH dan HL/LL.
    Returns dict dengan kunci 'highs' dan 'lows', masing-masing list of (idx, price, label).
    """
    labeled_highs = []
    for i, (idx, price) in enumerate(swing_highs):
        if i == 0:
            labeled_highs.append((idx, price, "HH"))
        else:
            prev_price = swing_highs[i - 1][1]
            labeled_highs.append((idx, price, "HH" if price > prev_price else "LH"))

    labeled_lows = []
    for i, (idx, price) in enumerate(swing_lows):
        if i == 0:
            labeled_lows.append((idx, price, "HL"))
        else:
            prev_price = swing_lows[i - 1][1]
            labeled_lows.append((idx, price, "HL" if price > prev_price else "LL"))

    return {"highs": labeled_highs, "lows": labeled_lows}


def get_market_structure(df: pd.DataFrame, left: int = 5, right: int = 2) -> str:
    """
    Deteksi BOS dan CHoCH dari price action terbaru.

    Bullish BOS   : Sebelumnya uptrend (HH+HL), close terbaru break HH terakhir → tren lanjut
    Bullish CHoCH : Sebelumnya downtrend (LH+LL), close terbaru break LH terakhir → reversal bullish

    Bearish BOS   : Sebelumnya downtrend (LH+LL), close terbaru break LL terakhir → tren lanjut
    Bearish CHoCH : Sebelumnya uptrend (HH+HL), close terbaru break HL terakhir → reversal bearish
    """
    if len(df) < (left + right + 10):
        return NO_STRUCTURE

    swing_highs, swing_lows = _find_swings(df, left, right)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return NO_STRUCTURE

    classified = _classify_swings(swing_highs, swing_lows)
    labeled_highs = classified["highs"]
    labeled_lows  = classified["lows"]

    close_now = df["close"].iloc[-1]

    # Ambil 2 swing terakhir untuk analisis
    last_high_idx,  last_high_price,  last_high_label  = labeled_highs[-1]
    prev_high_idx,  prev_high_price,  prev_high_label  = labeled_highs[-2]
    last_low_idx,   last_low_price,   last_low_label   = labeled_lows[-1]
    prev_low_idx,   prev_low_price,   prev_low_label   = labeled_lows[-2]

    # ── Bullish BOS ──────────────────────────────────────────────
    # Konteks uptrend (HH+HL), harga break above swing high terakhir
    uptrend_context = last_high_label == "HH" and last_low_label == "HL"
    if uptrend_context and close_now > last_high_price:
        return BULLISH_BOS

    # ── Bullish CHoCH ────────────────────────────────────────────
    # Konteks downtrend (LH+LL), harga break above last LH → reversal mulai
    downtrend_context = last_high_label == "LH" and last_low_label == "LL"
    if downtrend_context and close_now > last_high_price:
        return BULLISH_CHOCH

    # ── Bearish BOS ──────────────────────────────────────────────
    # Konteks downtrend (LH+LL), harga break below swing low terakhir
    if downtrend_context and close_now < last_low_price:
        return BEARISH_BOS

    # ── Bearish CHoCH ────────────────────────────────────────────
    # Konteks uptrend (HH+HL), harga break below last HL → reversal mulai
    if uptrend_context and close_now < last_low_price:
        return BEARISH_CHOCH

    return NO_STRUCTURE


def is_bullish_structure(result: str) -> bool:
    return result in (BULLISH_BOS, BULLISH_CHOCH)


def is_bearish_structure(result: str) -> bool:
    return result in (BEARISH_BOS, BEARISH_CHOCH)


def structure_strength(result: str) -> str:
    """BOS lebih kuat dari CHoCH karena mengkonfirmasi tren yang sudah ada."""
    if result in (BULLISH_BOS, BEARISH_BOS):
        return "STRONG"
    if result in (BULLISH_CHOCH, BEARISH_CHOCH):
        return "MODERATE"
    return "NONE"


# ── Continuation setups untuk mid-session re-entry ───────────────

def has_ema_retest_m15(df_m15: pd.DataFrame, direction: str, bos_lookback: int = 20) -> bool:
    """
    EMA Retest M15:
    Setelah BOS terkonfirmasi dalam N candle terakhir,
    harga pullback ke EMA20 M15 dan saat ini berada di area tersebut.

    BUY  : ada BOS bullish dalam lookback bar → harga turun ke EMA20 M15 → berada di atasnya
    SELL : ada BOS bearish dalam lookback bar → harga naik ke EMA20 M15 → berada di bawahnya
    """
    if len(df_m15) < bos_lookback + 10:
        return False

    # Cari apakah ada BOS dalam N candle terakhir
    recent = df_m15.iloc[-(bos_lookback + 10):-1]
    bos_found = False
    for i in range(10, len(recent)):
        sub = recent.iloc[:i + 1]
        structure = get_market_structure(sub)
        if direction == "BUY" and structure == BULLISH_BOS:
            bos_found = True
            break
        if direction == "SELL" and structure == BEARISH_BOS:
            bos_found = True
            break

    if not bos_found:
        return False

    last = df_m15.iloc[-1]
    close = last["close"]
    low   = last["low"]
    high  = last["high"]
    ema20 = last["ema20"]
    atr   = last["atr"]
    tolerance = atr * 0.3

    if direction == "BUY":
        # Harga menyentuh/mendekati EMA20 dari atas
        touched = low <= ema20 + tolerance
        above   = close >= ema20 - tolerance
        return touched and above

    if direction == "SELL":
        # Harga menyentuh/mendekati EMA20 dari bawah
        touched = high >= ema20 - tolerance
        below   = close <= ema20 + tolerance
        return touched and below

    return False


def has_hlc_continuation(df_h1: pd.DataFrame, direction: str) -> bool:
    """
    Higher Low Continuation (HLC) — BUY:
    HL baru terkonfirmasi di H1: swing low terbaru > swing low sebelumnya.

    Lower High Continuation (LHC) — SELL:
    LH baru terkonfirmasi di H1: swing high terbaru < swing high sebelumnya.
    """
    swing_highs, swing_lows = _find_swings(df_h1, left=5, right=2)

    if direction == "BUY":
        if len(swing_lows) < 2:
            return False
        return swing_lows[-1][1] > swing_lows[-2][1]  # HL terkonfirmasi

    if direction == "SELL":
        if len(swing_highs) < 2:
            return False
        return swing_highs[-1][1] < swing_highs[-2][1]  # LH terkonfirmasi

    return False
