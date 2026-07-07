# Founder checklist — the complete remaining handoff

Written 2026-07-07. Everything code-side is built, tested, and committed;
this page is the full list of founder actions that finish the operation,
each mapped to what it unlocks. When items 1-3 are done the ladder runs
end-to-end without prompting: paper -> PROMOTE -> rehearsal -> first real
$1-5k on validated edge.

## Use today (MT5 on this Mac)

- InfraShadow on a live chart: ops layer + phone alerts (wire MQID via
  Tools -> Options -> Notifications). Trades nothing, leave it running.
- WinRate80 in the Strategy Tester: the win-rate dial, quarantined.
  EURUSD defaults = 85%; gold: tp=30/sl=180. Tester-only by construction.
- SessionBreakout in the tester, EURUSD/M5/"1 minute OHLC" only: the
  parity instrument. Expect statistical noise; that is the point.

## Founder actions, in priority order

1. OKX demo-trading API keys (10 min, free) -> production rehearsal runs,
   executor validated with real fills vs the cost model.
2. Hong Kong VM (~30 min, ~$30/mo; Alibaba HK or AWS ap-east-1, Ubuntu 24,
   2vCPU/4GB) -> scripts/vm_bootstrap.sh makes recorder + paper book 24/7;
   C5 fires at recorded day 30; C6 reachable; latency 126ms -> 1-5ms.
3. Jurisdiction decision + KYC start (reports/m1_venue_brief.md, 1 hr +
   waiting) -> Branch B: current executor is production; Branch A: small
   onshore adapter gets built (six-method interface).
4. FCM account for CME micros (Branch A; days-weeks) -> C2 basis
   execution gets built — the strongest new edge measured this week.
5. Pin the FTMO rulebook (1 hr, free): fill config/ftmo_50k.json TBDs,
   flip verified:true with a dated rulebook -> FirmConfig regenerates; the
   funded-account pipeline is armed for the first family that passes.
6. Decision only: carry round 2 (cross-sectional basket spec; low prior) —
   "run it" or bank the round.

## Needs nothing

M0 paper episodes (accruing every 8h), daily journal (cron), recorder
self-healing (15-min supervisor while the laptop is awake; the VM makes it
permanent). Standing exclusions per the runbook: WinRate80 and every
FAIL-tagged family never touch demo or live.
