#!/usr/bin/env python3
"""Promotion gate for the paper-trading books — self-assessing.

Reads every data/paper/funding_state_*.json and evaluates the design-doc
promotion criterion mechanically, so "are we ready for a real-capital
conversation?" has a yes/no answer with numbers, not vibes.

PROMOTE requires ALL of:
- >=10 completed episodes pooled across instruments
- pooled mean episode net > 0
- t-stat >= 2.0 on episode nets
- pooled mean net within a sanity band of the backtest's round-1 mean
  (+74.2 bps): live falling below ~25% of backtest signals cost-model or
  regime divergence that must be explained before promotion.

Exit 0 = PROMOTE-ready. Exit 1 = not yet (prints exactly what's missing).
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

PAPER_DIR = Path(__file__).resolve().parents[1] / "data" / "paper"
BACKTEST_MEAN_NET_BPS = 74.2  # round 1, pooled BTC+ETH, 31 OOS episodes
MIN_EPISODES = 10
MIN_TSTAT = 2.0
CONSISTENCY_FLOOR = 0.25  # live mean must be >= 25% of backtest mean


def main() -> int:
    states = sorted(PAPER_DIR.glob("funding_state_*.json"))
    if not states:
        print("no paper state files yet — is the cron running? (crontab -l)")
        return 1

    nets: list[float] = []
    marks: list[dict] = []
    now_ms = time.time() * 1000
    for path in states:
        s = json.loads(path.read_text())
        inst = path.stem.replace("funding_state_", "")
        eps = s.get("episodes", [])
        inst_nets = [e["net"] for e in eps if "net" in e]
        nets.extend(inst_nets)
        marks.extend(s.get("markouts", []))
        open_note = ""
        if s.get("on"):
            age_h = (now_ms - (s.get("entry_time") or now_ms)) / 3.6e6
            open_note = (f" | OPEN {age_h:.1f}h, gross so far "
                         f"{s.get('episode_gross', 0.0) * 1e4:+.1f}bps")
        mean_str = f"{(sum(inst_nets) / len(inst_nets)) * 1e4:+.1f}" if inst_nets else "n/a"
        print(f"{inst}: {len(eps)} episodes, mean net {mean_str} bps, "
              f"equity {s.get('equity', 0.0) * 1e4:+.2f} bps{open_note}")

    # markouts: basis drift after each fill, + = favorable. Diagnostic only
    # (never gates promotion); persistently negative means fills are being
    # adversely selected and the entry timing needs a look before the episode
    # economics can be trusted.
    if marks:
        parts = []
        for m in (1, 5, 15, 60):
            vals = [mk[f"m{m}"] for mk in marks if mk.get(f"m{m}") is not None]
            if vals:
                parts.append(f"+{m}m {sum(vals) / len(vals):+.2f}")
        if parts:
            print(f"markouts ({len(marks)} fills, bps, + = favorable): " + " | ".join(parts))
        m15 = [mk["m15"] for mk in marks if mk.get("m15") is not None]
        if len(m15) >= 5 and sum(m15) / len(m15) < 0:
            print("  note: mean 15m markout is negative — fills are adversely "
                  "selected; investigate entry timing.")

    n = len(nets)
    print("-" * 60)
    if n == 0:
        print(f"pooled: 0 completed episodes (need {MIN_EPISODES}). "
              "Funding pays every 8h; episodes close when the smoothed rate "
              "crosses the exit threshold — this takes days, by design.")
        return 1

    mean = sum(nets) / n
    mean_bps = mean * 1e4
    if n > 1:
        var = sum((x - mean) ** 2 for x in nets) / (n - 1)
        t = mean / math.sqrt(var / n) if var > 0 else float("inf")
    else:
        t = 0.0

    checks = {
        f"episodes >= {MIN_EPISODES}": n >= MIN_EPISODES,
        "mean net > 0": mean > 0,
        f"t-stat >= {MIN_TSTAT}": t >= MIN_TSTAT,
        f"mean within sanity band of backtest ({BACKTEST_MEAN_NET_BPS}bps)":
            mean_bps >= CONSISTENCY_FLOOR * BACKTEST_MEAN_NET_BPS,
    }
    print(f"pooled: {n} episodes, mean net {mean_bps:+.1f} bps, t={t:.2f} "
          f"(backtest reference: +{BACKTEST_MEAN_NET_BPS} bps)")
    for label, ok in checks.items():
        print(f"  [{'x' if ok else ' '}] {label}")
    if all(checks.values()):
        print("PROMOTE: paper evidence is consistent with the backtest. "
              "Next rung is the founder's real-capital decision (see "
              "reports/scaling_roadmap.md M2).")
        return 0
    print("NOT YET: keep accruing. The gate re-evaluates every run.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
