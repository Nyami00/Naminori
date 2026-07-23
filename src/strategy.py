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

Data model: daily bars with high/low/close. The open is approximated by the
previous close (FX trades continuously except weekends); this approximation
is only used for gap handling on stop fills and is documented in the README.

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
    "entry_lookback": 20,   # new-wave breakout: close above prior N-day close high
    "trend_ema": 50,        # only trade in the direction of this EMA
    "atr_period": 14,
    "stop_atr_mult": 2.0,   # initial stop distance in ATRs (proxy for "below swing")
    "trail_atr_mult": 3.0,  # chandelier trailing stop distance in ATRs
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
    a = atr(bars, p["atr_period"])
    tr_ema = ema(closes, p["trend_ema"])
    hi_n = rolling_max(closes, p["entry_lookback"])
    lo_n = rolling_min(closes, p["entry_lookback"])

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

        open_proxy = bars[i - 1]["close"]

        # --- 1) manage open position intraday (stop computed from data <= i-1)
        if pos is not None:
            stop = pos["stop"]
            if pos["dir"] == 1 and b["low"] <= stop:
                fill = min(stop, open_proxy)  # gap through stop -> worse fill
                close_position(i, fill, "stop")
            elif pos["dir"] == -1 and b["high"] >= stop:
                fill = max(stop, open_proxy)
                close_position(i, fill, "stop")

        # --- 2) end-of-day: update trail from today's data (effective tomorrow)
        if pos is not None:
            if pos["dir"] == 1:
                pos["best_close"] = max(pos["best_close"], b["close"])
                cand = pos["best_close"] - p["trail_atr_mult"] * a[i]
                pos["stop"] = max(pos["stop"], cand)
            else:
                pos["best_close"] = min(pos["best_close"], b["close"])
                cand = pos["best_close"] + p["trail_atr_mult"] * a[i]
                pos["stop"] = min(pos["stop"], cand)

        # --- 3) signals on today's close
        long_sig = hi_n[i] is not None and b["close"] > hi_n[i] and b["close"] > tr_ema[i]
        short_sig = (p["allow_short"] and lo_n[i] is not None
                     and b["close"] < lo_n[i] and b["close"] < tr_ema[i])

        # wave-break flip: opposite breakout while holding
        if pos is not None:
            if pos["dir"] == 1 and short_sig:
                close_position(i, b["close"], "flip")
            elif pos["dir"] == -1 and long_sig:
                close_position(i, b["close"], "flip")

        # --- 4) entries at today's close
        if pos is None and (start_date is None or date >= start_date):
            sig = 1 if long_sig else (-1 if short_sig else 0)
            if sig != 0:
                stop_dist = p["stop_atr_mult"] * a[i]
                if stop_dist > 0:
                    risk_amt = p["risk_per_trade"] * equity
                    units = risk_amt / stop_dist
                    pos = {
                        "dir": sig, "units": units, "entry": b["close"],
                        "stop": b["close"] - sig * stop_dist,
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
    if eval_start is not None:
        # keep the last point before eval_start as the base so the first
        # evaluated day has a return
        idx = next((k for k, (d, _) in enumerate(eq) if d >= eval_start), 0)
        eq = eq[max(0, idx - 1):]
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

    trades = result["trades"]
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
