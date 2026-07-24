"""Fetch GBP/JPY daily BID and ASK candles from Dukascopy into
data/gbpjpy_dukascopy_daily.csv (the exact pipeline that produced the
committed dataset - regenerates it end to end).

Sources (datafeed.dukascopy.com must be in the network allowlist):
  - completed years : /GBPJPY/{year}/{SIDE}_candles_day_1.bi5  (one file/year)
  - current year    : completed months from /GBPJPY/{year}/{month0}/{SIDE}_candles_hour_1.bi5
                      current month from   /GBPJPY/{year}/{month0}/{day}/{SIDE}_candles_min_1.bi5
    (Dukascopy month folders are 0-based.)

bi5 format: LZMA stream of big-endian 24-byte records
  int32 time offset (seconds from the period start: year / month / day)
  int32 open, close, low, high  (price * 1000 for JPY pairs)
  float32 volume

Filtering (matches the committed dataset): keep Mon-Fri only (Saturdays are
flat placeholders, Sundays are thin 21-24 UTC sessions), drop zero-range
holiday placeholder rows. Days are UTC calendar days.

Usage: python3 tools/fetch_dukascopy_daily.py [--from-year 2014]
           [--to-date 2026-07-22] [--out data/gbpjpy_dukascopy_daily.csv]
"""

import argparse
import csv
import datetime as dt
import lzma
import os
import struct
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = "https://datafeed.dukascopy.com/datafeed"
SCALE = 1000.0   # set per symbol in main(): JPY quote = 1e3, else 1e5
REC = struct.Struct(">iiiiif")


def fetch(url, path, retries=4):
    """Download url to path; returns decompressed bytes or None (404/HTML)."""
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
    if raw[:1] == b"<":            # Dukascopy 404s are XHTML error pages
        return None
    try:
        return lzma.decompress(raw)
    except lzma.LZMAError:
        return None


def records(data):
    for off in range(0, len(data) - REC.size + 1, REC.size):
        t, o, c, lo, hi, vol = REC.unpack_from(data, off)
        yield t, o / SCALE, c / SCALE, lo / SCALE, hi / SCALE, vol


def merge(store, day, o, hi, lo, c, vol):
    cur = store.get(day)
    if cur is None:
        store[day] = [o, hi, lo, c, vol]
    else:
        cur[1] = max(cur[1], hi)
        cur[2] = min(cur[2], lo)
        cur[3] = c
        cur[4] += vol


SYMBOL = "GBPJPY"


def collect_side(side, from_year, to_date, cache):
    """Return {iso_date: [open, high, low, close, volume]} of UTC-day candles."""
    out = {}
    today = to_date
    for year in range(from_year, today.year + 1):
        base_dt = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        data = fetch(f"{BASE}/{year}/{side}_candles_day_1.bi5",
                     os.path.join(cache, f"{SYMBOL}_{side}_{year}.bi5"))
        if data is not None:
            for t, o, c, lo, hi, vol in records(data):
                d = (base_dt + dt.timedelta(seconds=t)).date().isoformat()
                out[d] = [o, hi, lo, c, vol]
            print(f"{year} {side}: yearly file, {sum(1 for k in out if k.startswith(str(year)))} days")
            time.sleep(0.3)
            continue
        # current year: completed months via hourly candles
        for m in range(0, today.month):
            mdata = fetch(f"{BASE}/{year}/{m:02d}/{side}_candles_hour_1.bi5",
                          os.path.join(cache, f"{SYMBOL}_{side}_h1_{year}_{m:02d}.bi5"))
            if mdata is not None:
                mbase = dt.datetime(year, m + 1, 1, tzinfo=dt.timezone.utc)
                for t, o, c, lo, hi, vol in records(mdata):
                    d = (mbase + dt.timedelta(seconds=t)).date().isoformat()
                    merge(out, d, o, hi, lo, c, vol)
                time.sleep(0.5)
                continue
            # month file missing (current month): per-day minute candles
            day = dt.date(year, m + 1, 1)
            while day.month == m + 1 and day <= today:
                if day.weekday() < 5:
                    ddata = fetch(f"{BASE}/{year}/{m:02d}/{day.day:02d}/{side}_candles_min_1.bi5",
                                  os.path.join(cache, f"{SYMBOL}_{side}_m1_{day.isoformat()}.bi5"))
                    if ddata is not None:
                        for t, o, c, lo, hi, vol in records(ddata):
                            merge(out, day.isoformat(), o, hi, lo, c, vol)
                    time.sleep(0.4)
                day += dt.timedelta(days=1)
            print(f"{year}-{m+1:02d} {side}: built from intraday files")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2014)
    ap.add_argument("--symbol", default="GBPJPY")
    ap.add_argument("--to-date", default="2026-07-22")
    ap.add_argument("--cache", default="/tmp/claude-0/-home-user-Naminori/"
                    "7d1b3223-4b72-5896-a528-3b8962c9ed8d/scratchpad/duka")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)
    to_date = dt.date.fromisoformat(args.to_date)
    global BASE, SCALE
    BASE = f"{BASE_URL}/{args.symbol}"
    SCALE = 1000.0 if args.symbol.upper().endswith("JPY") else 100000.0
    if args.out is None:
        args.out = os.path.join(ROOT, "data", f"{args.symbol.lower()}_dukascopy_daily.csv")

    globals()["SYMBOL"] = args.symbol
    bid = collect_side("BID", args.from_year, to_date, args.cache)
    ask = collect_side("ASK", args.from_year, to_date, args.cache)

    n_kept = 0
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "bid_open", "bid_high", "bid_low", "bid_close",
                    "ask_open", "ask_high", "ask_low", "ask_close",
                    "spread_close", "volume"])
        for d in sorted(set(bid) & set(ask)):
            if d > args.to_date or dt.date.fromisoformat(d).weekday() >= 5:
                continue
            bo, bh, bl, bc, bv = bid[d]
            ao, ah, al, ac, _ = ask[d]
            if bh == bl:               # zero-range holiday placeholder
                continue
            w.writerow([d, bo, bh, bl, bc, ao, ah, al, ac,
                        round(ac - bc, 4), round(bv, 2)])
            n_kept += 1
    print(f"wrote {n_kept} weekday bars to {args.out} (scale {SCALE:g})")


if __name__ == "__main__":
    main()
