"""
Dashboard monitoring — berjalan di browser http://localhost:5000

Menampilkan:
  - Status bot & filter (session, news, trend)
  - Posisi terbuka + unrealized PnL
  - Trade history hari ini
  - Equity curve (dari logs/trades.db)
  - Upcoming news events

Jalankan: python dashboard/app.py
Butuh: pip install flask (sudah ada di requirements.txt)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import sqlite3
from datetime import datetime, date, timezone, timedelta

from flask import Flask, jsonify, render_template_string
import MetaTrader5 as mt5

import config
from bot.session import is_trading_session
from bot.news_filter import is_news_lock
from bot.calendar import get_upcoming_events, refresh as calendar_refresh

app = Flask(__name__)
WIB = timezone(timedelta(hours=7))

_MT5_READY = False


def _init_mt5():
    global _MT5_READY
    if not _MT5_READY:
        if mt5.initialize():
            ok = mt5.login(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
            _MT5_READY = ok


def _get_account():
    _init_mt5()
    info = mt5.account_info()
    if info is None:
        return {}
    currency = config.ACCOUNT_CURRENCY
    return {
        "login":    info.login,
        "balance":  f"{info.balance:,.0f}" if currency == "IDR" else f"{info.balance:,.2f}",
        "equity":   f"{info.equity:,.0f}"  if currency == "IDR" else f"{info.equity:,.2f}",
        "margin":   f"{info.margin:,.0f}"  if currency == "IDR" else f"{info.margin:,.2f}",
        "currency": currency,
        "server":   info.server,
    }


def _get_positions():
    _init_mt5()
    positions = mt5.positions_get(symbol=config.SYMBOL) or []
    result = []
    for p in positions:
        if p.magic != config.MAGIC_NUMBER:
            continue
        direction = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
        result.append({
            "ticket":    p.ticket,
            "direction": direction,
            "lot":       p.volume,
            "entry":     p.price_open,
            "sl":        p.sl,
            "tp":        p.tp,
            "pnl":       round(p.profit, 2),
            "open_time": datetime.fromtimestamp(p.time).strftime("%H:%M:%S"),
        })
    return result


def _get_today_trades():
    if not os.path.exists(config.LOG_DB):
        return []
    try:
        conn = sqlite3.connect(config.LOG_DB)
        today = date.today().strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT timestamp, direction, entry_price, stop_loss, take_profit, lot_size, result, pnl "
            "FROM trades WHERE timestamp LIKE ? ORDER BY timestamp DESC LIMIT 50",
            (f"{today}%",)
        ).fetchall()
        conn.close()
        return [dict(zip(["time","dir","entry","sl","tp","lot","result","pnl"], r)) for r in rows]
    except Exception:
        return []


def _get_equity_curve():
    if not os.path.exists(config.LOG_DB):
        return [], []
    try:
        conn = sqlite3.connect(config.LOG_DB)
        rows = conn.execute(
            "SELECT timestamp, pnl FROM trades WHERE result IN ('SL','TP1','TP2','TRAIL_EXIT','CLOSED') "
            "ORDER BY timestamp ASC LIMIT 200"
        ).fetchall()
        conn.close()
        labels, values, cum = [], [], 0.0
        for ts, pnl in rows:
            try:
                cum += float(pnl or 0)
                labels.append(ts[:10])
                values.append(round(cum, 2))
            except Exception:
                pass
        return labels, values
    except Exception:
        return [], []


HTML = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="10">
<title>TrendBot Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; }
header { background: #161b22; padding: 16px 24px; border-bottom: 1px solid #30363d; display: flex; align-items: center; gap: 12px; }
header h1 { font-size: 18px; }
.badge { padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; }
.green { background: #1a4731; color: #3fb950; }
.red   { background: #4d1f1f; color: #f85149; }
.gray  { background: #21262d; color: #8b949e; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; padding: 20px 24px; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px 16px; }
.card .label { font-size: 11px; color: #8b949e; margin-bottom: 4px; }
.card .value { font-size: 20px; font-weight: bold; }
section { padding: 0 24px 20px; }
section h2 { font-size: 14px; color: #8b949e; margin-bottom: 10px; border-bottom: 1px solid #30363d; padding-bottom: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { color: #8b949e; text-align: left; padding: 6px 8px; border-bottom: 1px solid #21262d; }
td { padding: 6px 8px; border-bottom: 1px solid #21262d; }
.buy { color: #3fb950; } .sell { color: #f85149; }
canvas { border-radius: 8px; background: #161b22; border: 1px solid #30363d; }
.news-item { background: #21262d; border-radius: 6px; padding: 8px 12px; margin: 4px 0; font-size: 12px; }
.news-item .time { color: #f0883e; font-weight: bold; }
.filters { display: flex; gap: 10px; padding: 0 24px 16px; flex-wrap: wrap; }
</style>
</head>
<body>
<header>
  <span>📈</span>
  <h1>TrendBot Dashboard</h1>
  <span style="color:#8b949e;font-size:12px;margin-left:8px">XAUUSD · Auto-refresh 10s</span>
</header>

<div class="grid" id="account-cards">
  <div class="card"><div class="label">Balance</div><div class="value" id="balance">—</div></div>
  <div class="card"><div class="label">Equity</div><div class="value" id="equity-val">—</div></div>
  <div class="card"><div class="label">Margin</div><div class="value" id="margin">—</div></div>
  <div class="card"><div class="label">Open Trades</div><div class="value" id="open-count">—</div></div>
  <div class="card"><div class="label">Server</div><div class="value" style="font-size:13px" id="server">—</div></div>
</div>

<div class="filters" id="filters"></div>

<section>
  <h2>Equity Curve (Cumulative PnL)</h2>
  <canvas id="eq-chart" height="120"></canvas>
</section>

<section>
  <h2>Posisi Terbuka</h2>
  <table>
    <tr><th>Ticket</th><th>Dir</th><th>Lot</th><th>Entry</th><th>SL</th><th>TP</th><th>PnL</th><th>Waktu</th></tr>
    <tbody id="positions"></tbody>
  </table>
</section>

<section>
  <h2>Trade Hari Ini</h2>
  <table>
    <tr><th>Waktu</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>Lot</th><th>Result</th><th>PnL</th></tr>
    <tbody id="today-trades"></tbody>
  </table>
</section>

<section>
  <h2>Upcoming News (±30 menit)</h2>
  <div id="news-list"><span style="color:#8b949e">Tidak ada event dalam waktu dekat.</span></div>
</section>

<script>
let eqChart = null;

async function load() {
  const d = await fetch('/api/data').then(r => r.json());

  // Account
  document.getElementById('balance').textContent = d.account.balance + ' ' + d.account.currency;
  document.getElementById('equity-val').textContent = d.account.equity + ' ' + d.account.currency;
  document.getElementById('margin').textContent = d.account.margin + ' ' + d.account.currency;
  document.getElementById('open-count').textContent = d.positions.length;
  document.getElementById('server').textContent = d.account.server || '—';

  // Filters
  const fDiv = document.getElementById('filters');
  fDiv.innerHTML = '';
  const badges = [
    ['Session', d.filters.session ? 'ON' : 'OFF', d.filters.session ? 'green' : 'red'],
    ['News', d.filters.news ? 'LOCK' : 'OK', d.filters.news ? 'red' : 'green'],
  ];
  badges.forEach(([label, val, cls]) => {
    fDiv.innerHTML += '<span class="badge ' + cls + '">' + label + ': ' + val + '</span>';
  });

  // Positions
  const ptbody = document.getElementById('positions');
  ptbody.innerHTML = d.positions.length ? d.positions.map(p => `
    <tr>
      <td>${p.ticket}</td>
      <td class="${p.direction.toLowerCase()}">${p.direction}</td>
      <td>${p.lot}</td><td>${p.entry}</td><td>${p.sl}</td><td>${p.tp}</td>
      <td style="color:${p.pnl >= 0 ? '#3fb950' : '#f85149'}">${p.pnl >= 0 ? '+' : ''}${p.pnl}</td>
      <td>${p.open_time}</td>
    </tr>`).join('') : '<tr><td colspan="8" style="color:#8b949e">Tidak ada posisi terbuka.</td></tr>';

  // Today trades
  const ttbody = document.getElementById('today-trades');
  ttbody.innerHTML = d.today_trades.length ? d.today_trades.map(t => `
    <tr>
      <td>${t.time}</td>
      <td class="${(t.dir||'').toLowerCase()}">${t.dir}</td>
      <td>${t.entry}</td><td>${t.sl}</td><td>${t.tp}</td><td>${t.lot}</td>
      <td>${t.result}</td>
      <td style="color:${parseFloat(t.pnl||0) >= 0 ? '#3fb950' : '#f85149'}">${t.pnl || '—'}</td>
    </tr>`).join('') : '<tr><td colspan="8" style="color:#8b949e">Belum ada trade hari ini.</td></tr>';

  // Equity chart
  const ctx = document.getElementById('eq-chart').getContext('2d');
  if (eqChart) eqChart.destroy();
  eqChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: d.equity_labels,
      datasets: [{ label: 'Equity (cumulative PnL)', data: d.equity_values,
        borderColor: '#1f6feb', backgroundColor: 'rgba(31,111,235,0.1)',
        fill: true, tension: 0.3, pointRadius: 2 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#e6edf3', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: '#8b949e', maxTicksLimit: 8 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } }
      }
    }
  });

  // News
  const nDiv = document.getElementById('news-list');
  nDiv.innerHTML = d.news.length
    ? d.news.map(e => `<div class="news-item"><span class="time">${e.minutes_away > 0 ? '+' : ''}${e.minutes_away}m</span> — ${e.title} <span style="color:#8b949e">(${e.datetime_str})</span></div>`).join('')
    : '<span style="color:#8b949e">Tidak ada event dalam waktu dekat.</span>';
}

load();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/data")
def api_data():
    calendar_refresh()
    eq_labels, eq_values = _get_equity_curve()
    return jsonify({
        "account":      _get_account(),
        "positions":    _get_positions(),
        "today_trades": _get_today_trades(),
        "equity_labels": eq_labels,
        "equity_values": eq_values,
        "filters": {
            "session": is_trading_session(),
            "news":    is_news_lock(),
        },
        "news": get_upcoming_events(60),
    })


if __name__ == "__main__":
    print("[DASH] Dashboard berjalan di http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
