"""
Backtest report generator — output HTML + CSV.
"""
import os
import csv
from datetime import datetime


def save_csv(trades: list[dict], path: str = "logs/backtest_trades.csv"):
    if not trades:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=trades[0].keys())
        writer.writeheader()
        writer.writerows(trades)
    print(f"[RPT] CSV saved: {path}")


def save_html(trades: list[dict], summary: dict, path: str = "logs/backtest_report.html"):
    if not trades:
        print("[RPT] No trades to report.")
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Equity curve data
    equity = 0.0
    equity_points = []
    for t in trades:
        equity += t["pnl_r"]
        equity_points.append(round(equity, 3))

    labels = [t["time"][:10] for t in trades]
    colors = ["#26a69a" if t["pnl_r"] > 0 else "#ef5350" for t in trades]

    trade_rows = ""
    for t in trades:
        color = "#e8f5e9" if t["pnl_r"] > 0 else "#ffebee"
        trade_rows += f"""
        <tr style="background:{color}">
            <td>{t['time'][:16]}</td>
            <td>{t['direction']}</td>
            <td>{t['pattern']}</td>
            <td>{t['structure']}</td>
            <td>{t['entry']}</td>
            <td>{t['sl']}</td>
            <td>{t['tp1']}</td>
            <td>{t['tp2']}</td>
            <td>{t['exit_price']}</td>
            <td>{t['exit_reason']}</td>
            <td><b>{"+" if t['pnl_r'] > 0 else ""}{t['pnl_r']}R</b></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<title>TrendBot Backtest Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
  h1 {{ color: #333; }}
  .summary {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0; }}
  .card {{ background: #fff; border-radius: 8px; padding: 16px 24px; box-shadow: 0 1px 4px #ccc; min-width: 140px; }}
  .card .label {{ font-size: 12px; color: #888; }}
  .card .value {{ font-size: 22px; font-weight: bold; color: #333; }}
  .card.green .value {{ color: #26a69a; }}
  .card.red .value {{ color: #ef5350; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px #ccc; }}
  th {{ background: #37474f; color: #fff; padding: 10px; text-align: left; font-size: 13px; }}
  td {{ padding: 8px 10px; font-size: 12px; border-bottom: 1px solid #eee; }}
  canvas {{ background: #fff; border-radius: 8px; padding: 12px; box-shadow: 0 1px 4px #ccc; }}
</style>
</head>
<body>
<h1>📊 TrendBot Backtest Report</h1>
<p style="color:#888">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")} | Symbol: XAUUSD</p>

<div class="summary">
  <div class="card"><div class="label">Total Trades</div><div class="value">{summary.get('total_trades',0)}</div></div>
  <div class="card green"><div class="label">Win Rate</div><div class="value">{summary.get('win_rate',0)}%</div></div>
  <div class="card green"><div class="label">Total R</div><div class="value">{summary.get('total_r',0)}R</div></div>
  <div class="card green"><div class="label">Profit Factor</div><div class="value">{summary.get('profit_factor',0)}</div></div>
  <div class="card red"><div class="label">Max DD</div><div class="value">{summary.get('max_drawdown_r',0)}R</div></div>
  <div class="card"><div class="label">Expectancy</div><div class="value">{summary.get('expectancy_r',0)}R</div></div>
  <div class="card green"><div class="label">Avg Win</div><div class="value">{summary.get('avg_win_r',0)}R</div></div>
  <div class="card red"><div class="label">Avg Loss</div><div class="value">{summary.get('avg_loss_r',0)}R</div></div>
</div>

<canvas id="equity" width="1200" height="300"></canvas>
<br><br>

<table>
  <tr>
    <th>Time</th><th>Dir</th><th>Pattern</th><th>Structure</th>
    <th>Entry</th><th>SL</th><th>TP1</th><th>TP2</th>
    <th>Exit</th><th>Reason</th><th>PnL</th>
  </tr>
  {trade_rows}
</table>

<script>
new Chart(document.getElementById('equity'), {{
  type: 'line',
  data: {{
    labels: {labels},
    datasets: [{{
      label: 'Equity Curve (R)',
      data: {equity_points},
      borderColor: '#1976d2',
      backgroundColor: 'rgba(25,118,210,0.1)',
      fill: true,
      tension: 0.3,
      pointRadius: 3,
    }}]
  }},
  options: {{
    responsive: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ grid: {{ color: '#eee' }} }} }}
  }}
}});
</script>
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[RPT] HTML report saved: {path}")
