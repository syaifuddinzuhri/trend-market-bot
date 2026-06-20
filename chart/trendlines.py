"""
Deteksi swing points dan trendline untuk visualisasi.
"""
import pandas as pd
import numpy as np


def find_swing_points(df: pd.DataFrame, left: int = 5, right: int = 2) -> tuple[list, list]:
    """
    Return (swing_highs, swing_lows) sebagai list of (index, price, bar_index).
    """
    highs = df["high"].values
    lows  = df["low"].values
    n     = len(df)

    swing_highs = []
    swing_lows  = []

    for i in range(left, n - right):
        if highs[i] == max(highs[i - left: i + right + 1]):
            swing_highs.append((i, highs[i]))
        if lows[i] == min(lows[i - left: i + right + 1]):
            swing_lows.append((i, lows[i]))

    return swing_highs, swing_lows


def classify_swings(swing_highs: list, swing_lows: list):
    """Label HH/LH dan HL/LL."""
    labeled_highs = []
    for i, (idx, price) in enumerate(swing_highs):
        if i == 0:
            labeled_highs.append((idx, price, "HH"))
        else:
            prev = swing_highs[i - 1][1]
            labeled_highs.append((idx, price, "HH" if price > prev else "LH"))

    labeled_lows = []
    for i, (idx, price) in enumerate(swing_lows):
        if i == 0:
            labeled_lows.append((idx, price, "HL"))
        else:
            prev = swing_lows[i - 1][1]
            labeled_lows.append((idx, price, "HL" if price > prev else "LL"))

    return labeled_highs, labeled_lows


def build_trendlines(swing_highs: list, swing_lows: list, df: pd.DataFrame, max_lines: int = 3):
    """
    Bangun trendline dari swing points terakhir.
    Return list of dict: {x0, y0, x1, y1, color, label}
    """
    times = df["time"].tolist()
    lines = []

    # Trendline bearish: sambungkan 2-3 swing high terakhir
    sh = swing_highs[-max_lines:]
    if len(sh) >= 2:
        for i in range(len(sh) - 1):
            lines.append({
                "x0": times[sh[i][0]],
                "y0": sh[i][1],
                "x1": times[sh[i + 1][0]],
                "y1": sh[i + 1][1],
                "color": "#ef5350",
                "label": "Resistance TL",
                "dash": "dot",
            })

    # Trendline bullish: sambungkan 2-3 swing low terakhir
    sl = swing_lows[-max_lines:]
    if len(sl) >= 2:
        for i in range(len(sl) - 1):
            lines.append({
                "x0": times[sl[i][0]],
                "y0": sl[i][1],
                "x1": times[sl[i + 1][0]],
                "y1": sl[i + 1][1],
                "color": "#26a69a",
                "label": "Support TL",
                "dash": "dot",
            })

    return lines


def find_sr_levels(df: pd.DataFrame, swing_highs: list, swing_lows: list,
                   tolerance_pct: float = 0.002) -> list[dict]:
    """
    Cluster swing points yang berdekatan → S/R level horizontal.
    tolerance_pct: berapa % jarak dianggap sama level.
    """
    all_prices = [p for _, p, _ in swing_highs] + [p for _, p, _ in swing_lows]
    if not all_prices:
        return []

    all_prices.sort()
    levels = []
    used = [False] * len(all_prices)

    for i, price in enumerate(all_prices):
        if used[i]:
            continue
        cluster = [price]
        for j in range(i + 1, len(all_prices)):
            if abs(all_prices[j] - price) / price <= tolerance_pct:
                cluster.append(all_prices[j])
                used[j] = True
        level_price = np.mean(cluster)
        strength = len(cluster)
        levels.append({"price": level_price, "strength": strength})
        used[i] = True

    # Urutkan dari yang paling kuat
    levels.sort(key=lambda x: x["strength"], reverse=True)
    return levels[:8]  # ambil 8 level terkuat
