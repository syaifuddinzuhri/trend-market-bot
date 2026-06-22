"""
Deteksi Supply & Demand zone dari data M5.
Logika sama dengan TrendBot_SupplyDemand.mq5.
"""
import pandas as pd


def find_sd_zones(
    df: pd.DataFrame,
    base_bars_min: int = 1,
    base_bars_max: int = 6,
    impulse_body_ratio: float = 0.50,
    impulse_body_mult: float = 1.5,
    max_zones: int = 5,
    show_mitigated: bool = False,
) -> list[dict]:
    """
    Scan DataFrame OHLC untuk Supply & Demand zone.

    Return: list of dict:
      {type: 'demand'|'supply', top, bottom, mitigated, bar_index}
    """
    zones = []
    demand_count = 0
    supply_count = 0

    n = len(df)
    if n < base_bars_max + 3:
        return zones

    for i in range(base_bars_max + 2, n - 1):
        if demand_count >= max_zones and supply_count >= max_zones:
            break

        # ── Candle impulse ──────────────────────────────────────
        o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
        body_imp  = abs(c - o)
        range_imp = h - l
        if range_imp < 1e-6:
            continue

        bull_imp = c > o and body_imp / range_imp >= impulse_body_ratio
        bear_imp = c < o and body_imp / range_imp >= impulse_body_ratio
        if not bull_imp and not bear_imp:
            continue

        # ── Cari base sebelum impulse ───────────────────────────
        base_indices = []
        base_body_sum = 0.0

        for b in range(i - 1, max(0, i - base_bars_max - 1) - 1, -1):
            ob = df["open"].iloc[b]
            hb = df["high"].iloc[b]
            lb = df["low"].iloc[b]
            cb = df["close"].iloc[b]
            body_b  = abs(cb - ob)
            range_b = hb - lb
            if range_b < 1e-6:
                continue
            ratio_b = body_b / range_b
            if ratio_b <= 0.70:
                base_indices.append(b)
                base_body_sum += body_b
            else:
                if len(base_indices) >= base_bars_min:
                    break
                else:
                    base_indices = []
                    base_body_sum = 0.0

        if len(base_indices) < base_bars_min:
            continue

        avg_base_body = base_body_sum / len(base_indices) if base_indices else 1e-6
        if avg_base_body < 1e-6:
            avg_base_body = 0.03

        if body_imp < avg_base_body * impulse_body_mult:
            continue

        # ── Zona = range base ────────────────────────────────────
        base_highs = df["high"].iloc[base_indices]
        base_lows  = df["low"].iloc[base_indices]
        zone_top    = base_highs.max()
        zone_bottom = base_lows.min()

        if zone_top <= zone_bottom:
            continue

        is_demand = bull_imp

        if is_demand and demand_count >= max_zones:
            continue
        if not is_demand and supply_count >= max_zones:
            continue

        # ── Cek duplikat (overlap semua tipe) ───────────────────
        overlap = False
        for z in zones:
            ot = min(z["top"], zone_top)
            ob2 = max(z["bottom"], zone_bottom)
            if ot > ob2:
                overlap = True
                break
        if overlap:
            continue

        # ── Cek mitigation ──────────────────────────────────────
        mitigated = False
        for k in range(i + 1, n):
            if is_demand and df["low"].iloc[k] <= zone_bottom:
                mitigated = True
                break
            if not is_demand and df["high"].iloc[k] >= zone_top:
                mitigated = True
                break

        if mitigated and not show_mitigated:
            continue

        zones.append({
            "type":      "demand" if is_demand else "supply",
            "top":       zone_top,
            "bottom":    zone_bottom,
            "mitigated": mitigated,
            "bar_index": i,
        })

        if is_demand:
            demand_count += 1
        else:
            supply_count += 1

    return zones


def price_at_zone(zones: list[dict], current_price: float, direction: str, tolerance: float = 0.0) -> dict | None:
    """
    Cek apakah harga sedang berada di dalam atau menyentuh zona.
    SELL → harga menyentuh supply zone (current_price >= zone_bottom - tolerance)
    BUY  → harga menyentuh demand zone (current_price <= zone_top + tolerance)

    tolerance: buffer dalam harga (misal 0.5 untuk 5 pip gold)
    Return zona yang disentuh, atau None.
    """
    for z in zones:
        if z["mitigated"]:
            continue
        if direction == "SELL" and z["type"] == "supply":
            # Harga masuk dari bawah ke zona supply
            if z["bottom"] - tolerance <= current_price <= z["top"] + tolerance:
                return z
        elif direction == "BUY" and z["type"] == "demand":
            # Harga masuk dari atas ke zona demand
            if z["bottom"] - tolerance <= current_price <= z["top"] + tolerance:
                return z
    return None


def nearest_zone(zones: list[dict], current_price: float, direction: str) -> dict | None:
    """
    Ambil zona terdekat yang relevan untuk direction.
    SELL → supply zone di atas harga
    BUY  → demand zone di bawah harga
    """
    candidates = []
    for z in zones:
        if z["mitigated"]:
            continue
        if direction == "SELL" and z["type"] == "supply" and z["bottom"] > current_price:
            candidates.append(z)
        elif direction == "BUY" and z["type"] == "demand" and z["top"] < current_price:
            candidates.append(z)

    if not candidates:
        return None

    if direction == "SELL":
        return min(candidates, key=lambda z: z["bottom"])
    else:
        return max(candidates, key=lambda z: z["top"])
