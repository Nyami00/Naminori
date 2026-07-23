"""Reference run of the strategy on REAL USD/JPY daily closes (2026-03-07..07-22).

Purpose: demonstrate the full pipeline on genuine 2026 market data that the
user already owns (exported from their Notion market-data database). This is
NOT the target instrument (GBP/JPY) and the data is close-only, so bars are
degenerate (open=high=low=close) and stops can only trigger on a close
crossing them. Results are a pipeline demonstration on real data, not the
requested GBP/JPY backtest.

Usage: python3 tools/run_usdjpy_reference.py
"""

import csv
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from strategy import run_backtest, compute_metrics


def main():
    src_csv = os.path.join(ROOT, "data", "notion_usdjpy_daily_2026.csv")
    bars = []
    with open(src_csv, newline="") as f:
        for row in csv.DictReader(f):
            d = dt.date.fromisoformat(row["date"])
            if d.weekday() >= 5:      # drop carry-forward weekend rows
                continue
            c = float(row["close"])
            bars.append({"date": row["date"], "open": c, "high": c,
                         "low": c, "close": c})

    # shorter lookbacks: only ~98 weekday bars exist, and a 50-day EMA plus
    # 20-day breakout would leave almost no evaluation window
    params = {"entry_lookback": 10, "trend_ema": 20, "atr_period": 14,
              "stop_atr_mult": 2.0, "trail_atr_mult": 3.0,
              "risk_per_trade": 0.03, "spread_jpy": 0.01}
    res = run_backtest(bars, params)
    m = compute_metrics(res)

    out = os.path.join(ROOT, "results", "usdjpy_reference")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump({"note": "REAL USDJPY closes (user's Notion DB), close-only bars, "
                           "NOT the GBPJPY target backtest",
                   "bars_weekday": len(bars),
                   "first": bars[0]["date"], "last": bars[-1]["date"],
                   "params": res["params"], "metrics": m}, f, indent=2)
    with open(os.path.join(out, "trades.csv"), "w", newline="") as f:
        cols = ["entry_date", "exit_date", "dir", "entry", "exit", "units",
                "pnl_jpy", "r_multiple", "reason"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for t in res["trades"]:
            w.writerow(t)
    with open(os.path.join(out, "equity.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "equity"])
        for d_, v in res["equity_curve"]:
            w.writerow([d_, round(v, 2)])
    print(f"weekday bars: {len(bars)} ({bars[0]['date']} .. {bars[-1]['date']})")
    print(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
