# Scaling roadmap — from a $0 paper book to maximum defensible size

Written 2026-07-07. This is the honest version of "billion-dollar bot": a
ladder where every rung is a measurable gate, the money at risk is sized by
evidence, and the exits are pre-committed. No rung is skippable.

## Where the evidence stands today

- Forex round 1: three vanilla families refuted on 5.5y of real M1 data
  (session breakout dead beyond appeal; mean reversion dead at realistic
  cost; TSMOM dead pooled across 3 pairs). The harness that killed them
  passed two falsification layers and a power check — the refutations are
  trustworthy.
- Crypto round 1: conditional funding capture PASSED (31 pooled OOS episodes,
  +74.2 bps/episode net, t=3.50, 100% window stability, ~3.8%/yr net at 0.6
  utilization and conservative costs).
- Live now: both pooled instruments (BTC, ETH perps) running on paper against
  live OKX books, cron-driven, self-assessing via scripts/paper_status.py.

## The ladder

**M0 — Paper promotion (running now; owner: time + cron).**
Trigger: `paper_status.py` prints PROMOTE (>=10 episodes, t>=2, mean net
consistent with backtest). Kill: mean episode net < 25% of backtest after 15+
episodes -> back to research, live cost model is wrong.

**M1 — Venue + jurisdiction (owner: founder; blocking everything real).**
Choose the exchange account jurisdiction, KYC, withdrawal rails, and tax
treatment. Deliverable: a funded exchange account and one page of rules,
exactly like the FTMO rulebook page for forex. No code depends on this; all
capital does.

**M2 — First real capital, $1-5k (owner: founder).**
Same engine, real orders, spot+perp delta-neutral. Success metric is NOT the
pnl (at 4%/yr on $5k this earns ~$200/yr): it is slippage-vs-model, funding
accrual accuracy, and zero operational surprises over 10+ real episodes.
This rung buys verified live-ops, the one asset paper cannot produce.
Kill: any unexplained accounting divergence > 10 bps/episode.
2026-07-07 addendum: on Branch A, the fixed-expiry wrapper (CME micro
futures vs onshore spot) now has study evidence favoring it over floating
funding in the current regime — see reports/hft_research_implementation.md
(C2) before sizing this rung; it adds an FCM account to the M1 checklist.

**M3 — The VM and the tick-data families (owner: founder $40/mo + harness).**
2026-07-07 addendum: the recorder is LIVE on the laptop (cron, books5+trades,
BTC/ETH perp+spot) and the C4/C5/C6 gates are pre-registered blind in
reports/m3_preregistration.md — the M3 data clock started before M2, same
de-serialization move as M1. The VM remains required for C6 and for real
latency numbers; C5 can run on laptop data per the pre-registration.
Cloud VM in the exchange region (1-5ms; laptop measured 121ms). The recorder
(component 1) accumulates weeks of L2+trades data. Pre-registered families
(basis/dislocation class) run through the same gauntlet. Each family that
passes adds capacity and diversification; each that fails dies in 2 rounds,
per the standing kill rule. Funding capture capacity at these venues is
bounded by perp open interest — roughly $10-50M notional before self-impact
becomes measurable, far above any near-term book here.

**M4 — Forex track revival (owner: founder; parked, not dead).**
Requires: Dukascopy ticks from an unthrottled network (definitive spreads),
Windows VPS (compile the EA, run the parity gate), FTMO rulebook pinned. The
prop-firm funded account is the only 20-80x capital lever available without
raising money: a passed $100k evaluation at 80% split beats years of
compounding $5k. But per the standing decision, no fourth ad-hoc forex family
— only a-priori hypotheses on tick data.

**M5 — Compounding + multi-family book (owner: evidence).**
With 2-3 uncorrelated validated families (carry + basis + one directional)
and funded-account leverage, a realistic excellent outcome for a solo
operator is mid-single-digit-percent monthly on managed capital of low six
figures within 2-3 years. That is the honest ceiling of "one person + this
codebase."

**M6 — The billion-dollar question, answered honestly.**
A billion-dollar outcome is not a property of a bot; it is a property of a
FIRM: audited multi-year track record -> external capital -> team -> many
books. Renaissance's Medallion, the best systematic track record in history,
compounds ~66%/yr gross on deliberately capped capital. The only path from
here that ever touches nine zeros: M0-M5 produce a 3+ year verifiable record,
then that record raises outside money. Every attempted shortcut around that
sequence is one of the failure modes this repo's gates exist to kill:
overleverage (drawdown death), curve-fit families (round-2 death), or
skipped validation (the 80%-win-rate bot).

## Standing rules that govern every rung

Expectancy/t-stat/drawdown are the only success metrics; win rate is a
diagnostic. Families die after 2 failed rounds. Risk limits are frozen
config, never optimized. No rung is funded until the previous rung's gate
prints PASS.
