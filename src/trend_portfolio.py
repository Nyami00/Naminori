"""Diversified time-series-momentum portfolio with volatility targeting.

A structurally different edge from the spring/rejection strategy in
strategy.py. Where that one waits for a rare setup and is flat 67% of the
time, this one is ALWAYS positioned in every instrument (long or short) and
sizes each position by inverse realised volatility. That combination -
time-series momentum plus vol targeting plus cross-sectional diversification
- is the standard managed-futures construction and is the only well-evidenced
way to reach a double-digit annual return at a tolerable drawdown.

Everything is pure standard library.

Execution model (no look-ahead):
  - signal_t and vol_t use closes up to and INCLUDING day t
  - the resulting weight is applied to day t+1's return
  - rebalancing happens on a fixed calendar (weekly/monthly); between
    rebalances the weight is held fixed
  - turnover costs the real half-spread of that instrument on that day

Sizing convention: weight w = notional exposure / equity. A weight of 1.0
means notional equal to equity (1x). Vol targeting sets
    w = signal * (target_vol / realised_vol)
capped at max_leverage, so a quiet instrument gets a bigger position than a
wild one and every sleeve contributes a similar risk budget.
"""

import csv
import math
import os


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

def load_pair(path):
    """Load a Dukascopy bid/ask daily CSV -> list of dicts with mid + spread."""
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            bid, ask = float(r["bid_close"]), float(r["ask_close"])
            mid = 0.5 * (bid + ask)
            if mid <= 0:
                continue
            rows.append({"date": r["date"], "mid": mid,
                         "spread_frac": max(0.0, (ask - bid)) / mid})
    rows.sort(key=lambda x: x["date"])
    return rows


def load_universe(data_dir, symbols):
    """Return {symbol: {date: {"mid":..,"spread_frac":..}}} plus sorted dates."""
    uni, all_dates = {}, set()
    for s in symbols:
        path = os.path.join(data_dir, f"{s.lower()}_dukascopy_daily.csv")
        if not os.path.exists(path):
            continue
        rows = load_pair(path)
        uni[s] = {r["date"]: r for r in rows}
        all_dates |= set(uni[s])
    return uni, sorted(all_dates)


# ---------------------------------------------------------------------------
# per-instrument signal and risk
# ---------------------------------------------------------------------------

def realised_vol(returns, window, annualise=252):
    """Annualised stdev of the last `window` returns (None if insufficient)."""
    if len(returns) < window:
        return None
    w = returns[-window:]
    m = sum(w) / len(w)
    var = sum((x - m) ** 2 for x in w) / (len(w) - 1)
    return math.sqrt(var * annualise)


def tsmom_signal(mids, lookbacks):
    """Average of sign(total return over L) across lookbacks; in [-1, 1].

    A single lookback gives a pure +/-1 flip. Averaging several speeds
    (short/medium/long) is the standard multi-speed construction: it damps
    whipsaws and removes the need to pick one "right" lookback.
    """
    votes = []
    for L in lookbacks:
        if len(mids) > L:
            votes.append(1.0 if mids[-1] > mids[-1 - L] else -1.0)
    if not votes:
        return None
    return sum(votes) / len(votes)


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------

DEFAULT = {
    "lookbacks": (40, 120, 250),   # ~2, 6, 12 months
    "vol_window": 60,              # realised-vol estimation window (days)
    "target_vol": 0.10,            # annualised vol target per sleeve
    "max_leverage": 3.0,           # cap on |w| per sleeve
    "rebalance": "weekly",         # "weekly" | "monthly" | "daily"
    "cost_multiplier": 1.0,        # 1.0 = pay the real half-spread on turnover
}


def _is_rebalance_day(prev_date, date, mode):
    if prev_date is None:
        return True
    if mode == "daily":
        return True
    if mode == "weekly":
        # ISO week change
        import datetime as dt
        return (dt.date.fromisoformat(date).isocalendar()[1]
                != dt.date.fromisoformat(prev_date).isocalendar()[1])
    return date[:7] != prev_date[:7]      # monthly


def run_trend_portfolio(uni, dates, params=None, start_date=None,
                        start_equity=1_000_000.0):
    """Run the vol-targeted TSMOM portfolio over the universe.

    Returns dict with equity_curve, per-day gross/net returns, turnover and
    the per-sleeve weight history.
    """
    p = dict(DEFAULT)
    if params:
        p.update(params)

    symbols = sorted(uni)
    hist_mid = {s: [] for s in symbols}       # closes seen so far
    hist_ret = {s: [] for s in symbols}       # daily returns seen so far
    weight = {s: 0.0 for s in symbols}        # weight applied to the NEXT day

    equity = start_equity
    curve, day_rows = [], []
    prev_date = None

    for date in dates:
        # ---- 1) realise today's P&L from yesterday's weights -------------
        gross = 0.0
        n_active = 0
        for s in symbols:
            row = uni[s].get(date)
            if row is None:
                continue
            prev_mid = hist_mid[s][-1] if hist_mid[s] else None
            if prev_mid:
                r = row["mid"] / prev_mid - 1.0
                hist_ret[s].append(r)
                gross += weight[s] * r
                n_active += 1
            hist_mid[s].append(row["mid"])

        gross /= max(1, len(symbols))          # equal capital split per sleeve

        # ---- 2) decide today's target weights (data up to and incl. today)
        cost = 0.0
        if _is_rebalance_day(prev_date, date, p["rebalance"]):
            for s in symbols:
                row = uni[s].get(date)
                if row is None:
                    continue
                sig = tsmom_signal(hist_mid[s], p["lookbacks"])
                vol = realised_vol(hist_ret[s], p["vol_window"])
                if sig is None or vol is None or vol <= 0:
                    target = 0.0
                else:
                    target = sig * min(p["target_vol"] / vol, p["max_leverage"])
                turn = abs(target - weight[s])
                # crossing the spread once costs half the quoted spread
                cost += turn * row["spread_frac"] * 0.5 * p["cost_multiplier"]
                weight[s] = target
            cost /= max(1, len(symbols))

        net = gross - cost
        equity *= (1.0 + net)
        if start_date is None or date >= start_date:
            curve.append((date, equity))
            day_rows.append({"date": date, "gross": gross, "cost": cost,
                             "net": net, "active": n_active,
                             "gross_lev": sum(abs(w) for w in weight.values())
                             / max(1, len(symbols))})
        prev_date = date

    return {"params": p, "equity_curve": curve, "days": day_rows,
            "symbols": symbols, "final_equity": equity}


def metrics(result, eval_start=None, periods=252):
    curve = result["equity_curve"]
    if eval_start:
        idx = next((i for i, (d, _) in enumerate(curve) if d >= eval_start), 0)
        curve = curve[max(0, idx - 1):]
    vals = [v for _, v in curve]
    if len(vals) < 3:
        return {}
    rets = [(vals[i] - vals[i - 1]) / vals[i - 1] for i in range(1, len(vals))]
    n = len(rets)
    mean = sum(rets) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (n - 1))
    sharpe = mean / sd * math.sqrt(periods) if sd > 0 else 0.0
    downside = [r for r in rets if r < 0]
    dsd = math.sqrt(sum(r * r for r in downside) / n) if downside else 0.0
    peak, dd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        dd = max(dd, (peak - v) / peak)
    years = n / periods
    total = vals[-1] / vals[0] - 1.0
    cagr = (1.0 + total) ** (1.0 / years) - 1.0 if years > 0 and total > -1 else 0.0
    days = {d["date"]: d for d in result["days"]}
    ev = [d for dt_, d in days.items() if (not eval_start or dt_ >= eval_start)]
    return {
        "days": n,
        "cagr": round(cagr, 4),
        "total_return": round(total, 4),
        "ann_vol": round(sd * math.sqrt(periods), 4),
        "sharpe": round(sharpe, 3),
        "sortino": round(mean / dsd * math.sqrt(periods), 3) if dsd > 0 else 0.0,
        "max_drawdown": round(dd, 4),
        "calmar": round(cagr / dd, 2) if dd > 0 else None,
        "avg_gross_leverage": round(sum(d["gross_lev"] for d in ev) / len(ev), 2) if ev else None,
        "cost_drag_annual": round(sum(d["cost"] for d in ev) / years, 4) if ev and years else None,
    }
