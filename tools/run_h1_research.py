"""Pre-registered H1 edge research on GBP/JPY (hypotheses A and B).

Protocol (fixed BEFORE looking at any result):
  - Data: Dukascopy H1 bid/ask, 2014-2026.07; warmup 2014.
  - Train window 2015-01-01..2021-12-31 (selection happens here ONLY);
    test window 2022-01-01..2026-07-22 is the untouched referee.
  - Hypothesis A "ema_bounce" (12 configs): touch-and-hold of the H1 200EMA
    (the blog's explicit high-probability bounce point), long-only;
    target {1.5r, 2r, ema_line(25EMA)} x slope gate {off, 24 bars} x
    time stop {none, 48 bars}.
  - Hypothesis B "swing_daily" (12 configs): H1 spring of the PREVIOUS DAY's
    low (line trading at daily levels), long-only above the H1 200EMA;
    rejection {0, 0.25 ATR} x target {boundary(prev-day high), mid, 2r} x
    time stop {none, 48 bars}.
  - Selection rule: max train Sharpe subject to train trades >= 100 AND
    train win rate >= 45%. Sharpe from DAILY-resampled equity, sqrt(252).
  - Risk 3% of equity per trade, compounding; real per-bar spread.

Writes results/h1_research/{hypA,hypB}.csv.
Usage: python3 tools/run_h1_research.py
"""

import csv
import gzip
import itertools
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from strategy import run_backtest, compute_metrics

TRAIN_END = "2022-01-01"
EVAL_START = "2015-01-01"
TEST_START = "2022-01-01"


def load_h1(path):
    bars = []
    with gzip.open(path, "rt", newline="") as f:
        for row in csv.DictReader(f):
            bars.append({"date": row["ts"],
                         "open": float(row["bid_open"]),
                         "high": float(row["bid_high"]),
                         "low": float(row["bid_low"]),
                         "close": float(row["bid_close"]),
                         "spread": max(0.0, float(row["spread_close"]))})
    return bars


def daily_metrics(result, eval_start=None):
    """compute_metrics on the day-end-resampled equity curve (sqrt-252 valid)."""
    daily, last_day = [], None
    for ts, v in result["equity_curve"]:
        d = ts[:10]
        if d != last_day and last_day is not None:
            daily.append((last_day, last_v))
        last_day, last_v = d, v
    daily.append((last_day, last_v))
    return compute_metrics({"equity_curve": daily, "trades": result["trades"]},
                           eval_start=eval_start)


HYPS = {
    "hypA": ({"swing_target": ["1.5r", "2r", "ema_line"],
              "gate_rising_bars": [None, 24],
              "max_hold_days": [None, 48]},
             {"mode": "ema_bounce", "trend_ema": 200, "pb_ema": 25,
              "swing_wick_atr": 0.25, "allow_short": False}),
    "hypB": ({"swing_reject_atr": [0.0, 0.25],
              "swing_target": ["boundary", "mid", "2r"],
              "max_hold_days": [None, 48]},
             {"mode": "swing_daily", "swing_gate_ema": 200,
              "swing_wick_atr": 0.25, "allow_short": False}),
}
BASE = {"risk_per_trade": 0.03, "spread_jpy": 0.0, "atr_period": 14}


def main():
    bars = load_h1(os.path.join(ROOT, "data", "gbpjpy_dukascopy_h1.csv.gz"))
    print(f"H1 bars: {len(bars)} ({bars[0]['date']} .. {bars[-1]['date']})")
    train_bars = [b for b in bars if b["date"] < TRAIN_END]
    out_dir = os.path.join(ROOT, "results", "h1_research")
    os.makedirs(out_dir, exist_ok=True)

    for name, (grid, fixed) in HYPS.items():
        rows = []
        for vals in itertools.product(*grid.values()):
            cfg = dict(BASE, **fixed, **dict(zip(grid, vals)))
            m_tr = daily_metrics(run_backtest(train_bars, cfg, start_date=EVAL_START),
                                 eval_start=EVAL_START)
            rf = run_backtest(bars, cfg, start_date=EVAL_START)
            m_te = daily_metrics(rf, eval_start=TEST_START)
            m_f = daily_metrics(rf, eval_start=EVAL_START)
            rows.append({**{k: vals[j] for j, k in enumerate(grid)},
                         "train_sharpe": m_tr["sharpe_annualized"],
                         "train_trades": m_tr["num_trades"],
                         "train_winrate": m_tr["win_rate"],
                         "train_return": m_tr["total_return"],
                         "test_sharpe": m_te["sharpe_annualized"],
                         "test_trades": m_te["num_trades"],
                         "test_winrate": m_te["win_rate"],
                         "test_return": m_te["total_return"],
                         "full_sharpe": m_f["sharpe_annualized"],
                         "full_return": m_f["total_return"],
                         "full_maxdd": m_f["max_drawdown"],
                         "full_trades": m_f["num_trades"],
                         "full_winrate": m_f["win_rate"]})
            r = rows[-1]
            print(f"{name} {dict(zip(grid, vals))}: "
                  f"train S {r['train_sharpe']:+.2f} n={r['train_trades']} "
                  f"wr={(r['train_winrate'] or 0)*100:.0f}% | "
                  f"test S {r['test_sharpe']:+.2f} n={r['test_trades']}", flush=True)
        rows.sort(key=lambda r: r["train_sharpe"], reverse=True)
        with open(os.path.join(out_dir, f"{name}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        passing = [r for r in rows if r["train_trades"] >= 100
                   and (r["train_winrate"] or 0) >= 0.45]
        print(f"\n{name}: best train Sharpe {rows[0]['train_sharpe']:+.2f}; "
              f"configs passing pre-registered constraints: {len(passing)}")
        if passing:
            print("SELECTED:", {k: passing[0][k] for k in grid},
                  json.dumps({k: passing[0][k] for k in
                              ("train_sharpe", "test_sharpe", "test_trades",
                               "test_winrate", "full_sharpe")}))
        print()


if __name__ == "__main__":
    main()
