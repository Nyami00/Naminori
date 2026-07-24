"""Pre-registered test of Hypothesis E: diversified vol-targeted TSMOM.

Protocol fixed BEFORE looking at any result:
  - Universe: every FX pair with a committed Dukascopy daily bid/ask file.
  - Warmup 2014; TRAIN 2015-01-01..2021-12-31 (the only window used to
    choose a configuration); TEST 2022-01-01..2026-07-22 held out.
  - Grid (8 configs): lookbacks {(250,) , (40,120,250)} x rebalance
    {weekly, monthly} x vol_window {60, 120}. Everything else fixed:
    per-sleeve vol target 10%, leverage cap 3x, real half-spread costs.
  - Selection rule: maximum TRAIN Sharpe. No other criterion.
  - Only after selection: scale the vol target so the CAGR reaches the 10%
    goal, and report the drawdown that comes with it.

Writes results/trend_portfolio/{grid.csv,selected.json,equity.csv,per_year.csv}
Usage: python3 tools/run_trend_research.py
"""

import csv
import glob
import itertools
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from trend_portfolio import load_universe, run_trend_portfolio, metrics

DATA = os.path.join(ROOT, "data")
EVAL_START = "2015-01-01"
TRAIN_END = "2021-12-31"
TEST_START = "2022-01-01"
GOAL_CAGR = 0.10

GRID = {
    "lookbacks": [(250,), (40, 120, 250)],
    "rebalance": ["weekly", "monthly"],
    "vol_window": [60, 120],
}
FIXED = {"target_vol": 0.10, "max_leverage": 3.0, "cost_multiplier": 1.0}


def discover_symbols():
    out = []
    for p in sorted(glob.glob(os.path.join(DATA, "*_dukascopy_daily.csv"))):
        out.append(os.path.basename(p).split("_")[0].upper())
    return out


def per_year_table(res):
    by = {}
    for d, v in res["equity_curve"]:
        by.setdefault(d[:4], []).append(v)
    rows, prev = [], None
    for y in sorted(by):
        vals = ([prev] if prev else []) + by[y]
        rets = [(vals[i] - vals[i - 1]) / vals[i - 1] for i in range(1, len(vals))]
        n = len(rets)
        mean = sum(rets) / n
        sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (n - 1)) if n > 1 else 0.0
        peak, dd = vals[0], 0.0
        for v in vals:
            peak = max(peak, v)
            dd = max(dd, (peak - v) / peak)
        rows.append({"year": y, "return": round(vals[-1] / vals[0] - 1, 4),
                     "sharpe": round(mean / sd * math.sqrt(252), 2) if sd > 0 else 0.0,
                     "max_dd": round(dd, 4)})
        prev = vals[-1]
    return rows


def main():
    symbols = discover_symbols()
    uni, dates = load_universe(DATA, symbols)
    dates = [d for d in dates if d <= "2026-07-22"]
    print(f"universe: {len(uni)} pairs {sorted(uni)}")
    print(f"dates: {len(dates)} ({dates[0]} .. {dates[-1]})\n")

    train_dates = [d for d in dates if d <= TRAIN_END]
    out_dir = os.path.join(ROOT, "results", "trend_portfolio")
    os.makedirs(out_dir, exist_ok=True)

    rows = []
    for vals in itertools.product(*GRID.values()):
        cfg = dict(FIXED, **dict(zip(GRID, vals)))
        m_tr = metrics(run_trend_portfolio(uni, train_dates, cfg,
                                           start_date=EVAL_START),
                       eval_start=EVAL_START)
        rf = run_trend_portfolio(uni, dates, cfg, start_date=EVAL_START)
        m_te = metrics(rf, eval_start=TEST_START)
        m_f = metrics(rf, eval_start=EVAL_START)
        rows.append({"lookbacks": "/".join(map(str, cfg["lookbacks"])),
                     "rebalance": cfg["rebalance"], "vol_window": cfg["vol_window"],
                     "train_sharpe": m_tr["sharpe"], "train_cagr": m_tr["cagr"],
                     "train_dd": m_tr["max_drawdown"],
                     "test_sharpe": m_te["sharpe"], "test_cagr": m_te["cagr"],
                     "test_dd": m_te["max_drawdown"],
                     "full_sharpe": m_f["sharpe"], "full_cagr": m_f["cagr"],
                     "full_dd": m_f["max_drawdown"], "full_vol": m_f["ann_vol"],
                     "cost_drag": m_f["cost_drag_annual"]})
        r = rows[-1]
        print(f"{r['lookbacks']:>12} {r['rebalance']:>8} vw{r['vol_window']:>4} | "
              f"train S {r['train_sharpe']:+.2f} cagr {r['train_cagr']:+.1%} | "
              f"test S {r['test_sharpe']:+.2f} cagr {r['test_cagr']:+.1%} | "
              f"full S {r['full_sharpe']:+.2f} cagr {r['full_cagr']:+.1%} "
              f"dd {r['full_dd']:.1%}", flush=True)

    with open(os.path.join(out_dir, "grid.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    best = max(rows, key=lambda r: r["train_sharpe"])
    sel_cfg = dict(FIXED,
                   lookbacks=tuple(int(x) for x in best["lookbacks"].split("/")),
                   rebalance=best["rebalance"], vol_window=best["vol_window"])
    print(f"\nSELECTED on train Sharpe: {best['lookbacks']} {best['rebalance']} "
          f"vw{best['vol_window']} (train S {best['train_sharpe']:+.2f})")

    res = run_trend_portfolio(uni, dates, sel_cfg, start_date=EVAL_START)
    m_full = metrics(res, eval_start=EVAL_START)
    m_test = metrics(res, eval_start=TEST_START)
    print("\nselected config, 10% per-sleeve vol target:")
    print("  full 2015-2026:", json.dumps(m_full))
    print("  test 2022-2026:", json.dumps(m_test))

    # scale the risk budget to the 10% CAGR goal (linear in target_vol)
    scale = GOAL_CAGR / m_full["cagr"] if m_full["cagr"] > 0 else None
    scaled = None
    if scale and scale > 0:
        cfg_s = dict(sel_cfg, target_vol=FIXED["target_vol"] * scale,
                     max_leverage=FIXED["max_leverage"] * scale)
        res_s = run_trend_portfolio(uni, dates, cfg_s, start_date=EVAL_START)
        scaled = {"target_vol": round(cfg_s["target_vol"], 4),
                  "full": metrics(res_s, eval_start=EVAL_START),
                  "test": metrics(res_s, eval_start=TEST_START)}
        print(f"\nscaled to the 10% goal (per-sleeve vol target "
              f"{cfg_s['target_vol']:.1%}):")
        print("  full 2015-2026:", json.dumps(scaled["full"]))
        print("  test 2022-2026:", json.dumps(scaled["test"]))
        res = res_s

    with open(os.path.join(out_dir, "selected.json"), "w") as f:
        json.dump({"universe": sorted(uni), "selected": {**best},
                   "config": {k: (list(v) if isinstance(v, tuple) else v)
                              for k, v in sel_cfg.items()},
                   "metrics_target10pct_vol": {"full": m_full, "test": m_test},
                   "scaled_to_goal": scaled}, f, indent=2)
    with open(os.path.join(out_dir, "equity.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "equity"])
        for d, v in res["equity_curve"]:
            w.writerow([d, round(v, 2)])
    py = per_year_table(res)
    with open(os.path.join(out_dir, "per_year.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["year", "return", "sharpe", "max_dd"])
        w.writeheader()
        w.writerows(py)
    print("\nper-year (final, scaled):")
    for r in py:
        print(f"  {r['year']}: {r['return']:+7.1%}  S {r['sharpe']:+5.2f}  dd {r['max_dd']:.1%}")


if __name__ == "__main__":
    main()
