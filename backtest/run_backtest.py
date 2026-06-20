"""
Jalankan backtest:

  python backtest/run_backtest.py
  python backtest/run_backtest.py --from 2024-01-01 --to 2024-12-31
  python backtest/run_backtest.py --from 2024-06-01 --to 2024-06-30 --balance 15000000
"""
import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from backtest.engine import run
from backtest.report import save_csv, save_html
import config


def parse_args():
    parser = argparse.ArgumentParser(description="TrendBot Backtest")
    parser.add_argument("--from", dest="date_from", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--to",   dest="date_to",   default="2024-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--symbol",  default=config.SYMBOL)
    parser.add_argument("--balance", type=float, default=10_000_000, help="Initial balance (IDR)")
    return parser.parse_args()


def main():
    args = parse_args()
    date_from = datetime.strptime(args.date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    date_to   = datetime.strptime(args.date_to,   "%Y-%m-%d").replace(tzinfo=timezone.utc)

    result = run(
        symbol=args.symbol,
        date_from=date_from,
        date_to=date_to,
        initial_balance=args.balance,
    )

    summary = result.summary()

    print("\n" + "=" * 50)
    print("  BACKTEST RESULT")
    print("=" * 50)
    for k, v in summary.items():
        print(f"  {k:<22} : {v}")
    print("=" * 50)

    save_csv(result.trades)
    save_html(result.trades, summary)
    print("\n✅ Buka logs/backtest_report.html di browser untuk detail lengkap.")


if __name__ == "__main__":
    main()
