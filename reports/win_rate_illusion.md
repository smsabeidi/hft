# The win-rate illusion, measured — why "100% win rate" is a geometry, not an edge

Written 2026-07-07, in answer to the request for an MT5 EA with a "100% win
rate," 1:3 or 1:5 risk:reward, and micro-second-to-minutes holds. Rather than
argue, the harness measured it: five bots on 5.5 years of real EURUSD M1
(1,989,623 bars), identical in every respect except take-profit:stop-loss
geometry, all completely SIGNAL-FREE (strictly alternating direction, fixed
cadence — zero forecasting anywhere). Reproduce with
`python3 scripts/run_win_rate_illusion.py`; the property is also pinned in
the test suite (tests/test_win_rate_illusion.py).

## Frictionless panel (cost = 0)

| bot | tp/sl | trades | win rate | theory sl/(tp+sl) | exp/trade | t |
|---|---|---|---|---|---|---|
| grail_2_100 | 2/100 | 12,444 | **97.9%** | 98.0% | -0.08p | -0.6 |
| rr_1to5 | 10/50 | 5,907 | 82.9% | 83.3% | -0.25p | -0.8 |
| rr_1to3 | 10/30 | 9,133 | 75.0% | 75.0% | +0.01p | +0.1 |
| symmetric | 20/20 | 7,111 | 51.3% | 50.0% | +0.53p | +2.2 |
| inverse_3to1 | 30/10 | 9,134 | 25.0% | 25.0% | -0.02p | -0.1 |

Win rate lands within ~1 point of the pure-geometry formula at every shape,
from 25% to 98%, with zero forecasting skill and ~zero expectancy. Win rate
is a DIAL. Anyone can set it anywhere. It is not evidence of anything.
(The symmetric row's +0.53p at t=2.2 is gross M1 mean-reversion — exactly
the family round 1 already refuted after costs; see the next panel.)

## Friendly real costs (1.05 pips RT — the optimistic round-1 variant)

| bot | win rate | exp/trade | t | total 5.5y | max DD | wins erased per stop |
|---|---|---|---|---|---|---|
| grail_2_100 | **97.9%** | **-1.13p** | **-8.8** | **-14,059p** | 14,129p | 50 |
| rr_1to5 | 82.9% | -1.30p | -4.4 | -7,659p | 7,911p | 5 |
| rr_1to3 | 75.0% | -1.04p | -5.7 | -9,475p | 10,074p | 3 |
| symmetric | 51.3% | -0.52p | -2.2 | -3,716p | 4,321p | 1 |
| inverse_3to1 | 25.0% | -1.07p | -5.9 | -9,796p | 9,849p | 0.3 |

The 98%-win-rate bot is the WORST performer in the table: statistically the
most certain loser (t = -8.8), bleeding for 5.5 years with no recovery — a
smooth equity ramp punctuated by 100-pip amputations, each erasing 50 wins.
This is the exact payoff shape behind marketplace "99% win rate" EAs and the
social-media clips of bots rapid-firing green trades: the clip shows the
ramp; the account meets the amputation. It is also precisely the profile
the design doc's hard-fail rule exists to reject ("any strategy relying on
martingale, grid, or averaging-down is rejected regardless of win rate" —
this is the same pathology without the position-sizing accelerant).

## What each requested property actually costs

A 100% win rate with a 1:3 or 1:5 stop:target is an arithmetic
contradiction: those geometries HAVE a stop, and on real data the stop gets
hit — 17-25% of the time, per the table. The only way to push the win rate
toward 100% is to widen the stop toward infinity (the grail row, ruin by
amputation) or remove it (martingale, ruin by leverage). Micro-second holds
on MT5 are physically unavailable (50-300ms broker round trip, dealer last
look), and minutes holds need breakeven skill of 0.49-1.2 per the edge
budget — at or beyond the mathematical maximum of 1.0.

What IS legitimately achievable — and what the famous firms actually have —
is near-certainty at the PORTFOLIO level: Virtu's one losing day in 1,238
was built from ~51-55% win-rate trades in enormous numbers with strict cost
control, i.e. law of large numbers over a small real edge, which is exactly
the shape of this project's funding book (86% positive intervals, episode
t=3.5) and of every family in the pipeline. Chase per-trade certainty and
you get the first table's first row. Chase small verified edges at scale
and you get Virtu's number. There is no third option on the menu.
