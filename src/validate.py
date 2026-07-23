"""Statistical validation of backtest results: Monte Carlo + significance tests.

Designed to be run by an independent validation agent against the artifacts
produced by src/backtest.py (results/equity.csv, results/trades.csv,
results/summary.json). Pure standard library.

Tests performed
---------------
1. Sharpe ratio point estimate re-computed independently from equity.csv
   (must match summary.json within tolerance).
2. Moving-block bootstrap of daily returns (Monte Carlo): distribution of the
   annualized Sharpe under resampling; percentile CI and P(Sharpe > threshold).
3. One-sample significance test on daily returns: t-statistic with
   Newey-West (lag) adjusted standard error, plus a sign-flip randomization
   test on trade R-multiples (H0: trade expectancy = 0).
4. Trade-order Monte Carlo: shuffle trade sequence to obtain drawdown
   distribution (path risk of the same trade population).
5. Risk-spec compliance: every trade's intended risk equals the configured
   fraction of equity at entry (checked structurally from trades.csv:
   worst-case realized loss cannot exceed the risk fraction by more than the
   documented gap allowance).

Usage:
    python3 src/validate.py --results results/ --sharpe-target 1.5 \
        --risk-per-trade 0.03 [--n-boot 10000] [--seed 12345]

Output: results/validation.json and a human-readable report to stdout.
"""

import argparse
import csv
import json
import math
import os
import random


def load_equity(path):
    dates, values = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            dates.append(row["date"])
            values.append(float(row["equity"]))
    return dates, values


def load_trades(path):
    trades = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            trades.append({
                "pnl_jpy": float(row["pnl_jpy"]),
                "r_multiple": float(row["r_multiple"]),
                "dir": row["dir"],
                "entry_date": row["entry_date"],
                "exit_date": row["exit_date"],
                "reason": row["reason"],
            })
    return trades


def daily_returns(values):
    rets = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        rets.append((values[i] - prev) / prev if prev > 0 else 0.0)
    return rets


def annualized_sharpe(rets, periods=252):
    n = len(rets)
    if n < 2:
        return 0.0
    m = sum(rets) / n
    var = sum((r - m) ** 2 for r in rets) / (n - 1)
    sd = math.sqrt(var)
    return (m / sd) * math.sqrt(periods) if sd > 0 else 0.0


def max_drawdown(values):
    peak, dd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            dd = max(dd, (peak - v) / peak)
    return dd


def newey_west_tstat(rets, lags=5):
    """t-stat of mean daily return with HAC (Newey-West) standard error."""
    n = len(rets)
    if n < 10:
        return None
    m = sum(rets) / n
    e = [r - m for r in rets]
    gamma0 = sum(x * x for x in e) / n
    s = gamma0
    for l in range(1, lags + 1):
        w = 1.0 - l / (lags + 1.0)
        cov = sum(e[t] * e[t - l] for t in range(l, n)) / n
        s += 2.0 * w * cov
    se = math.sqrt(s / n) if s > 0 else 0.0
    return m / se if se > 0 else None


def block_bootstrap_sharpe(rets, n_boot, block, rng, periods=252):
    """Moving-block bootstrap distribution of annualized Sharpe."""
    n = len(rets)
    out = []
    if n < block + 1:
        return out
    starts_max = n - block
    for _ in range(n_boot):
        sample = []
        while len(sample) < n:
            s = rng.randint(0, starts_max)
            sample.extend(rets[s:s + block])
        out.append(annualized_sharpe(sample[:n], periods))
    out.sort()
    return out


def trade_shuffle_drawdown(trades, start_equity, n_boot, rng):
    """Distribution of max drawdown when the same trades occur in random order.

    Uses each trade's return-on-equity ratio so compounding is respected.
    """
    if not trades:
        return []
    # approximate per-trade return on equity from pnl sequence replay
    # (pnl_jpy was realized against a compounding equity; we normalize by
    # reconstructing equity forward in the original order)
    eq = start_equity
    ratios = []
    for t in trades:
        ratios.append(t["pnl_jpy"] / eq)
        eq += t["pnl_jpy"]
    dds = []
    for _ in range(n_boot):
        order = ratios[:]
        rng.shuffle(order)
        e, peak, dd = 1.0, 1.0, 0.0
        for r in order:
            e *= (1.0 + r)
            peak = max(peak, e)
            dd = max(dd, (peak - e) / peak)
        dds.append(dd)
    dds.sort()
    return dds


def signflip_pvalue(r_multiples, n_boot, rng):
    """Randomization test: H0 symmetric-around-zero trade outcomes."""
    if not r_multiples:
        return None
    obs = sum(r_multiples) / len(r_multiples)
    ge = 0
    for _ in range(n_boot):
        s = sum(x if rng.random() < 0.5 else -x for x in r_multiples)
        if s / len(r_multiples) >= obs:
            ge += 1
    return (ge + 1) / (n_boot + 1)


def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, max(0, int(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--sharpe-target", type=float, default=1.5)
    ap.add_argument("--risk-per-trade", type=float, default=0.03)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--block", type=int, default=5)
    ap.add_argument("--seed", type=int, default=12345)
    args = ap.parse_args()

    rng = random.Random(args.seed)

    with open(os.path.join(args.results, "summary.json")) as f:
        summary = json.load(f)
    dates, values = load_equity(os.path.join(args.results, "equity.csv"))
    trades = load_trades(os.path.join(args.results, "trades.csv"))

    eval_start = summary.get("eval_start")
    if eval_start:
        idx = next((k for k, d in enumerate(dates) if d >= eval_start), 0)
        keep = max(0, idx - 1)
        dates, values = dates[keep:], values[keep:]

    rets = daily_returns(values)
    sharpe = annualized_sharpe(rets)
    reported = summary["metrics"]["sharpe_annualized"]
    sharpe_matches = abs(sharpe - reported) < 0.02

    boot = block_bootstrap_sharpe(rets, args.n_boot, args.block, rng)
    p_above = (sum(1 for s in boot if s > args.sharpe_target) / len(boot)
               if boot else None)
    p_above0 = (sum(1 for s in boot if s > 0.0) / len(boot) if boot else None)

    nw_t = newey_west_tstat(rets)
    r_mults = [t["r_multiple"] for t in trades]
    p_sign = signflip_pvalue(r_mults, min(args.n_boot, 20000), rng)

    dds = trade_shuffle_drawdown(trades, summary.get("start_equity", 1_000_000.0)
                                 if "start_equity" in summary else 1_000_000.0,
                                 min(args.n_boot, 5000), rng)

    worst_r = min(r_mults) if r_mults else None
    # A single-trade loss should be ~ -1R (= risk_per_trade of equity).
    # Gap fills can exceed it; flag anything beyond 2R as a spec violation.
    risk_ok = worst_r is None or worst_r >= -2.0

    validation = {
        "recomputed_sharpe": round(sharpe, 3),
        "reported_sharpe": reported,
        "sharpe_recomputation_matches": sharpe_matches,
        "n_daily_returns": len(rets),
        "n_trades": len(trades),
        "monte_carlo": {
            "method": f"moving-block bootstrap, block={args.block}, n={args.n_boot}, seed={args.seed}",
            "sharpe_ci_5_95": [round(pct(boot, 0.05), 3) if boot else None,
                               round(pct(boot, 0.95), 3) if boot else None],
            "sharpe_median": round(pct(boot, 0.50), 3) if boot else None,
            "prob_sharpe_above_target": round(p_above, 4) if p_above is not None else None,
            "prob_sharpe_above_zero": round(p_above0, 4) if p_above0 is not None else None,
        },
        "significance": {
            "newey_west_tstat_daily_mean": round(nw_t, 3) if nw_t is not None else None,
            "signflip_pvalue_trade_expectancy": round(p_sign, 4) if p_sign is not None else None,
        },
        "trade_order_mc": {
            "max_dd_median": round(pct(dds, 0.50), 4) if dds else None,
            "max_dd_p95": round(pct(dds, 0.95), 4) if dds else None,
        },
        "risk_spec": {
            "risk_per_trade_config": args.risk_per_trade,
            "worst_trade_r_multiple": worst_r,
            "within_2R_gap_allowance": risk_ok,
        },
        "target": {
            "sharpe_target": args.sharpe_target,
            "point_estimate_meets_target": sharpe >= args.sharpe_target,
        },
    }

    with open(os.path.join(args.results, "validation.json"), "w") as f:
        json.dump(validation, f, indent=2)
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
