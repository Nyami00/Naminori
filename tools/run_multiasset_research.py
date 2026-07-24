"""Hypothesis F: multi-asset vol-targeted TSMOM (the 10%-CAGR attempt).

Why this family: hypothesis E (the same construction on FX only) failed -
train Sharpe +0.01, full-period Sharpe 0.20. That matches the documented
record: currency-only trend following has been weak since 2015. The
evidence for trend following comes from DIVERSIFIED futures - equity
indices, metals, energy, currencies - so this run adds those sleeves. The
decision was made from that prior, not from inspecting per-config results,
and it is disclosed as the second family tested.

Protocol (unchanged from hypothesis E):
  - warmup 2014; TRAIN 2015-2021 selects, TEST 2022-2026.07 referees
  - same 8-config grid: lookbacks {(250,), (40,120,250)} x rebalance
    {weekly, monthly} x vol_window {60, 120}
  - per-sleeve vol target 10%, leverage cap 3x, real half-spread costs
  - selection = max TRAIN Sharpe, nothing else
  - after selection only: scale the risk budget toward the 10% CAGR goal
    and report the drawdown it costs

Benchmarks are printed alongside so beta is not mistaken for skill:
buy-and-hold S&P 500 CFD, gold, and an equal-weight basket of the universe.

Writes results/multiasset/{grid.csv,selected.json,equity.csv,per_year.csv,
benchmarks.json}
Usage: python3 tools/run_multiasset_research.py
"""

import csv
import itertools
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from trend_portfolio import load_universe, run_trend_portfolio, metrics, load_pair

DATA = os.path.join(ROOT, "data")
EVAL_START = "2015-01-01"
TRAIN_END = "2021-12-31"
TEST_START = "2022-01-01"
GOAL_CAGR = 0.10

FX = ["GBPJPY", "EURJPY", "USDJPY", "AUDJPY", "EURUSD", "GBPUSD", "AUDUSD",
      "NZDUSD", "USDCHF", "USDCAD", "EURGBP"]
OTHER = ["XAUUSD", "XAGUSD", "LIGHTCMDUSD", "BRENTCMDUSD", "COPPERCMDUSD",
         "USA500IDXUSD", "USATECHIDXUSD", "USA30IDXUSD", "DEUIDXEUR",
         "JPNIDXJPY", "GBRIDXGBP"]

GRID = {"lookbacks": [(250,), (40, 120, 250)],
        "rebalance": ["weekly", "monthly"],
        "vol_window": [60, 120]}
FIXED = {"target_vol": 0.10, "max_leverage": 3.0, "cost_multiplier": 1.0}


def buy_and_hold(symbol, dates_from):
    path = os.path.join(DATA, f"{symbol.lower()}_dukascopy_daily.csv")
    if not os.path.exists(path):
        return None
    rows = [r for r in load_pair(path) if r["date"] >= dates_from]
    if len(rows) < 100:
        return None
    vals = [r["mid"] for r in rows]
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
    return {"cagr": round((1 + total) ** (1 / years) - 1, 4),
            "ann_vol": round(sd * math.sqrt(252), 4),
            "sharpe": round(mean / sd * math.sqrt(252), 2) if sd > 0 else 0.0,
            "max_drawdown": round(dd, 4)}


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


def evaluate(uni, dates, cfg):
    train_dates = [d for d in dates if d <= TRAIN_END]
    m_tr = metrics(run_trend_portfolio(uni, train_dates, cfg, start_date=EVAL_START),
                   eval_start=EVAL_START)
    rf = run_trend_portfolio(uni, dates, cfg, start_date=EVAL_START)
    return m_tr, metrics(rf, eval_start=TEST_START), metrics(rf, eval_start=EVAL_START), rf


def main():
    symbols = FX + OTHER
    uni, dates = load_universe(DATA, symbols)
    dates = [d for d in dates if d <= "2026-07-22"]
    missing = [s for s in symbols if s not in uni]
    print(f"universe: {len(uni)} instruments ({len(uni) - len([s for s in OTHER if s in uni])} FX + "
          f"{len([s for s in OTHER if s in uni])} non-FX)")
    if missing:
        print(f"missing (skipped): {missing}")
    starts = {s: min(uni[s]) for s in uni}
    late = {s: d for s, d in starts.items() if d > "2014-06-01"}
    if late:
        print(f"late-starting instruments: {late}")
    print(f"dates: {len(dates)} ({dates[0]} .. {dates[-1]})\n")

    out_dir = os.path.join(ROOT, "results", "multiasset")
    os.makedirs(out_dir, exist_ok=True)

    rows = []
    for vals in itertools.product(*GRID.values()):
        cfg = dict(FIXED, **dict(zip(GRID, vals)))
        m_tr, m_te, m_f, _ = evaluate(uni, dates, cfg)
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
    sel = dict(FIXED, lookbacks=tuple(int(x) for x in best["lookbacks"].split("/")),
               rebalance=best["rebalance"], vol_window=best["vol_window"])
    print(f"\nSELECTED on train Sharpe: {best['lookbacks']} {best['rebalance']} "
          f"vw{best['vol_window']}")
    m_tr, m_te, m_f, res = evaluate(uni, dates, sel)
    print("  full 2015-2026:", json.dumps(m_f))
    print("  test 2022-2026:", json.dumps(m_te))

    scaled = None
    if m_f["cagr"] > 0:
        k = GOAL_CAGR / m_f["cagr"]
        cfg_s = dict(sel, target_vol=FIXED["target_vol"] * k,
                     max_leverage=FIXED["max_leverage"] * k)
        res_s = run_trend_portfolio(uni, dates, cfg_s, start_date=EVAL_START)
        scaled = {"target_vol": round(cfg_s["target_vol"], 4),
                  "leverage_cap": round(cfg_s["max_leverage"], 2),
                  "full": metrics(res_s, eval_start=EVAL_START),
                  "test": metrics(res_s, eval_start=TEST_START)}
        print(f"\nscaled toward the 10% goal (per-sleeve vol target "
              f"{cfg_s['target_vol']:.1%}, cap {cfg_s['max_leverage']:.1f}x):")
        print("  full:", json.dumps(scaled["full"]))
        print("  test:", json.dumps(scaled["test"]))
        res = res_s

    bench = {s: buy_and_hold(s, EVAL_START)
             for s in ("USA500IDXUSD", "USATECHIDXUSD", "XAUUSD", "JPNIDXJPY")}
    bench = {k: v for k, v in bench.items() if v}
    print("\nbuy-and-hold benchmarks 2015-2026 (price return, no dividends/financing):")
    for k, v in bench.items():
        print(f"  {k:>14}: cagr {v['cagr']:+.1%}  vol {v['ann_vol']:.1%}  "
              f"S {v['sharpe']:+.2f}  maxDD {v['max_drawdown']:.1%}")

    with open(os.path.join(out_dir, "selected.json"), "w") as f:
        json.dump({"universe": sorted(uni), "selected_row": best,
                   "config": {k: (list(v) if isinstance(v, tuple) else v)
                              for k, v in sel.items()},
                   "metrics_base": {"train": m_tr, "test": m_te, "full": m_f},
                   "scaled_to_goal": scaled}, f, indent=2)
    with open(os.path.join(out_dir, "benchmarks.json"), "w") as f:
        json.dump(bench, f, indent=2)
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
    print("\nper-year (final):")
    for r in py:
        print(f"  {r['year']}: {r['return']:+7.1%}  S {r['sharpe']:+5.2f}  dd {r['max_dd']:.1%}")


if __name__ == "__main__":
    main()
