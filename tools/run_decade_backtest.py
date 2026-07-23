"""Decade backtest: frozen params on Dukascopy bid/ask dailies (2015-2026).

No re-tuning of any kind happens here - params_final.json (frozen on the
2026 walk-forward) is applied as-is to 2015-2026 with real per-bar bid/ask
spreads (spread_jpy forced to 0). 2014 serves as indicator warmup.

Writes results/gbpjpy_decade/{summary.json,trades.csv,equity.csv,per_year.csv}

Usage: python3 tools/run_decade_backtest.py
"""

import csv
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from strategy import load_bidask_bars, run_backtest, compute_metrics

EVAL_START = "2015-01-01"


def main():
    bars = load_bidask_bars(os.path.join(ROOT, "data", "gbpjpy_dukascopy_daily.csv"))
    params = json.load(open(os.path.join(ROOT, "params_final.json")))
    params["spread_jpy"] = 0.0  # costs come from the real per-bar spread

    res = run_backtest(bars, params, start_date=EVAL_START)
    metrics = compute_metrics(res, eval_start=EVAL_START)

    out = os.path.join(ROOT, "results", "gbpjpy_decade")
    os.makedirs(out, exist_ok=True)

    per_year = []
    by_year = {}
    for d, v in res["equity_curve"]:
        by_year.setdefault(d[:4], []).append(v)
    prev_last = by_year.get("2014", [1_000_000.0])[-1]
    for y in sorted(by_year):
        if y < "2015":
            continue
        vals = [prev_last] + by_year[y]
        rets = [(vals[i] - vals[i - 1]) / vals[i - 1] for i in range(1, len(vals))]
        n = len(rets)
        mean = sum(rets) / n
        sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (n - 1)) if n > 1 else 0.0
        peak, dd = vals[0], 0.0
        for v in vals:
            peak = max(peak, v)
            dd = max(dd, (peak - v) / peak if peak > 0 else 0.0)
        tr = [t for t in res["trades"] if t["entry_date"][:4] == y]
        per_year.append({
            "year": y,
            "sharpe": round(mean / sd * math.sqrt(252), 2) if sd > 0 else 0.0,
            "return": round(vals[-1] / vals[0] - 1.0, 4),
            "max_dd": round(dd, 4),
            "trades": len(tr),
            "wins": sum(1 for t in tr if t["pnl_jpy"] > 0),
        })
        prev_last = vals[-1]

    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump({"data_file": "data/gbpjpy_dukascopy_daily.csv",
                   "note": "frozen 2026 walk-forward params applied unchanged to "
                           "2015-2026; execution buys at ask, exits at bid; "
                           "UTC-day bars",
                   "bars": len(bars), "first_date": bars[0]["date"],
                   "last_date": bars[-1]["date"], "eval_start": EVAL_START,
                   "start_equity": 1_000_000.0,
                   "params": res["params"], "metrics": metrics}, f, indent=2)
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
        for d, v in res["equity_curve"]:
            w.writerow([d, round(v, 2)])
    with open(os.path.join(out, "per_year.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["year", "sharpe", "return", "max_dd",
                                          "trades", "wins"])
        w.writeheader()
        w.writerows(per_year)

    print(json.dumps(metrics, indent=2))
    for r in per_year:
        print(r)


if __name__ == "__main__":
    main()
