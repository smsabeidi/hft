# ORB research — the opening range breakout, and what "adding it to our
# session breakout" honestly means

Written 2026-07-09 on founder direction. Deep-dive on the strategy class,
its evidence base, and the integration verdict.

## What ORB is, and where it comes from

The Opening Range Breakout trades the thesis that the range formed in the
first minutes AFTER a market's open — not before it — resolves the
overnight order-flow imbalance, and that a break of that range carries
intraday momentum. Toby Crabel's 1990 book (*Day Trading with Short Term
Price Patterns and Opening Range Breakout*) is the canonical origin; the
idea predates him on trading floors. The modern revival is Zarattini &
Aziz (2023): a 5-minute ORB on QQQ (leveraged via TQQQ), 2016-2023, enter
on the break of the first 5-minute bar with a stop at its other side and
an end-of-day exit, reporting dramatic outperformance net of commissions;
a companion paper applies ORB to "stocks in play" (high relative volume
names) with similar claims. The serious academic anchor for the mechanism
is Gao, Han, Li & Zhou (2018), "Market Intraday Momentum": the first
half-hour's return on SPY predicts the last half-hour's, strongest on
high-volatility and high-volume days — real, replicated, and specifically
an EQUITY-MARKET-OPEN phenomenon.

Honest critique file on Zarattini-Aziz: single instrument classes riding a
strongly trending tech decade; leverage (TQQQ) does the heavy lifting in
the headline numbers; the 2016-2023 window contains no extended bear-chop
regime for QQQ except 2022 (where the strategy's short side helped);
transaction costs are modeled but retail CFD costs differ from US equity
commissions; and the papers are practitioner-published, not peer-reviewed.
None of that makes ORB fake; it makes it a candidate — exactly the kind
this repo feeds to a pre-registered gate.

## Why the mechanism does NOT graft onto our FX session breakout

Our dead family (session_breakout, refuted twice, "dead beyond appeal")
trades the LONDON open against the ASIAN range — a pre-open range, on a
market with no opening auction. ORB's evidence lives in the opposite
construction: a post-open range on a market WITH a true opening auction
(US equities, 09:30 New York), where overnight orders queue and the first
minutes genuinely price-discover. FX has no such moment at London: dealing
is continuous, there is no auction imbalance to resolve, and our own 5.5y
refutation is direct evidence that session-range breakouts on FX majors
carry no after-cost edge. Bolting an ORB window onto the FX EA would be
re-tuning a dead family — prohibited, and predictably futile.

The seamless integration, done honestly, is therefore: TEST ORB WHERE ITS
EVIDENCE LIVES — index CFDs (US500/NAS100) at the true US cash open, which
the founder's MT5 accounts already carry. Instrument class, open mechanism,
and literature anchor all differ from the dead FX family: this is a NEW
family (us_open_orb_indices), founder-directed, entitled to its own two
rounds. If it passes, the MQL5 implementation is a sibling of
SessionBreakout (the live-ops skeleton ports wholesale; the strategy diff
is ~30 lines: NY-clock session windows, post-open range, same
one-trade-per-day discipline, same risk engine) and it fills SignalHost's
slot through the standard parity gate.

Cost sanity per the edge budget: US500/NAS100 CFD spreads run ~0.5-1.5bp
with ~40-90bp of 30-minute open-window volatility — breakeven IC ~0.02-0.04,
the "institutional-hard but possible" band, and the ONLY breakout context
this project has met where the cost math does not veto the attempt outright.

## ROUND 1 RESULT (2026-07-09, same day): FAIL

1,823 pooled OOS trades across US500+NAS100, 2021-2026: mean net -0.64bps
(95% CI [-3.6, +2.3], t=-0.43), win rate 32.9%, window stability 30%.
Gross expectancy ~+1.9bps vs 2.5bp costs — a coin flip paying spread. The
profit concentrates in single hot windows (Dec-2024: +778/+1074bps) and
evaporates across regimes — the same signature as every breakout variant
this project has tested. This directly fails to reproduce the
Zarattini-Aziz headline on out-of-sample walk-forward at retail CFD costs,
consistent with the critique file above (their window, their leverage,
their cost structure). One round remains; the literature-anchored round-2
direction, requiring founder sign-off: the Gao et al. conditioning — trade
ONLY high-volatility/high-volume opens, where intraday momentum
concentrates. Prior: low-to-moderate.

## PRE-REGISTRATION — us_open_orb_indices, round 1 of 2 (frozen before any run)

- Universe: US500 (SPXUSD) + NAS100 (NSXUSD), histdata M1, 2021-2026.
- Clock: all session logic in America/New_York (auction open 09:30 NY;
  UTC shifts with DST and is handled by tz conversion, never hardcoded).
- Opening range: first R minutes from 09:30 NY, R in {15, 30}.
- Entry: first M1 CLOSE beyond the range high (long) or low (short)
  before 12:00 NY; one trade per instrument per day, first signal only.
- Stop: opposite edge of the opening range. Target grid: {none, 4R}.
  Hard exit at 15:55 NY close regardless.
- Costs: 2.5bp of notional round trip (spread+slippage, retail index CFD,
  friendly-conservative), charged per trade.
- Walk-forward: train 500 trading days / test 120, rolled 120; grid
  (R x target) = 4 combos, optimized on train by after-cost net.
- GATE: pooled OOS >= 100 trades, mean net > 0 bps, t >= 2.0, window
  stability >= 0.6. Standard 2-round kill rule; this is round 1.
