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
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hft.crypto.recorder import Recorder

OUT_ROOT = Path(__file__).resolve().parents[1] / "data" / "crypto"
# perp legs feed C5/C6 research; spot legs make the basis directly observable
DEFAULT_INSTS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "BTC-USDT", "ETH-USDT"]


def _dataset_gb(root: Path) -> float:
    return sum(f.stat().st_size for f in root.rglob("*.parquet")) / 1e9 if root.exists() else 0.0


def disk_guard(min_free_gb: float, cap_gb: float) -> str | None:
    """Fail LOUDLY before recording instead of quietly filling the disk.
    The dataset is the asset — the guard never deletes, it only refuses."""
    free_gb = shutil.disk_usage(OUT_ROOT.parent).free / 1e9
    if free_gb < min_free_gb:
        return f"free disk {free_gb:.1f}GB < {min_free_gb}GB floor — not recording"
    ds = _dataset_gb(OUT_ROOT)
    if ds > cap_gb:
        return (f"dataset {ds:.1f}GB > {cap_gb}GB cap — not recording. "
                "Raise --cap-gb deliberately or archive data/crypto elsewhere.")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", nargs="+", default=DEFAULT_INSTS)
    ap.add_argument("--minutes", type=int, default=120)
    ap.add_argument("--rotate", type=int, default=15)
    ap.add_argument("--min-free-gb", type=float, default=5.0)
    ap.add_argument("--cap-gb", type=float, default=20.0)
    args = ap.parse_args()

    if (reason := disk_guard(args.min_free_gb, args.cap_gb)) is not None:
        print(f"DISK GUARD: {reason}")
        return 1

    rec = Recorder(args.inst, OUT_ROOT, rotate_minutes=args.rotate, max_minutes=args.minutes)
    try:
        asyncio.run(rec.run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
