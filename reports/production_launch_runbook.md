# Production launch runbook — funding book to a real account

Written 2026-07-07, on the founder's "make it production and real-account
ready" order. As of this document the execution layer is CODE-COMPLETE and
the real-money path is LOCKED by the M0 gate, exactly as the ladder
requires. This page is the complete, ordered path from here to the first
real dollar; nothing on it is optional and nothing else is needed.

## What is now built (production side)

- hft/crypto/okx_executor.py — signed OKX v5 client: post-only entries
  (the fee-engineering finding), reconciliation queries, and a kill switch
  (close_all_positions — the only method allowed to cross the spread).
  One code path serves demo-trading (x-simulated-trading header) and real.
  Keys only from environment; never on disk.
- scripts/rehearsal_funding.py — the dress rehearsal: minimal delta-neutral
  round trip on OKX demo-trading with fill verification and executed-basis
  accounting vs the cost model. Safe to run repeatedly.
  REAL mode refuses unless scripts/paper_status.py exits PROMOTE. No
  override flag exists; tests/test_okx_executor.py pins the refusal.

## Gate status at writing

M0 promotion gate: NOT PASSED (0 completed paper episodes; both books OPEN
and accruing — episodes close when the smoothed funding rate crosses the
exit threshold; this takes days-weeks by design). The rehearsal is
available NOW; real orders are not, and won't be until the gate prints.

## The ordered path to the first real dollar

1. (Founder, ~15 min, today if desired) Create OKX DEMO-trading API keys
   (web UI: Trade -> Demo trading -> API), export OKX_API_KEY /
   OKX_SECRET_KEY / OKX_PASSPHRASE, run
   `python3 scripts/rehearsal_funding.py --notional 100`.
   Success = full round trip with fills and executed basis within ~2bps of
   the cost model. Repeat until boring — boring is the goal.
2. (Time) M0 accrues: >=10 completed paper episodes, t>=2, mean inside the
   backtest sanity band. `scripts/paper_journal.sh` reports daily; nothing
   to do but let the cron run.
3. (Founder, blocking) M1 decision per reports/m1_venue_brief.md: confirm
   jurisdiction branch. Branch B (non-US): OKX real keys after KYC and this
   executor is the production executor. Branch A (US): open Coinbase/Kraken
   accounts; an onshore adapter mirroring okx_executor.py is an M2 build
   task (the interface is deliberately small: balance / instrument / place
   / order / cancel / positions / close_all).
4. (Founder) Fund the venue account at the M2 size — the SMALL end of
   $1-5k per reports/m2_sizing_brief.md (Kelly does not bind; venue tail
   risk and ops verification set the size).
5. Run `rehearsal_funding.py --real` — it now passes its gate — then
   switch the live engine loop on at M2 scale. Success metric per the
   roadmap is NOT pnl: slippage-vs-model, funding accrual accuracy, zero
   accounting surprises over 10+ real episodes. Kill: any unexplained
   divergence > 10 bps/episode.

## What is explicitly NOT launching

WinRate80 and every strategy in rounds.log marked FAIL. A real account
runs validated positive expectancy only — currently that list has exactly
one name on it (funding capture), which is why this runbook is short.
