# HFT firm strategy research — what the majors actually run, and what transfers here

Written 2026-07-07. Companion to the design doc (`~/.gstack/projects/HFT/`),
`reports/scaling_roadmap.md`, and `reports/m1_venue_brief.md`. Purpose: a
mechanism-level survey of the strategy families behind the well-known HFT and
proprietary trading firms (Citadel Securities, Virtu, Jane Street, Jump, HRT,
XTX, Optiver, SIG, Tower, DRW, Flow Traders, IMC, and the rest of the founder's
list), an honest analysis of which families survive at this project's
latency/capital/venue tier, and a ranked set of pre-registerable candidate
families that fit the existing gauntlet (after-cost gates, walk-forward,
2-round kill rule). Nothing here changes the ladder in the scaling roadmap;
this document feeds the family pipeline, mostly at rungs M3 and M4.

Descriptive research, not investment advice. No candidate in this document
moves money; every one of them dies or survives in the harness like everything
else has.

---

## 1. Epistemic ground rules: what is actually knowable

No firm on the list publishes its alpha. Anyone claiming to sell "Citadel's
strategy" is selling folklore. But the *mechanisms* by which these firms make
money are unusually well documented, because HFT has been studied with
regulator-grade non-public data for fifteen years. The reliable sources, in
descending order of evidentiary quality:

1. **Regulatory studies on message-level data.** The FCA's latency-arbitrage
   study (published as Aquilina, Budish & O'Neill, QJE 2022) used complete
   exchange message data to measure speed races directly. The CFTC's flash
   crash and HFT-profitability work (Kirilenko et al., JF 2017; Baron,
   Brogaard, Hagströmer & Kirilenko, JFQA 2019) used trader-identified e-mini
   data. These are the closest thing to ground truth that exists.
2. **Securities filings.** Virtu's 2014 IPO prospectus (the famous "one losing
   day out of 1,238"), KCG/Getco filings, Flow Traders' annual reports, and
   the Jane Street bond-offering documents reported in the financial press.
   These reveal P&L shape — small per-trade edge, enormous trade count, near
   daily-level certainty — which is itself the most important strategic fact.
3. **Academic microstructure literature.** Market-making economics
   (Glosten-Milgrom, Avellaneda-Stoikov), the speed arms race
   (Budish-Cramton-Shim, QJE 2015), order-flow prediction
   (Cont-Kukanov-Stoikov), single-firm case studies (Menkveld 2013, widely
   believed to describe Getco's Chi-X entry).
4. **Court and enforcement records.** Spoofing prosecutions (Sarao,
   Oystacher/3Red, the JPMorgan precious-metals case), code-theft cases
   (Aleynikov v. Goldman), and SEBI's 2025 interim order against Jane Street's
   India index-expiry trading (contested, later resolved with conditions).
   These document both the manipulation boundary and how much firms value
   infrastructure code.
5. **Serious journalism and sociology.** MacKenzie's *Trading at the Speed of
   Light* (interviews inside Jump, Virtu, and the microwave-tower ecosystem)
   and Patterson's *Dark Pools* are informative about infrastructure and
   culture; they contain no tradeable signals.

The single most important finding across all of it: **the edge of these firms
is predominantly structural, not mathematical.** Baron et al. (2019) found HFT
profits in the e-mini were highly concentrated, persistent across time, and
strongly correlated with relative speed rank; new entrants systematically
underperformed incumbents. Aquilina-Budish-O'Neill found latency races decided
in 5–10 microseconds, with a handful of firms winning the large majority of
races. The math (fair value estimation, inventory control) is table stakes and
mostly public; the moat is co-location, custom hardware, fee tiers, exchange
memberships, and decades of accumulated execution data. This is why the answer
to "which of their strategies can we use" is mostly *none directly, several by
analogy* — and the analogies are precisely characterizable.

## 2. The firms, grouped by archetype

Thirty mini-profiles would hide the structure. The list collapses into five
archetypes, and most firms straddle two:

| Archetype | Core trade | Firms from the list |
|---|---|---|
| A. Electronic market making (equities/FX/futures) | Capture spread + rebates, shed inventory fast, avoid adverse selection | Citadel Securities, Virtu, GTS, Tradebot, Two Sigma Securities, Getco/Knight (hist.), XTX (FX), IMC, Quantlab |
| B. Options market making / volatility | Quote thousands of options, hedge delta instantly, earn vol spread + vol risk premium | SIG, Optiver, IMC, Akuna, CTC, Peak6, Maven, Vivienne Court |
| C. Latency-sensitive futures/cross-venue arb | Win the race when correlated instruments diverge (ES↔SPY, cash↔futures, cross-venue) | Jump, Tower, DRW, XR, TransMarket, Allston, Headlands (rates), Radix, Vatic |
| D. Short-horizon statistical prediction / ML | Forecast minutes-to-hours moves from order flow and cross-asset signals; latency-tolerant by design | XTX (explicitly), HRT, Two Sigma, TGS, Quantlab |
| E. ETF / index / relative-value arb | Creation-redemption and NAV-vs-basket convergence at global scale | Jane Street, Flow Traders, SIG, IMC |

Firm-level facts worth having in one's head, all public and all hedged as
"reported": Virtu disclosed one losing day in 1,238 through its IPO — the
signature of thousands of tiny positive-expectancy trades per day, not of any
single brilliant idea. Citadel Securities internalizes a large share of US
retail order flow via payment for order flow, reportedly around a fifth to a
quarter of total US equity volume; its edge there is a *contractual* position
in the market structure, not a signal. Jane Street's trading revenue reportedly
exceeded $20B in 2024, driven heavily by ETF arbitrage and its role in crypto
ETP creation/redemption. Jump built and bought microwave towers between
Chicago and New Jersey because 4.0ms beats 6.5ms of fiber. XTX is the
counter-example that matters most for this project: it states publicly that it
competes on *forecasting* (massive ML on market data at horizons where
microseconds don't decide the winner) rather than on winning co-location races
— proof that archetype D is viable without the speed moat, albeit with a GPU
budget this project also doesn't have. Knight Capital's $460M loss in 45
minutes (2012) came from a *deployment* error — dead code reactivated by a
partial rollout — and is the single most instructive event in the industry for
a solo operator: ops discipline is a survival trait, not overhead.

## 3. The strategy families, mechanism by mechanism

Each family below gets: what it is, why it pays (whose money it takes or what
service it sells), what it structurally requires, and a transfer verdict for
this project's two tracks (MT5 prop-firm forex; crypto funding/basis at OKX or
onshore venues per the M1 brief).

### 3.1 Passive market making (spread capture)

The bread of archetype A. Quote both sides, earn the spread plus maker
rebates, keep inventory near zero, and — the actual hard part — avoid being
run over by informed flow. The economics are governed by adverse selection
(Glosten-Milgrom 1985): every fill is a small bet that the counterparty knows
less than you. Profitability requires (a) queue priority, because in a
price-time market the front of the queue gets the benign fills and the back
gets the toxic ones — and queue position is won by reaction speed measured in
microseconds; (b) fee tier — maker rebates of fractions of a basis point are
the margin at scale; (c) the ability to cancel within microseconds when the
fair value moves. Menkveld (2013) documented a single new HFT market maker
(believed to be Getco) earning its keep on Chi-X almost entirely from
spread+fees while roughly breaking even on inventory positions.

**Verdict: no transfer at the MT5 tier — inverted, in fact.** A retail MT5
account is on the *paying* side of this trade; the dealer's last look and
spread ARE someone's market-making P&L. Partial transfer in crypto at M3+:
crypto exchanges pay maker rebates at VIP tiers and even retail maker fees are
near zero, and on a young, thin venue the competition is temporarily sparse —
see candidate C6, which is exactly the Menkveld new-venue-entrant story writ
tiny. On the majors' books (Binance/OKX BTC), a solo operator quoting against
Wintermute-class firms will be adversely selected to death; the family is only
plausible where the professionals haven't bothered to show up yet.

### 3.2 Latency arbitrage (same asset, multiple venues)

The purest speed trade: when the same instrument (or its near-perfect
equivalent) trades on two venues, the first mover picks off stale quotes.
Budish-Cramton-Shim (2015) showed the ES↔SPY arbitrage window shrank from
~100ms in 2005 to single-digit milliseconds by 2011 while per-race profit
stayed roughly constant — the arms race changes who wins, not the prize.
Aquilina-Budish-O'Neill (2022) measured the global "latency-arbitrage tax" at
roughly 0.4bp of volume — on the order of $5B/yr — won overwhelmingly by a
handful of the fastest firms in races decided within 5–10μs.

**Verdict: zero transfer, and banned anyway.** The retail parody of this trade
(exploiting slow MT5 broker feeds) is explicitly prohibited by FTMO-class
firms and defeated by last look. In crypto, cross-venue latency arb at 1–5ms is
real but the fast tier there (Jump Crypto-class) is already sub-millisecond
co-located; a $40/mo VM does not win races. What survives at this project's
tier is the *slow residue* — dislocations that persist for seconds to minutes
because they're too small or too operationally annoying for the big firms
(candidate C4), which is not a race but a capacity-constrained scavenger trade.

### 3.3 Futures↔cash / basis arbitrage

Archetype C and E's structural trade: the same economic exposure priced in two
wrappers (future vs basket, ETF vs NAV, perp vs spot) mean-reverts, and
holding the pair earns the spread with near-zero market risk. At institutional
scale this is index arb, ETF creation/redemption (Jane Street, Flow Traders),
and the CME cash-and-carry basis trade.

**Verdict: this is the family this project already validated.** Crypto
perpetual funding capture — long spot, short perp, collect funding — *is* the
retail-capacity tail of the institutional cash-and-carry trade; Schmeling,
Schrimpf & Todorov ("Crypto Carry", BIS/JFE) document the premium, its
time-variation, and its crash risk in exactly the form the harness found it
(+74.2 bps/episode offshore, decaying hard into 2026, +19.6 bps on the Kraken
transfer test). The reframe matters: the project is not *missing* the majors'
strategies — one of the survivors in its rounds.log is a legitimate,
capacity-limited member of the same family DRW/Cumberland and every basis desk
runs at size. The extensions that remain untested are the fixed-expiry version
(candidate C2, which locks the carry at entry instead of floating with
funding) and cross-venue funding dispersion (part of C1).

### 3.4 Order-flow and microstructure prediction

Archetype D. Forecast short-horizon price moves from the order book itself:
order-flow imbalance (Cont-Kukanov-Stoikov 2014 — OFI explains a striking
share of price variance at seconds-to-minutes horizons), microprice (Stoikov
2018), queue dynamics, and deep-learning-on-LOB (DeepLOB and successors —
which show statistically real but *economically thin* predictability that
fees usually eat). This is XTX's stated lane and requires data and compute,
not co-location.

**Verdict: partial transfer at M3 — this is exactly what the phase-3 L2
recorder was designed to enable.** The published evidence cuts both ways:
signals exist and replicate, but net-of-fee profitability at retail fee tiers
is marginal, and most published results evaporate outside the top of book.
Treat as research families entering the standard gauntlet once the recorder
has weeks of L2 data (candidates C5, C6 use these signals as filters).
Explicitly not available on the MT5 track: retail FX feeds carry no
depth-of-book, so this entire family is dark there — a data constraint, not a
skill constraint.

### 3.5 Slower statistical arbitrage (pairs, cross-sectional, momentum, carry)

The middle-frequency shelf: cointegrated pairs (Gatev et al.), cross-sectional
mean reversion (Avellaneda-Lee 2010), time-series momentum
(Moskowitz-Ooi-Pedersen 2012), and carry as a universal asset-class premium
(Koijen et al. 2018). The prop firms on the list run these as capacity
overlays; pure-play stat-arb is more the Two Sigma/HRT-adjacent lane.

**Verdict: partial, with scars already earned.** The project's tsmom_pooled
FAIL on FX majors at M1-bar horizons is consistent with the post-2010 decay
documented in the FX momentum literature — that refutation was *predictable
from the literature*, which is worth internalizing: vanilla price-pattern
families on the most liquid FX pairs are the most arbed objects on earth.
What the literature still supports at retail-accessible horizons is carry
(FX carry at daily+ horizons; crypto funding carry — already in the book) and
relative-value spreads with a structural anchor (basis, funding dispersion)
rather than statistical co-movement alone. Candidate C7 shapes the M4 forex
revival accordingly.

### 3.6 Event and news trading

Machine-readable news, scheduled macro releases (NFP, CPI, FOMC), earnings.
The HFT expression is a pure race (first to parse, first to hit stale quotes)
— gone in the first milliseconds. Slower post-event drift exists in the
literature but is regime-fragile.

**Verdict: mostly no.** The race is unwinnable at any budget here; the slow
residue on the MT5 track collides with prop-firm news-trading restrictions and
with spread blowouts that break the cost model exactly when the signal fires
(both already flagged in the design doc's compliance section). Not worth a
round before M4, if ever.

### 3.7 Options market making and the volatility risk premium

Archetype B: quote the whole surface, hedge delta continuously, earn the
options spread plus the persistent gap between implied and realized volatility
(Carr-Wu and the VRP literature). SIG, Optiver, Akuna, CTC live here.

**Verdict: shelved, honestly.** The premium is real and documented, but the
firm-level version needs mass-quoting infrastructure, and the retail-shaped
version (systematic short vol) has a tail profile that is close to the
definition of what the risk engine and prop-firm drawdown constants exist to
forbid. Deribit is off the table on Branch A jurisdiction; CME crypto options
via an FCM is a distant M4+ conversation. Recorded here so it stops being a
temptation: this family is *research-later*, tail-first, and enters through
the same gauntlet if it ever enters at all.

### 3.8 Structural/fee games (PFOF, rebate tiering, order-type games)

Citadel Securities' retail internalization, exchange fee-tier optimization,
and the order-type gamesmanship documented in the Bodek saga. These are
contractual and regulatory positions, not strategies.

**Verdict: no transfer as strategies — full transfer as a lesson.** At this
project's size the only controllable analog is fee engineering: maker-vs-taker
choice, venue fee schedules, and utilization discipline. The existing
25bp-round-trip cost assumption dominated round 1's economics; a strategy
that is negative as a taker can be positive as a patient maker on the same
venue. Fee minimization is the one "edge" that transfers at 100% fidelity.

### 3.9 The manipulation boundary (documented, illegal, excluded)

Any honest survey must mark the line. Spoofing/layering (Sarao, Oystacher,
the JPMorgan precious-metals prosecutions), momentum ignition, quote stuffing,
and wash trading are documented profit mechanisms *and* felonies or their
regulatory equivalents. SEBI's 2025 action against Jane Street's India
expiry-day trading — alleging that cash/futures-leg buying pushed index levels
that its options leg monetized — shows regulators now police *impact-based*
strategies even when every individual order is real, and that the boundary
is contested territory even for the most sophisticated firm on the list.

**Verdict: excluded by construction.** Nothing in this project's pipeline may
depend on moving the price to profit from the move. This is also the standing
answer to any future "optimization" that quietly turns a passive family
aggressive: if the backtest's profit mechanism requires our own orders to
change other participants' behavior, it fails review regardless of P&L. Same
standing rejection as martingale/grid (design-doc hard fail), one shelf over.

## 4. The moat, quantified — why none of this photocopies

The gap between the firms on the list and this project is not intelligence or
even math; it is four ladders, each spanning several orders of magnitude.

**Latency.** Co-located FPGA reaction: ~100ns–5μs wire-to-wire. Microwave
Chicago↔NJ: ~4.0ms one way (fiber ~6.5ms — the entire Jump tower business
lives in that 2.5ms). Cloud VM co-region with a crypto matching engine:
0.5–5ms (the M3 plan; the laptop measured 121ms to OKX). Retail MT5 through a
dealer: 50–300ms *plus last look*. Between the top and bottom rung: roughly
five orders of magnitude, and the races are decided at the top one.

**Fees.** A US-equities HFT at scale nets maker rebates; a crypto VIP pays
~0–2bp maker; this project's conservative cost model books 25bp round trip.
A signal worth +3bp/trade gross is a business at the top of the ladder and a
donation at the bottom. Identical strategy, sign flipped purely by fee tier.

**Information.** Full-depth direct feeds with nanosecond timestamps and
years of archived message data, versus M1 bars (forex track) and public
websocket L2 that the M3 recorder has yet to accumulate. Whole families
(3.1, 3.4) are simply invisible below a data threshold.

**Capital & legal structure.** Exchange memberships, self-clearing, PFOF
contracts, AP status for ETF creation — moats made of paperwork that no
amount of code replicates.

The strategic conclusion, and it matches what the harness has already proven
empirically: **a solo operator's durable edge is not out-speeding or
out-modeling these firms — it is harvesting risk premia and dislocations that
are too small, too capacity-constrained, or too operationally fiddly for
their cost structures to bother with.** Round 1 demonstrated this: the three
speed-agnostic pattern families (the kind everyone can trade) were refuted,
while the capacity-limited structural carry (the kind nobody at size wants at
this project's book size) passed. The ocean, boiled, precipitates that one
crystal.

## 5. What transfers: ranked candidate families

Ranked by (prior confidence × nearness to current rungs). Each entry is a
pre-registerable family in the rounds.log sense; none is a promise. Standing
rules apply: 2 failed walk-forward rounds kill a family; costs modeled
conservatively; gates pre-registered before the run.

**C1. funding_capture — extensions of the running family (M0–M2, now).**
Institutional analog: cash-and-carry basis desks (§3.3). Three concrete,
cheap-to-test optimizations on data already in the repo or one fetcher away:
(a) *cross-venue funding dispersion* — when tradable venues' funding rates
diverge, hold the delta-neutral pair where funding is richest (or long-perp
the negative-funding venue against short-perp the positive one); needs only
funding-history fetchers per venue; (b) *funding persistence conditioning* —
funding is strongly autocorrelated; test whether an AR/premium-index filter on
top of the existing threshold improves net capture per unit of utilization;
(c) *symbol expansion* — SOL/XRP perps carry richer funding than BTC/ETH but
worse liquidity and borrow risk; gate on after-cost capture with realistic
slippage for the thinner books. All three stay inside the existing family
(re-tunes, not new families) under the design doc's family definition.

**C2. cme_micro_basis — fixed-expiry cash-and-carry, onshore (M2–M3, Branch A).**
Hypothesis: CME micro BTC/ETH futures vs onshore spot locks the annualized
basis at entry — the carry becomes a *known* number rather than a floating
funding stream, eliminating the funding-decay regime risk that M1.5 flagged.
Analog: the institutional CME basis trade. Requires an FCM account (margin
~$1–3k per micro contract; fees dollars, not bps, so favorable at small size).
Data: CME settlements + spot history, publicly reconstructable. Gate:
annualized locked basis net of all fees must exceed the trailing realized
funding-capture rate — otherwise it adds ops complexity for nothing. This is
the strongest genuinely-new candidate in this document for Branch A.

**C3. funding_timing_micro — snapshot-timing study (research now, execution M3).**
Hypothesis: funding accrues to positions held at discrete snapshots; entering
minutes before and exiting after captures the payment with far less price
exposure — *if* the perp premium doesn't systematically move against holders
around the snapshot (the literature and folklore both say it partially does;
that decay is the thing to measure). Known-crowded, so the prior is low, but
the test costs one script on public 1m candles + existing funding history.
Pre-register the gate before looking.

**C4. cross_exchange_dislocation — the slow residue of §3.2 (M3).**
Makarov-Schoar (JFE 2020) documented large, persistent cross-venue crypto
price gaps; the microsecond version belongs to Jump Crypto, but
seconds-to-minutes dislocations on venue pairs the majors underweight
(onshore: Coinbase↔Kraken) persist because monetizing them requires holding
inventory on both venues and eating withdrawal frictions — operationally
annoying, capacity-tiny, ideal for this book size. Requires the M3 recorder
running against both venues and the 1–5ms VM. Gate: dislocation frequency ×
net capture after both venues' fees, from recorded (not simulated) books.

**C5. perp_spot_basis_meanrev — intraday basis oscillation (M3).**
Hypothesis: the perp-spot basis mean-reverts at minutes horizons within its
no-arb band; trade the band edges delta-neutral. The OFI/microprice toolkit
(§3.4) serves as entry filter. Entirely dependent on recorder L2 data; enters
the gauntlet when weeks of it exist.

**C6. passive_maker_young_venue — the Menkveld entrant trade, writ tiny (M3+).**
Hypothesis: newly launched venues (Kraken US perps went live June 2026) have
wide spreads and thin professional maker presence for a window; a small
Avellaneda-Stoikov quoter with hard inventory bounds and a markout-based
toxicity cutoff can capture spread where the Wintermute-class hasn't deployed.
Highest difficulty and highest operational risk in this list; strict kill
(negative markout-adjusted capture over any 2-week window kills it), and a
compliance read of the venue's market-maker/fee schedule first. The window
closes as the venue matures — this is a scavenger trade with an expiry date.

**C7. fx_carry_session_overlay — shaping the M4 forex revival (M4, parked).**
Lesson from §3.5: when the forex track revives, spend its two rounds per
family on structurally-anchored candidates (carry-tilted holding with
vol-regime filters, compatible with FTMO Swing rules) rather than on further
price-pattern families — the literature already predicted the round-1
refutations, and it points the same direction for round 2.

**C8. vol_risk_premium — shelf, explicitly deprioritized (M4++).**
Documented premium, wrong tail shape for prop-firm constraints, no accessible
venue on Branch A today. Recorded so it's a decision, not a discovery.

## 6. The meta-edge: practices that transfer at full fidelity

The strategies mostly don't photocopy; the *operating system* does, and most
of it is already built here, which the firm evidence validates rather than
embarrasses. Virtu's loss-day statistic is not alpha, it's law-of-large-
numbers risk management over thousands of tiny edges — the same logic as the
episode-count and confidence-interval gates in `paper_status.py`. Knight's
$460M deployment failure is the argument for the parity gate and the frozen
risk-engine config. The firms' obsessive cost accounting is the 25bp
conservative cost model. Their kill discipline is the 2-round rule.

One genuinely new tool worth adopting from market-making practice now, at M0,
at zero cost: **markout (post-fill drift) tracking.** For every paper fill,
record mid-price at fill and at +1s/+10s/+60s/+300s, and report the signed
drift ("markout") alongside expectancy in the paper journal. Markouts are how
market makers measure adverse selection — whether the market systematically
moves against you right after you trade. For the funding book it will detect
execution toxicity (entering exactly when the basis is about to widen) that
episode-level P&L hides, and it becomes load-bearing infrastructure for C4–C6
later. This is a small addition to `paper_journal`/`paper_status` and the
single most concrete "utilize their methods" item this research produces.

## 7. Annotated reading list

Books, in the order they should be read for this project: Harris, *Trading
and Exchanges* (the institutional map — why each player trades); Bouchaud,
Bonart, Donier & Gould, *Trades, Quotes and Prices* (the empirical
microstructure bible; impact and order-flow facts C4–C6 depend on); Cartea,
Jaimungal & Penalva, *Algorithmic and High-Frequency Trading* (the
Avellaneda-Stoikov lineage with worked math for C6); MacKenzie, *Trading at
the Speed of Light* (what the moat physically is; cures copy-the-majors
thinking permanently).

Papers, each with why it matters here: Budish, Cramton & Shim (QJE 2015) —
the arms race is structural; don't enter races. Aquilina, Budish & O'Neill
(QJE 2022) — measures who wins races and by how much; the quantitative case
for §4. Baron, Brogaard, Hagströmer & Kirilenko (JFQA 2019) — HFT profits are
concentrated and persistent; entrants lose; the empirical warning label.
Menkveld (JFM 2013) — the new-venue market-maker case study; the thesis
behind C6. Kirilenko, Kyle, Samadi & Tuzun (JF 2017) — flash-crash dynamics;
why inventory bounds are hard constraints. Avellaneda & Stoikov (2008) —
the quoting model for C6. Cont, Kukanov & Stoikov (2014) — order-flow
imbalance; the filter for C5. Stoikov (2018) — microprice; better fair value
for thin books. Avellaneda & Lee (2010) — stat-arb reference point for §3.5.
Moskowitz, Ooi & Pedersen (2012) and Koijen et al. (2018) — momentum and
carry as premia; context for the tsmom refutation and the carry survivor.
Makarov & Schoar (JFE 2020) — cross-exchange crypto dislocations; the
empirical basis for C4. Schmeling, Schrimpf & Todorov, "Crypto Carry" — the
funding-capture family in the literature, including its crash-risk profile;
required reading before M2 sizes anything.

## 8. Bottom line

The famous firms' profits decompose into structure (speed, fees, memberships,
data) and discipline (measurement, cost accounting, inventory limits, kill
rules). The structure does not transfer at any budget available here — five
orders of magnitude of latency and two orders of magnitude of fees sit in
between — and the strategies that depend on it (latency arb, queue-priority
market making on major books, news races, PFOF-style internalization) are
closed, while the manipulation-adjacent mechanisms are excluded by law and by
construction. The discipline transfers completely and is already this
project's architecture. The strategy families that survive the transfer
analysis are the capacity-constrained structural trades — carry, basis,
dislocation — of which the first (funding capture) has already passed the
gauntlet and is running on paper; this document adds one strong onshore
candidate (C2, fixed-expiry CME micro basis), three data-cheap extensions
(C1a–c, C3), three recorder-dependent M3 families (C4–C6), a shaping
constraint for the M4 forex revival (C7), and one immediately actionable
practice upgrade (markout tracking in the paper journal). The ocean's
composition is now documented; the parts of it this vessel can actually fish
are on the map, and every one of them still has to pass through the same
gates as everything that came before.
