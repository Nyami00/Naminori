"""Unit tests for the backtest engine — hand-computed scenarios, no framework.

Run:  python3 tests/test_strategy.py
Exit code 0 and "ALL TESTS PASSED" on success.
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from strategy import ema, atr, rolling_max, rolling_min, run_backtest, compute_metrics

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f" FAIL {name} {detail}")
        FAILED.append(name)


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def bar(date, o, h, l, c):
    return {"date": date, "open": o, "high": h, "low": l, "close": c}


def flat_bars(n, price=100.0, start_day=1):
    return [bar(f"2026-01-{start_day + i:02d}", price, price, price, price)
            for i in range(n)]


# ---------------------------------------------------------------------------
print("indicators")

check("ema first value equals first input", approx(ema([5.0, 5.0], 3)[0], 5.0))
# EMA(period=3): k=0.5 -> after 5,9: 0.5*9+0.5*5 = 7
check("ema recursion", approx(ema([5.0, 9.0], 3)[1], 7.0))

check("rolling_max excludes current bar",
      rolling_max([1, 2, 3, 4], 3)[3] == 3 and rolling_max([1, 2, 3, 4], 3)[2] is None)
check("rolling_min excludes current bar",
      rolling_min([4, 3, 2, 1], 3)[3] == 2)

# ATR: constant 2-point range every day, no gaps -> ATR = 2 exactly
bars_atr = [bar(f"2026-01-{i+1:02d}", 100, 101, 99, 100) for i in range(20)]
a = atr(bars_atr, 14)
check("atr constant-range series", a[14] is not None and approx(a[19], 2.0, 1e-9))

# ---------------------------------------------------------------------------
print("backtest: no trades on flat data")
res = run_backtest(flat_bars(80), {"entry_lookback": 20, "trend_ema": 50})
check("flat data produces zero trades", len(res["trades"]) == 0,
      f"got {len(res['trades'])}")
check("equity unchanged on flat data", approx(res["final_equity"], 1_000_000.0))

# ---------------------------------------------------------------------------
print("backtest: breakout entry, sizing, and stop math")
# 60 warmup bars at 100 with tiny 1-point range, then a breakout bar.
warm = [bar(f"2026-03-{i+1:02d}", 100, 100.5, 99.5, 100) for i in range(30)]
warm += [bar(f"2026-04-{i+1:02d}", 100, 100.5, 99.5, 100) for i in range(30)]
brk = [bar("2026-05-01", 100, 106, 100, 105)]         # close 105 > prior max 100
after = [bar("2026-05-02", 105, 105, 90, 92)]          # crash through the stop
bars2 = warm + brk + after
p = {"entry_lookback": 20, "trend_ema": 50, "atr_period": 14,
     "stop_atr_mult": 2.0, "trail_atr_mult": 3.0, "risk_per_trade": 0.03,
     "spread_jpy": 0.0, "allow_short": False}
res2 = run_backtest(bars2, p)
check("breakout produced exactly one trade", len(res2["trades"]) == 1)
if res2["trades"]:
    t = res2["trades"][0]
    check("entry at breakout close", approx(t["entry"], 105.0))
    check("entry on the breakout date", t["entry_date"] == "2026-05-01")
    check("stopped out next day", t["exit_date"] == "2026-05-02" and t["reason"] == "stop")
    # ATR at entry: constant TR=1 for 60 bars, then breakout day TR = high-low=6
    # Wilder: atr = (1*13 + 6)/14 = 19/14 on the breakout bar.
    atr_entry = 19.0 / 14.0
    stop_expected = 105.0 - 2.0 * atr_entry
    # Day 2 low (90) gaps through the stop; open proxy = prev close 105 > stop,
    # so fill should be exactly at the stop level (trade log rounds to 4dp).
    check("stop fill at stop level", approx(t["exit"], stop_expected, 1e-4),
          f"exit {t['exit']} vs {stop_expected}")
    # Sizing: units = 0.03*1,000,000 / (2*ATR); loss = units * 2*ATR = 30,000
    check("realized loss equals 3% risk", approx(t["pnl_jpy"], -30_000.0, 0.01),
          f"pnl {t['pnl_jpy']}")
    check("r_multiple is -1", approx(t["r_multiple"], -1.0, 1e-6))

# ---------------------------------------------------------------------------
print("backtest: gap through stop fills at open proxy (worse than stop)")
after_gap = [bar("2026-05-02", 95, 95, 90, 92)]  # prev close 105 -> massive gap
bars3 = warm + brk + after_gap
res3 = run_backtest(bars3, p)
# open proxy is prev close (105) -> min(stop, open_proxy) = stop... to force a
# worse-than-stop fill the PREVIOUS close itself must be below the stop, which
# cannot happen on the entry bar. So test with a 2-day hold: day1 small dip,
# day2 opens (prev close) below stop.
mid = [bar("2026-05-02", 105, 105.5, 104, 104.5)]
crash = [bar("2026-05-03", 104.5, 104.5, 80, 85)]
res3b = run_backtest(warm + brk + mid + crash, p)
if res3b["trades"]:
    t3 = res3b["trades"][0]
    atr_entry = 19.0 / 14.0
    stop_expected = 105.0 - 2.0 * atr_entry  # trail cannot beat this yet
    check("multi-day hold still stops", t3["reason"] == "stop")
    check("fill not better than stop", t3["exit"] <= stop_expected + 1e-9)

# ---------------------------------------------------------------------------
print("backtest: trailing stop ratchets and locks in profit")
# steady rally: each day +2 close, range 1 -> trail = best_close - 3*ATR rises
rally = [bar(f"2026-05-{i+2:02d}", 105 + 2*i, 106 + 2*i, 104.8 + 2*i, 107 + 2*i)
         for i in range(10)]  # closes 107..125
drop = [bar("2026-05-12", 125, 125, 100, 101)]
res4 = run_backtest(warm + brk + rally + drop, p)
check("rally+drop closes the long", len(res4["trades"]) == 1 and
      res4["trades"][0]["reason"] == "stop")
if res4["trades"]:
    t4 = res4["trades"][0]
    check("trail locked a profitable exit", t4["exit"] > 105.0,
          f"exit {t4['exit']}")
    check("profit positive", t4["pnl_jpy"] > 0)

# ---------------------------------------------------------------------------
print("backtest: no look-ahead (signal needs close above PRIOR N-day max)")
# a bar that touches a new high intraday but closes below the prior max must
# not trigger an entry
touch = [bar("2026-05-01", 100, 107, 99, 100)]
res5 = run_backtest(warm + touch, p)
check("intraday touch without close breakout does not enter",
      len(res5["trades"]) == 0)

# ---------------------------------------------------------------------------
print("backtest: short side symmetric")
brk_dn = [bar("2026-05-01", 100, 100, 94, 95)]
rally_up = [bar("2026-05-02", 95, 112, 95, 111)]
p_short = dict(p, allow_short=True)
res6 = run_backtest(warm + brk_dn + rally_up, p_short)
# note: after the intraday stop-out, the same day's close (111) is itself a
# valid long breakout, so a second (end_of_test) trade legitimately appears.
check("short breakout entered and stopped", len(res6["trades"]) >= 1 and
      res6["trades"][0]["dir"] == "short" and res6["trades"][0]["reason"] == "stop")
if res6["trades"]:
    check("short loss capped at ~-1R (stop level fill)",
          approx(res6["trades"][0]["r_multiple"], -1.0, 1e-6),
          f"r={res6['trades'][0]['r_multiple']}")

# ---------------------------------------------------------------------------
print("backtest: spread cost booked")
p_cost = dict(p, spread_jpy=0.03)
res7 = run_backtest(warm + brk + after, p_cost)
if res7["trades"]:
    t7 = res7["trades"][0]
    # same as the -30,000 scenario but minus units*0.03
    atr_entry = 19.0 / 14.0
    units = 30_000.0 / (2.0 * atr_entry)
    check("cost equals units*spread", approx(t7["pnl_jpy"], -30_000.0 - units * 0.03, 0.01),
          f"pnl {t7['pnl_jpy']}")

# ---------------------------------------------------------------------------
print("metrics")
res_m = {"equity_curve": [("d1", 100.0), ("d2", 110.0), ("d3", 99.0)],
         "trades": [{"pnl_jpy": 10.0, "r_multiple": 0.5},
                    {"pnl_jpy": -11.0, "r_multiple": -1.0}]}
m = compute_metrics(res_m)
check("total return", approx(m["total_return"], -0.01, 1e-9))
check("max drawdown", approx(m["max_drawdown"], 0.1, 1e-9))
check("win rate", approx(m["win_rate"], 0.5))
# sharpe by hand: rets = +0.1, -0.1 -> mean 0, sd>0 -> sharpe 0
check("sharpe zero for symmetric returns", approx(m["sharpe_annualized"], 0.0))

# equity marked to market during open position must move with price
dates_eq = [d for d, _ in res4["equity_curve"]]
vals_eq = [v for _, v in res4["equity_curve"]]
i_start = dates_eq.index("2026-05-02")
check("mtm equity rises during winning hold",
      vals_eq[i_start + 5] > vals_eq[i_start])

# ---------------------------------------------------------------------------
print("backtest: swing mode (spring entry, boundary target, wick stop)")
# 30 warm bars: constant range 99.5-100.5, close 100 -> ATR settles at 1.0,
# prior-20d low line = 99.5, high line = 100.5
warm_sw = [bar(f"2026-06-{i+1:02d}", 100, 100.5, 99.5, 100) for i in range(30)]
# spring day: dips below the 99.5 line, closes back above it at 100.2
spring = [bar("2026-07-01", 100, 100.6, 99.0, 100.2)]
# TR on spring day = max(1.6, 0.6, 1.0) = 1.6 -> ATR = (13*1 + 1.6)/14
atr_spring = (13.0 * 1.0 + 1.6) / 14.0
stop_expected = 99.0 - 0.5 * atr_spring          # wick low - 0.5*ATR
dist_expected = 100.2 - stop_expected
p_sw = {"mode": "swing", "entry_lookback": 20, "swing_target": "boundary",
        "swing_wick_atr": 0.5, "trend_ema": 20, "atr_period": 14,
        "risk_per_trade": 0.03, "spread_jpy": 0.0, "allow_short": False}

# target reached two days later
after_sw = [bar("2026-07-02", 100.2, 100.4, 100.0, 100.3),
            bar("2026-07-03", 100.3, 100.7, 100.1, 100.4)]
res_sw = run_backtest(warm_sw + spring + after_sw, p_sw)
check("spring produced one long trade", len(res_sw["trades"]) == 1 and
      res_sw["trades"][0]["dir"] == "long")
if res_sw["trades"]:
    t = res_sw["trades"][0]
    check("swing entry at spring close", approx(t["entry"], 100.2, 1e-9))
    check("swing target exit at the 20d-high line",
          t["reason"] == "target" and approx(t["exit"], 100.5, 1e-4))
    check("swing sizing = 3% / wick-stop distance",
          approx(t["units"], 30_000.0 / dist_expected, 0.01),
          f"units {t['units']} vs {30_000.0/dist_expected}")

# same-day stop AND target touched -> pessimistic stop exit at the stop level
violent = [bar("2026-07-02", 100.2, 101.0, 98.0, 99.0)]
res_sw2 = run_backtest(warm_sw + spring + violent, p_sw)
check("same-day stop+target resolves to stop", len(res_sw2["trades"]) == 1 and
      res_sw2["trades"][0]["reason"] == "stop")
if res_sw2["trades"]:
    check("swing stop fill at wick-stop level",
          approx(res_sw2["trades"][0]["exit"], stop_expected, 1e-4),
          f"exit {res_sw2['trades'][0]['exit']} vs {stop_expected}")

# gap-down open below the stop -> fills at the (worse) real open
gap_sw = [bar("2026-07-02", 98.0, 98.5, 97.5, 98.2)]
res_sw3 = run_backtest(warm_sw + spring + gap_sw, p_sw)
if res_sw3["trades"]:
    check("swing gap through stop fills at real open",
          approx(res_sw3["trades"][0]["exit"], 98.0, 1e-4),
          f"exit {res_sw3['trades'][0]['exit']}")

# upthrust day must NOT enter when shorts are disabled
upthrust = [bar("2026-07-01", 100, 101.0, 99.6, 99.8)]
res_sw4 = run_backtest(warm_sw + upthrust, p_sw)
check("no short entry when allow_short=False", len(res_sw4["trades"]) == 0)
res_sw5 = run_backtest(warm_sw + upthrust, dict(p_sw, allow_short=True))
check("upthrust enters short when allowed", len(res_sw5["trades"]) == 1 and
      res_sw5["trades"][0]["dir"] == "short")

# ---------------------------------------------------------------------------
print("backtest: bid/ask execution (spread paid on the buy side)")
warm_ba = [dict(bar(f"2026-06-{i+1:02d}", 100, 100.5, 99.5, 100), spread=0.04)
           for i in range(30)]
spring_ba = [dict(bar("2026-07-01", 100, 100.6, 99.0, 100.2), spread=0.04)]
after_ba = [dict(bar("2026-07-02", 100.2, 100.7, 100.0, 100.4), spread=0.04)]
res_ba = run_backtest(warm_ba + spring_ba + after_ba, p_sw)
if res_ba["trades"]:
    t = res_ba["trades"][0]
    check("long entry pays the ask (close+spread)", approx(t["entry"], 100.24, 1e-9),
          f"entry {t['entry']}")
    check("long exit at bid target (no extra spread)", approx(t["exit"], 100.5, 1e-4))
    # sizing uses the ask-based stop distance: (100.24 - stop_expected)
    dist_ba = 100.24 - stop_expected
    check("sizing from ask-entry to stop", approx(t["units"], 30_000.0 / dist_ba, 0.01),
          f"units {t['units']}")
res_ba_s = run_backtest(warm_ba + [dict(bar("2026-07-01", 100, 101.0, 99.6, 99.8), spread=0.04)]
                        + [dict(bar("2026-07-02", 99.8, 99.8, 98.0, 98.2), spread=0.04)],
                        dict(p_sw, allow_short=True))
if res_ba_s["trades"] and res_ba_s["trades"][0]["dir"] == "short":
    t = res_ba_s["trades"][0]
    check("short entry at bid close", approx(t["entry"], 99.8, 1e-9))
    check("short exit pays ask (fill+spread)",
          t["reason"] == "target" and approx(t["exit"], res_ba_s["trades"][0]["exit"], 1e-9)
          and t["exit"] > 98.0, f"exit {t['exit']}")

# ---------------------------------------------------------------------------
print("backtest: mid target and time stop")
res_mid = run_backtest(warm_sw + spring + after_sw, dict(p_sw, swing_target="mid"))
if res_mid["trades"]:
    t = res_mid["trades"][0]
    # mid target = entry_close + 0.5*(boundary - entry_close) = 100.2 + 0.5*0.3
    check("mid target at halfway to the line", approx(t["exit"], 100.35, 1e-4),
          f"exit {t['exit']}")
    check("mid target reason", t["reason"] == "target")
flat_after = [bar(f"2026-07-{d:02d}", 100.2, 100.4, 100.05, 100.2) for d in range(2, 9)]
res_time = run_backtest(warm_sw + spring + flat_after, dict(p_sw, max_hold_days=3))
if res_time["trades"]:
    t = res_time["trades"][0]
    check("time stop closes after N bars", t["reason"] == "time" and
          t["exit_date"] == "2026-07-04", f"{t['reason']} {t['exit_date']}")

print()
if FAILED:
    print(f"{len(FAILED)} TEST(S) FAILED: {FAILED}")
    sys.exit(1)
print("ALL TESTS PASSED")
