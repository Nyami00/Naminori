"""Fetch GBP/JPY hourly BID/ASK candles from Dukascopy (2014 - present).

Sources: monthly files /GBPJPY/{year}/{month0}/{SIDE}_candles_hour_1.bi5;
months whose file is missing (the current month) are built from per-day
minute files aggregated to hours. Output is gzip-compressed CSV with both
sides per hour (UTC): data/gbpjpy_dukascopy_h1.csv.gz

Usage: python3 tools/fetch_dukascopy_h1.py [--from-year 2014]
           [--to-date 2026-07-22] [--symbol GBPJPY] [--out <path>]
"""

import argparse
import csv
import datetime as dt
import gzip
import io
import lzma
import os
import struct
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCALE = 1000.0
REC = struct.Struct(">iiiiif")


def fetch(url, path, retries=4):
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        for attempt in range(retries):
            subprocess.run(["curl", "-sS", "--max-time", "60", url, "-o", path],
                           capture_output=True)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                break
            time.sleep(6 * (attempt + 1))
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return None
    raw = open(path, "rb").read()
    if raw[:1] == b"<":
        return None
    try:
        return lzma.decompress(raw)
    except lzma.LZMAError:
        return None


def records(data):
    for off in range(0, len(data) - REC.size + 1, REC.size):
        t, o, c, lo, hi, vol = REC.unpack_from(data, off)
        yield t, o / SCALE, c / SCALE, lo / SCALE, hi / SCALE, vol


def collect_side(symbol, side, from_year, to_date, cache, base_url):
    out = {}
    for year in range(from_year, to_date.year + 1):
        last_month = 11 if year < to_date.year else to_date.month - 1
        for m in range(0, last_month + 1):
            mdata = fetch(f"{base_url}/{year}/{m:02d}/{side}_candles_hour_1.bi5",
                          os.path.join(cache, f"{symbol}_{side}_h1_{year}_{m:02d}.bi5"))
            if mdata is not None:
                mbase = dt.datetime(year, m + 1, 1, tzinfo=dt.timezone.utc)
                for t, o, c, lo, hi, vol in records(mdata):
                    ts = mbase + dt.timedelta(seconds=t)
                    out[ts.isoformat()] = (o, hi, lo, c, vol)
                time.sleep(0.25)
                continue
            # current month: build hours from per-day minute files
            day = dt.date(year, m + 1, 1)
            while day.month == m + 1 and day <= to_date:
                ddata = fetch(f"{base_url}/{year}/{m:02d}/{day.day:02d}/{side}_candles_min_1.bi5",
                              os.path.join(cache, f"{symbol}_{side}_m1_{day.isoformat()}.bi5"))
                if ddata is not None:
                    dbase = dt.datetime(day.year, day.month, day.day,
                                        tzinfo=dt.timezone.utc)
                    for t, o, c, lo, hi, vol in records(ddata):
                        ts = (dbase + dt.timedelta(seconds=t)).replace(
                            minute=0, second=0)
                        key = ts.isoformat()
                        cur = out.get(key)
                        if cur is None:
                            out[key] = (o, hi, lo, c, vol)
                        else:
                            out[key] = (cur[0], max(cur[1], hi), min(cur[2], lo),
                                        c, cur[4] + vol)
                    time.sleep(0.3)
                day += dt.timedelta(days=1)
        print(f"{symbol} {side} {year}: cumulative {len(out)} hours", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2014)
    ap.add_argument("--to-date", default="2026-07-22")
    ap.add_argument("--symbol", default="GBPJPY")
    ap.add_argument("--cache", default="/tmp/claude-0/-home-user-Naminori/"
                    "7d1b3223-4b72-5896-a528-3b8962c9ed8d/scratchpad/duka_h1")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)
    to_date = dt.date.fromisoformat(args.to_date)
    out_path = args.out or os.path.join(
        ROOT, "data", f"{args.symbol.lower()}_dukascopy_h1.csv.gz")
    base_url = f"https://datafeed.dukascopy.com/datafeed/{args.symbol}"

    bid = collect_side(args.symbol, "BID", args.from_year, to_date, args.cache, base_url)
    ask = collect_side(args.symbol, "ASK", args.from_year, to_date, args.cache, base_url)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ts", "bid_open", "bid_high", "bid_low", "bid_close",
                "ask_close", "spread_close", "volume"])
    n = 0
    for ts in sorted(set(bid) & set(ask)):
        d = dt.datetime.fromisoformat(ts)
        if d.date() > to_date or d.weekday() >= 5:
            continue
        bo, bh, bl, bc, bv = bid[ts]
        _, _, _, ac, _ = ask[ts]
        if bh == bl and bv == 0:
            continue
        w.writerow([ts, bo, bh, bl, bc, ac, round(ac - bc, 4), round(bv, 2)])
        n += 1
    with gzip.open(out_path, "wt", newline="") as f:
        f.write(buf.getvalue())
    print(f"wrote {n} hourly bars to {out_path}")


if __name__ == "__main__":
    main()
