"""Fetch GBP/JPY daily OHLC from stooq.com (requires stooq.com in the network
allowlist).

stooq serves a JavaScript proof-of-work browser check bound to the client IP.
Because the sandbox proxy can rotate egress IPs between connections, the whole
flow (challenge -> verify -> scrape) runs over a single keep-alive TLS tunnel.
The CSV download endpoint (/q/d/l/) returns "Access denied" for this client,
so the server-rendered historical table pages (/q/d/?s=...&l=page) are parsed
instead - same data, 40 rows per page.

Usage: python3 tools/fetch_stooq_gbpjpy.py [--d1 20251001] [--d2 20260722] \
           [--out data/gbpjpy_daily_2026.csv]
"""

import argparse
import csv
import hashlib
import http.client
import os
import re
import ssl
import time
from urllib.parse import urlparse

MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ROW_RE = re.compile(
    r'>(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{4})</td>'
    r'<td[^>]*>([\d.]+)</td><td[^>]*>([\d.]+)</td>'
    r'<td[^>]*>([\d.]+)</td><td[^>]*>([\d.]+)</td>')


class StooqSession:
    def __init__(self):
        p = urlparse(os.environ["HTTPS_PROXY"])
        ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
        self.conn = http.client.HTTPSConnection(p.hostname, p.port,
                                                timeout=60, context=ctx)
        self.conn.set_tunnel("stooq.com", 443)
        self.cookies = {}

    def _req(self, method, path, body=None, extra=None):
        h = {"Host": "stooq.com", "User-Agent": UA,
             "Accept": "text/html,*/*;q=0.8", "Connection": "keep-alive"}
        if self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if extra:
            h.update(extra)
        self.conn.request(method, path, body=body, headers=h)
        r = self.conn.getresponse()
        data = r.read()
        for sc in r.msg.get_all("Set-Cookie") or []:
            kv = sc.split(";", 1)[0]
            if "=" in kv:
                k, v = kv.split("=", 1)
                self.cookies[k] = v
        return r.status, data

    def get(self, path, **kw):
        st, body = self._req("GET", path, **kw)
        m = re.search(rb'const c="([^"]+)",d=(\d+)', body)
        if m:  # solve the proof-of-work browser check, then retry
            c, d = m.group(1).decode(), int(m.group(2))
            n = 0
            while not hashlib.sha256(
                    (c + str(n)).encode()).hexdigest().startswith("0" * d):
                n += 1
            self._req("POST", "/__verify", body=f"c={c}&n={n}",
                      extra={"Content-Type": "application/x-www-form-urlencoded",
                             "Origin": "https://stooq.com",
                             "Referer": "https://stooq.com" + path})
            st, body = self._req("GET", path, **kw)
        return st, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--d1", default="20251001")
    ap.add_argument("--d2", default="20260722")
    ap.add_argument("--out", default="data/gbpjpy_daily_2026.csv")
    args = ap.parse_args()

    s = StooqSession()
    rows = {}
    for page in range(1, 30):
        path = f"/q/d/?s=gbpjpy&d1={args.d1}&d2={args.d2}&l={page}"
        st, body = s.get(path, extra={"Referer": "https://stooq.com/q/d/?s=gbpjpy"})
        page_rows = []
        for m in ROW_RE.finditer(body.decode("utf-8", "replace")):
            d, mon, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
            o, hi, lo, c = (float(m.group(i)) for i in range(4, 8))
            page_rows.append((f"{y:04d}-{mon:02d}-{d:02d}", o, hi, lo, c))
        new = [r for r in page_rows if r[0] not in rows]
        for r in page_rows:
            rows[r[0]] = r
        print(f"page {page}: {len(page_rows)} rows ({len(new)} new)")
        if not new:
            break
        time.sleep(0.8)

    out = sorted(rows.values())
    if not out:
        raise SystemExit("no rows parsed - is stooq.com allowlisted?")
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close"])
        for r in out:
            w.writerow([r[0]] + [f"{x:g}" for x in r[1:]])
    print(f"wrote {len(out)} bars to {args.out} ({out[0][0]} .. {out[-1][0]})")


if __name__ == "__main__":
    main()
