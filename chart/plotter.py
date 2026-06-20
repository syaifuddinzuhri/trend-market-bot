"""
Chart interaktif TrendBot — Plotly HTML.

Panel:
  1. Candlestick + EMA Ribbon + Trendlines + S/R + BOS/CHoCH + Entry/Exit markers
  2. ADX (dengan threshold line)
  3. ATR vs ATR_MA

Output: chart/output/chart_<symbol>_<tf>.html
"""
import os
import sys
import sqlite3
from datetime import datetime, timezone, timedelta

import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from bot.indicators import add_emas, add_adx, add_atr
from bot.structure import (
    get_market_structure,
    BULLISH_BOS, BULLISH_CHOCH, BEARISH_BOS, BEARISH_CHOCH,
)
from chart.trendlines import (
    find_swing_points, classify_swings,
    build_trendlines, find_sr_levels,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ── Warna tema gelap ──────────────────────────────────────────────
C_BG        = "#0d1117"
C_PAPER     = "#161b22"
C_GRID      = "#21262d"
C_TEXT      = "#e6edf3"
C_BULL      = "#26a69a"
C_BEAR      = "#ef5350"
C_EMA20     = "#ffeb3b"
C_EMA50     = "#ff9800"
C_EMA100    = "#4caf50"
C_EMA200    = "#2196f3"
C_ADX       = "#ce93d8"
C_ATR       = "#80cbc4"
C_ATR_MA    = "#ff8a65"
C_SR_STRONG = "rgba(255,193,7,0.25)"
C_SR_WEAK   = "rgba(255,193,7,0.10)"


def _tf_label(tf) -> str:
    mapping = {
        mt5.TIMEFRAME_M15: "M15",
        mt5.TIMEFRAME_H1:  "H1",
        mt5.TIMEFRAME_H4:  "H4",
        mt5.TIMEFRAME_D1:  "D1",
    }
    return mapping.get(tf, str(tf))


def _fetch_df(symbol: str, timeframe, bars: int = 300) -> pd.DataFrame | None:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = add_emas(df)
    df = add_adx(df, config.ADX_PERIOD)
    df = add_atr(df, config.ATR_PERIOD, config.ATR_MA_PERIOD)
    return df.reset_index(drop=True)


def _load_trades(symbol: str) -> pd.DataFrame:
    """Load trade history dari SQLite."""
    if not os.path.exists(config.LOG_DB):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(config.LOG_DB)
        df = pd.read_sql_query(
            "SELECT * FROM trades WHERE symbol=? ORDER BY timestamp ASC",
            conn, params=(symbol,)
        )
        conn.close()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    except Exception:
        return pd.DataFrame()


def _detect_bos_choch_markers(df: pd.DataFrame, lookback: int = 5) -> list[dict]:
    """Scan setiap bar dan tandai BOS/CHoCH."""
    markers = []
    for i in range(lookback * 2 + 10, len(df)):
        sub = df.iloc[:i + 1]
        result = get_market_structure(sub, left=lookback, right=2)
        if result == NO_RESULT:
            continue
        # Hanya catat jika berbeda dari marker sebelumnya
        if markers and markers[-1]["label"] == result:
            continue
        price = df.iloc[i]["high"] if "BULLISH" in result else df.iloc[i]["low"]
        color = C_BULL if "BULLISH" in result else C_BEAR
        symbol_marker = "triangle-up" if "BULLISH" in result else "triangle-down"
        markers.append({
            "time":   df.iloc[i]["time"],
            "price":  price,
            "label":  result,
            "color":  color,
            "symbol": symbol_marker,
        })
    return markers


# Sentinel untuk skip marker yang sama berurutan
NO_RESULT = "NO_STRUCTURE"


def build_chart(
    symbol: str = None,
    timeframe=None,
    bars: int = 200,
    show_trades: bool = True,
    show_trendlines: bool = True,
    show_sr: bool = True,
    show_bos: bool = True,
    open_browser: bool = True,
) -> str:
    """
    Bangun chart interaktif dan simpan ke HTML.
    Returns path file HTML.
    """
    symbol    = symbol or config.SYMBOL
    timeframe = timeframe or config.TF_M15 or mt5.TIMEFRAME_M15
    tf_label  = _tf_label(timeframe)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"[CHART] Fetching {symbol} {tf_label} ({bars} bars)...")
    df = _fetch_df(symbol, timeframe, bars)
    if df is None:
        raise RuntimeError(f"Tidak ada data untuk {symbol} {tf_label}")

    # ── Swing points ─────────────────────────────────────────────
    swing_highs_raw, swing_lows_raw = find_swing_points(df, left=5, right=2)
    labeled_highs, labeled_lows = classify_swings(swing_highs_raw, swing_lows_raw)
    trendlines = build_trendlines(swing_highs_raw, swing_lows_raw, df) if show_trendlines else []
    sr_levels  = find_sr_levels(df, labeled_highs, labeled_lows) if show_sr else []

    # ── Trade markers dari log ────────────────────────────────────
    trades_df = _load_trades(symbol) if show_trades else pd.DataFrame()

    # ── BOS / CHoCH scan (ringan — hanya 30 bar terakhir) ────────
    bos_markers = []
    if show_bos:
        print("[CHART] Scanning BOS/CHoCH markers...")
        bos_markers = _detect_bos_choch_markers(df.tail(80).reset_index(drop=True))

    # ── Layout: 3 panel ─────────────────────────────────────────
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.65, 0.18, 0.17],
        subplot_titles=[
            f"{symbol} {tf_label} — EMA Ribbon + Structure",
            "ADX (14)",
            "ATR (14) vs ATR MA (20)",
        ],
    )

    # ── 1. Candlestick ───────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=df["time"],
        open=df["open"], high=df["high"],
        low=df["low"],   close=df["close"],
        name="OHLC",
        increasing_line_color=C_BULL,
        decreasing_line_color=C_BEAR,
        increasing_fillcolor=C_BULL,
        decreasing_fillcolor=C_BEAR,
        line=dict(width=1),
    ), row=1, col=1)

    # ── 2. EMA Ribbon ────────────────────────────────────────────
    ema_cfg = [
        ("ema20",  C_EMA20,  "EMA 20",  1.2),
        ("ema50",  C_EMA50,  "EMA 50",  1.5),
        ("ema100", C_EMA100, "EMA 100", 1.5),
        ("ema200", C_EMA200, "EMA 200", 2.0),
    ]
    for col_name, color, label, width in ema_cfg:
        fig.add_trace(go.Scatter(
            x=df["time"], y=df[col_name],
            name=label, line=dict(color=color, width=width),
            hovertemplate=f"{label}: %{{y:.2f}}<extra></extra>",
        ), row=1, col=1)

    # ── 3. S/R Levels ────────────────────────────────────────────
    for lvl in sr_levels:
        opacity = 0.5 if lvl["strength"] >= 3 else 0.25
        fig.add_hline(
            y=lvl["price"],
            line=dict(color=f"rgba(255,193,7,{opacity})", width=1, dash="dash"),
            row=1, col=1,
            annotation_text=f"SR {lvl['price']:.2f} (×{lvl['strength']})",
            annotation_font=dict(size=9, color="#ffc107"),
            annotation_position="right",
        )

    # ── 4. Trendlines ────────────────────────────────────────────
    for tl in trendlines:
        fig.add_shape(
            type="line",
            x0=tl["x0"], y0=tl["y0"],
            x1=tl["x1"], y1=tl["y1"],
            line=dict(color=tl["color"], width=1.5, dash=tl["dash"]),
            row=1, col=1,
        )

    # ── 5. Swing High/Low labels ─────────────────────────────────
    for idx, price, label in labeled_highs[-12:]:
        color = C_BEAR if label == "LH" else "#ff8a65"
        fig.add_trace(go.Scatter(
            x=[df.iloc[idx]["time"]],
            y=[price + price * 0.0005],
            mode="text+markers",
            text=[label],
            textposition="top center",
            textfont=dict(size=9, color=color),
            marker=dict(symbol="circle", size=5, color=color),
            showlegend=False,
            hovertemplate=f"{label}: {price:.2f}<extra></extra>",
        ), row=1, col=1)

    for idx, price, label in labeled_lows[-12:]:
        color = C_BULL if label == "HL" else "#ff5252"
        fig.add_trace(go.Scatter(
            x=[df.iloc[idx]["time"]],
            y=[price - price * 0.0005],
            mode="text+markers",
            text=[label],
            textposition="bottom center",
            textfont=dict(size=9, color=color),
            marker=dict(symbol="circle", size=5, color=color),
            showlegend=False,
            hovertemplate=f"{label}: {price:.2f}<extra></extra>",
        ), row=1, col=1)

    # ── 6. BOS / CHoCH markers ───────────────────────────────────
    for m in bos_markers:
        short = {"BULLISH_BOS": "BOS↑", "BEARISH_BOS": "BOS↓",
                 "BULLISH_CHOCH": "CHoCH↑", "BEARISH_CHOCH": "CHoCH↓"}.get(m["label"], m["label"])
        offset = m["price"] * 0.001
        ypos = m["price"] + offset if "BULLISH" in m["label"] else m["price"] - offset
        fig.add_trace(go.Scatter(
            x=[m["time"]], y=[ypos],
            mode="text+markers",
            text=[short],
            textposition="top center" if "BULLISH" in m["label"] else "bottom center",
            textfont=dict(size=10, color=m["color"], family="monospace"),
            marker=dict(symbol=m["symbol"], size=10, color=m["color"]),
            showlegend=False,
            name=m["label"],
            hovertemplate=f"{m['label']}<br>Price: {m['price']:.2f}<extra></extra>",
        ), row=1, col=1)

    # ── 7. Trade entry / exit markers dari log ───────────────────
    if not trades_df.empty:
        # Entry BUY
        buy_entries = trades_df[
            (trades_df["direction"] == "BUY") &
            (trades_df["result"].isin(["OPEN", "PRIMARY", "EMA_RETEST", "HLC"]))
        ]
        if not buy_entries.empty:
            fig.add_trace(go.Scatter(
                x=buy_entries["timestamp"],
                y=buy_entries["entry_price"].astype(float),
                mode="markers",
                name="BUY Entry",
                marker=dict(symbol="triangle-up", size=14, color=C_BULL,
                            line=dict(color="white", width=1)),
                hovertemplate="BUY Entry<br>%{x}<br>Price: %{y:.2f}<extra></extra>",
            ), row=1, col=1)

        # Entry SELL
        sell_entries = trades_df[
            (trades_df["direction"] == "SELL") &
            (trades_df["result"].isin(["OPEN", "PRIMARY", "EMA_RETEST", "HLC"]))
        ]
        if not sell_entries.empty:
            fig.add_trace(go.Scatter(
                x=sell_entries["timestamp"],
                y=sell_entries["entry_price"].astype(float),
                mode="markers",
                name="SELL Entry",
                marker=dict(symbol="triangle-down", size=14, color=C_BEAR,
                            line=dict(color="white", width=1)),
                hovertemplate="SELL Entry<br>%{x}<br>Price: %{y:.2f}<extra></extra>",
            ), row=1, col=1)

        # TP hits
        tp_trades = trades_df[trades_df["result"].isin(["TP1", "TP2", "TRAIL_EXIT", "CLOSED"])]
        if not tp_trades.empty:
            fig.add_trace(go.Scatter(
                x=tp_trades["timestamp"],
                y=tp_trades["take_profit"].astype(float, errors="ignore"),
                mode="markers",
                name="TP",
                marker=dict(symbol="star", size=12, color="#ffd700",
                            line=dict(color="white", width=0.5)),
                hovertemplate="TP Hit<br>%{x}<br>%{y:.2f}<extra></extra>",
            ), row=1, col=1)

        # SL hits
        sl_trades = trades_df[trades_df["result"] == "SL"]
        if not sl_trades.empty:
            fig.add_trace(go.Scatter(
                x=sl_trades["timestamp"],
                y=sl_trades["stop_loss"].astype(float, errors="ignore"),
                mode="markers",
                name="SL",
                marker=dict(symbol="x", size=12, color="#ff1744",
                            line=dict(color="white", width=1)),
                hovertemplate="SL Hit<br>%{x}<br>%{y:.2f}<extra></extra>",
            ), row=1, col=1)

        # SL lines (entry → SL)
        for _, row_t in trades_df[trades_df["result"].isin(["OPEN","PRIMARY"])].iterrows():
            try:
                ep = float(row_t["entry_price"])
                sl = float(row_t["stop_loss"])
                tp = float(row_t["take_profit"])
                ts = row_t["timestamp"]
                # SL line (merah transparan)
                fig.add_shape(type="line",
                    x0=ts, y0=ep, x1=ts + pd.Timedelta(hours=4), y1=sl,
                    line=dict(color="rgba(239,83,80,0.4)", width=1, dash="dot"),
                    row=1, col=1)
                # TP line (hijau transparan)
                fig.add_shape(type="line",
                    x0=ts, y0=ep, x1=ts + pd.Timedelta(hours=4), y1=tp,
                    line=dict(color="rgba(38,166,154,0.4)", width=1, dash="dot"),
                    row=1, col=1)
            except Exception:
                pass

    # ── 8. ADX panel ─────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=df["time"], y=df["adx"],
        name="ADX", line=dict(color=C_ADX, width=1.5),
        hovertemplate="ADX: %{y:.1f}<extra></extra>",
    ), row=2, col=1)

    fig.add_hline(y=config.ADX_MIN, line=dict(color="#ffc107", width=1, dash="dash"),
                  annotation_text=f"Min {config.ADX_MIN}", row=2, col=1,
                  annotation_font=dict(size=9, color="#ffc107"))
    fig.add_hline(y=20, line=dict(color="#ef5350", width=1, dash="dot"),
                  annotation_text="Skip 20", row=2, col=1,
                  annotation_font=dict(size=9, color="#ef5350"))
    fig.add_hline(y=40, line=dict(color="#ce93d8", width=0.8, dash="dot"),
                  annotation_text="Strong 40", row=2, col=1,
                  annotation_font=dict(size=9, color="#ce93d8"))

    # ── 9. ATR panel ─────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=df["time"], y=df["atr"],
        name="ATR 14", line=dict(color=C_ATR, width=1.5),
        hovertemplate="ATR: %{y:.4f}<extra></extra>",
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=df["time"], y=df["atr_ma"],
        name="ATR MA 20", line=dict(color=C_ATR_MA, width=1.5, dash="dash"),
        hovertemplate="ATR MA: %{y:.4f}<extra></extra>",
    ), row=3, col=1)

    # Fill ATR > ATR_MA (zona entry diizinkan)
    fig.add_trace(go.Scatter(
        x=pd.concat([df["time"], df["time"][::-1]]),
        y=pd.concat([df["atr"], df["atr_ma"][::-1]]),
        fill="toself",
        fillcolor="rgba(38,166,154,0.1)",
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=False,
        hoverinfo="skip",
    ), row=3, col=1)

    # ── Layout ───────────────────────────────────────────────────
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    fig.update_layout(
        title=dict(
            text=f"TrendBot — {symbol} {tf_label}  |  {now_str}",
            font=dict(size=16, color=C_TEXT),
            x=0.01,
        ),
        paper_bgcolor=C_BG,
        plot_bgcolor=C_PAPER,
        font=dict(color=C_TEXT, size=11),
        xaxis_rangeslider_visible=False,
        legend=dict(
            bgcolor="rgba(22,27,34,0.8)",
            bordercolor="#30363d",
            borderwidth=1,
            font=dict(size=11),
            orientation="h",
            y=1.02,
            x=0,
        ),
        hovermode="x unified",
        height=900,
        margin=dict(l=60, r=100, t=60, b=40),
    )

    # Grid semua panel
    for row in [1, 2, 3]:
        fig.update_xaxes(
            gridcolor=C_GRID, gridwidth=0.5,
            zerolinecolor=C_GRID,
            showspikes=True, spikecolor="#555", spikethickness=1,
            row=row, col=1,
        )
        fig.update_yaxes(
            gridcolor=C_GRID, gridwidth=0.5,
            zerolinecolor=C_GRID,
            showspikes=True, spikecolor="#555", spikethickness=1,
            row=row, col=1,
        )

    # ── Simpan HTML ──────────────────────────────────────────────
    filename = f"chart_{symbol}_{tf_label}.html"
    output_path = os.path.join(OUTPUT_DIR, filename)
    fig.write_html(
        output_path,
        include_plotlyjs="cdn",
        config={
            "scrollZoom": True,
            "displayModeBar": True,
            "modeBarButtonsToAdd": ["drawline", "drawopenpath", "eraseshape"],
            "modeBarButtonsToRemove": ["toImage"],
        },
    )

    print(f"[CHART] Saved: {output_path}")

    if open_browser:
        import webbrowser
        webbrowser.open(f"file:///{os.path.abspath(output_path)}")

    return output_path
