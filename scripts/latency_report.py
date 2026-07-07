#!/usr/bin/env python3
"""Feed-latency QA on recorded books5 — permitted QA per the pre-registration
(latency distributions carry no signal content).

recv_ts (local wall clock at message receipt) minus ts (exchange event time)
per instrument. On the laptop this number is INDICATIVE — it includes local
clock skew (macOS NTP is typically within tens of ms) and OKX's own snapshot
batching (books5 pushes at ~100ms cadence) — but its distribution is exactly
what the C5 cost model needs to know: how stale is a book by the time the
strategy can see it? The VM-phase rerun of this report is the before/after
for the $40/mo decision.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data" / "crypto"
INSTS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "BTC-USDT", "ETH-USDT"]


def main() -> int:
    print(f"{'instrument':>14} {'msgs':>8} {'p50':>7} {'p90':>7} {'p99':>7} {'rate/min':>9}")
    for inst in INSTS:
        files = sorted((DATA / inst / "books5").glob("*.parquet"))
        if not files:
            print(f"{inst:>14} — no data")
            continue
        df = pd.concat(
            [pd.read_parquet(f, columns=["ts", "recv_ts"]) for f in files],
            ignore_index=True,
        )
        lat = (df["recv_ts"] - df["ts"]).to_numpy()
        lat = lat[(lat > -1_000) & (lat < 60_000)]  # clock-skew outlier guard
        span_min = (df["ts"].max() - df["ts"].min()) / 60_000
        p50, p90, p99 = np.percentile(lat, [50, 90, 99])
        print(f"{inst:>14} {len(df):>8,} {p50:>6.0f}ms {p90:>6.0f}ms {p99:>6.0f}ms "
              f"{len(df)/span_min:>8.1f}")
    print("\nnote: laptop-tier numbers (clock skew + wifi + OKX 100ms snapshot")
    print("cadence). Rerun on the in-region VM for the before/after that prices")
    print("the M3 infrastructure decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
