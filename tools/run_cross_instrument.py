"""Cross-instrument transfer test: frozen GBP/JPY params on sibling yen crosses.

The frozen strategy (params_final.json - daily spring at the 20-day low,
long-only above the daily EMA200, 3% compounding risk) was designed and
selected ONLY on GBP/JPY. Here it is applied UNCHANGED to EUR/JPY and
USD/JPY daily bid/ask data (fresh, never-touched instruments), 2015-2026.07.
If the "buy springs in a yen-weakening regime" concept is structural, the
siblings should show a similar regime-conditional profile; if GBP/JPY was
luck, they should not.

Writes results/cross_instrument/{symbol}_summary.json and _per_year.csv.
Usage: python3 tools/run_cross_instrument.py
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


def per_year(res):
    by_year = {}
    for d, v in res["equity_curve"]:
        by_year.setdefault(d[:4], []).append(v)
    prev = by_year.get("2014", [1_000_000.0])[-1]
    out = []
    for y in sorted(by_year):
        if y < "2015":
            continue
        vals = [prev] + by_year[y]
        rets = [(vals[i] - vals[i-1]) / vals[i-1] for i in range(1, len(vals))]
        n = len(rets)
        mean = sum(rets) / n
        sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (n - 1)) if n > 1 else 0
        tr = [t for t in res["trades"] if t["entry_date"][:4] == y]
        out.append({"year": y,
                    "sharpe": round(mean / sd * math.sqrt(252), 2) if sd > 0 else 0.0,
                    "return": round(vals[-1] / vals[0] - 1, 4),
                    "trades": len(tr),
                    "wins": sum(1 for t in tr if t["pnl_jpy"] > 0)})
        prev = vals[-1]
    return out


def main():
    params = json.load(open(os.path.join(ROOT, "params_final.json")))
    params["spread_jpy"] = 0.0
    out_dir = os.path.join(ROOT, "results", "cross_instrument")
    os.makedirs(out_dir, exist_ok=True)

    for sym in ("eurjpy", "usdjpy"):
        path = os.path.join(ROOT, "data", f"{sym}_dukascopy_daily.csv")
        if not os.path.exists(path):
            print(f"{sym}: data missing, skip")
            continue
        bars = load_bidask_bars(path)
        res = run_backtest(bars, params, start_date=EVAL_START)
        m = compute_metrics(res, eval_start=EVAL_START)
        m22 = compute_metrics(res, eval_start="2022-01-01")
        py = per_year(res)
        with open(os.path.join(out_dir, f"{sym}_summary.json"), "w") as f:
            json.dump({"symbol": sym.upper(), "bars": len(bars),
                       "first": bars[0]["date"], "last": bars[-1]["date"],
                       "note": "frozen GBPJPY params applied unchanged",
                       "metrics_full": m, "metrics_2022on": m22}, f, indent=2)
        with open(os.path.join(out_dir, f"{sym}_per_year.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["year", "sharpe", "return", "trades", "wins"])
            w.writeheader()
            w.writerows(py)
        print(f"\n=== {sym.upper()} (frozen params, {bars[0]['date']}..{bars[-1]['date']}) ===")
        print(f"full 2015-2026: Sharpe {m['sharpe_annualized']:+.2f}, ret {m['total_return']:+.1%}, "
              f"dd {m['max_drawdown']:.1%}, trades {m['num_trades']}, wr {(m['win_rate'] or 0)*100:.0f}%")
        print(f"2022 onward   : Sharpe {m22['sharpe_annualized']:+.2f}, ret {m22['total_return']:+.1%}, "
              f"trades {m22['num_trades']}, wr {(m22['win_rate'] or 0)*100:.0f}%")
        for r in py:
            print(f"  {r['year']}: S {r['sharpe']:+6.2f}  ret {r['return']:+7.1%}  "
                  f"n={r['trades']} w={r['wins']}")


if __name__ == "__main__":
    main()
