#!/usr/bin/env python3
"""Run the HF one-day backtest: concurrency + loss-rate dial toward 0%."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hft.__init__ import *  # noqa (path only)
from scripts.hf_day_backtest import HFConfig, simulate_hf_day, load_one_day

BARS = Path(__file__).resolve().parents[1] / "data" / "bars" / "histdata"
DAY = "2026-06-15"  # a representative recent Monday

def main() -> int:
    bars = load_one_day(BARS, "EURUSD", DAY)
    if bars.empty:
        print(f"no EURUSD bars for {DAY}"); return 1
    print(f"EURUSD {DAY}: {len(bars)} M1 bars "
          f"({bars['time'].iloc[0].strftime('%H:%M')}..{bars['time'].iloc[-1].strftime('%H:%M')} UTC)")
    print("=" * 92)
    # base: cadence 1s, cap 50 (the EA defaults)
    base = simulate_hf_day(bars, HFConfig(tp_pips=10, sl_pips=60, cadence_ms=1000, max_open=50))
    print(f"BASE (cadence 1s, cap 50, tp10/sl60): {base.entries} entries, "
          f"peak {base.peak_concurrent} concurrent, avg {base.avg_concurrent:.1f}, "
          f"{base.open_at_eod} open at EOD")
    print("-" * 92)
    # loss-rate dial: widen SL:TP toward ~0% loss rate, price each notch
    print("LOSS-RATE DIAL — signal-free geometry on this day (cadence 1s, cap 50):")
    print(f"{'geometry':>12} {'entries':>8} {'peak':>5} {'closed':>7} {'loss rate':>10} "
          f"{'win rate':>9} {'exp/trade':>10} {'day net':>9}")
    for tp, sl in [(10, 30), (10, 60), (5, 95), (10, 200), (5, 250), (2, 400), (1, 800)]:
        r = simulate_hf_day(bars, HFConfig(tp_pips=tp, sl_pips=sl, cadence_ms=1000, max_open=50))
        print(f"{'tp'+str(tp)+'/sl'+str(sl):>12} {r.entries:>8} {r.peak_concurrent:>5} "
              f"{r.closed:>7} {r.loss_rate:>9.1%} {r.win_rate:>8.1%} "
              f"{r.exp_per_trade:>+9.2f}p {r.net_pips:>+8.0f}p")
    print("-" * 92)
    print("reading: loss rate -> 0% as SL widens, but day-net stays NEGATIVE at every")
    print("notch (open EOD positions carry deep unrealized losses the 'win rate' hides).")
    print("The loss rate and the P&L are different axes; only P&L pays.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
