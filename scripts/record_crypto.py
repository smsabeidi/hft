#!/usr/bin/env python3
"""Run the OKX market-data recorder (phase-3 component 1).

Usage:
    python3 scripts/record_crypto.py --inst BTC-USDT-SWAP ETH-USDT-SWAP \
        --minutes 120 --rotate 15

Self-terminates after --minutes (default 120) so a forgotten recorder can't
fill the disk. Output: data/crypto/{instId}/{books5|trades}/*.parquet with
exchange ts + local recv_ts on every row. On the laptop the recv latency is
indicative only; deploy to a VM in the exchange region for real numbers.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hft.crypto.recorder import Recorder

OUT_ROOT = Path(__file__).resolve().parents[1] / "data" / "crypto"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", nargs="+", default=["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
    ap.add_argument("--minutes", type=int, default=120)
    ap.add_argument("--rotate", type=int, default=15)
    args = ap.parse_args()

    rec = Recorder(args.inst, OUT_ROOT, rotate_minutes=args.rotate, max_minutes=args.minutes)
    try:
        asyncio.run(rec.run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
