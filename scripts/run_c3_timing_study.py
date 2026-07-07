#!/usr/bin/env python3
"""C3 — funding snapshot-timing study (research doc §5, candidate C3).

Hypothesis: funding is exchanged at discrete 8h snapshots; holding the
delta-neutral pair (short perp / long spot) only around the snapshot —
enter T-delta, exit T+delta — collects the payment with minutes of exposure
instead of hours, IF the perp premium does not systematically collapse by
the same amount around the snapshot.

P&L per unit notional per event = rate + (pi(T-delta) - pi(T+delta)) - costs,
where pi is Binance's premium index (basis proxy: short perp gains when the
premium falls while the position is on).

KNOWN FAVORABLE BIAS, stated up front: the study conditions on the rate
actually paid at T, treated as knowable at T-delta. The rate is an 8h average
that is nearly pinned in its final minutes, so for delta <= 30m this is mild,
but it can only flatter the result. Therefore: a FAIL here is conclusive;
a PASS would require a stricter re-run on the predicted-rate series before
being believed.

PRE-REGISTERED GATE (written before the run):
- events: all snapshots with rate >= 30bp (the only regime where 25bp RT
  costs could possibly clear); deltas {5, 15, 30, 60} minutes.
- gate: at 25bp RT costs (round-1 conservative), pooled BTC+ETH mean net > 0
  with t >= 2.0 and >= 100 events, for at least one pre-registered delta.
- also reported, non-gating: 5bp RT (all-maker floor) and descriptive drift
  tables at rate >= 3bp and >= 10bp. No post-hoc threshold shopping.
"""

from __future__ import annotations

import io
import ssl
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FUNDING_DIR = ROOT / "data" / "funding"
PREMIUM_DIR = FUNDING_DIR / "premium"
ROUNDS_LOG = ROOT / "reports" / "rounds.log"
BASE = "https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines"

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
FROM_MONTH, TO_MONTH = "2023-07", "2026-06"
DELTAS_MIN = (5, 15, 30, 60)
GATE_RATE_BPS = 30.0
COSTS_BPS = {"conservative_25bpRT": 25.0, "maker_floor_5bpRT": 5.0}
MIN_EVENTS = 100


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_premium_month(symbol: str, month: str) -> pd.DataFrame | None:
    """Monthly 1m premium-index klines, cached as parquet. None if missing."""
    cache = PREMIUM_DIR / f"{symbol}-{month}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    url = f"{BASE}/{symbol}/1m/{symbol}-1m-{month}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as r:
            payload = r.read()
    except Exception:
        return None
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        raw = zf.read(zf.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), header=None)
    if not str(df.iloc[0, 0]).lstrip("-").isdigit():  # newer files carry a header row
        df = df.iloc[1:].reset_index(drop=True)
    out = pd.DataFrame(
        {
            "minute_ms": df[0].astype("int64"),
            "pi": df[4].astype(float),  # close of the premium index for the minute
        }
    )
    PREMIUM_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache, index=False)
    return out


def load_premium(symbol: str, months: list[str]) -> pd.Series:
    frames, missing = [], []
    for m in months:
        df = fetch_premium_month(symbol, m)
        if df is None:
            missing.append(m)
        else:
            frames.append(df)
    if missing:
        print(f"{symbol}: missing premium months: {','.join(missing)}")
    all_df = pd.concat(frames, ignore_index=True).drop_duplicates("minute_ms")
    return all_df.set_index("minute_ms")["pi"].sort_index()


def event_table(symbol: str, pi: pd.Series) -> pd.DataFrame:
    funding = pd.read_parquet(FUNDING_DIR / f"{symbol}_funding.parquet")
    funding = funding[
        (funding["time"] >= pd.Timestamp(FROM_MONTH + "-01", tz="UTC"))
    ]
    rows = []
    for _, rec in funding.iterrows():
        t_ms = (rec["time"].value // 10**6) // 60_000 * 60_000  # minute floor
        row = {"symbol": symbol, "time": rec["time"], "rate": rec["rate"]}
        ok = False
        for d in DELTAS_MIN:
            pre = pi.get(t_ms - d * 60_000)
            post = pi.get(t_ms + d * 60_000)
            if pre is None or post is None or np.isnan(pre) or np.isnan(post):
                row[f"drift_{d}"] = np.nan
                continue
            # short perp / long spot: gain = premium at entry minus at exit
            row[f"drift_{d}"] = pre - post
            ok = True
        if ok:
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> int:
    months = [m.strftime("%Y-%m") for m in pd.period_range(FROM_MONTH, TO_MONTH, freq="M")]
    events = []
    for sym in SYMBOLS:
        pi = load_premium(sym, months)
        ev = event_table(sym, pi)
        print(f"{sym}: {len(ev)} snapshots with premium coverage "
              f"({ev['time'].min().date()} .. {ev['time'].max().date()})")
        events.append(ev)
    ev = pd.concat(events, ignore_index=True)
    ev.to_parquet(FUNDING_DIR / "c3_timing_events.parquet", index=False)

    # descriptive: premium drift around snapshots by funding-rate bucket
    print("-" * 70)
    print("mean premium drift T-d -> T+d (bps, + = favorable to short-perp), by rate bucket:")
    for lo, label in [(3e-4, ">=3bp"), (1e-3, ">=10bp"), (3e-3, ">=30bp")]:
        sub = ev[ev["rate"] >= lo]
        drifts = [f"d={d}m {sub[f'drift_{d}'].mean()*1e4:+.2f}" for d in DELTAS_MIN]
        print(f"  rate {label} (n={len(sub)}): " + " | ".join(drifts)
              + f" | mean rate {sub['rate'].mean()*1e4:.1f}bp")

    # the gate: net = rate + drift - costs, at rate >= 30bp
    sub = ev[ev["rate"] >= GATE_RATE_BPS / 1e4]
    print("-" * 70)
    print(f"GATE SAMPLE: rate >= {GATE_RATE_BPS:.0f}bp -> {len(sub)} events")
    best = {}
    for cost_label, cost_bps in COSTS_BPS.items():
        for d in DELTAS_MIN:
            net = (sub["rate"] + sub[f"drift_{d}"] - cost_bps / 1e4).dropna()
            n = len(net)
            mean = net.mean() if n else 0.0
            t = float(mean / (net.std(ddof=1) / np.sqrt(n))) if n > 1 and net.std(ddof=1) > 0 else 0.0
            print(f"  {cost_label:24s} d={d:>2}m: n={n:>4} mean net {mean*1e4:+7.2f}bp t={t:+.2f}")
            if cost_label == "conservative_25bpRT":
                best[d] = (n, float(mean), t)

    passed = any(n >= MIN_EVENTS and m > 0 and t >= 2.0 for n, m, t in best.values())
    n_gate = max((v[0] for v in best.values()), default=0)
    best_d = max(best, key=lambda d: best[d][1]) if best else 0
    print(f"C3 GATE: {'PASS (needs stricter predicted-rate re-run before belief)' if passed else 'FAIL'}")

    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=funding_timing_micro "
            f"range={FROM_MONTH}..{TO_MONTH} scheme=event-study costs=25bpRT "
            f"gate_events={n_gate} best_delta={best_d}m "
            f"best_mean_net_bps={best.get(best_d, (0, 0, 0))[1]*1e4:.1f} "
            f"t={best.get(best_d, (0, 0, 0))[2]:.2f} result={'PASS-provisional' if passed else 'FAIL'}\n"
        )
    print(f"study logged to {ROUNDS_LOG}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
