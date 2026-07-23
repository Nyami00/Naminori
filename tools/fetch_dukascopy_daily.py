"""Fetch GBP/JPY daily BID and ASK candles from Dukascopy (2014-2026).

Dukascopy serves one .bi5 file per instrument/year/side with all daily
candles: /datafeed/GBPJPY/{year}/BID_candles_day_1.bi5 (and ASK_...).
Format: LZMA-compressed records of 24 bytes, big-endian
  int32 time-offset (seconds from Jan 1 00:00 UTC of that year)
  int32 open, int32 close, int32 low, int32 high  (price * 1000 for JPY pairs)
  float32 volume
Writes data/gbpjpy_dukascopy_daily.csv with bid+ask OHLC per date and the
close-to-close spread. Requires datafeed.dukascopy.com in the allowlist.

Usage: python3 tools/fetch_dukascopy_daily.py [--from-year 2014] [--to-year 2026]
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
BASE = "https://datafeed.dukascopy.com/datafeed/GBPJPY"
SCALE = 1000.0  # JPY pairs are quoted with point = 0.001


def fetch(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    r = subprocess.run(["curl", "-sS", "--max-time", "60", url, "-o", path],
                       capture_output=True, text=True)
    ok = r.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 0
    if not ok and os.path.exists(path):
        os.remove(path)
    return ok


def decode_candles(path, year):
    raw = lzma.decompress(open(path, "rb").read())
    rec = struct.Struct(">iiiiif")
    out = {}
    base = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
    for off in range(0, len(raw) - rec.size + 1, rec.size):
        t, o, c, lo, hi, vol = rec.unpack_from(raw, off)
        day = (base + dt.timedelta(seconds=t)).date().isoformat()
        out[day] = (o / SCALE, hi / SCALE, lo / SCALE, c / SCALE, vol)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2014)
    ap.add_argument("--to-year", type=int, default=2026)
    ap.add_argument("--cache", default="/tmp/claude-0/-home-user-Naminori/"
                    "7d1b3223-4b72-5896-a528-3b8962c9ed8d/scratchpad/duka")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "gbpjpy_dukascopy_daily.csv"))
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)

    bid, ask = {}, {}
    for year in range(args.from_year, args.to_year + 1):
        for side, store in (("BID", bid), ("ASK", ask)):
            url = f"{BASE}/{year}/{side}_candles_day_1.bi5"
            path = os.path.join(args.cache, f"{side}_{year}.bi5")
            if not fetch(url, path):
                print(f"MISS {year} {side}")
                continue
            got = decode_candles(path, year)
            store.update(got)
            print(f"{year} {side}: {len(got)} days "
                  f"({min(got) if got else '-'} .. {max(got) if got else '-'})")
            time.sleep(0.3)

    days = sorted(set(bid) & set(ask))
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "bid_open", "bid_high", "bid_low", "bid_close",
                    "ask_open", "ask_high", "ask_low", "ask_close",
                    "spread_close", "volume"])
        for d in days:
            bo, bh, bl, bc, bv = bid[d]
            ao, ah, al, ac, _ = ask[d]
            w.writerow([d, bo, bh, bl, bc, ao, ah, al, ac,
                        round(ac - bc, 4), round(bv, 2)])
    print(f"wrote {len(days)} days to {args.out}")


if __name__ == "__main__":
    main()
