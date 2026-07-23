"""Small walk-forward parameter search (anti-overfitting by construction).

Grid is deliberately tiny (classic parameter neighborhoods only). Selection
uses the TRAIN window; the reported number is the untouched TEST window.
Run this once real GBP/JPY data is in place:

    python3 src/grid_search.py --data data/gbpjpy_daily_2026.csv \
        --train-end 2026-04-30 --eval-start 2026-01-01

Prints ranked train results, the selected params, and the honest test-window
metrics for the selected params only.
"""

import argparse
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy import load_bars, run_backtest, compute_metrics

GRID = {
    "entry_lookback": [10, 20],
    "trail_atr_mult": [2.5, 3.5],
    "stop_atr_mult": [1.5, 2.0],
}


def slice_bars(bars, end=None):
    return [b for b in bars if end is None or b["date"] <= end]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--train-end", required=True)
    ap.add_argument("--eval-start", default=None,
                    help="first date counted in metrics (skip warmup)")
    args = ap.parse_args()

    bars = load_bars(args.data)
    train_bars = slice_bars(bars, args.train_end)

    combos = [dict(zip(GRID, vals)) for vals in itertools.product(*GRID.values())]
    ranked = []
    for c in combos:
        res = run_backtest(train_bars, c, start_date=args.eval_start)
        m = compute_metrics(res, eval_start=args.eval_start)
        ranked.append((m["sharpe_annualized"], c, m))
    ranked.sort(key=lambda x: x[0], reverse=True)

    print("train ranking (Sharpe | params | trades, maxDD):")
    for s, c, m in ranked:
        print(f"  {s:6.2f} | {c} | n={m['num_trades']} dd={m['max_drawdown']:.1%}")

    best = ranked[0][1]
    # robustness: neighbors of the best must not collapse
    neighbor_sharpes = [s for s, c, _ in ranked
                       if sum(c[k] != best[k] for k in best) == 1]
    print(f"\nselected: {best}")
    if neighbor_sharpes:
        print(f"neighbor train Sharpes (1 param changed): "
              f"{[round(s,2) for s in neighbor_sharpes]}")

    res_full = run_backtest(bars, best, start_date=args.eval_start)
    m_test = compute_metrics(res_full, eval_start=args.train_end)
    print("\nTEST window (after train-end), selected params only:")
    print(json.dumps(m_test, indent=2))


if __name__ == "__main__":
    main()
