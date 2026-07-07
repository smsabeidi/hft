#!/usr/bin/env python3
"""Run one paper-trading evaluation of the funding-capture strategy.

Cron-able: state persists in data/paper/funding_state.json. Suggested laptop
schedule while the VM doesn't exist yet (funding pays every 8h; a 30-minute
cadence is more than enough):

    */30 * * * * cd ~/Documents/HFT && python3 scripts/paper_funding.py --once

Promotion to a real-capital conversation requires >=10 completed paper
episodes with accounting consistent with the backtest (design doc demo-gate
spirit). This script trades nothing, ever.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hft.crypto.paper_funding import PaperFundingEngine, PaperParams

PAPER_DIR = Path(__file__).resolve().parents[1] / "data" / "paper"


def state_path(inst: str) -> Path:
    # one state file PER instrument — round 1 passed on pooled BTC+ETH, so
    # both run on paper, and their books must never clobber each other
    return PAPER_DIR / f"funding_state_{inst}.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", default="BTC-USDT-SWAP")
    ap.add_argument("--once", action="store_true", help="single evaluation (default)")
    args = ap.parse_args()

    engine = PaperFundingEngine(PaperParams(perp_inst=args.inst), state_path(args.inst))
    result = engine.tick()
    st = engine.state
    print(f"{args.inst}: {result['action']} | position {'ON' if result['on'] else 'OFF'} | "
          f"smooth {result.get('smooth_bps', float('nan'))} bps/8h | "
          f"paper equity {result.get('equity_bps', 0)} bps | "
          f"completed episodes: {len(st['episodes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
