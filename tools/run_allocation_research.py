"""Hypothesis G: long-only diversified allocation with a trend filter.

Motivation from the two failures before it. Hypothesis E (FX TSMOM) and F
(multi-asset TSMOM) reached Sharpe 0.20 and 0.42; reaching a 10% CAGR from
those needs 5-14x leverage and a 50-88% drawdown. Meanwhile the plain
buy-and-hold benchmarks printed by run F did 11-18% CAGR at Sharpe 0.6-0.9.
The honest conclusion is that in this period the return came from OWNING
risk assets, not from timing them. So this run asks the only remaining
useful question: can a simple, long-only, diversified allocation keep most
of that return while cutting the 28-36% single-asset drawdown?

The construction is deliberately the most-documented one available
(Faber's moving-average timing model): equal weight across the sleeves,
hold a sleeve only while its price is above a long moving average,
otherwise hold cash for that sleeve, rebalance monthly.

Protocol: same as E/F. Warmup 2014, TRAIN 2015-2021 selects, TEST
2022-2026.07 referees, 8 configs, selection = max TRAIN Sharpe.
Buy-and-hold of the same basket is reported as the benchmark to beat.

IMPORTANT accounting notes, applied to every number printed here:
  - Index prices are PRICE indices: dividends (~1.5-2%/yr on equities) are
    NOT included, so the real cash-funded return is higher than shown.
  - No financing cost is charged, which is correct for a cash-funded
    position (ETF/fund) and wrong for a leveraged CFD - at current rates a
    CFD long would pay roughly the policy rate per year.
  - Cash sleeves earn 0% here; in reality they would earn the deposit rate.
    That is another conservative omission.

Writes results/allocation/{grid.csv,selected.json,equity.csv,per_year.csv}
Usage: python3 tools/run_allocation_research.py
"""

import csv
import itertools
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from trend_portfolio import load_universe, realised_vol

DATA = os.path.join(ROOT, "data")
EVAL_START = "2015-01-01"
TRAIN_END = "2021-12-31"
TEST_START = "2022-01-01"

EQUITY = ["USA500IDXUSD", "USATECHIDXUSD", "DEUIDXEUR", "JPNIDXJPY", "GBRIDXGBP"]
DIVERSIFIERS = ["XAUUSD"]

GRID = {"sma": [200, 250],
        "basket": ["equity", "equity_gold"],
        "sizing": ["equal", "voltarget"]}
TARGET_VOL = 0.12          # per-sleeve target when sizing == "voltarget"
MAX_W = 1.0                # never lever a sleeve above its equal-weight share


def run_allocation(uni, dates, cfg, start_date=EVAL_START, start_equity=1e6):
    """Monthly-rebalanced, long-only, trend-filtered equal-weight allocation."""
    symbols = cfg["symbols"]
    hist_mid = {s: [] for s in symbols}
    hist_ret = {s: [] for s in symbols}
    weight = {s: 0.0 for s in symbols}
    equity, curve, rows = start_equity, [], []
    prev_month = None

    for date in dates:
        gross = 0.0
        for s in symbols:
            row = uni[s].get(date)
            if row is None:
                continue
            if hist_mid[s]:
                r = row["mid"] / hist_mid[s][-1] - 1.0
                hist_ret[s].append(r)
                gross += weight[s] * r
            hist_mid[s].append(row["mid"])
        gross /= len(symbols)

        cost = 0.0
        if prev_month != date[:7]:                      # monthly rebalance
            for s in symbols:
                row = uni[s].get(date)
                if row is None:
                    continue
                mids = hist_mid[s]
                if len(mids) <= cfg["sma"]:
                    target = 0.0
                else:
                    sma = sum(mids[-cfg["sma"]:]) / cfg["sma"]
                    in_trend = mids[-1] > sma
                    if not in_trend:
                        target = 0.0
                    elif cfg["sizing"] == "voltarget":
                        vol = realised_vol(hist_ret[s], 60)
                        target = min(TARGET_VOL / vol, MAX_W) if vol else 0.0
                    else:
                        target = 1.0
                target *= cfg.get("leverage", 1.0)
                cost += abs(target - weight[s]) * row["spread_frac"] * 0.5
                weight[s] = target
            cost /= len(symbols)
            prev_month = date[:7]

        net = gross - cost
        equity *= 1.0 + net
        if date >= start_date:
            curve.append((date, equity))
            rows.append({"date": date, "net": net,
                         "invested": sum(weight.values()) / len(symbols)})
    return {"equity_curve": curve, "days": rows, "symbols": symbols}


def stats(curve, eval_start=None):
    if eval_start:
        i = next((k for k, (d, _) in enumerate(curve) if d >= eval_start), 0)
        curve = curve[max(0, i - 1):]
    vals = [v for _, v in curve]
    rets = [(vals[i] - vals[i - 1]) / vals[i - 1] for i in range(1, len(vals))]
    n = len(rets)
    mean = sum(rets) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (n - 1))
    peak, dd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        dd = max(dd, (peak - v) / peak)
    years = n / 252
    total = vals[-1] / vals[0] - 1
    cagr = (1 + total) ** (1 / years) - 1
    return {"cagr": round(cagr, 4), "ann_vol": round(sd * math.sqrt(252), 4),
            "sharpe": round(mean / sd * math.sqrt(252), 3) if sd > 0 else 0.0,
            "max_drawdown": round(dd, 4),
            "calmar": round(cagr / dd, 2) if dd > 0 else None,
            "total_return": round(total, 4)}


def buy_hold(uni, dates, symbols, start_date=EVAL_START):
    cfg = {"symbols": symbols, "sma": 0, "sizing": "equal"}
    hist = {s: None for s in symbols}
    equity, curve = 1e6, []
    for date in dates:
        gross = 0.0
        for s in symbols:
            row = uni[s].get(date)
            if row is None:
                continue
            if hist[s]:
                gross += row["mid"] / hist[s] - 1.0
            hist[s] = row["mid"]
        equity *= 1.0 + gross / len(symbols)
        if date >= start_date:
            curve.append((date, equity))
    return curve


def main():
    uni, dates = load_universe(DATA, EQUITY + DIVERSIFIERS)
    dates = [d for d in dates if d <= "2026-07-22"]
    print(f"instruments: {sorted(uni)}\ndates: {len(dates)} "
          f"({dates[0]} .. {dates[-1]})\n")
    train_dates = [d for d in dates if d <= TRAIN_END]
    out_dir = os.path.join(ROOT, "results", "allocation")
    os.makedirs(out_dir, exist_ok=True)

    rows = []
    for vals in itertools.product(*GRID.values()):
        cfg = dict(zip(GRID, vals))
        cfg["symbols"] = EQUITY if cfg["basket"] == "equity" else EQUITY + DIVERSIFIERS
        tr = stats(run_allocation(uni, train_dates, cfg)["equity_curve"])
        full_res = run_allocation(uni, dates, cfg)
        te = stats(full_res["equity_curve"], TEST_START)
        fu = stats(full_res["equity_curve"])
        rows.append({"sma": cfg["sma"], "basket": cfg["basket"], "sizing": cfg["sizing"],
                     "train_sharpe": tr["sharpe"], "train_cagr": tr["cagr"],
                     "train_dd": tr["max_drawdown"],
                     "test_sharpe": te["sharpe"], "test_cagr": te["cagr"],
                     "test_dd": te["max_drawdown"],
                     "full_sharpe": fu["sharpe"], "full_cagr": fu["cagr"],
                     "full_dd": fu["max_drawdown"], "full_vol": fu["ann_vol"],
                     "full_calmar": fu["calmar"]})
        r = rows[-1]
        print(f"sma{r['sma']:>4} {r['basket']:>12} {r['sizing']:>10} | "
              f"train S {r['train_sharpe']:+.2f} cagr {r['train_cagr']:+.1%} | "
              f"test S {r['test_sharpe']:+.2f} cagr {r['test_cagr']:+.1%} | "
              f"full S {r['full_sharpe']:+.2f} cagr {r['full_cagr']:+.1%} "
              f"dd {r['full_dd']:.1%} calmar {r['full_calmar']}", flush=True)

    with open(os.path.join(out_dir, "grid.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    best = max(rows, key=lambda r: r["train_sharpe"])
    cfg = {"sma": best["sma"], "basket": best["basket"], "sizing": best["sizing"]}
    cfg["symbols"] = EQUITY if cfg["basket"] == "equity" else EQUITY + DIVERSIFIERS
    print(f"\nSELECTED on train Sharpe: sma{cfg['sma']} {cfg['basket']} {cfg['sizing']}")
    res = run_allocation(uni, dates, cfg)
    fu, te = stats(res["equity_curve"]), stats(res["equity_curve"], TEST_START)
    print("  full 2015-2026:", json.dumps(fu))
    print("  test 2022-2026:", json.dumps(te))
    inv = sum(d["invested"] for d in res["days"]) / len(res["days"])
    print(f"  average invested fraction: {inv:.0%} (rest in cash, earning 0% here)")

    print("\nbenchmarks (same basket, no timing):")
    bh_eq = buy_hold(uni, dates, EQUITY)
    bh_all = buy_hold(uni, dates, EQUITY + DIVERSIFIERS)
    b1, b2 = stats(bh_eq), stats(bh_all)
    print(f"  buy&hold 5 equity indices : {json.dumps(b1)}")
    print(f"  buy&hold + gold           : {json.dumps(b2)}")
    print(f"  (test window) equity      : {json.dumps(stats(bh_eq, TEST_START))}")
    print(f"  (test window) +gold       : {json.dumps(stats(bh_all, TEST_START))}")

    with open(os.path.join(out_dir, "selected.json"), "w") as f:
        json.dump({"config": {k: v for k, v in cfg.items() if k != "symbols"},
                   "symbols": cfg["symbols"], "selected_row": best,
                   "metrics": {"full": fu, "test": te},
                   "avg_invested": round(inv, 4),
                   "benchmark_buyhold_equity": b1,
                   "benchmark_buyhold_equity_gold": b2,
                   "notes": "price indices (no dividends), cash sleeves earn 0%, "
                            "no financing charged - correct for cash-funded ETFs"},
                  f, indent=2)
    with open(os.path.join(out_dir, "equity.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "equity"])
        for d, v in res["equity_curve"]:
            w.writerow([d, round(v, 2)])

    by = {}
    for d, v in res["equity_curve"]:
        by.setdefault(d[:4], []).append(v)
    py, prev = [], None
    print("\nper-year (selected):")
    for y in sorted(by):
        vals = ([prev] if prev else []) + by[y]
        peak, dd = vals[0], 0.0
        for v in vals:
            peak = max(peak, v)
            dd = max(dd, (peak - v) / peak)
        py.append({"year": y, "return": round(vals[-1] / vals[0] - 1, 4),
                   "max_dd": round(dd, 4)})
        print(f"  {y}: {py[-1]['return']:+7.1%}  dd {py[-1]['max_dd']:.1%}")
        prev = vals[-1]
    with open(os.path.join(out_dir, "per_year.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["year", "return", "max_dd"])
        w.writeheader()
        w.writerows(py)


if __name__ == "__main__":
    main()
