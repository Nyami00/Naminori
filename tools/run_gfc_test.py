"""Backward out-of-sample test through the global financial crisis.

No re-selection of anything. The configuration chosen on 2015-2021
(sma250, equities+gold, equal weight, monthly) is applied unchanged to
2008-2026, so 2008-2014 - a window never used for warmup, selection or
confirmation - acts as a fresh out-of-sample period that contains the
2008 crash (S&P 500 -57%), the 2011 euro crisis and the 2013 taper.

Buy-and-hold of the same basket is run alongside, because the 2015-2026
result was that buy-and-hold beat every timing rule; this test asks
whether that survives a decade that starts with a crash.

Same accounting caveats as run_allocation_research.py: price indices
(dividends excluded), cash earns 0%, no financing charged.

Writes results/allocation/gfc_test.json and gfc_equity.csv.
Usage: python3 tools/run_gfc_test.py
"""

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from trend_portfolio import load_universe

sys.path.insert(0, os.path.join(ROOT, "tools"))
from run_allocation_research import run_allocation, stats, buy_hold

DATA = os.path.join(ROOT, "data")
CONFIG = {"sma": 250, "sizing": "equal"}     # selected on 2015-2021, frozen
WINDOWS = [("2008-01-01", "2014-12-31", "GFC decade (never used before)"),
           ("2015-01-01", "2026-07-22", "the original study window"),
           ("2008-01-01", "2026-07-22", "full 18.5 years")]


def window(curve, start, end):
    return [(d, v) for d, v in curve if start <= d <= end]


def main():
    candidates = ["USA500IDXUSD", "USATECHIDXUSD", "JPNIDXJPY", "GBRIDXGBP",
                  "DEUIDXEUR", "XAUUSD"]
    uni_all, _ = load_universe(DATA, candidates)
    starts = {s: min(uni_all[s]) for s in uni_all}
    print("data start per instrument:")
    for s, d in sorted(starts.items()):
        print(f"  {s:>14}: {d}")
    symbols = [s for s in candidates if starts.get(s, "9999") <= "2007-12-31"]
    dropped = [s for s in candidates if s not in symbols]
    print(f"\nusing {symbols}")
    if dropped:
        print(f"dropped (history starts too late): {dropped}")

    uni, dates = load_universe(DATA, symbols)
    dates = [d for d in dates if "2007-01-01" <= d <= "2026-07-22"]
    print(f"dates: {len(dates)} ({dates[0]} .. {dates[-1]})\n")

    cfg = dict(CONFIG, symbols=symbols, basket="equity_gold")
    res = run_allocation(uni, dates, cfg, start_date="2008-01-01")
    bh = buy_hold(uni, dates, symbols, start_date="2008-01-01")

    out = {"config": {k: v for k, v in cfg.items() if k != "symbols"},
           "symbols": symbols, "windows": {}}
    print(f"{'window':>34} | {'trend-filtered':^38} | {'buy & hold':^38}")
    print(f"{'':>34} | {'cagr':>7} {'sharpe':>7} {'maxDD':>7} {'calmar':>7} | "
          f"{'cagr':>7} {'sharpe':>7} {'maxDD':>7} {'calmar':>7}")
    for start, end, label in WINDOWS:
        a = stats(window(res["equity_curve"], start, end))
        b = stats(window(bh, start, end))
        out["windows"][label] = {"trend_filtered": a, "buy_hold": b}
        print(f"{label:>34} | {a['cagr']:>7.1%} {a['sharpe']:>7.2f} "
              f"{a['max_drawdown']:>7.1%} {str(a['calmar']):>7} | "
              f"{b['cagr']:>7.1%} {b['sharpe']:>7.2f} {b['max_drawdown']:>7.1%} "
              f"{str(b['calmar']):>7}")

    print("\nper-year (trend-filtered vs buy & hold):")
    by_a, by_b = {}, {}
    for d, v in res["equity_curve"]:
        by_a.setdefault(d[:4], []).append(v)
    for d, v in bh:
        by_b.setdefault(d[:4], []).append(v)
    prev_a = prev_b = None
    rows = []
    for y in sorted(by_a):
        va = ([prev_a] if prev_a else []) + by_a[y]
        vb = ([prev_b] if prev_b else []) + by_b[y]
        ra, rb = va[-1] / va[0] - 1, vb[-1] / vb[0] - 1
        peak, dda = va[0], 0.0
        for v in va:
            peak = max(peak, v)
            dda = max(dda, (peak - v) / peak)
        peak, ddb = vb[0], 0.0
        for v in vb:
            peak = max(peak, v)
            ddb = max(ddb, (peak - v) / peak)
        rows.append({"year": y, "trend_return": round(ra, 4), "trend_dd": round(dda, 4),
                     "buyhold_return": round(rb, 4), "buyhold_dd": round(ddb, 4)})
        flag = "  <-- crisis" if y in ("2008", "2011", "2020", "2022") else ""
        print(f"  {y}: trend {ra:+7.1%} (dd {dda:5.1%})   buy&hold {rb:+7.1%} "
              f"(dd {ddb:5.1%}){flag}")
        prev_a, prev_b = va[-1], vb[-1]
    out["per_year"] = rows

    out_dir = os.path.join(ROOT, "results", "allocation")
    with open(os.path.join(out_dir, "gfc_test.json"), "w") as f:
        json.dump(out, f, indent=2)
    with open(os.path.join(out_dir, "gfc_equity.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "trend_filtered", "buy_hold"])
        bh_map = dict(bh)
        for d, v in res["equity_curve"]:
            w.writerow([d, round(v, 2), round(bh_map.get(d, float("nan")), 2)])
    print("\nwrote results/allocation/gfc_test.json")


if __name__ == "__main__":
    main()
