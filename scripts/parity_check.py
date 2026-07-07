#!/usr/bin/env python3
"""Parity gate: diff the Python harness trade log against the MT5 parity CSV.

The gate (design doc, Recommended Approach): the same tick window replayed
through the Python engine and the MT5 Strategy Tester ("every tick based on
real ticks", Dukascopy custom symbol) must produce the same trades. Every
divergence must be explained by a documented cost-model difference;
unexplained divergence blocks demo promotion.

Usage:
    # 1. Python side: run a backtest and save trades
    #    res.trades.to_csv("reports/py_trades.csv", index=False)
    # 2. MT5 side: run the EA in the Strategy Tester; grab the parity CSV
    #    from the terminal COMMON files folder.
    python3 scripts/parity_check.py reports/py_trades.csv parity_session_breakout.csv \
        --time-tol-s 90 --price-tol-pips 1.0

Exit 0 = parity holds inside tolerances. Non-zero = divergence, gate blocked.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

PIP = 0.0001

# MT5 DEAL_TYPE: 0=buy, 1=sell. A buy deal opens a long or closes a short;
# we match on ENTRY deals by pairing consecutive deals per position, so the
# comparison below works on entries extracted from each side's log.


def load_python(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["entry_time", "exit_time"])
    return pd.DataFrame(
        {
            "time": pd.to_datetime(df["entry_time"], utc=True),
            "side": df["side"].astype(int),
            "lots": df["lots"].astype(float),
            "price": df["entry_price"].astype(float),
        }
    ).sort_values("time", ignore_index=True)


def load_mt5(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df["deal_type"] = df["deal_type"].astype(int)
    # entries: the first deal of each in/out pair. MT5 logs both in and out
    # deals; profit==0 rows are entries on netting accounts (heuristic — the
    # profit column is 0 for the IN deal). Adjust here if the firm's server
    # logs differently; parity failures from pairing show up as count diffs.
    entries = df[df["profit"] == 0.0].copy()
    entries["side"] = entries["deal_type"].map({0: 1, 1: -1})
    return pd.DataFrame(
        {
            "time": entries["time"],
            "side": entries["side"].astype(int),
            "lots": entries["lots"].astype(float),
            "price": entries["price"].astype(float),
        }
    ).sort_values("time", ignore_index=True)


def diff(py: pd.DataFrame, mt5: pd.DataFrame, time_tol_s: int, price_tol_pips: float) -> int:
    issues = 0
    print(f"python entries: {len(py)}   mt5 entries: {len(mt5)}")
    if len(py) != len(mt5):
        print(f"DIVERGENCE: trade count mismatch ({len(py)} vs {len(mt5)})")
        issues += abs(len(py) - len(mt5))

    n = min(len(py), len(mt5))
    for i in range(n):
        p, m = py.iloc[i], mt5.iloc[i]
        problems = []
        dt = abs((p["time"] - m["time"]).total_seconds())
        if dt > time_tol_s:
            problems.append(f"time off by {dt:.0f}s")
        if p["side"] != m["side"]:
            problems.append(f"side {p['side']} vs {m['side']}")
        if abs(p["lots"] - m["lots"]) > 1e-9:
            problems.append(f"lots {p['lots']} vs {m['lots']}")
        dp = abs(p["price"] - m["price"]) / PIP
        if dp > price_tol_pips:
            problems.append(f"price off by {dp:.2f} pips")
        if problems:
            issues += 1
            print(f"  trade {i}: " + "; ".join(problems))
    return issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("python_csv")
    ap.add_argument("mt5_csv")
    ap.add_argument("--time-tol-s", type=int, default=90)
    ap.add_argument("--price-tol-pips", type=float, default=1.0)
    args = ap.parse_args()

    issues = diff(
        load_python(args.python_csv),
        load_mt5(args.mt5_csv),
        args.time_tol_s,
        args.price_tol_pips,
    )
    print("-" * 50)
    if issues == 0:
        print("PARITY GATE PASSED: implementations agree inside tolerances.")
        return 0
    print(f"PARITY GATE BLOCKED: {issues} divergence(s). Each one must be explained "
          "by a documented cost-model difference before demo promotion.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
