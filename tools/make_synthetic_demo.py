"""Generate a SYNTHETIC GBP/JPY-like daily OHLC series for pipeline testing.

*** THIS IS NOT REAL MARKET DATA. ***
Every real market-data source is blocked by this sandbox's network policy, so
this seeded series exists ONLY to exercise the backtest + validation pipeline
end-to-end. Any performance number computed on it is a test of the machinery,
never a claim about real GBP/JPY performance. The output file name contains
"SYNTHETIC" for this reason, and data_qc.py will FAIL it against the real
anchors (as it should).

Usage: python3 tools/make_synthetic_demo.py [--seed 20260101] [--out data/SYNTHETIC_demo_gbpjpy.csv]
"""

import argparse
import csv
import datetime as dt
import math
import random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260101)
    ap.add_argument("--out", default="data/SYNTHETIC_demo_gbpjpy.csv")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    d = dt.date(2025, 10, 1)          # warmup before Jan so eval can start Jan 1
    end = dt.date(2026, 7, 22)
    price = 199.0
    daily_vol = 0.0055                # ~GBPJPY-like daily volatility
    # regime drifts: alternating multi-week trends, like a trending FX year
    regimes = [(35, 0.0009), (20, -0.0011), (30, 0.0008), (25, -0.0004),
               (35, 0.0012), (20, -0.0009), (45, 0.0007)]
    seq = []
    for length, drift in regimes:
        seq.extend([drift] * length)

    rows = []
    i = 0
    prev_close = price
    while d <= end:
        if d.weekday() < 5:
            drift = seq[i % len(seq)]
            i += 1
            r = drift + rng.gauss(0.0, daily_vol)
            close = prev_close * math.exp(r)
            o = prev_close
            hi = max(o, close) * (1.0 + abs(rng.gauss(0, daily_vol / 2.5)))
            lo = min(o, close) * (1.0 - abs(rng.gauss(0, daily_vol / 2.5)))
            rows.append((d.isoformat(), round(o, 4), round(hi, 4),
                         round(lo, 4), round(close, 4)))
            prev_close = close
        d += dt.timedelta(days=1)

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close"])
        w.writerows(rows)
    print(f"wrote {len(rows)} SYNTHETIC bars to {args.out} "
          f"({rows[0][0]} .. {rows[-1][0]}), final price {rows[-1][4]}")


if __name__ == "__main__":
    main()
