"""Naminori GBP/JPY trend-following swing strategy and backtest engine.

Implementation notes
--------------------
The strategy is a systematic translation of the discretionary "wave riding"
(naminori) approach described publicly by the GBP/JPY specialist trader
Naminori-Akki (blog "Pound-Yen Naminori Nikki"): ride directional waves
identified from price structure (N-wave: successive higher highs / higher
lows), enter on breakouts that start a new wave leg, hold while the wave
lasts, and exit when the wave structure breaks. Position size is derived
from a fixed fraction of account equity at risk per trade.

Everything is pure standard-library Python (no third-party packages are
installable in this environment).

Data model: daily bars with open/high/low/close. The open is used for gap
handling on stop fills: a day that opens beyond the stop fills at the open,
i.e. worse than the stop level.

Execution model (no look-ahead):
  - Signals are computed on data up to and including day t's close and are
    filled at day t's close.
  - Protective stops are evaluated intraday from day t+1 onward using the
    day's high/low. A gap through the stop fills at the open proxy
    (previous close), i.e. worse than the stop level.
  - The trailing stop level used intraday on day t is computed from data up
    to day t-1 only.
"""

import csv
import math


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bars(csv_path):
    """Load daily bars from CSV with columns date,open,high,low,close."""
    bars = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            bars.append({
                "date": row["date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    bars.sort(key=lambda b: b["date"])
    return bars


# ---------------------------------------------------------------------------
# Indicators (all causal: value at index i uses data up to and including i)
# ---------------------------------------------------------------------------

def ema(values, period):
    out = [None] * len(values)
    k = 2.0 / (period + 1.0)
    prev = None
    for i, v in enumerate(values):
        prev = v if prev is None else v * k + prev * (1.0 - k)
        out[i] = prev
    return out


def atr(bars, period=14):
    """Wilder ATR from high/low/close."""
    out = [None] * len(bars)
    trs = []
    prev_atr = None
    for i, b in enumerate(bars):
        if i == 0:
            tr = b["high"] - b["low"]
        else:
            pc = bars[i - 1]["close"]
            tr = max(b["high"] - b["low"], abs(b["high"] - pc), abs(b["low"] - pc))
        if prev_atr is None:
            trs.append(tr)
            if len(trs) == period:
                prev_atr = sum(trs) / period
                out[i] = prev_atr
        else:
            prev_atr = (prev_atr * (period - 1) + tr) / period
            out[i] = prev_atr
    return out


def rolling_max(values, period):
    """Max of the previous `period` values, EXCLUDING the current index."""
    out = [None] * len(values)
    for i in range(len(values)):
        if i >= period:
            out[i] = max(values[i - period:i])
    return out


def rolling_min(values, period):
    """Min of the previous `period` values, EXCLUDING the current index."""
    out = [None] * len(values)
    for i in range(len(values)):
        if i >= period:
            out[i] = min(values[i - period:i])
    return out


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------

DEFAULT_PARAMS = {
    "mode": "breakout",     # "breakout" (new-wave Donchian), "pullback" (dip-buy in
                            # trend), or "swing" (failed-break rejection at range edges)
    "entry_lookback": 20,   # breakout: close above prior N-day close high;
                            # swing: range lookback for the support/resistance lines
    "pb_ema": 20,           # pullback: the dynamic support/resistance line being touched
    "trend_ema": 50,        # only trade in the direction of this EMA (breakout/pullback)
    "atr_period": 14,
    "stop_atr_mult": 2.0,   # initial stop distance in ATRs (breakout/pullback)
    "trail_atr_mult": 3.0,  # chandelier trailing stop distance in ATRs (breakout/pullback)
    "swing_wick_atr": 0.5,  # swing: stop buffer below the rejection wick, in ATRs
    "swing_target": "2r",   # swing: "2r" (two risk units) or "boundary" (opposite line)
    "risk_per_trade": 0.03, # fraction of current equity risked per trade
    "spread_jpy": 0.03,     # round-trip cost in JPY per unit of GBP (3 pips)
    "allow_short": True,
}


def run_backtest(bars, params=None, start_equity=1_000_000.0, start_date=None):
    """Run the wave-riding backtest. Returns dict with equity curve, trades, params.

    Long logic (short is symmetric):
      Entry  : close > max(close of prior `entry_lookback` days)
               and close > EMA(trend_ema)   -> buy at close.
      Stop   : entry - stop_atr_mult * ATR (intraday, from next day).
      Trail  : chandelier stop = highest close since entry - trail_atr_mult*ATR,
               ratcheting up only; evaluated intraday with previous day's level.
      Exit   : stop/trail hit intraday, or (wave break) close crossing back
               below the prior `entry_lookback`-day close low triggers a flip
               if shorts are allowed.
    """
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)

    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    a = atr(bars, p["atr_period"])
    tr_ema = ema(closes, p["trend_ema"])
    hi_n = rolling_max(closes, p["entry_lookback"])
    lo_n = rolling_min(closes, p["entry_lookback"])
    pb = ema(closes, p["pb_ema"])
    rng_hi = rolling_max(highs, p["entry_lookback"])   # swing: resistance line
    rng_lo = rolling_min(lows, p["entry_lookback"])    # swing: support line

    equity = start_equity
    pos = None  # dict(dir, units, entry, stop, best_close, entry_date, risk_amt)
    trades = []
    eq_curve = []  # (date, equity)

    warmup = max(p["entry_lookback"], p["trend_ema"], p["atr_period"]) + 1

    def close_position(i, price, reason):
        nonlocal equity, pos
        b = bars[i]
        pnl = (price - pos["entry"]) * pos["units"] * pos["dir"]
        cost = p["spread_jpy"] * pos["units"]  # full round-trip cost booked at exit
        equity += pnl - cost
        trades.append({
            "entry_date": pos["entry_date"], "exit_date": b["date"],
            "dir": "long" if pos["dir"] == 1 else "short",
            "entry": round(pos["entry"], 4), "exit": round(price, 4),
            "units": round(pos["units"], 2),
            "pnl_jpy": round(pnl - cost, 2),
            "r_multiple": round((pnl - cost) / pos["risk_amt"], 3),
            "reason": reason,
        })
        pos = None

    for i, b in enumerate(bars):
        date = b["date"]
        if i < warmup or a[i] is None:
            eq_curve.append((date, equity))
            continue

        open_proxy = b["open"]  # real open; gaps through a stop fill at the open

        # --- 1) manage open position intraday (stop computed from data <= i-1)
        if pos is not None:
            stop = pos["stop"]
            if pos["dir"] == 1 and b["low"] <= stop:
                fill = min(stop, open_proxy)  # gap through stop -> worse fill
                close_position(i, fill, "stop")
            elif pos["dir"] == -1 and b["high"] >= stop:
                fill = max(stop, open_proxy)
                close_position(i, fill, "stop")

        # --- 1b) swing positions: fixed profit target, checked after the stop
        # (pessimistic ordering when both are touched on the same day)
        if pos is not None and pos.get("target") is not None:
            tgt = pos["target"]
            if pos["dir"] == 1 and b["high"] >= tgt:
                close_position(i, tgt, "target")
            elif pos["dir"] == -1 and b["low"] <= tgt:
                close_position(i, tgt, "target")

        # --- 2) end-of-day: update trail from today's data (effective tomorrow)
        if pos is not None and pos.get("target") is None:
            if pos["dir"] == 1:
                pos["best_close"] = max(pos["best_close"], b["close"])
                cand = pos["best_close"] - p["trail_atr_mult"] * a[i]
                pos["stop"] = max(pos["stop"], cand)
            else:
                pos["best_close"] = min(pos["best_close"], b["close"])
                cand = pos["best_close"] + p["trail_atr_mult"] * a[i]
                pos["stop"] = min(pos["stop"], cand)

        # --- 3) signals on today's close
        if p["mode"] == "pullback":
            # dip-buy in an established up-wave: the day dips into the EMA
            # support zone and closes back above it (the pullback held);
            # symmetric for rallies into resistance during a down-wave
            uptrend = pb[i] > tr_ema[i] and b["close"] > tr_ema[i]
            downtrend = pb[i] < tr_ema[i] and b["close"] < tr_ema[i]
            long_sig = uptrend and b["low"] <= pb[i] and b["close"] >= pb[i]
            short_sig = (p["allow_short"] and downtrend
                         and b["high"] >= pb[i] and b["close"] <= pb[i])
        elif p["mode"] == "swing":
            # failed break of a range edge: intraday push beyond the prior
            # K-day extreme that closes back inside the range (spring /
            # upthrust - the systematic form of the double-bottom / double-top
            # rejection at a horizontal line)
            long_sig = (rng_lo[i] is not None and b["low"] < rng_lo[i]
                        and b["close"] > rng_lo[i])
            short_sig = (p["allow_short"] and rng_hi[i] is not None
                         and b["high"] > rng_hi[i] and b["close"] < rng_hi[i])
        else:
            long_sig = hi_n[i] is not None and b["close"] > hi_n[i] and b["close"] > tr_ema[i]
            short_sig = (p["allow_short"] and lo_n[i] is not None
                         and b["close"] < lo_n[i] and b["close"] < tr_ema[i])

        # wave-break exits while holding (swing mode exits only via stop/target)
        if pos is not None and p["mode"] != "swing":
            if p["mode"] == "pullback":
                # the wave is broken when price closes through the trend EMA
                if pos["dir"] == 1 and b["close"] < tr_ema[i]:
                    close_position(i, b["close"], "trend_break")
                elif pos["dir"] == -1 and b["close"] > tr_ema[i]:
                    close_position(i, b["close"], "trend_break")
            else:
                # breakout mode: opposite breakout while holding -> flip
                if pos["dir"] == 1 and short_sig:
                    close_position(i, b["close"], "flip")
                elif pos["dir"] == -1 and long_sig:
                    close_position(i, b["close"], "flip")

        # --- 4) entries at today's close
        if pos is None and (start_date is None or date >= start_date):
            sig = 1 if long_sig else (-1 if short_sig else 0)
            target = None
            if sig != 0 and p["mode"] == "swing":
                # stop just beyond the rejection wick; target from structure
                wick = b["low"] if sig == 1 else b["high"]
                stop_level = wick - sig * p["swing_wick_atr"] * a[i]
                stop_dist = abs(b["close"] - stop_level)
                if p["swing_target"] == "boundary":
                    target = rng_hi[i] if sig == 1 else rng_lo[i]
                    if (target - b["close"]) * sig <= 0:
                        sig = 0  # opposite line already passed; no room to trade
                else:
                    target = b["close"] + sig * 2.0 * stop_dist
            elif sig != 0:
                stop_dist = p["stop_atr_mult"] * a[i]
                stop_level = b["close"] - sig * stop_dist
            if sig != 0 and stop_dist > 0:
                risk_amt = p["risk_per_trade"] * equity
                units = risk_amt / stop_dist
                pos = {
                    "dir": sig, "units": units, "entry": b["close"],
                    "stop": stop_level, "target": target,
                    "best_close": b["close"], "entry_date": date,
                    "risk_amt": risk_amt,
                }

        # --- 5) mark to market
        mtm = equity
        if pos is not None:
            mtm += (b["close"] - pos["entry"]) * pos["units"] * pos["dir"]
        eq_curve.append((date, mtm))

    # close any open position at the last close so results are fully realized
    if pos is not None:
        close_position(len(bars) - 1, bars[-1]["close"], "end_of_test")
        eq_curve[-1] = (bars[-1]["date"], equity)

    return {"params": p, "equity_curve": eq_curve, "trades": trades,
            "final_equity": equity, "start_equity": start_equity}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(result, trading_days_per_year=252, eval_start=None):
    eq = result["equity_curve"]
    trades = result["trades"]
    if eval_start is not None:
        # keep the last point before eval_start as the base so the first
        # evaluated day has a return; trade stats cover the same window
        idx = next((k for k, (d, _) in enumerate(eq) if d >= eval_start), 0)
        eq = eq[max(0, idx - 1):]
        trades = [t for t in trades if t["entry_date"] >= eval_start]
    values = [v for _, v in eq]
    rets = []
    for j in range(1, len(values)):
        prev = values[j - 1]
        rets.append((values[j] - prev) / prev if prev > 0 else 0.0)

    n = len(rets)
    mean_r = sum(rets) / n if n else 0.0
    var = sum((r - mean_r) ** 2 for r in rets) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    sharpe = (mean_r / sd) * math.sqrt(trading_days_per_year) if sd > 0 else 0.0

    downside = [r for r in rets if r < 0]
    dvar = sum(r * r for r in downside) / n if n else 0.0
    dsd = math.sqrt(dvar)
    sortino = (mean_r / dsd) * math.sqrt(trading_days_per_year) if dsd > 0 else 0.0

    peak, max_dd = values[0] if values else 0.0, 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)

    wins = [t for t in trades if t["pnl_jpy"] > 0]
    total_ret = values[-1] / values[0] - 1.0 if values and values[0] > 0 else 0.0
    years = n / trading_days_per_year if n else 0.0
    cagr = (1.0 + total_ret) ** (1.0 / years) - 1.0 if years > 0 and total_ret > -1 else 0.0

    return {
        "days": n,
        "total_return": round(total_ret, 4),
        "cagr": round(cagr, 4),
        "sharpe_annualized": round(sharpe, 3),
        "sortino_annualized": round(sortino, 3),
        "max_drawdown": round(max_dd, 4),
        "num_trades": len(trades),
        "win_rate": round(len(wins) / len(trades), 3) if trades else None,
        "avg_r_multiple": round(sum(t["r_multiple"] for t in trades) / len(trades), 3) if trades else None,
        "best_r": max((t["r_multiple"] for t in trades), default=None),
        "worst_r": min((t["r_multiple"] for t in trades), default=None),
    }
