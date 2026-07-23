# Final Independent Validation Report — GBP/JPY Swing Strategy Backtest

Auditor: independent validation agent (clean context), 2026-07-23.
Scope: spec = annualized Sharpe >= 1.5 over Jan-Jul 2026, 3% account risk per trade, GBP/JPY.
Everything below was re-executed and re-derived by the auditor; no numbers were taken on trust.

## VERDICT

Backtest is clean and byte-reproducible on real QC'd data; the point-estimate spec (Sharpe 3.165 >= 1.5,
3% risk implemented exactly) is MET, but the forward-looking claim rests on 3 trades in a single regime
with selection-adjusted significance of only p ~= 0.05-0.07, so it is met **with qualifiers**.

## 1. Tests

`python3 tests/test_strategy.py` — ALL TESTS PASSED (22 assertions).
Gap: the suite covers breakout/pullback engine paths only; **zero swing-mode tests**
(`grep -c swing tests/test_strategy.py` = 0). The swing path was therefore audited manually (section 2)
and re-implemented independently (section 3).

## 2. Look-ahead audit of the swing code (src/strategy.py)

- (a) **Range lines are causal.** `rolling_max`/`rolling_min` (strategy.py:90-105) use slice
  `values[i-period:i]`, excluding the current bar; `rng_hi`/`rng_lo` (lines 155-156) are built from them.
  Warmup (line 163) is sufficient. Confirmed by hand-recomputation of all three entry signals.
- (b) **Same-bar entry is computable at the close.** The signal (lines 235-238) needs only day-t low,
  day-t close, and the prior-20-day lines; ATR[i] uses data through day t. Entry at day-t close
  (line 281). This is the standard "act in the final moments of the daily bar" idealization —
  an execution assumption, not look-ahead.
- (c) **Exit fills are pessimistically ordered.** Stop is checked (lines 191-198) before target
  (lines 202-207); same-day stop+target resolves to the stop. Entry-day exits are impossible because
  entries (section 4) run after the exit sections — conservative. Target fills exactly at the target
  even if price gaps beyond it — conservative.
  **One minor optimistic finding:** the stop gap-fill uses `open_proxy = prev close`
  (lines 188, 194) and ignores the CSV's real `open` column (loaded at line 45 but unused by the
  engine). For a swing position the fixed stop is always below the previous close of a surviving
  position, so `min(stop, open_proxy)` = stop: a true gap below the stop would fill AT the stop,
  never worse. Materiality for this result: **zero** — all 3 trades exited at targets and I verified
  the stop was never touched intraday during any hold. It should still be fixed (use the real open).
- (d) **Sizing meets the 3% spec.** `units = risk_per_trade*equity / stop_dist` (lines 277-279) with
  per-trade `stop_dist = close - (low - 0.5*ATR)`. Verified numerically: risk at entry is exactly
  3.0000% of current equity for all 3 trades (30,000.00 / 31,852.81 / 36,109.97 JPY). A stop-out
  realizes ~ -1.02R to -1.03R (3% + spread), confirmed empirically from the both-directions variant's
  stopped trades (-1.024/-1.032/-1.007/-1.033R) — within the documented gap allowance.

## 3. Trade arithmetic (fully independent re-implementation)

An auditor-written engine (own ATR, own rolling extremes, own fill walk) reproduces every figure:

| entry date | signal check (low < 20d-min-low, close back above) | entry=close | stop | target=20d-max-high | units = 0.03*eq/dist | exit | pnl (incl. 0.03 JPY/unit) | R |
|---|---|---|---|---|---|---|---|---|
| 2026-01-26 | 209.636 < 210.267, close 210.834 > 210.267 | 210.834 | 208.8949 | 214.856 (=2026-01-23 high) | 15471.04 | 2026-02-04 high 215.008 >= tgt | +61,760.39 | 2.059 |
| 2026-02-17 | 207.241 < 207.570, close 207.912 > 207.570 | 207.912 | 206.3259 | 215.008 (=2026-02-04 high) | 20082.85 | 2026-04-13 high 215.379 >= tgt | +141,905.40 | 4.455 |
| 2026-06-18 | 212.475 < 212.941, close 213.121 > 212.941 | 213.121 | 211.8963 | 215.605 | 29485.54 | 2026-06-30 high 215.774 >= tgt | +72,357.52 | 2.004 |

Stops never touched during any hold (checked bar by bar). Final equity 1,276,023.32 = +27.60%.
Independent Sharpe over the 144 eval-window daily returns: 3.165; maxDD 5.33%. All match the report.

## 4. Data audit (data/gbpjpy_daily_2026.csv, 209 bars 2025-10-01..2026-07-22)

- Coverage: 211 business days in span; only 2025-12-25 and 2026-01-01 missing (holidays). No weekend
  bars, no duplicate/unsorted dates.
- Continuity: open vs prior close median gap 0.011 (1.1 pips), mean 0.069 — consistent with genuine
  continuous FX quotes. Daily range median 1.20 yen, max 6.11 (2026-04-30, an evident event day that
  also shows in the anchors as the pre-July "2026 best" reversal day). Max daily close move 1.89% (<3%).
- QC: `python3 src/data_qc.py` reproduced — PASS, 22 anchor values checked, 1 benign warning
  (wise.com 2026-02-18 snapshot 207.697 inside day range 207.632-209.222).
- Spot checks vs independent anchors:
  - 2026-02-17: dataset low 207.241 / close 207.912 vs anchor low 207.7855 (flagged "2026 worst",
    same date) / close 207.93 (close diff 0.018). Dataset low 0.54 under the reference low is
    consistent with sparse-snapshot reference sampling vs true intraday extreme.
  - 2026-07-15: dataset high 219.648 = period max, vs anchor high 219.5016, same date.
  - 2026-04-29: dataset high 216.284 / close 216.125 vs anchor "2026 best (pre-July)" 216.1368.
  - 2026-07-22: close 218.152 vs anchor 218.1284. 2026-06-30 (trade-3 target day): close 215.559 vs
    anchor 215.594; anchor low 214.577 >= dataset low 214.189; anchor close just under the 215.605
    target makes the target touch (dataset high 215.774) plausible.
  - Mean 2026 close 213.23 vs anchor 180-day average 213.25.
- Caveats: single OHLC source (stooq scrape); the intraday highs/lows that drive both entries and
  target fills are corroborated only at a handful of anchor points; anchors were collected by the same
  research process (multi-site consistency and the USDJPY cross-check mitigate this).

## 5. Reproduction

- Backtest re-run (`--params params_final.json --eval-start 2026-01-01`): trades.csv, equity.csv and
  metrics **byte-identical** to results/gbpjpy_final (Sharpe 3.165, +27.6%, maxDD 5.33%, 3 trades).
- validate.py (seed 12345, n-boot 10000, block 5) reproduces committed validation.json exactly.
- Disclosed search history reproduced: breakout 8/8 train-negative (-1.95..-2.79); pullback
  -0.39..-1.12; swing both-dir train +3.02 / test ~ -2.15 (disclosed -1.80; direction confirmed,
  difference is metric-window convention); swing long-only train +3.48 / test +2.70 (disclosed +2.72);
  18-combo neighborhood full-period Sharpes min +1.44, ~14-16/18 >= 1.9. Config count ~34 confirmed.

## 6. Statistical judgment

**(a) 3 trades / 144 daily returns.** Trade-level inference is structurally impossible: with 3 trades
the sign-flip test's best attainable p is 1/2^3 = 0.125 and the observed p (~0.123) sits at that floor.
Daily-return inference: Newey-West t = 2.37, one-sided p ~= 0.009 — but that is pre-selection. The
effective sample is ~3 independent trade episodes inside one regime (long rebounds in an uptrend).
Can be claimed: correct implementation, risk spec honored, realized Sharpe 3.165 on real data.
Cannot be claimed: a stable edge estimated with useful precision.

**(b) ~34-config multiplicity.** Auditor ran a White's-Reality-Check-style bootstrap over the whole
family (all 34 configs' daily return series, recentered to zero mean, joint moving-block bootstrap,
block 15, B = 2000): under "no edge anywhere", the best-of-34 Sharpe has median 1.68, p90 2.97,
p95 3.33, p99 4.09. Selection-adjusted p ~= 0.042 for the family max (3.45) and ~= 0.068 for the
delivered config (3.165). Naive Bonferroni x35 on the daily-mean p gives 0.31 (over-conservative given
correlation). So: the result clears the pure-luck median easily but sits near the 90-95th percentile
of the luck distribution — **suggestive, not conclusive**. The walk-forward protocol was genuinely
followed (verified reproducible) and mitigates this, but mode-level selection still consumed the train
window ~34 times. The "all 18 neighbors positive" scan is weaker than it looks: K=14 and K=20 rows are
literally identical (same 3 trades) and all K=26 rows contain 1 trade — effectively ~7 distinct trade
sets, all riding the same 3 episodes. It rules out knife-edge parameter overfit, not regime dependence.

**(c) Long-only taint.** Long-only was introduced after observing the both-directions TEST failure, so
the test window was consumed at least twice; the +2.70 test Sharpe is not fully out-of-sample. It is
partially redeemed by the train window independently preferring long-only (+3.48 vs +3.02, verified),
but test-only evidence is individually insignificant anyway (NW t = 1.26, one-sided p = 0.104, ~0.21
after a x2 look adjustment). The direction restriction also aligns with the realized 2026 uptrend —
partly a regime bet. Useful lower bound: the untainted both-directions config still delivers
full-period Sharpe 1.512 (8 trades) — right at spec.

**(d) Block-size sensitivity.** Moving-block bootstrap of the realized daily returns (n = 10000,
seed 12345): block=5 -> CI90 [1.04, 5.51], P(Sharpe>1.5) = 0.90; block=15 -> [1.68, 5.07], 0.96;
block=30 -> [1.82, 4.54], 0.98. Larger blocks preserve the multi-week winning holds, tightening the
distribution — the shipped block=5 was the most conservative of the three. P(Sharpe>0) >= 0.993 in all
variants. Caveat: this bootstrap conditions on the realized path (path risk only); it cannot speak to
selection or regime risk. The trade-order MC is uninformative here (3 winners -> shuffle DD = 0).

## 7. Spec status

**Met, with qualifiers.** Sharpe 3.165 >= 1.5 as a point estimate on real, QC'd, byte-reproducible
data with the 3% risk spec implemented exactly. Honest forward-looking qualifier: *the strategy
performed as claimed on Jan-Jul 2026 and the evidence is suggestive of a real edge
(selection-adjusted p ~= 0.05-0.07; even the unselected both-directions variant reaches Sharpe ~1.5),
but with only 3 trades drawn from a single market regime the forward Sharpe >= 1.5 claim is
plausible-but-unproven and should not be relied on without live/incubation confirmation.*

## Recommended follow-ups
1. Add swing-mode unit tests (entry-day non-exit, stop-before-target ordering, boundary no-room skip).
2. Use the real `open` column for gap fills instead of `open_proxy` (removes the one optimistic path).
3. Incubate the frozen params_final.json on forward data; ~15-20 additional trades would allow
   trade-level inference that is currently impossible.
