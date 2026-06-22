# TrendBot MT5 Indicators — Cara Install

## File yang tersedia

| File | Fungsi | Pasang di |
|------|--------|-----------|
| `TrendBot_EMA_Ribbon.mq5` | EMA 20/50/100/200 | H4 + H1 |
| `TrendBot_ADX_ATR.mq5` | ADX(14) + ATR(14) vs MA20 sub-window | H1 |
| `TrendBot_Structure.mq5` | Swing HH/HL/LH/LL + BOS/CHoCH label | M15 |
| `TrendBot_Dashboard.mq5` | Panel status semua filter + Entry/SL/TP | M15 |

---

## Langkah install

1. Buka MT5 → **File → Open Data Folder**
2. Masuk ke folder `MQL5 → Indicators`
3. Copy semua file `.mq5` ke sana
4. Di MT5: **Navigator panel → Indicators** → klik kanan → **Refresh**
5. Drag masing-masing indicator ke chart yang sesuai

---

## Setup chart yang disarankan

Buka **3 chart XAUUSD** secara bersamaan:

### Chart 1 — H4 (Trend)
- Pasang: `TrendBot_EMA_Ribbon`
- Fungsi: lihat trend utama (Close vs EMA200, EMA50 vs EMA200)

### Chart 2 — H1 (Momentum)
- Pasang: `TrendBot_EMA_Ribbon` + `TrendBot_ADX_ATR`
- Fungsi: cek pullback ke EMA20/50, ADX kekuatan, ATR volatilitas

### Chart 3 — M15 (Entry)
- Pasang: `TrendBot_Structure` + `TrendBot_Dashboard`
- Fungsi: lihat BOS/CHoCH, panel status filter, proyeksi Entry/SL/TP

---

## Parameter penting — sesuaikan dengan .env bot

| Parameter di indicator | Nilai default | Sesuaikan dengan .env |
|------------------------|--------------|----------------------|
| `ADX_MIN` | 25 | `ADX_MIN` |
| `ADX_SKIP` | 20 | `ADX_SKIP` |
| `ATR_SL_Mult` | 1.5 | `ATR_SL_MULTIPLIER` |
| `TP1_R` | 1.0 | `TP1_R` |
| `TP2_R` | 2.0 | `TP2_R` |
| `SwingLeft` | 5 | `SWING_LEFT` |
| `SwingRight` | 2 | `SWING_RIGHT` |

---

## Panel Dashboard — cara baca

```
━━ TrendBot Scanner ━━━━━━━━━━━━━━
Arah    : BUY
Status  : 🟢 SIAP ENTRY
─────────────────────────────────
[✓] Session (WIB 13:00-01:00)
[✓] Trend H4 (Close vs EMA200)  BULL
[✓] ADX H1 = 28.3 (min 25)
[✓] ATR H1 = 21.50 | MA=20.30
[✓] Pullback ke EMA20/50 H1
[✓] Structure M15: BOS↑
[✓] Candle M15:   Engulf↑
─────────────────────────────────
Entry  : 3285.50
SL     : 3271.30 (-14.20)
TP1    : 3299.70 (+14.20)
TP2    : 3313.90 (+28.40)
```

Saat status `🔥 HAMPIR` atau `🟢 SIAP ENTRY`, proyeksi harga langsung muncul
sehingga bisa langsung entry manual di akun lain dengan level yang sama.
