"""
CLI untuk generate chart.

Contoh:
  python chart/run_chart.py
  python chart/run_chart.py --tf H1 --bars 300
  python chart/run_chart.py --tf H4 --bars 200 --no-trades
  python chart/run_chart.py --tf M15 --bars 150 --no-trendlines --no-bos
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import MetaTrader5 as mt5
import config
from chart.plotter import build_chart


TF_MAP = {
    "M15": mt5.TIMEFRAME_M15,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}


def main():
    parser = argparse.ArgumentParser(description="TrendBot Chart Generator")
    parser.add_argument("--symbol",        default=config.SYMBOL)
    parser.add_argument("--tf",            default="M15", choices=TF_MAP.keys())
    parser.add_argument("--bars",          type=int, default=200)
    parser.add_argument("--no-trades",     action="store_true")
    parser.add_argument("--no-trendlines", action="store_true")
    parser.add_argument("--no-sr",         action="store_true")
    parser.add_argument("--no-bos",        action="store_true")
    parser.add_argument("--no-browser",    action="store_true")
    args = parser.parse_args()

    print(f"\n[CHART] Connecting to MT5...")
    if not mt5.initialize():
        print(f"[CHART] MT5 initialize failed: {mt5.last_error()}")
        sys.exit(1)

    ok = mt5.login(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    if not ok:
        print(f"[CHART] MT5 login failed: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)

    # Set TF constants di config
    config.TF_H4  = mt5.TIMEFRAME_H4
    config.TF_H1  = mt5.TIMEFRAME_H1
    config.TF_M15 = mt5.TIMEFRAME_M15

    timeframe = TF_MAP[args.tf]

    try:
        path = build_chart(
            symbol=args.symbol,
            timeframe=timeframe,
            bars=args.bars,
            show_trades=not args.no_trades,
            show_trendlines=not args.no_trendlines,
            show_sr=not args.no_sr,
            show_bos=not args.no_bos,
            open_browser=not args.no_browser,
        )
        print(f"\n✅ Chart berhasil dibuat: {path}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
