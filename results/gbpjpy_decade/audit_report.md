# Independent Audit — Dukascopy Bid/Ask Decade Extension (2015–2026)

Auditor: independent session, 2026-07-23.
Scope: NEW work since the two prior audits — `tools/fetch_dukascopy_daily.py`,
`load_bidask_bars()` + bid/ask execution in `src/strategy.py`,
`tools/run_decade_backtest.py`, and `results/gbpjpy_decade/`.
All downloads, decodes, replays and recomputations below were performed by the
auditor with independent code; no project decode code was trusted.

## VERDICT

PASS with caveats. The decade result (Sharpe 0.101, +5.8%, maxDD 24.1%,
33 trades) reproduces byte-identically, the Dukascopy data is verified
bit-for-bit against fresh independent downloads/decodes, the bid/ask execution
model is conservative, and the near-zero Sharpe is honestly reported as
statistically indistinguishable from zero. Main caveats: the committed fetch
tool cannot regenerate the committed dataset (weekend filtering and the 2026
intraday aggregation were done by uncommitted ad-hoc code), and the 2026
stooq-vs-Dukascopy gap is partly a *signal-level* difference (a third June
trade fires on stooq bars but not on UTC bars), not only spreads/boundaries.

## 1. Tests

`python3 tests/test_strategy.py` → **ALL TESTS PASSED** (42 checks, including
the 5 new bid/ask fill tests: long pays ask, exit at bid, ask-based sizing,
short at bid, short cover pays ask).

## 2. Independent bi5 decode and data verification

Own decode (`lzma` + big-endian `>iiiiif`, price/1000, offset = seconds from
year start), files downloaded fresh by the auditor:

- **2014–2025 yearly daily files (BID+ASK)**: every one of the repo CSV's
  3,129 weekday rows matches the independent decode on all 9 fields
  (worst |error| 2.8e-14). The repo CSV = yearly weekday bars minus
  2 zero-volume New Year placeholders (2016-01-01, 2021-01-01, both flat
  O=H=L=C, vol 0 — correctly dropped). Saturdays are flat placeholders;
  Sundays (thin 21:00–24:00 UTC session) are dropped — see Concerns.
- **2026 (yearly file 404s at Dukascopy)**: independently rebuilt from
  auditor-downloaded monthly H1 files (Jan–Jun) and per-day M1 files (Jul),
  aggregated to UTC days. 145/145 repo rows match; only 2026-01-01 (dead
  holiday) differs in its open fields by ~0.37–0.48 due to placeholder
  ambiguity — immaterial (warmup region, no trade within weeks).
- **Internal consistency (2020 sample)**: 0 OHLC violations, ask_close ≥
  bid_close on all days, close-spread median 0.020, p90 0.111 (COVID).
- **COVID March 2020**: BID low **124.062 on 2020-03-18**, high 139.183 on
  2020-03-02 — matches the known GBPJPY crash to the ~124–126 area; spreads
  widen to 0.04–0.11 through the crash week. Plausible and internally
  consistent.
- **Stooq cross-check** (overlap 2024-09-02..2026-07-22, n=488):
  |bid_close − stooq close| median 0.089, p90 0.280, max 0.698 — consistent
  with the claimed "typically < ~0.3, different day boundary".
  |high|/|low| diffs median 0.009/0.019 — intraday extremes agree closely,
  as expected for boundary-only differences.

## 3. Bid/ask execution code review (src/strategy.py)

Verified in code and against all 33 decade trades:

- Long entry = `bid_close + spread_close` = **ask_close exactly** (all 33
  trade entries reconciled against the CSV to <0.0005).
- Sizing uses the **ask-entry → bid-stop distance**, so a stop-out loses
  exactly `risk_amt` including the spread → worst R = −1.0 by construction.
- Exits at **bid** (target = prior-20d bid-high line; stop at bid level;
  gap-through-stop fills at the worse real open). All 33 exit fills verified
  to lie within the exit-day bid range.
- Same-day stop+target resolves to **stop** (pessimistic ordering).
- Mark-to-market at **bid close** → entry-day equity immediately shows the
  spread as a drawdown (conservative).
- Shorts cover at ask (`fill + exit-day spread`) — correct direction, though
  this path is unused (frozen params: `allow_short=false`).
- No look-ahead introduced: the spread charged at entry is the entry day's
  own close spread (contemporaneous with the fill).

Nothing optimistic found. Two immaterial notes: (a) the short cover uses the
exit-day *close* spread as a proxy for the spread at the intraday fill moment
(unused path); (b) the boundary-target "room to trade" check compares the
target to the bid close rather than the ask entry — in the worst case this
admits a guaranteed-small-loss trade (pessimistic, not optimistic; requires
the target within one ~1–3 pip spread of the close). No slippage beyond
spread + gap-open modeling — standard for daily-bar backtests.

## 4. Reproduction

`python3 tools/run_decade_backtest.py` re-run → `summary.json`, `trades.csv`,
`equity.csv`, `per_year.csv` all **byte-identical** to the checked-in files.
Metrics exactly as claimed: Sharpe 0.101, total_return 0.0582, CAGR 0.0047,
maxDD 0.2406, 33 trades, win_rate 0.364, worst R −1.0.
Independent recomputation of Sharpe/total-return/maxDD from `equity.csv`
(own code): 0.101 / 0.0582 / 0.2406 — match.
`per_year.csv` reconciled by hand against `trades.csv`: 6/0/4/1/0/3/7/3/3/3/1/2
trades per year 2015–2026 and 12 wins total — all rows correct; the 2026 row
(+21.88%, Sharpe 2.53, 2 trades, 2 wins) matches the consistency claim.

## 5. Frozen params

`summary.json` params = `params_final.json` on every key it defines
(mode=swing, entry_lookback=20, swing_target=boundary, swing_wick_atr=0.5,
allow_short=false, risk_per_trade=0.03, atr_period=14, swing_gate_ema=200)
with the single documented override `spread_jpy: 0.03 → 0.0`. The remaining
keys (pb_ema, trend_ema, stop_atr_mult, trail_atr_mult) are engine defaults
that are inert in swing mode. `run_decade_backtest.py` contains no tuning
logic of any kind. Claim verified.

## 6. 3%-risk invariant

Equity replayed from 1,000,000 through all 33 trades: implied risk fraction
at each entry (`pnl/r_multiple ÷ equity-at-entry`) = **0.0300** for every
trade (max deviation 1.3e-5, pure CSV rounding). All 21 losers are exactly
−1.0R; no gap loss beyond −1R occurred in the decade (the engine supports
worse-than-stop gap fills; none triggered). Final equity 1,058,230.08 =
+5.82%, matching the equity curve.

## 7. Tick spread methodology

`tick_spread_check.csv` independently verified: the auditor re-downloaded
tick files (`>iiiff`, ask/bid ×1000) for Brexit day 2016-06-24 h00 and h14,
COVID Monday 2020-03-16 h00 and normal day 2021-05-12 h00 — tick counts and
medians reproduce **exactly** (12271/0.072, 0.038, 21670/0.054, 4628/0.013).
The `candle_close_spread` column matches the dataset's `spread_close` on all
12 sampled days.

Methodology assessment: fills are modeled at the UTC-midnight close, a
thin-liquidity time; charging the close-time snapshot spread matches the
around-midnight tick medians on normal days (0.023 vs 0.021, 0.016 vs 0.016,
0.013 vs 0.013 …) and **overcharges event days** (Brexit: 0.487 charged vs
0.072 tick median; 2024-08-05 carry-unwind: 0.043 vs 0.038) because the
close snapshot captures the event spread. On the one *actual* entry day
sampled (2026-02-17) the charge was 0.014 vs a 0.018 h00 tick median —
0.4 pips light, negligible against the ~3.7 JPY target distance. Overall the
model is fair on normal days and conservative on event days, as claimed.

## 8. Concerns

1. **Data pipeline not reproducible from the committed tool.** Running
   `tools/fetch_dukascopy_daily.py` verbatim (a) crashes on 2026 — the yearly
   file 404s, and `fetch()` saves the HTML error body (no `curl -f`) which
   then fails LZMA; (b) would include weekend/holiday placeholder rows that
   the committed CSV excludes. The 2026 daily bars were actually built from
   monthly-H1/per-day-M1 files, and the weekend/holiday filter applied, by
   ad-hoc code that was never committed. The *data itself is correct*
   (verified bit-for-bit above), but the committed tool does not produce it.
   Likewise no committed script generates `tick_spread_check.csv` or
   `validation.json`.
2. **Sunday sessions dropped.** 623 Sunday bars with real (21:00–24:00 UTC)
   ranges are excluded, so Sunday-evening extremes never enter ranges/ATR and
   stops cannot trigger during those 3 thin hours. Standard practice and
   minor, but live behavior can differ slightly around weekend gaps.
3. **Statistical weakness (honestly disclosed).** Sharpe 0.101 with bootstrap
   CI [−0.38, 0.58], NW t-stat 0.344, P(SR>0)=0.64 — indistinguishable from
   zero. Profits concentrate in 2022/2025/2026 yen-weakness regimes;
   2015–2021 is cumulatively negative. Only 33 trades in 11.5 years. The
   README/report label this correctly as regime-dependent.
4. **2026 consistency claim — fair, with a nuance.** Both datasets produce
   the same two large trades on identical dates (2026-01-26→02-04,
   2026-02-17→04-13). But the stooq run also has a third trade
   (2026-06-18→06-30, +2.0R) that never fires on UTC-day bars; that missing
   trade — a signal-level, vendor-sensitive difference — explains most of the
   +27.6% vs +21.9% gap, alongside the stated spread/sizing/boundary effects.
   Directional reproduction is genuine (both strongly positive, Sharpe 3.17
   vs 2.53), but signal counts are boundary-sensitive (3 vs 2 trades in
   7 months).
5. During this audit the working tree was committed as 779cb0d; the auditor
   verified the commit's `src/strategy.py`/test diff is exactly the code
   audited here.

## Final answers

(a) **Decade result trustworthy as computed: YES.** Exact reproduction,
independently verified data, conservative execution, correct 3% risk math,
and the near-zero Sharpe is reported as such rather than oversold.
(b) **"2026 reproduces directionally on independent data": FAIR**, provided
the third-trade nuance in Concern 4 is acknowledged.
(c) **Data/execution concerns:** pipeline reproducibility (Concern 1),
Sunday-session exclusion (2), midnight-fill liquidity assumption and
close-snapshot spread proxy (Section 7) — all minor or conservative in
effect; none overturn the headline numbers.
