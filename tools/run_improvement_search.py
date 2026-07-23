"""Pre-registered improvement search: more trades + higher win rate.

Two bounded rounds, both selected on the TRAIN window (2015-2021) only,
with the TEST window (2022-2026.07) untouched as referee:
  round 1 (24 configs): direction x lookback x target(boundary/mid/2r) x
      time-stop, all with the EMA200 gate, 3% compounding risk, real spreads.
  round 2 (16 configs): long-only + spring-quality filters from the blog's
      own teachings (rejection strength 0.25 ATR, max undershoot) x lookback
      x target x time-stop.
Pre-registered selection rule: max train Sharpe subject to train trades >= 40
(round 2: >= 30) AND train win rate >= 45%.

RESULT (2026-07-23 run): zero configs met the constraints in either round;
every one of the 40 configs had a NEGATIVE train-window Sharpe. Within this
daily spring/rejection family, trade count and win rate can each be raised
(mid targets reach 50%+ win rate; K=10 doubles trade count) but no variant
had positive expectancy in 2015-2021. The edge is regime-bound (2022+).

Writes results/improvement_search/round{1,2}.csv.
Usage: python3 tools/run_improvement_search.py
"""

import csv
import itertools
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from strategy import load_bidask_bars, run_backtest, compute_metrics

TRAIN_END = "2021-12-31"
EVAL_START = "2015-01-01"
TEST_START = "2022-01-01"

BASE = {"mode": "swing", "swing_wick_atr": 0.5, "swing_gate_ema": 200,
        "risk_per_trade": 0.03, "spread_jpy": 0.0}

ROUNDS = {
    "round1": ({"allow_short": [False, True],
                "entry_lookback": [10, 20],
                "swing_target": ["boundary", "mid", "2r"],
                "max_hold_days": [None, 15]}, {}),
    "round2": ({"entry_lookback": [10, 20],
                "swing_target": ["boundary", "mid"],
                "swing_max_wick_atr": [0.75, 1.5],
                "max_hold_days": [None, 15]},
               {"allow_short": False, "swing_reject_atr": 0.25}),
}


def main():
    bars = load_bidask_bars(os.path.join(ROOT, "data", "gbpjpy_dukascopy_daily.csv"))
    train_bars = [b for b in bars if b["date"] <= TRAIN_END]
    out_dir = os.path.join(ROOT, "results", "improvement_search")
    os.makedirs(out_dir, exist_ok=True)

    for name, (grid, extra) in ROUNDS.items():
        rows = []
        for vals in itertools.product(*grid.values()):
            cfg = dict(BASE, **extra, **dict(zip(grid, vals)))
            m_tr = compute_metrics(run_backtest(train_bars, cfg, start_date=EVAL_START),
                                   eval_start=EVAL_START)
            rf = run_backtest(bars, cfg, start_date=EVAL_START)
            m_te = compute_metrics(rf, eval_start=TEST_START)
            m_f = compute_metrics(rf, eval_start=EVAL_START)
            rows.append({**{k: cfg.get(k) for k in
                            ("allow_short", "entry_lookback", "swing_target",
                             "swing_max_wick_atr", "max_hold_days")},
                         "train_sharpe": m_tr["sharpe_annualized"],
                         "train_trades": m_tr["num_trades"],
                         "train_winrate": m_tr["win_rate"],
                         "test_sharpe": m_te["sharpe_annualized"],
                         "test_trades": m_te["num_trades"],
                         "test_winrate": m_te["win_rate"],
                         "full_sharpe": m_f["sharpe_annualized"],
                         "full_return": m_f["total_return"],
                         "full_maxdd": m_f["max_drawdown"],
                         "full_trades": m_f["num_trades"],
                         "full_winrate": m_f["win_rate"]})
        rows.sort(key=lambda r: r["train_sharpe"], reverse=True)
        path = os.path.join(out_dir, f"{name}.csv")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        n_pass = sum(1 for r in rows
                     if r["train_trades"] >= (40 if name == "round1" else 30)
                     and (r["train_winrate"] or 0) >= 0.45)
        print(f"{name}: {len(rows)} configs, best train Sharpe "
              f"{rows[0]['train_sharpe']:+.2f}, configs passing constraints: {n_pass}")


if __name__ == "__main__":
    main()
