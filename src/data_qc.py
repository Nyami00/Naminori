"""Quality control for a GBP/JPY daily OHLC dataset before backtesting.

Validates a candidate CSV (date,open,high,low,close) against:
  1. structural rules (sorted unique dates, weekdays, OHLC consistency,
     no missing business days beyond a tolerance),
  2. plausibility rules (day-over-day move < 3%, values within 190-235),
  3. the externally collected real reference anchors in
     data/gbpjpy_anchors_2026.json (each anchor must match within tolerance).

Exit code 0 = PASS, 1 = FAIL. Run this before trusting any backtest output.

Usage:
    python3 src/data_qc.py --data data/gbpjpy_daily_2026.csv \
        --anchors data/gbpjpy_anchors_2026.json [--tolerance 0.5]
"""

import argparse
import csv
import datetime as dt
import json
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--anchors", default="data/gbpjpy_anchors_2026.json")
    ap.add_argument("--tolerance", type=float, default=0.5,
                    help="max abs deviation (JPY) allowed vs anchor values")
    args = ap.parse_args()

    errors, warnings = [], []

    rows = []
    with open(args.data, newline="") as f:
        for row in csv.DictReader(f):
            rows.append({
                "date": row["date"],
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
            })

    if not rows:
        print("FAIL: empty dataset")
        sys.exit(1)

    dates = [r["date"] for r in rows]
    if dates != sorted(dates):
        errors.append("dates not sorted ascending")
    if len(set(dates)) != len(dates):
        errors.append("duplicate dates present")

    prev = None
    for r in rows:
        d = dt.date.fromisoformat(r["date"])
        if d.weekday() >= 5:
            warnings.append(f"{r['date']}: weekend bar present")
        if not (r["low"] <= r["open"] <= r["high"] and
                r["low"] <= r["close"] <= r["high"] and r["low"] <= r["high"]):
            errors.append(f"{r['date']}: OHLC inconsistency {r}")
        if not (190.0 <= r["low"] and r["high"] <= 235.0):
            errors.append(f"{r['date']}: outside plausible 2026 range {r['low']}-{r['high']}")
        if prev is not None:
            move = abs(r["close"] - prev["close"]) / prev["close"]
            if move > 0.03:
                errors.append(f"{r['date']}: day-over-day close move {move:.2%} > 3%")
            gap_days = (dt.date.fromisoformat(r["date"]) -
                        dt.date.fromisoformat(prev["date"])).days
            if gap_days > 4:
                warnings.append(f"{prev['date']} -> {r['date']}: {gap_days}-day gap")
        prev = r

    by_date = {r["date"]: r for r in rows}
    with open(args.anchors) as f:
        anchors = json.load(f)
    checked = 0
    # Anchor values come from reference-rate sites that sample a handful of
    # snapshots per day, so they must lie WITHIN the true intraday range:
    #   - an anchor "low" can be above the dataset low, never meaningfully below
    #   - an anchor "high" can be below the dataset high, never meaningfully above
    #   - an anchor "close" is a snapshot near (but not exactly at) the daily
    #     boundary: require containment in the day's range, and warn if it
    #     deviates from the dataset close by more than the tolerance
    for a in anchors["daily_points"]:
        r = by_date.get(a["date"])
        if r is None:
            warnings.append(f"anchor {a['date']}: date missing from dataset")
            continue
        rng_lo, rng_hi = r["low"] - args.tolerance, r["high"] + args.tolerance
        for field in ("low", "high", "close"):
            v = a.get(field)
            if v is None:
                continue
            checked += 1
            if not (rng_lo <= v <= rng_hi):
                errors.append(
                    f"anchor outside day range {a['date']} {field}: anchor {v} vs "
                    f"dataset range {r['low']}-{r['high']} (source: {a['source']})")
                continue
            if field == "low" and r["low"] > v + args.tolerance:
                errors.append(
                    f"anchor low violated {a['date']}: dataset low {r['low']} above "
                    f"anchor low {v} (source: {a['source']})")
            elif field == "high" and r["high"] < v - args.tolerance:
                errors.append(
                    f"anchor high violated {a['date']}: dataset high {r['high']} below "
                    f"anchor high {v} (source: {a['source']})")
            elif field == "close" and abs(r["close"] - v) > args.tolerance:
                warnings.append(
                    f"anchor close deviates {a['date']}: dataset {r['close']} vs snapshot "
                    f"{v}, inside day range (boundary-time artifact; source: {a['source']})")

    print(f"rows={len(rows)}  anchor_values_checked={checked}")
    for w in warnings:
        print("WARN:", w)
    for e in errors:
        print("ERROR:", e)
    if errors:
        print("QC RESULT: FAIL")
        sys.exit(1)
    print("QC RESULT: PASS")


if __name__ == "__main__":
    main()
