"""Equal-weight 3-pair portfolio of the frozen strategy (no new parameters).

Runs params_final.json unchanged on GBPJPY / EURJPY / USDJPY daily bid/ask
(each sleeve = one third of capital, 3% risk per trade within its sleeve)
and combines the daily returns equally. Diversification across the yen
crosses is the blog's own practice ("whatever pair looks profitable") and
introduces zero fitted parameters.

Writes results/cross_instrument/portfolio.json.
Usage: python3 tools/run_portfolio.py
"""

import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from strategy import load_bidask_bars, run_backtest

EVAL_START = "2015-01-01"
SYMBOLS = ("gbpjpy", "eurjpy", "usdjpy")


def sleeve_returns(sym, params):
    bars = load_bidask_bars(os.path.join(ROOT, "data", f"{sym}_dukascopy_daily.csv"))
    res = run_backtest(bars, params, start_date=EVAL_START)
    daily = {}
    for ts, v in res["equity_curve"]:
        if ts[:10] >= EVAL_START:
            daily[ts[:10]] = v
    rets, prev = {}, 1_000_000.0
    for d in sorted(daily):
        rets[d] = daily[d] / prev - 1.0
        prev = daily[d]
    return rets, res["trades"]


def window_stats(dates, sleeves):
    eq, peak, dd, rs = 1.0, 1.0, 0.0, []
    for d in dates:
        r = sum(s.get(d, 0.0) for s in sleeves) / len(sleeves)
        rs.append(r)
        eq *= 1.0 + r
        peak = max(peak, eq)
        dd = max(dd, (peak - eq) / peak)
    n = len(rs)
    mean = sum(rs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in rs) / (n - 1)) if n > 1 else 0.0
    return {"sharpe": round(mean / sd * math.sqrt(252), 2) if sd > 0 else 0.0,
            "return": round(eq - 1.0, 4), "max_dd": round(dd, 4), "days": n}


def main():
    params = json.load(open(os.path.join(ROOT, "params_final.json")))
    params["spread_jpy"] = 0.0
    sleeves, n_trades = [], 0
    for sym in SYMBOLS:
        rets, trades = sleeve_returns(sym, params)
        sleeves.append(rets)
        n_trades += len(trades)
    all_dates = sorted(set().union(*[set(s) for s in sleeves]))

    out = {"note": "equal-weight portfolio of the frozen strategy across "
                   "GBPJPY/EURJPY/USDJPY; zero new parameters",
           "total_trades": n_trades,
           "full_2015_2026": window_stats(all_dates, sleeves),
           "from_2022": window_stats([d for d in all_dates if d >= "2022-01-01"], sleeves),
           "until_2021": window_stats([d for d in all_dates if d < "2022-01-01"], sleeves),
           "per_year": {}}
    by = {}
    for d in all_dates:
        by.setdefault(d[:4], []).append(d)
    for y in sorted(by):
        out["per_year"][y] = window_stats(by[y], sleeves)

    path = os.path.join(ROOT, "results", "cross_instrument", "portfolio.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({k: out[k] for k in
                      ("total_trades", "full_2015_2026", "from_2022", "until_2021")},
                     indent=2))


if __name__ == "__main__":
    main()
