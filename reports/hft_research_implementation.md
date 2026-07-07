# Research-to-code round: what got implemented from the HFT firm study

Executed 2026-07-07, same day as `reports/hft_firm_strategy_research.md`.
Everything below ran through the standing gauntlet: pre-registered gates
written into each script's docstring BEFORE the run, results appended to
`reports/rounds.log`, no post-hoc threshold shopping. Three of four
candidates FAILED their gates — that is the system working, not the system
failing. The scoreboard money-weighted: the running family stands unchanged,
one new Branch-A candidate got materially stronger evidence, and the paper
books gained an adverse-selection instrument.

## What was built

**Markout tracking (research doc §6) — live in the paper engine.**
`hft/crypto/paper_funding.py` now records the perp-spot basis at every paper
fill and resolves post-fill basis drift at +1/+5/+15/+60 minutes from OKX 1m
candles, signed so positive = favorable. `scripts/paper_status.py` reports
pooled markouts and warns when the 15m mean turns negative (fills being
adversely selected). Diagnostic only: it cannot touch equity or the M0
promotion gate. Old state files migrate automatically; fetch failures retry
and never break a tick. Both live books (BTC, ETH — currently OPEN) start
accruing markouts from their next fill.

## Round results (all logged to rounds.log)

**C1b — AR(1) funding-persistence conditioning: FAIL, baseline stands.**
An AR(1) one-step funding forecast driving the same hysteresis machine
passes the episode gate on its own (31 OOS episodes, +67.2 bps/episode,
t=3.04, 100% stability) but does not beat the trailing-mean baseline
(+74.2 bps, 3.83%/yr vs 3.47%/yr). Pre-registered replacement criterion not
met; the simple signal keeps its seat. Lesson consistent with the research
doc: funding persistence is real but the 3-interval mean already harvests
essentially all of it.

**C1c — symbol expansion to SOL/XRP: FAIL on sample size, not on sign.**
Pooled SOL+XRP at bumped 35bp RT costs: 27 OOS episodes, +60.0 bps/episode,
t=2.15, 62% stability. Every gate condition passed EXCEPT the >=30 episode
floor. Per the pre-registration this is a FAIL and alts stay out — but the
family is not refuted; each passing year adds episodes, and the round can
re-run when the count clears 30 without touching the grid. Do not admit alts
early: the whole point of the floor is that 27 borderline episodes is how
false positives get hired.

**C3 — funding snapshot timing: FAIL, conclusive kill.**
Three years of minute-level premium-index data (2023-07..2026-06, BTC+ETH,
6,566 snapshots) contain ZERO snapshots with funding >= 30bp — the fat-
funding regime this trade needs to clear 25bp costs no longer exists. Worse,
around ordinary >=3bp snapshots the premium systematically decays ~1bp
against the short-perp side before/after the payment: the market already
prices the funding exchange. Since the study's stated bias (conditioning on
the paid rate) was FAVORABLE and it still failed, this kill is final. The
family is dead at retail costs in the current regime; no second round is
warranted unless the fat-funding regime visibly returns.

**C2 — fixed-expiry basis vs floating funding: the day's real finding.**
Study (decision support, like crypto_opportunity.md — not a rounds.log
entry). 4,115 contract-days of Binance quarterly-delivery basis (proxy for
the CME micro trade), entry windows 14-120 days to expiry, versus realized
funding over the identical windows:

| year | n | locked median | locked IQR | floating median | locked wins |
|---|---|---|---|---|---|
| 2021 | 611 | 14.0% | [7.5%, 25.1%] | 16.8% | 41% |
| 2022 | 668 | 1.8% | [-0.1%, 3.1%] | 3.4% | 45% |
| 2023 | 760 | 5.1% | [4.0%, 7.5%] | 7.3% | 23% |
| 2024 | 860 | 11.7% | [8.8%, 15.7%] | 10.7% | 62% |
| 2025 | 858 | 5.5% | [4.5%, 6.9%] | 4.3% | 74% |
| 2026 | 358 | 2.2% | [1.4%, 3.1%] | 0.6% | 78% |

The regime flipped: through 2023, floating funding beat the locked basis
(locking would have capped the upside); since 2024 locking wins a rising
majority of entry windows, and in 2026 the locked carry is ~4x the realized
floating funding. In exactly the funding-decay regime that M1.5 flagged,
the fixed-expiry structure is the better wrapper for the same trade. Caveats
that keep this a study and not a green light: 2.2%/yr gross is still thin;
proxy data is Binance delivery (CME term structure must be read directly at
decision time — typically fatter, but verify); and the trade needs an FCM
account (margin ~$1-3k per micro contract, dollar-denominated fees).

## What this changes

1. **Running family: unchanged.** C1b/C1c/C3 all failed their gates; the
   BTC+ETH trailing-mean parameterization keeps running on paper. M0
   promotion criteria untouched.
2. **M1/M2 (Branch A): C2 moves up.** The venue brief's recommended
   sequencing gains a concrete step: alongside Coinbase/Kraken KYC, open the
   FCM conversation for CME micro BTC/ETH futures. At decision time, read
   the live CME basis and compare against trailing realized funding — the
   comparison machinery is now in the repo
   (`scripts/run_c2_basis_study.py`, `data/funding/c2_basis_vs_funding.parquet`).
3. **M3 recorder families (C4-C6): still gated on infrastructure**, not
   implemented, deliberately — L2 evidence does not exist yet, and
   pretending otherwise would be exactly the shortcut the ladder forbids.
4. **Markouts accrue from today**; by the time the M0 episode count matures,
   there will be an adverse-selection record to read alongside it.

## Reproduction

```
python3 scripts/run_funding_c1b_round.py   # C1b: ar1 vs sma, gates in docstring
python3 scripts/run_funding_c1c_round.py   # C1c: SOL+XRP pool at 35bp RT
python3 scripts/run_c3_timing_study.py     # C3: snapshot-timing event study
python3 scripts/run_c2_basis_study.py      # C2: locked vs floating carry
```

All fetchers cache under `data/funding/` (gitignored); first runs download
from Binance's public archive, re-runs are offline.
