# C7 pre-registration — fx_carry_vol_filtered (the M4 revival family)

Written 2026-07-07, BEFORE any carry-conditioned analysis of this repo's
forex data. The M1 bars (2021-2026, EURUSD/GBPUSD/AUDUSD) have been used by
prior rounds for breakout/mean-reversion/TSMOM — never conditioned on
interest differentials. The spec below is frozen blind, same contract as
reports/m3_preregistration.md: dated additions only, deviation voids the
round, 2 failed rounds kill the family.

GOVERNANCE, stated plainly: the standing M4 rule says "no fourth ad-hoc
forex family — only a-priori hypotheses on tick data." Carry is a-priori
(the documented institutional FX premium: Koijen et al. 2018 carry;
Brunnermeier et al. carry crashes; C7 in the strategy research doc) and
daily-horizon, so it does not need ticks — but running it is the FOUNDER's
call because it reopens the parked forex fork. This document makes that a
one-word decision. Pre-registration is binding once the round runs.

## Frozen spec

Universe: EURUSD, GBPUSD, AUDUSD daily bars (aggregated from the histdata
M1 already on disk, 22:00 UTC day boundary).

Signal (per pair XXXUSD, evaluated daily on data through t-1):
  diff_t = 3m rate(XXX) - 3m rate(USD), annualized, latest published value.
  Direction: long XXXUSD when diff_t > +thresh, short when < -thresh,
  flat inside the band. Grid: thresh in {0, 50, 100} bps annualized.
Vol filter (carry-crash guard): flat when trailing 20d realized vol of the
  pair exceeds its trailing 1y q-quantile. Grid: q in {none, 0.80}.

Execution model: position changes only (signal flips/band entries) pay
spread+commission+slippage at the repo cost model's conservative values;
positions persist otherwise (expected holding: weeks-months).

Swap model — the honest killer, pinned before analysis: retail brokers pay
carry as SWAP with a markup. Daily accrual = interbank differential minus
markup m, with m in {0.5%, 1.0%, 1.5%}/yr pre-registered as scenarios.
THE GATE IS EVALUATED AT m = 1.0%. The 0.5% and 1.5% panels are reported,
non-gating. (The demo gate later replaces this model with the actual
broker's swap table — that recalibration is already design-doc law.)

Walk-forward: train 500 trading days / test 120, rolled by 120 (the round-1
scheme at daily frequency); optimize the (thresh, q) grid by after-cost net
on train, freeze, evaluate on test.

GATE (episode-based, deviation from the 100-trade floor documented exactly
as the funding round did — carry episodes span weeks): >= 20 pooled OOS
episodes across the 3 pairs, mean episode net > 0 at m=1.0%, t >= 2.0,
window stability >= 0.6. Kill: standing 2-round rule.

## Data dependency

Daily/monthly 3m (or policy-proxy) rates for USD, EUR, GBP, AUD —
scripts/fetch_rates_fred.py fetches and caches; coverage reported by the
script (QA only, no return analysis). Gaps in any leg shrink the universe
for that period rather than blocking the round; a pair-period without rate
data is simply untraded.

## Deployment target (so this connects to the EA explicitly)

If the round passes: FTMO SWING account type (overnight/weekend holds and
swap collection are the whole point — pin this in the rulebook page), EA
built on the existing live-ops pattern (mql5/README) with FirmConfig.mqh,
signal computed once daily — no tick logic anywhere. Parity gate applies
before demo, demo gate before evaluation, per the design doc. This is the
institutional strategy an MT5 EA can actually carry; everything faster was
priced out in reports/scalping_brief.md.
