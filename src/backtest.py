"""Backtest runner: loads data, runs the strategy, writes results artifacts.

Usage:
    python3 src/backtest.py [--data data/gbpjpy_daily_2026.csv] [--out results/]

Writes:
    results/summary.json   - parameters + performance metrics
    results/trades.csv     - one row per closed trade
    results/equity.csv     - daily marked-to-market equity
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy import load_bars, run_backtest, compute_metrics, DEFAULT_PARAMS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/gbpjpy_daily_2026.csv")
    ap.add_argument("--out", default="results")
    ap.add_argument("--params", default=None, help="JSON file or inline JSON of param overrides")
    ap.add_argument("--start-equity", type=float, default=1_000_000.0)
    ap.add_argument("--eval-start", default=None,
                    help="metrics computed from this date (warmup data before it)")
    args = ap.parse_args()

    params = {}
    if args.params:
        if os.path.exists(args.params):
            with open(args.params) as f:
                params = json.load(f)
        else:
            params = json.loads(args.params)

    bars = load_bars(args.data)
    result = run_backtest(bars, params, start_equity=args.start_equity,
                          start_date=args.eval_start)
    metrics = compute_metrics(result, eval_start=args.eval_start)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump({"data_file": args.data, "bars": len(bars),
                   "first_date": bars[0]["date"], "last_date": bars[-1]["date"],
                   "eval_start": args.eval_start,
                   "params": result["params"], "metrics": metrics}, f, indent=2)

    with open(os.path.join(args.out, "trades.csv"), "w", newline="") as f:
        cols = ["entry_date", "exit_date", "dir", "entry", "exit", "units",
                "pnl_jpy", "r_multiple", "reason"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for t in result["trades"]:
            w.writerow(t)

    with open(os.path.join(args.out, "equity.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "equity"])
        for d, v in result["equity_curve"]:
            w.writerow([d, round(v, 2)])

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
