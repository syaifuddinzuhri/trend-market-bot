"""
Baca zona S/R dari rectangle yang di-draw di MT5.

Alur:
  1. ZoneExporter.mq5 (EA di MT5) baca semua rectangle → tulis ke
     %APPDATA%\MetaQuotes\Terminal\Common\Files\zones.csv setiap 5 detik
  2. Modul ini baca file CSV tersebut dan parse zona-nya
  3. signals.py pakai price_in_zone() untuk filter entry

Konvensi penamaan rectangle di MT5:
  - Nama/label mengandung "supply" / "resist" / "res" → SUPPLY (zona jual)
  - Nama/label mengandung "demand" / "support" / "sup" → DEMAND (zona beli)
  - Merah/oranye (default supply color) → SUPPLY
  - Hijau/biru (default demand color) → DEMAND
  - Tanpa label → NEUTRAL (valid untuk kedua arah)
"""

import os
import csv
from typing import Optional

# Path default ke MT5 Common Files (berlaku di semua terminal MT5)
_DEFAULT_PATH = os.path.join(
    os.environ.get("APPDATA", ""),
    "MetaQuotes", "Terminal", "Common", "Files", "zones.csv",
)

# Fallback: cari di folder alternatif kalau tidak ketemu
_FALLBACK_PATH = os.path.join(
    os.environ.get("USERPROFILE", ""),
    "AppData", "Roaming", "MetaQuotes", "Terminal", "Common", "Files", "zones.csv",
)

# Warna yang dianggap supply (merah/oranye) dan demand (hijau/biru)
# Format hex: #RRGGBB setelah konversi dari MT5 BGR
_SUPPLY_COLORS = {"#FF0000", "#FF3300", "#FF6600", "#FF4500", "#DC143C",
                  "#800000", "#8B0000", "#B22222", "#CD5C5C", "#FA8072"}
_DEMAND_COLORS = {"#00FF00", "#008000", "#006400", "#228B22", "#32CD32",
                  "#0000FF", "#0000CD", "#00008B", "#4169E1", "#1E90FF",
                  "#00CED1", "#20B2AA", "#008B8B"}


def _detect_zone_type(name: str, label: str, color_hex: str) -> str:
    """Tentukan tipe zona dari nama, label, dan warna rectangle."""
    text = (name + " " + label).upper()

    supply_kw = {"SUPPLY", "RESIST", "RES", "SR", "SELL", "OB_BEAR", "BEARISH"}
    demand_kw = {"DEMAND", "SUPPORT", "SUP", "SD", "BUY", "OB_BULL", "BULLISH"}

    for kw in supply_kw:
        if kw in text:
            return "SUPPLY"
    for kw in demand_kw:
        if kw in text:
            return "DEMAND"

    # Fallback: deteksi dari warna
    clr = color_hex.upper()
    if clr in {c.upper() for c in _SUPPLY_COLORS}:
        return "SUPPLY"
    if clr in {c.upper() for c in _DEMAND_COLORS}:
        return "DEMAND"

    return "NEUTRAL"


def load_zones(filepath: str = "") -> list[dict]:
    """
    Baca file CSV yang di-export ZoneExporter.mq5.
    Return list of dict: {name, high, low, label, zone_type, mid}
    List kosong jika file belum ada atau tidak ada zona.
    """
    path = filepath or _DEFAULT_PATH
    if not os.path.exists(path):
        path = _FALLBACK_PATH
    if not os.path.exists(path):
        return []

    zones = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    high  = float(row["price_high"])
                    low   = float(row["price_low"])
                    name  = row.get("name", "")
                    label = row.get("label", "")
                    color = row.get("color_hex", "")
                    zone_type = _detect_zone_type(name, label, color)
                    mid = (high + low) / 2
                    zones.append({
                        "name":      name,
                        "high":      high,
                        "low":       low,
                        "mid":       mid,
                        "label":     label,
                        "color":     color,
                        "zone_type": zone_type,
                    })
                except (ValueError, KeyError):
                    continue
    except Exception:
        pass

    return zones


def price_in_zone(
    zones: list[dict],
    price: float,
    direction: str,
    tolerance: float = 1.0,
) -> Optional[dict]:
    """
    Cek apakah harga sedang berada di dalam zona yang relevan.

    SELL → cari SUPPLY atau NEUTRAL zone
    BUY  → cari DEMAND atau NEUTRAL zone

    tolerance: pip buffer di luar zona yang masih dianggap "masuk"
    Return zona pertama yang cocok, atau None.
    """
    for z in zones:
        in_zone = (price >= z["low"] - tolerance) and (price <= z["high"] + tolerance)
        if not in_zone:
            continue
        if direction == "SELL" and z["zone_type"] in ("SUPPLY", "NEUTRAL"):
            return z
        if direction == "BUY" and z["zone_type"] in ("DEMAND", "NEUTRAL"):
            return z
    return None


def nearest_zones(zones: list[dict], price: float, n: int = 3) -> list[dict]:
    """
    Return N zona terdekat dari harga sekarang, diurutkan dari yang paling dekat.
    Berguna untuk tampilkan zona di analisa Telegram.
    """
    def _dist(z):
        return abs(z["mid"] - price)
    return sorted(zones, key=_dist)[:n]


def zones_summary(zones: list[dict], price: float, pip_size: float = 1.0) -> str:
    """
    Buat ringkasan zona terdekat untuk ditampilkan di Telegram.
    Contoh: 'Supply 4140–4145 (+27 pip) | Demand 4090–4095 (-18 pip)'
    """
    if not zones:
        return "Tidak ada zona S/R yang di-draw"

    parts = []
    for z in nearest_zones(zones, price, n=3):
        dist_pip = (z["mid"] - price) / pip_size
        sign = f"+{dist_pip:.0f}" if dist_pip > 0 else f"{dist_pip:.0f}"
        label = z["label"] or z["zone_type"]
        parts.append(f"{label} `{z['low']:.2f}`–`{z['high']:.2f}` ({sign} pip)")

    return " | ".join(parts)
