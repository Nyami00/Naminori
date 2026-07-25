"""Leverage sensitivity for the frozen allocation, 2008-2026 (incl. the GFC).

The frozen config (sma250, equal weight, monthly, equities+gold) was chosen
on 2015-2021 and is NOT re-tuned here. Because its drawdown is roughly half
buy-and-hold's, it has room to be levered - this table shows exactly what
each notch of leverage buys and costs, and compares against buy-and-hold.

Backtested figures are price-only. The adjustment block is an explicit,
labelled ESTIMATE (not a backtest) using stated assumptions, because index
CFD/ETF total return differs from price return:
    equity dividend yield  2.0%/yr on the invested equity portion
    cash sleeve interest   2.0%/yr on the uninvested portion
    financing on borrowing 3.5%/yr on exposure above 1x
Change the constants below to see other rate environments.

Writes results/allocation/leverage_table.json
Usage: python3 tools/run_leverage_table.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from trend_portfolio import load_universe
from run_allocation_research import run_allocation, stats, buy_hold

SYMBOLS = ["USA500IDXUSD", "USATECHIDXUSD", "JPNIDXJPY", "GBRIDXGBP", "XAUUSD"]
START = "2008-01-01"
END = "2026-07-22"
LEVERAGES = (1.0, 1.25, 1.5, 1.75)
DIV_YIELD, CASH_RATE, FIN_RATE = 0.020, 0.020, 0.035
EQUITY_SHARE = 4.0 / 5.0          # 4 equity sleeves out of 5 instruments


def adjust(cagr, invested, lev):
    """Labelled estimate of total return from a price-only CAGR."""
    exposure = invested * lev
    div = DIV_YIELD * exposure * EQUITY_SHARE
    cash = CASH_RATE * max(0.0, 1.0 - exposure)
    fin = FIN_RATE * max(0.0, exposure - 1.0)
    return {"dividends": round(div, 4), "cash_interest": round(cash, 4),
            "financing": round(-fin, 4),
            "estimated_total_return": round(cagr + div + cash - fin, 4)}


def main():
    uni, dates = load_universe(os.path.join(ROOT, "data"), SYMBOLS)
    dates = [d for d in dates if "2007-01-01" <= d <= END]
    out = {"window": f"{START}..{END}", "symbols": SYMBOLS,
           "assumptions": {"dividend_yield": DIV_YIELD, "cash_rate": CASH_RATE,
                           "financing_rate": FIN_RATE},
           "rows": []}

    print(f"{'leverage':>9} {'cagr':>7} {'vol':>7} {'sharpe':>7} {'maxDD':>7} "
          f"{'calmar':>7} {'avg exp':>8} | {'est. total':>10}")
    for lev in LEVERAGES:
        cfg = {"sma": 250, "sizing": "equal", "symbols": SYMBOLS,
               "basket": "equity_gold", "leverage": lev}
        res = run_allocation(uni, dates, cfg, start_date=START)
        s = stats(res["equity_curve"])
        inv = sum(d["invested"] for d in res["days"]) / len(res["days"]) / lev
        adj = adjust(s["cagr"], inv, lev)
        row = {"leverage": lev, **s, "avg_invested_fraction": round(inv, 4),
               "avg_exposure": round(inv * lev, 4), **adj}
        out["rows"].append(row)
        print(f"{lev:>9.2f} {s['cagr']:>7.1%} {s['ann_vol']:>7.1%} "
              f"{s['sharpe']:>7.2f} {s['max_drawdown']:>7.1%} "
              f"{str(s['calmar']):>7} {inv*lev:>8.0%} | "
              f"{adj['estimated_total_return']:>10.1%}")

    bh_curve = buy_hold(uni, dates, SYMBOLS, start_date=START)
    b = stats(bh_curve)
    badj = adjust(b["cagr"], 1.0, 1.0)
    out["buy_and_hold"] = {**b, "avg_exposure": 1.0, **badj}
    print(f"{'buy&hold':>9} {b['cagr']:>7.1%} {b['ann_vol']:>7.1%} "
          f"{b['sharpe']:>7.2f} {b['max_drawdown']:>7.1%} {str(b['calmar']):>7} "
          f"{'100%':>8} | {badj['estimated_total_return']:>10.1%}")

    with open(os.path.join(ROOT, "results", "allocation", "leverage_table.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote results/allocation/leverage_table.json")


if __name__ == "__main__":
    main()
