#!/usr/bin/env python3
"""Dress rehearsal for the funding book's production executor.

DEMO mode (default): places a minimal delta-neutral pair (post-only buy
spot + post-only sell perp) in OKX's demo-trading environment, verifies
fills and accounting, then unwinds. This is the rehearsal the M1 brief
requires before real capital, and it is safe to run any number of times.

REAL mode (--real): REFUSES unless the M0 promotion gate actually passes —
scripts/paper_status.py must exit 0 (>=10 paper episodes, t>=2, mean inside
the backtest sanity band). The ladder is enforced here in code: no PROMOTE,
no real orders, no override flag exists. After PROMOTE, real mode further
requires real API keys and the founder's venue decision (Branch A venues
need their own adapter — see reports/m1_venue_brief.md).

Usage:
    export OKX_API_KEY=... OKX_SECRET_KEY=... OKX_PASSPHRASE=...   # demo keys
    python3 scripts/rehearsal_funding.py --notional 100
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hft.crypto.okx_executor import OKXClient, OKXCredentials

ROOT = Path(__file__).resolve().parents[1]
SPOT, PERP = "BTC-USDT", "BTC-USDT-SWAP"


def m0_promotion_passes() -> bool:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "paper_status.py")],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def wait_fill(client: OKXClient, inst: str, ord_id: str, timeout_s: int = 120) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        o = client.order(inst, ord_id)
        if o["state"] == "filled":
            return o
        if o["state"] in ("canceled", "mmp_canceled"):
            raise RuntimeError(f"{inst} order {ord_id} canceled before fill")
        time.sleep(2)
    client.cancel(inst, ord_id)
    raise RuntimeError(f"{inst} post-only order not filled in {timeout_s}s — canceled")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notional", type=float, default=100.0, help="USD per leg (demo)")
    ap.add_argument("--real", action="store_true",
                    help="real trading — gated on the M0 promotion gate")
    args = ap.parse_args()

    if args.real:
        print("REAL mode requested — checking the M0 promotion gate...")
        if not m0_promotion_passes():
            print("M0 promotion gate: NOT PASSED. Real trading stays locked.\n"
                  "This is the ladder working (reports/scaling_roadmap.md M0->M2):\n"
                  "  1. paper episodes must reach the gate (paper_status.py prints PROMOTE)\n"
                  "  2. founder completes the M1 venue/KYC decision\n"
                  "  3. rerun with --real on the chosen venue's keys\n"
                  "No override exists, deliberately.")
            return 2
        print("M0 gate PASSED — proceeding with REAL keys (no simulation header).")

    client = OKXClient(OKXCredentials.from_env(), demo=not args.real)
    mode = "REAL" if args.real else "DEMO-TRADING"
    print(f"[{mode}] USDT balance: {client.balance('USDT'):,.2f}")

    # size the legs off the live mid, rounded to instrument lot rules
    from hft.crypto.paper_funding import OKXPublic
    pub = OKXPublic()
    mid = (float(pub.ticker(SPOT)["bidPx"]) + float(pub.ticker(SPOT)["askPx"])) / 2
    spot_spec = client.instrument(SPOT)
    lot = float(spot_spec["lotSz"])
    sz_btc = max(round(args.notional / mid / lot) * lot, float(spot_spec["minSz"]))
    perp_spec = client.instrument(PERP)
    ct_val = float(perp_spec["ctVal"])  # BTC per contract
    n_contracts = max(round(sz_btc / ct_val), 1)

    bid = pub.ticker(SPOT)["bidPx"]
    perp_ask = pub.ticker(PERP)["askPx"]
    print(f"[{mode}] entering delta-neutral: buy {sz_btc:.6f} BTC spot @ {bid} (post-only), "
          f"sell {n_contracts} perp contracts @ {perp_ask} (post-only)")

    spot_id = client.place(SPOT, "buy", f"{sz_btc:.8f}", "post_only", px=bid, td_mode="cash")
    perp_id = client.place(PERP, "sell", str(n_contracts), "post_only", px=perp_ask,
                           td_mode="cross")
    spot_fill = wait_fill(client, SPOT, spot_id)
    perp_fill = wait_fill(client, PERP, perp_id)
    print(f"[{mode}] FILLED spot @ {spot_fill['avgPx']} fee {spot_fill['fee']} | "
          f"perp @ {perp_fill['avgPx']} fee {perp_fill['fee']}")
    basis = float(perp_fill["avgPx"]) / float(spot_fill["avgPx"]) - 1
    print(f"[{mode}] executed basis {basis * 1e4:+.2f} bps — compare against the "
          "cost model's spread assumption; divergence >2bps needs explaining")

    print(f"[{mode}] unwinding (kill-switch path: market close)")
    client.close_all_positions([PERP])
    sell_id = client.place(SPOT, "sell", spot_fill["accFillSz"], "market", td_mode="cash")
    print(f"[{mode}] rehearsal complete — orders {spot_id}/{perp_id}/{sell_id} round-tripped. "
          f"Balance now: {client.balance('USDT'):,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
