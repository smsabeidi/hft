# Optimization pass — done the way desks actually do it

Written 2026-07-07. Request: "optimize the strategies." At the firms whose
names get invoked for this, optimization overwhelmingly means costs, sizing,
execution, and data hygiene — NOT re-tuning validated signals. This repo has
already run that experiment both ways: the C1b re-tune lost to the baseline,
and the pre-registration makes C5/C6 untouchable before their rounds by
construction. So this pass optimized the only things that are honestly
optimizable today, with arithmetic rather than fitting.

## 1. Fee engineering (scripts/m2_sizing_brief.py)

Pure arithmetic on the round-1 pooled OOS episodes (gross is
fee-independent; zero re-optimization). Same 31 episodes, four fee tiers:

| execution | RT fee | mean episode | ~annualized* | P(episode<0) |
|---|---|---|---|---|
| taker tier-0 | 30bp | +71.2bp | 7.39%/yr | 29% |
| round-1 assumption | 25bp | +74.2bp | 7.70%/yr | 29% |
| maker tier-0 (post-only) | 20bp | +77.2bp | 8.01%/yr | 29% |
| maker + volume tier | 14bp | +80.8bp | 8.38%/yr | 19% |

*Aggregation note, stated honestly: episodes/yr x mean-episode gives
~7.7%/yr because episodes cluster in rich-funding windows; the official
conservative number remains the window-annualized 3.83%/yr from round 1.
The RELATIVE uplifts are aggregation-independent.

Action that follows: the M2 executor should enter and exit with post-only
orders (episodes last days; entry latency is worthless here). Worth ~+4%
of the book's return for zero new risk — the cheapest real alpha available
anywhere in this project. The fee tier belongs in the venue decision (M1)
alongside jurisdiction.

## 2. Sizing (same script)

Kelly leverage on the episode distribution: f* = 53x at the round-1 mean,
14x even at the thin Kraken-regime mean — i.e. Kelly does NOT bind, and
variance is not the constraint. The binding risks are venue/counterparty
tail and operational unknowns, which is what the M2 rung exists to
de-risk. Regime honesty: at the Kraken-1y mean (+19.6bp), 61% of episodes
individually lose (sd 118bp dwarfs the mean) — the book earns through
patience across episodes, not per-episode certainty, consistent with the
win-rate-illusion memo. Recommendation unchanged from the roadmap: small
end of $1-5k; M2 buys verified operations, not income.

## 3. Data hygiene (scripts/latency_report.py — permitted QA)

Laptop-tier feed staleness, measured on ~110k recorded book updates:
p50 126-127ms, p90 ~148ms, p99 ~240ms, uniform across all four
instruments (wifi + clock skew + OKX's ~100ms books5 cadence). This is
the number the C5 cost model inherits, and the before/after baseline that
prices the $40/mo in-region VM (expected: 1-5ms). Rerun on the VM the day
it exists.

## 4. What was deliberately NOT optimized

The funding signal (C1b already lost to it), the C5/C6 specs (pre-registered
blind; touching them voids rounds), the risk-engine constants (frozen by
design doc rule), and the M0 paper books mid-flight (changing the live cost
model would contaminate the promotion gate). Declining these is the
optimization discipline the invoked firms are actually famous for.
