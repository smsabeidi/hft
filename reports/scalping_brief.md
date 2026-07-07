# Scalping brief — the frequency dial, priced

Written 2026-07-07. Question asked: can this stack scalp — multiple trades
per minute, rapid open/close, "HFT-grade agentic" — through MT5, TradingView,
or prop-firm brokers? The answer is arithmetic, not opinion, and the
arithmetic is now a repo tool: `scripts/edge_budget.py`.

## The law

A round trip costs a fixed number of bps (spread + fees + slippage). Price
noise over a holding period h scales as sigma(h) ~ vol x sqrt(h). By
Grinold's first-order rule, expected gross per trade ~ IC x sigma(h), where
IC is the correlation between your forecast and the realized return. So the
signal quality needed just to break even is required IC = cost / sigma(h),
which grows like 1/sqrt(h) as the hold shrinks. Costs are per-trade and
fixed; information is not improved by trading more often. Frequency
multiplies whatever per-trade expectancy you have — including its sign.

## The numbers (edge_budget.py, measured spread from the live recorder)

MT5 EURUSD on a raw-spread prop account (~0.9bp RT all-in, 8% vol): a
1-minute hold needs breakeven IC ~ 0.68 — you must correctly capture
two-thirds of a standard deviation of 1-minute noise, every trade, just to
pay the desk. With realistic slippage (1.6bp RT) it is IC ~ 1.2, which is
not a hard trade; it is a logical impossibility (IC <= 1). At 15 minutes it
is still 0.17-0.31 — the territory firms reach only with full-depth feeds
and microsecond reaction, i.e. precisely the inputs an MT5 retail feed does
not carry (no order book on FX CFDs, 50-300ms round trip, dealer last look).
At a 4-hour hold it is 0.04-0.08 (institutional-hard), and at 1 day ~0.02-
0.03 — the class where real, documented signals live (carry, structural
flows). This is why the M4 forex families are specified as minutes-to-days
holds at 1-10 trades/day, and why the three refuted price-pattern families
died exactly as the table predicts.

Crypto taker (OKX perp, ~10bp RT in fees; measured spread only 0.02bp over
1,590 live book updates — the cost is the FEES, not the spread): 1-minute
scalping needs IC ~ 1.6 (impossible), one hour needs 0.21. Aggressive
taker scalping at retail fee tiers is dead at every horizon under a day —
this is the C3 result generalized. Crypto MAKER (~2bp floor): 5-15 minute
horizons need 0.08-0.14 — hard but real WITH order-book information and
queue discipline, which is exactly family C6 and why it is pre-committed to
VM-grade incremental L2 and a queue-aware simulator, not to a laptop loop.

## The other two walls (for completeness)

Rules: the design doc's compliance section already records that FTMO-class
firms ban tick scalping and latency-style HFT outright; sub-minute
open/close patterns are the signature their surveillance looks for, and the
rulebook pin (The Assignment) precedes any risk-engine code. A
multiple-trades-per-minute EA on a prop account is not an edge strategy;
it is a payout-denial strategy.

Latency tier: TradingView is a charting and alerting layer — webhook to
broker is a seconds-scale path, and Pine strategies evaluate on bar events.
Fine for research visualization; not an execution tier for anything in this
brief. Its script library is the same refuted-family museum the last
research pass catalogued.

## What "many orders per minute, fully agentic" legitimately maps to here

The stack already IS agentic end to end: cron-driven paper books that
enter, exit, account, and self-assess (paper_status gates), a self-healing
data recorder, markout diagnostics, and pre-registered strategy gates that
run without a human. Autonomy is not the missing piece and never was.

High ORDER rates (not high taker-trade rates) arrive with C6: a passive
maker quotes and re-quotes many times per minute while trading against it
stays selective — you are paid to be there instead of paying to be there.
That family has a binding pre-registered gate, a designated simulator
(hftbacktest), and a data pipeline already recording toward it. C5 (basis
mean-reversion, minutes-hours) is the intermediate-frequency family and
becomes round-eligible ~30 recorded days from now. On MT5, the honest
frequency ceiling from the table is single-digit trades/day at multi-hour
holds — which is what the M4 revival was already scoped to be, now with
the quantitative reason attached.

## Bottom line

The frequency dial is set by cost/sigma(h), and at retail information and
fee tiers every sub-15-minute taker setting on MT5 or crypto prices out as
mathematically unreachable before the prop-firm rulebook even gets a vote.
The scalping-shaped edges this project can actually own are passive (C6)
and structural (C5, funding, C2 basis) — all already in the pipeline with
gates that will say PASS or FAIL without anyone's enthusiasm involved.
`scripts/edge_budget.py` reprices this table any time costs, venues, or
vol regimes change.
