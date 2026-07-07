#!/usr/bin/env python3
"""Rung M1.5 (provisional): does the funding-capture edge transfer to Kraken?

Design — pre-registered BEFORE results were seen (git history is the witness):
- Data: Kraken Futures public funding history (~1 trailing year), PF_XBTUSD +
  PF_ETHUSD, hourly rates summed to 8h buckets (full buckets only).
- Strategy: hft/crypto/funding_capture.backtest_capture with the EXACT frozen
  round-1 parameters (enter 0.5bps/8h, exit 0, smooth 9, fee 25bps RT,
  util 0.6). No grid. No optimization. Pure out-of-sample transfer.
- PROVISIONAL gate (1y of data supports ~6 pooled episodes at round-1 rates,
  so the full 30-episode/t>=2 gate is unreachable by construction):
    PASS-provisional: pooled episodes >= 4 AND mean episode net > 0 AND
                      mean >= 25% of round 1's +74.2 bps.
    FAIL: mean episode net <= 0  ->  the edge does NOT transfer onshore;
          Branch A (US) needs a rethink before any real capital.
    INCONCLUSIVE: anything else (too few episodes) — wait for history.
- Whatever prints, the verdict is logged to reports/rounds.log and the full
  gate must still pass once enough onshore history exists.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from hft.crypto.funding_capture import CaptureParams, backtest_capture
from hft.crypto.kraken_funding import fetch_funding, to_8h_intervals

ROUNDS_LOG = Path(__file__).resolve().parents[1] / "reports" / "rounds.log"
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "funding"

FROZEN = CaptureParams(enter_bps=0.5, exit_bps=0.0, smooth_n=9,
                       fee_rt_bps=25.0, utilization=0.6)
BACKTEST_MEAN_NET = 74.2e-4  # round 1 pooled mean episode net
SYMBOLS = ("PF_XBTUSD", "PF_ETHUSD")


def main() -> int:
    pooled = []
    for sym in SYMBOLS:
        hourly = fetch_funding(sym)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        hourly.to_parquet(DATA_DIR / f"kraken_{sym}_hourly.parquet", index=False)
        intervals = to_8h_intervals(hourly)
        dropped = 0 if hourly.empty else (
            len(to_8h_intervals(hourly, require_full=False)) - len(intervals)
        )
        r = backtest_capture(intervals.rename(columns={"rate": "rate"}), FROZEN)
        pooled.extend(r.episodes)
        span = (f"{intervals['time'].iloc[0].date()}..{intervals['time'].iloc[-1].date()}"
                if len(intervals) else "n/a")
        print(f"{sym}: {len(hourly):,} hourly rates -> {len(intervals):,} full 8h "
              f"intervals ({span}, {dropped} partial dropped)")
        print(f"  frozen-param result: {len(r.episodes)} episodes, "
              f"net {r.net_return * 1e4:+.1f} bps total, "
              f"annualized {r.annualized_net:+.2%}, "
              f"time-in-market {r.time_in_market:.0%}")
        for e in r.episodes:
            print(f"    {e.entry_time.date()} -> {e.exit_time.date()}  "
                  f"{e.intervals} intervals  net {e.net_return * 1e4:+.1f} bps")

    print("-" * 60)
    n = len(pooled)
    nets = np.array([e.net_return for e in pooled])
    mean = float(nets.mean()) if n else 0.0
    print(f"pooled: {n} episodes, mean net {mean * 1e4:+.1f} bps "
          f"(round-1 reference +{BACKTEST_MEAN_NET * 1e4:.1f} bps)")

    if n and mean <= 0:
        verdict = "FAIL"
        msg = ("edge does NOT transfer to Kraken funding at frozen params. "
               "Branch A (US) real-capital plan is blocked pending rethink.")
    elif n >= 4 and mean > 0 and mean >= 0.25 * BACKTEST_MEAN_NET:
        verdict = "PASS-provisional"
        msg = ("edge transfers at frozen params on ~1y of onshore-relevant "
               "history. Full gate still required as history deepens.")
    else:
        verdict = "INCONCLUSIVE"
        msg = "not enough episodes yet; re-run as Kraken history accrues."
    print(f"M1.5 {verdict}: {msg}")

    ROUNDS_LOG.parent.mkdir(exist_ok=True)
    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=funding_capture_m15_kraken "
            f"range=trailing-1y scheme=frozen-params-transfer costs=25bpRT/0.6util "
            f"episodes={n} mean_ep_net_bps={mean * 1e4:.1f} result={verdict}\n"
        )
    print(f"logged to {ROUNDS_LOG}")
    return 0 if verdict != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
