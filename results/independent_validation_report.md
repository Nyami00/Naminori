# Independent Validation Report — Naminori GBP/JPY Backtest Pipeline

Auditor: independent validation agent (clean context, all checks re-executed from scratch)
Date: 2026-07-23
Scope: /home/user/Naminori @ branch `claude/gbpjpy-trading-strategy-qz2dfv` (no commits yet; audited working tree)

## Verdict

The pipeline is deterministic, internally consistent, free of look-ahead bias as far as
code review plus an empirical causality test can establish, and the 3%-per-trade risk
spec is correctly implemented. The Sharpe >= 1.5 target on real GBP/JPY remains
**UNVERIFIED** — no real GBP/JPY daily series exists in this workspace, and all
performance numbers on disk are either synthetic-data machinery tests or a
wrong-instrument (USD/JPY, close-only) demonstration with negative performance.

## 1. Unit tests

`python3 tests/test_strategy.py` → **28/28 checks pass, exit code 0** ("ALL TESTS PASSED").
Coverage includes hand-computed ATR/EMA values, exact stop math (Wilder ATR 19/14 on the
breakout bar), exact -30,000 JPY = 3% loss sizing, gap-fill behavior, trailing-stop
ratchet, short symmetry, spread booking, and metrics formulas. The tests are genuine
(hand-derived expectations, not snapshots of engine output).

## 2. Look-ahead / bias review of src/strategy.py

Verified correct (file: /home/user/Naminori/src/strategy.py):

- **rolling_max/rolling_min exclude the current bar** (lines 90-105): window is
  `values[i-period:i]`. Confirmed by unit test and by reading. Entry requires
  `close[i] > max(closes[i-N..i-1])` — no same-bar contamination (line 201).
- **Trail update timing is correct** (lines 179-198): the intraday stop check for day i
  (step 1, lines 180-187) uses the stop last updated at the END of day i-1; the trail is
  ratcheted only afterwards (step 2, lines 189-198) using day i's close and ATR, so a
  level computed from day-i data can never trigger during day i. Matches the docstring
  contract.
- **Initial stop uses ATR[i] at entry** (line 216) — ATR through the entry bar's close,
  which is known at the close-of-day entry time. Causal.
- **Empirical causality test (run by auditor): PASS.** Re-running the backtest on data
  truncated at 4 different cut points (bars 120/150/180/200) produced byte-identical
  closed trades and identical open-position state on every common prefix. Any
  future-data leak would have broken this.
- **EMA/ATR are strictly causal recursions**; `load_bars` sorts ISO dates so ordering is
  safe (line 50).

Findings (execution-realism assumptions, not look-ahead bugs — all documented in
docs/methodology.md section 3/6, but material for interpreting any future real-data
result):

- **F1. Same-bar close fill (line 201 → 213-225):** the entry signal is computed from
  day t's close and filled AT day t's close (zero latency). Implementable in continuous
  FX but mildly optimistic; a next-open fill variant would be more conservative. Same
  applies to `flip` exits (lines 207-210).
- **F2. Open proxy ignores the real open column (line 177):** gap fills use
  `bars[i-1]["close"]` as the open proxy even though `load_bars` reads an `open` column.
  For the synthetic data open == prev close exactly, so no effect there; for real data
  with weekend gaps this can understate Monday stop slippage. Documented approximation,
  but the engine should prefer the actual open when a genuine one is available.
- **F3. Close-only bars (USD/JPY reference) give optimistic stop fills:** with
  open=high=low=close, `fill = min(stop, prev_close)` books a stop-level fill even
  though the only tradable price that day was the (worse) close. Acknowledged in
  tools/run_usdjpy_reference.py's docstring; results are negative anyway, so this
  optimism does not flatter the pipeline.
- **F4. No notional cap:** `units = risk/stopdist` implies leverage 1.7-1.9x on the
  synthetic run but up to **7.39x** on the USD/JPY reference (degenerate low-ATR bars).
  Legal under 25x JP retail margin but margin requirements are unmodeled; in a very
  low-ATR regime sizing could balloon.
- **F5. Swap/rollover interest not modeled** (documented, claimed conservative for 2026
  GBP/JPY longs — not verifiable offline).

## 3. Risk-spec (3% per trade) verification

Code (lines 216-225): `risk_amt = 0.03 * equity` (realized equity at entry — correct,
only one position at a time), `units = risk_amt / (2.0 * ATR)`, stop at
`entry ± stop_dist`. Spread is excluded from sizing, so a stop-out loses
risk_amt + spread → r slightly below -1.

Empirical audit of both trade logs (equity replayed trade-by-trade):

- results/synthetic_demo/trades.csv (6 trades): every loser in [-1.009, -0.524] R;
  implied risk amount / (3% of equity-at-entry) = 0.9998-1.0004 on every trade; worst
  single-trade equity loss = **-3.027%** of equity at entry.
- results/usdjpy_reference/trades.csv (7 trades): every loser in [-1.015, -0.076] R;
  ratio 0.9935-1.0005; worst equity loss = -3.044%.
- No trade anywhere near the -2R violation threshold. Overshoot beyond -1.000R is fully
  explained by the round-trip spread booked at exit. **COMPLIANT.**

## 4. Reproducibility / determinism

All regenerated by the auditor and compared by md5 to the pre-existing artifacts:

| Artifact | Result |
|---|---|
| data/SYNTHETIC_demo_gbpjpy.csv (tools/make_synthetic_demo.py, seed 20260101) | md5 identical (72b9c683...) |
| results/synthetic_demo/{summary.json,trades.csv,equity.csv} | byte-identical |
| results/synthetic_demo/validation.json re-run with stored settings (n=5000, seed 12345) | byte-identical |
| results/usdjpy_reference/{summary.json,trades.csv,equity.csv} | byte-identical |

Independent Sharpe recomputation (auditor's own code, straight from equity.csv, not
validate.py): **1.0333** vs reported 1.033 — match. Max drawdown 0.0875 — match. Days
n=145 equals the weekday count Jan 1-Jul 22 2026 — correct. Equity before eval-start is
flat at 1,000,000 (no pre-eval trade contamination). validate.py's own recomputation
also matches (`sharpe_recomputation_matches: true`).

Validation with the audited command (`--n-boot 10000`, seed 12345):
CI(5-95%) = [-1.195, 3.451], median 1.153, P(Sharpe>1.5)=0.397, P(Sharpe>0)=0.792,
NW t=0.734, sign-flip p=0.235, trade-order-MC DD median 4.55% / p95 7.44%,
worst r=-1.009, point estimate 1.033 < target → `point_estimate_meets_target: false`.

Statistical sanity: Lo (2002) iid analytic SE of the annualized Sharpe at n=145 is
~1.63 → 90% CI ≈ [-1.65, 3.72] (width 5.4). The bootstrap CI width (4.65) is the same
order and slightly narrower, as expected for a block-percentile CI. P-values and CI are
mutually coherent (nothing significant — exactly what a 145-day seeded random walk with
mild drift should produce). data_qc.py correctly **FAILS** the synthetic file against
the real anchors (exit code 1) — the guardrail against passing synthetic results off as
real works.

## 5. USD/JPY reference run

`python3 tools/run_usdjpy_reference.py` reproduces byte-identically:
98 weekday bars (2026-03-09..07-22), Sharpe **-1.066**, total return -5.93%,
max DD 10.78%, 7 trades, win rate 14.3%. Clearly labeled as NOT the target instrument.
The anchors file's cross-check arithmetic was independently verified: GBPJPY anchor /
Notion USDJPY close = 1.326 (2026-06-30) and 1.352 (2026-05-12), a plausible GBPUSD
range — the two real datasets are mutually consistent. The 17 anchor values themselves
cannot be re-verified offline (network blocked); they are trusted-but-unverifiable.

## 6. Monte Carlo / significance methodology notes

- **Block length 5 vs multi-week holds:** the moving-block bootstrap (block=5) preserves
  only ~1-week dependence; the strategy holds positions for weeks, so longer-range
  autocorrelation in strategy returns is destroyed under resampling. CI may be somewhat
  mis-calibrated; a stationary bootstrap or larger blocks would be a better robustness
  check.
- **Interpretation caveat:** `prob_sharpe_above_target` is the bootstrap resampling
  probability, not a posterior probability that the true Sharpe exceeds 1.5. Fine as a
  heuristic; should not be quoted as "probability the strategy works".
- **Sign-flip null is structurally violated:** trend-following R-multiples are skewed by
  design (losses capped near -1R, wins unbounded), so H0 "symmetric around zero" is not
  the natural null of zero expectancy. With n=6-7 trades the test is near-powerless
  anyway (granularity ~1/65 at 6 trades). Harmless here, but weak evidence either way.
- **Trade-order MC assumes exchangeable trades** (independence); with 6 trades the
  permutation space is tiny (720). Output is a path-risk illustration, not inference.
- **pct() uses truncated indexing** rather than interpolation — negligible bias at
  n_boot=10000, but nonstandard.
- **Latent bug (no effect here):** validate.py lines 209-211 try to read `start_equity`
  from summary.json, but backtest.py never writes that key, so the 1,000,000 fallback is
  always used. Wrong drawdown normalization would result if `--start-equity` were ever
  non-default. Recommend: persist `start_equity` in summary.json.
- **Sharpe uses rf=0** (documented). A JPY cash rate deduction would lower it slightly.
- **Multiple-testing:** stored results use DEFAULT_PARAMS (classic 20/50/14/2x/3x
  values), not the grid search; grid_search.py itself has a proper train/test split and
  a neighbor-collapse check, but if it is ever used, the bootstrap on the selected
  variant will overstate significance absent a selection correction (e.g. White's
  reality check). Also, n=145 days is simply too short to establish Sharpe >= 1.5 with
  confidence even with perfect data: the analytic SE (~1.6) means a true-1.5 strategy
  cannot be distinguished from zero over 7 months.

## 7. Spec status (auditor's independent statement)

- VERIFIED: engine correctness on hand-computed scenarios; causality (no look-ahead)
  by both code review and truncation experiment; 3%-risk sizing exact to <0.05%
  per trade with losses bounded near -1R; full pipeline determinism; validate.py's
  Sharpe recomputation; internally coherent MC outputs; QC guardrail rejects synthetic
  data against real anchors.
- VERIFIED (real data, wrong instrument): the strategy pipeline runs on the user's real
  USD/JPY closes and honestly reports negative performance (Sharpe -1.066).
- **UNVERIFIED: Sharpe >= 1.5 on real GBP/JPY Jan-Jul 2026.** No real GBP/JPY daily
  series exists in the workspace (network-blocked; 17 spot anchors are far too sparse to
  backtest). The synthetic run's Sharpe 1.033 is a machinery test on a seeded random
  walk — it says nothing about real GBP/JPY, and even it misses the 1.5 target with
  P(bootstrap Sharpe > 1.5) only ~0.40. Any claim that the target is met would be
  unsupported until data/gbpjpy_daily_2026.csv is supplied and passes data_qc.py.
