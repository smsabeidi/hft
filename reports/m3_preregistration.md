# M3 pre-registration — order-book families C4/C5/C6, gates fixed blind

Written 2026-07-07 ~06:20 UTC. At this moment the L2 dataset contains about
four minutes of smoke-test data (two short recorder verification runs). No
signal-bearing analysis of any recorded order-book data has been performed.
Everything below — signal definitions, grids, cost models, walk-forward
schemes, floors, kill criteria — is therefore fixed BEFORE the data exists.

Binding rules: this document may be AMENDED only by dated additions, never
by editing what is written, and only before the affected family's first
round runs. A round that deviates from its pre-registered spec is void and
still consumes one of the family's two rounds. This is the same discipline
that produced trustworthy refutations on the forex track, applied one rung
earlier — at design time.

## The recorder (running as of this document)

OKX public websocket, books5 (5-level snapshots; exchange ts, local recv_ts,
seq) + trades, for BTC-USDT-SWAP, ETH-USDT-SWAP, BTC-USDT, ETH-USDT.
Laptop-tier ops: cron slot at minute 10 of every even hour, self-terminating
118-minute runs (a hung recorder self-heals at the next slot), zstd parquet,
disk guard refusing to start below 5GB free or above a 20GB dataset cap.
Measured smoke-run rate ≈ 250MB/day for all four instruments → the cap holds
roughly 75 recorded days. Laptop recv latency is indicative (~121ms measured
earlier); it is adequate for seconds-to-minutes signals and inadequate for
any queue-position claim — that asymmetry shapes which families may run on
this data (C5 yes; C6 no, see below).

Permitted before any round, as data QA (non-signal, analogous to the forex
data-sanity pass): gap/coverage scans, latency and spread distributions,
message-rate statistics. NOT permitted outside a round: any analysis that
estimates predictability (basis autocorrelation, imbalance→return
regressions, and the like).

AMENDMENT 2026-07-07 (ops only, no gate touched): the fixed 2h cron slot
proved fragile against laptop sleep (skipped slots + suspended runs observed
same day). Replaced by a 15-minute supervisor (`scripts/ensure_recorder.sh`)
that restarts a self-terminating run whenever none is alive, bounding
post-wake recovery at 15 minutes. Coverage accounting in the C5 data floor
is unchanged and will reflect whatever gaps sleep still causes.

## Common cost model (all families)

Taker legs at 25bp round trip for the 4-leg perp+spot pair (identical to the
funding-capture convention) — but slippage is now MEASURED: half the
observed book5 spread per leg at signal time, from the recorded books, not
an assumed constant. A 5bp RT all-maker scenario is reported alongside every
result, non-gating. No result may be quoted net of the optimistic scenario
only.

## C5 — perp_spot_basis_meanrev (first eligible family on laptop data)

Hypothesis: the OKX perp-spot basis mean-reverts at minutes horizons inside
its no-arbitrage band; entering delta-neutral at stretched basis and exiting
at reversion captures the swing after costs.

Frozen spec:
- basis_t = perp_mid/spot_mid − 1, from books5 snapshots of the two legs
  matched within 500ms (unmatched snapshots dropped, drop-rate reported).
- z_t = (basis_t − mean_w(basis)) / std_w(basis), rolling window w.
- Enter when z ≥ z_enter (short perp / long spot — the side executable
  without borrowing spot). The z ≤ −z_enter side is recorded as a SHADOW
  book only, non-gating, because the mirrored execution needs margin/borrow
  the venue setup does not yet have.
- Exit when z ≤ z_exit, or after max_hold minutes, whichever first.
- Grid, frozen: w ∈ {30m, 120m, 480m}; z_enter ∈ {1.5, 2.0, 3.0};
  z_exit ∈ {0.0, 0.5}; max_hold ∈ {60m, 240m}. 36 combinations, pooled
  BTC+ETH. No additions after this line.
- Walk-forward: train 10 recorded days / test 5, rolled by 5; optimize by
  after-cost net on train, freeze, evaluate on test — the standard scheme.
- Data floor: no round before 30 distinct recorded days spanning ≥ 21
  calendar days with ≥ 60% minute coverage; the coverage report publishes
  with the round.
- GATE: ≥ 100 pooled OOS trades, mean net > 0, t ≥ 2.0 on trade nets,
  window stability ≥ 60%. Kill: 2 failed rounds, standing rule.

## C4 — cross_exchange_dislocation (procedure pre-registered, thresholds deferred)

Thresholds cannot be honestly fixed without the second venue's fee schedule
and book data, and the venue depends on the founder's Branch-A/B decision
(reports/m1_venue_brief.md). Pre-committed procedure: when the M1 decision
lands, (1) the recorder gains the second venue's matching instruments;
(2) a dated amendment here fixes the entry/exit thresholds and fee model
BEFORE any joint cross-venue analysis is run; (3) until that amendment,
only descriptive statistics (distribution of cross-venue mid gaps versus
combined round-trip fees) may be produced, and they may not inform the
amendment's thresholds beyond the published fee arithmetic. Violation voids
the family's first round.

## C6 — passive_maker_young_venue (pre-committed to VM-grade data; cannot run on laptop data)

Queue position is the entire economics of passive making, and books5
snapshots at ~121ms cannot support queue claims. Pre-committed requirements
before round 1: incremental full-depth feed (OKX `books` channel or the
chosen venue's equivalent) recorded from an in-region VM; venue maker/taker
fee schedule pinned in config (founder); quoting model is Avellaneda-Stoikov
with hard inventory bounds (risk-engine constants, never optimized).
Simulation engine: hftbacktest (v2.4.4 resolves cleanly against this Python;
install deferred until needed) for queue-position and latency-aware replay.
GATE (fixed now): in simulation on ≥ 2 disjoint recorded weeks, positive
markout-adjusted spread capture net of fees with t ≥ 2.0 on daily P&L;
any 2-week window with negative markout-adjusted capture fails the round.
Live paper quoting begins only after the sim gate passes. Kill: 2 rounds.

## Sequencing note

Nothing here jumps the ladder. M0 (paper promotion) and the founder-owned
M1/M2 rungs proceed unchanged; the recorder simply makes the M3 clock start
now instead of after M2, exactly as M1 was de-serialized from M0. First
possible C5 round: ~30 recorded days out, early August 2026 at best.
