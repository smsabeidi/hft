# Requirements analysis — the $2-4k/day target

Quant memo, 2026-07-09. Target set by founder: $2,000-4,000/day
(~$500k-1M/yr at 250 trading days). This memo derives what the target
requires. No advice; arithmetic.

## What the target requires at different capital levels

Daily P&L target M requires capital C such that M/C is an achievable
daily return under the drawdown constraints of the account.

| Capital | $3k/day equals | Feasibility reference |
|---|---|---|
| $6k (current) | +50%/day, 12,500%/yr | ~190x Medallion (66%/yr, best ever recorded) |
| $100k funded | +3%/day, 750%/yr | ~11x Medallion; see Sharpe requirement below |
| $1M | +0.3%/day, 75%/yr | ~1.1x Medallion — world-record territory |
| $2-4M | 19-38%/yr | top-decile hedge fund; ACHIEVABLE for a real edge |

## The Sharpe requirement under prop-firm rules

A funded account dies at -5% in a day / -10% total. Surviving while
TARGETING mean +3%/day requires the -5% day to be a >=3-sigma event:
daily sigma <= 2.7%, hence daily Sharpe >= 1.1, hence ANNUALIZED SHARPE
>= ~17. The best sustained track record in recorded history (Medallion)
is estimated at 2-7 depending on gross/net telling. The requirement is
2.5-8x the all-time frontier, on retail costs. Verdict: infeasible at
$100k. Not hard — beyond the documented frontier.

At $2-4M under management, the same dollar target needs Sharpe ~1.5-2.5
at 20-40%/yr — demanding but inside the achievable band for genuinely
validated strategies.

## Therefore

The target is a CAPITAL requirement, not a frequency requirement.
$2-4k/day becomes arithmetic at roughly $2-4M under management; no trade
frequency reaches it from $6k because frequency multiplies per-trade
edge, which is measured (rounds.log, 16 entries) at <= 0 for every
retail-cost family. The path to $2-4M in this repo's terms: validated
families (one live, three gated) -> funded accounts and scaling plans
(prop firms scale to $300k-$4M across accounts) -> compounding + the M6
track-record raise. Every rung is already specified in
reports/scaling_roadmap.md.

Open research levers that move this timeline are unchanged and all
capital-side or data-side: VM (C5 at +30 days), FCM (C2), KYC (M2),
rulebook pin (M4 pipeline). There is no strategy-side lever left on
bar-data at retail costs; that program is complete.
