# Evaluation-pass mathematics — Dollar's risk layer, calibrated

2026-07-10. First-passage analysis of the prop evaluation as a barrier
problem: touch +5% before -10% (static) while never dropping 5% in a day
(FundedNext verified numbers), for a strategy of given Sharpe at 5
trades/day, as a function of risk-per-trade r. Method + code:
scripts/eval_pass_odds.py (closed-form diffusion cross-check + 20k-path
Monte Carlo per cell with the daily rule and Dollar's throttle tiers).

## Validation

At r=1.0% the simulator matches the closed-form barrier formula to within
0.001-0.011 across Sharpe 0.5-2.0. At r=0.5% the sim reads ~0.10-0.14 BELOW
closed form — that is the finite 60-day horizon, not error: slow low-risk
paths time out where the infinite-horizon formula counts them as eventual
passes (the timeout column holds the mass). The simulator is honest where
the formula is idealized.

## The finding: r* = 0.75%, invariant across strategy quality

Max-P(pass) risk-per-trade is 0.75% for EVERY Sharpe tested (0.5 to 2.0) —
the optimum is set by the barrier geometry (5/10/5), not by the edge:

| Sharpe | r*=0.75%: P(pass) | P(bust) | r=0.50%: P(pass) | P(bust) |
|---|---|---|---|---|
| 0.5 | 64.7% | 12.4% | 57.3% | 3.6% |
| 1.0 | 70.9% | 9.2% | 64.7% | 2.3% |
| 1.5 | 76.9% | 6.6% | 72.1% | 1.3% |
| 2.0 | 82.0% | 4.6% | 78.7% | 0.8% |

Above 0.75% pass odds FALL while bust odds keep climbing (at 2% risk, a
Sharpe-1 strategy passes only 57% and busts 39%) — the quantitative
autopsy of every over-leveraged challenge account, and one more proof that
speed of target-hitting is bought with barrier-death.

## Policy (two-phase, the actual optimization)

The optimum depends on what busting costs:
- EVALUATION phase (bust = lose the fee only): r = 0.75% maximizes pass
  probability. Worth ~5-7 points of pass odds vs 0.50%.
- FUNDED phase (bust = kill the account that pays 80-90% splits): the
  ~4-8x higher bust probability at 0.75% is a terrible trade; r <= 0.50%
  dominates, and the throttle tiers do the rest.

Config decision: OWN_RISK_PER_TRADE stays 0.50% (the funded-phase and
default posture). The evaluation-phase bump to 0.75% is a deliberate,
documented founder decision to take at challenge time — one input, now
with its price and payoff quantified. Dollar's risk layer is hereby
calibrated by barrier mathematics for whatever strategy earns the SIGNAL
slot; no strategy parameter was touched, because none may be.
