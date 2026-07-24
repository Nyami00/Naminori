"""Unit tests for the vol-targeted TSMOM portfolio engine.

Run:  python3 tests/test_trend_portfolio.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from trend_portfolio import (realised_vol, tsmom_signal, run_trend_portfolio,
                             metrics)

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f" FAIL {name} {detail}")
        FAILED.append(name)


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def synth(symbol, n, drift, vol=0.0, spread_frac=0.0001, seed=1):
    """Deterministic price path: mid_t = mid_0 * exp(drift*t + vol*wave)."""
    uni, mid = {}, 100.0
    dates = []
    import datetime as dt
    d = dt.date(2020, 1, 1)
    for i in range(n):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        iso = d.isoformat()
        wiggle = vol * math.sin(i * 0.7 + seed)
        mid = 100.0 * math.exp(drift * i + wiggle)
        uni[iso] = {"date": iso, "mid": mid, "spread_frac": spread_frac}
        dates.append(iso)
        d += dt.timedelta(days=1)
    return {symbol: uni}, dates


# ---------------------------------------------------------------------------
print("indicators")
check("realised_vol none when short", realised_vol([0.01] * 5, 60) is None)
# returns [+x,-x,...]: mean 0, sample var = n*x^2/(n-1) -> sd = x*sqrt(n/(n-1))
rv = realised_vol([0.01, -0.01] * 30, 60)
expected = 0.01 * math.sqrt(60 / 59) * math.sqrt(252)
check("realised_vol annualises (n-1 sample sd)", rv is not None and approx(rv, expected, 1e-9),
      f"{rv} vs {expected}")

up = [100.0 * (1.01 ** i) for i in range(300)]
check("tsmom +1 in uptrend", approx(tsmom_signal(up, (40, 120, 250)), 1.0))
down = [100.0 * (0.99 ** i) for i in range(300)]
check("tsmom -1 in downtrend", approx(tsmom_signal(down, (40, 120, 250)), -1.0))
mixed = up[:150] + [up[149] * (0.995 ** i) for i in range(1, 151)]
sig = tsmom_signal(mixed, (40, 120, 250))
check("tsmom mixed speeds gives intermediate value", -1.0 < sig < 1.0, f"{sig}")
check("tsmom None before warmup", tsmom_signal([100.0] * 10, (40, 120, 250)) is None)

# ---------------------------------------------------------------------------
print("portfolio: trend capture and sizing")
uni, dates = synth("UP", 400, 0.001, vol=0.004)
res = run_trend_portfolio(uni, dates, {"rebalance": "weekly", "target_vol": 0.10,
                                       "cost_multiplier": 0.0})
m = metrics(res)
check("uptrend produces positive return", m["total_return"] > 0, f"{m['total_return']}")
check("realised vol lands near the target",
      0.05 <= m["ann_vol"] <= 0.20, f"ann_vol {m['ann_vol']}")

# same path, opposite direction: a short trend must also profit
uni_d, dates_d = synth("DN", 400, -0.001, vol=0.004)
res_d = run_trend_portfolio(uni_d, dates_d, {"rebalance": "weekly", "cost_multiplier": 0.0})
check("downtrend also profits (short side works)",
      metrics(res_d)["total_return"] > 0, f"{metrics(res_d)['total_return']}")

# vol targeting: a 3x noisier instrument must get a materially smaller weight
uni_q, dq = synth("QUIET", 400, 0.001, vol=0.002)
uni_w, dw = synth("WILD", 400, 0.001, vol=0.012)
rq = run_trend_portfolio(uni_q, dq, {"cost_multiplier": 0.0})
rw = run_trend_portfolio(uni_w, dw, {"cost_multiplier": 0.0})
lev_q = rq["days"][-1]["gross_lev"]
lev_w = rw["days"][-1]["gross_lev"]
check("vol targeting shrinks the noisy sleeve", lev_w < lev_q,
      f"quiet {lev_q} vs wild {lev_w}")

# ---------------------------------------------------------------------------
print("portfolio: no look-ahead")
res_full = run_trend_portfolio(uni, dates, {"cost_multiplier": 0.0})
for cut in (250, 300, 350):
    res_cut = run_trend_portfolio(uni, dates[:cut], {"cost_multiplier": 0.0})
    same = all(approx(a[1], b[1], 1e-6)
               for a, b in zip(res_cut["equity_curve"], res_full["equity_curve"][:cut]))
    check(f"truncating at {cut} leaves earlier equity unchanged", same)

# ---------------------------------------------------------------------------
print("portfolio: costs")
res_free = run_trend_portfolio(uni, dates, {"rebalance": "daily", "cost_multiplier": 0.0})
res_cost = run_trend_portfolio(uni, dates, {"rebalance": "daily", "cost_multiplier": 1.0})
check("costs reduce return", metrics(res_cost)["total_return"] < metrics(res_free)["total_return"])

# exact cost accounting on the first rebalance: weight 0 -> target costs
# |target| * spread_frac * 0.5, divided by the number of sleeves
uni_c, dc = synth("C", 400, 0.001, vol=0.004, spread_frac=0.002)
res_c = run_trend_portfolio(uni_c, dc, {"rebalance": "weekly", "cost_multiplier": 1.0})
first = next(d for d in res_c["days"] if d["cost"] > 0)
res_c0 = run_trend_portfolio(uni_c, dc, {"rebalance": "weekly", "cost_multiplier": 0.0})
lev_then = next(d["gross_lev"] for d in res_c0["days"] if d["date"] == first["date"])
check("turnover charged at half the quoted spread",
      approx(first["cost"], lev_then * 0.002 * 0.5, 1e-12),
      f"cost {first['cost']} vs {lev_then * 0.002 * 0.5}")

# with a volatility that keeps changing, daily resizing must churn more than weekly
uni_v, dv = {}, None
import datetime as dt
prices, d0, mid = {}, dt.date(2020, 1, 1), 100.0
seq = []
for i in range(400):
    while d0.weekday() >= 5:
        d0 += dt.timedelta(days=1)
    amp = 0.002 if (i // 25) % 2 == 0 else 0.02      # alternating vol regimes
    mid = 100.0 * math.exp(0.001 * i + amp * math.sin(i * 1.3))
    prices[d0.isoformat()] = {"date": d0.isoformat(), "mid": mid, "spread_frac": 0.0005}
    seq.append(d0.isoformat())
    d0 += dt.timedelta(days=1)
uni_v = {"V": prices}
cost_daily = sum(d["cost"] for d in run_trend_portfolio(
    uni_v, seq, {"rebalance": "daily", "cost_multiplier": 1.0})["days"])
cost_weekly = sum(d["cost"] for d in run_trend_portfolio(
    uni_v, seq, {"rebalance": "weekly", "cost_multiplier": 1.0})["days"])
check("weekly rebalancing costs less than daily", cost_weekly < cost_daily,
      f"weekly {cost_weekly:.6f} vs daily {cost_daily:.6f}")

# leverage cap must bind
res_cap = run_trend_portfolio(uni_q, dq, {"target_vol": 0.50, "max_leverage": 1.5,
                                          "cost_multiplier": 0.0})
check("leverage cap binds", max(d["gross_lev"] for d in res_cap["days"]) <= 1.5 + 1e-9)

# ---------------------------------------------------------------------------
print("metrics")
fake = {"equity_curve": [("d1", 100.0), ("d2", 110.0), ("d3", 99.0)],
        "days": [{"date": "d1", "cost": 0.0, "gross_lev": 1.0},
                 {"date": "d2", "cost": 0.0, "gross_lev": 1.0},
                 {"date": "d3", "cost": 0.0, "gross_lev": 1.0}]}
mf = metrics(fake)
check("total return", approx(mf["total_return"], -0.01, 1e-9))
check("max drawdown", approx(mf["max_drawdown"], 0.1, 1e-9))

print()
if FAILED:
    print(f"{len(FAILED)} TEST(S) FAILED: {FAILED}")
    sys.exit(1)
print("ALL TESTS PASSED")
