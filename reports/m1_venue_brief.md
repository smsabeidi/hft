# M1 decision brief — venue & jurisdiction for first real capital

Written 2026-07-07, deliberately BEFORE M0 closes, so this decision can run in
parallel with paper-episode accumulation instead of after it. Facts below are
search-sourced as of this date; re-verify numbers at decision time (links at
bottom). The founder decides; this document only structures the choice.

## The one question that decides everything

**Are you a US person for KYC purposes?** Evidence from this project already
hints at the answer (Binance's API is geo-blocked from this network while
data.binance.vision is open — the classic US pattern). The two branches lead
to completely different venues AND different validation obligations.

## Branch A — US person (likely)

The offshore big three (Binance, OKX, Bybit) are unavailable for real trading.
That includes OKX — the venue our paper books run against. Paper evidence
stays valid as strategy evidence; the venue itself does not transfer.

Onshore options (all new since 2025 — this market just came into existence):
- **Coinbase Financial Markets** — CFTC-registered FCM; US perpetual-style
  futures since July 2025; BTC + ETH, up to 10x. Longest onshore funding
  history (~1 year by now).
- **Kraken Derivatives US** — CFTC-regulated US perpetuals via Kraken Pro
  since June 2026; broad contract list (BTC, ETH, SOL, XRP, more).
- **Kalshi** — CFTC-approved BTC perpetual (May 2026); newest, narrowest.

**The honest catch (do not skip):** round 1 validated funding capture on
OFFSHORE funding-rate history (Binance/OKX, 8h intervals, their participant
mix and rate caps). Onshore perps have their own funding mechanics — interval,
caps, and a different (more regulated, plausibly less retail-levered) crowd.
The +74.2bps/episode result does NOT automatically transfer. Before real
dollars on an onshore venue: pull that venue's full funding history and rerun
the strategy gate on it (the harness needs only a fetcher; Coinbase's ~1y of
data supports a provisional round, flagged provisional until history deepens).

Recommended sequencing (Branch A): open the Coinbase and/or Kraken account
now (KYC takes days) -> fetch onshore funding history -> provisional strategy
round on it -> if PASS and M0 closes, first $1-5k there; if FAIL, the edge is
offshore-only and the US path needs a different family (or entity-level
choices that are a lawyer conversation, not a bot conversation).

## Branch B — non-US person

The paper venue is the real venue: OKX (or Bybit; both fee-competitive).
- Fees at retail size are near-identical: spot ~0.08-0.10%, perp taker
  0.05-0.055%; the differences are under $5/month at this book's size.
- OKX advantages here: it is the venue already paper-traded (zero
  cost-model transfer risk), has a demo-trading mode for a dress rehearsal,
  and unified-account margin suits delta-neutral spot+perp.
- Sequencing: KYC now -> demo-mode dress rehearsal of the executor -> M0
  closes -> first $1-5k live, same instruments, same frozen params.

## Pre-decision checklist (founder, ~1 hour)

1. Confirm jurisdiction branch (and state-level restrictions if US — some
   states are excluded at sign-up).
2. Branch A: verify Coinbase/Kraken US perp funding interval, rate caps, and
   whether spot+perp cross-margin is possible (or whether the hedge leg must
   sit in a separate spot account — this changes the cost model).
3. Confirm tax treatment of perp funding income locally (CPA question).
4. Start KYC at the chosen venue — it's the longest-lead-time item and costs
   nothing.

## What this changes in the roadmap

M1 can now complete during M0 instead of after it. If Branch A: add one rung
M1.5 (onshore funding-history validation round) before M2's first dollars.
The M2 kill criteria and sizing are unchanged.

Sources (retrieved 2026-07-07):
- https://edge-ledger.io/blog/binance-vs-bybit-vs-okx-2026
- https://itrusty.io/en/exchanges/crypto-exchanges-comparison-2026
- https://www.okx.com/en-us/fees
- https://www.coindesk.com/markets/2026/06/15/kraken-debuts-u-s-perpetual-futures-as-crypto-derivatives-move-onshore
- https://coincentral.com/kraken-launches-cftc-regulated-perpetual-futures-for-us-crypto-traders/
- https://www.bnnbloomberg.ca/markets/crypto/2026/04/22/crypto-exchanges-gear-up-to-launch-us-perpetual-futures-ahead-of-rule-change/
- https://www.kraken.com/features/futures
