# HFT — MT5 Prop-Firm Algorithmic Trading System

A solo-operator systematic trading operation. Layer 1 (this repo's Python
harness) proves or disproves edge; layer 2 (MQL5 on a Windows VPS) executes
what survives; layer 3 turns a verified track record into prop-firm capital.

Full design doc (approved 2026-07-06, 3 adversarial review rounds):
`~/.gstack/projects/HFT/admin-main-design-20260706-192039.md`

**Honesty note.** Nothing in this repo is a validated edge. The two strategy
files are candidate FAMILIES. The falsification gate proves the harness can
say no; only walk-forward + demo evidence can ever say yes. Win rate is a
diagnostic, never a target. Most retail algo traders lose money.

## Layout

```
hft/data/        Dukascopy download + decode, tick sanity validation, parquet store, ticks->M1 bars
hft/backtest/    cost model, no-lookahead engine (conservative fills), metrics with CIs, walk-forward
hft/risk/        prop-firm risk engine — the Python REFERENCE for mql5/Include/RiskEngine.mqh
hft/strategies/  RandomFlipper (falsification), SessionBreakout, MeanReversion
scripts/         download_data.py, run_falsification.py, run_walkforward.py
mql5/            execution layer for the Windows VPS (see mql5/README.md)
config/          per-firm rule config — placeholder until the rulebook is pinned
tests/           55 tests; the pre-commit hook runs them (fast, ~6s)
```

## The gauntlet (phase gates — in order, no skipping)

1. **Harness gate** — `python3 scripts/run_falsification.py` must PASS
   (naive strategy loses decisively). Runs in CI-of-one via pre-commit tests.
2. **Strategy gate** — positive after-cost expectancy on 5+ years of ticks AND
   a passing walk-forward round: `scripts/run_walkforward.py`. A family dies
   after 2 failed rounds (rounds auto-logged to `reports/rounds.log`).
3. **Parity gate** — Python vs MT5 Strategy Tester, trade-by-trade, identical
   tick data. See `mql5/README.md`.
4. **Demo gate** — ≥100 demo trades, zero risk-engine violations, slippage
   inside the cost model, expectancy positive and inside the backtest CI.
5. **Business gate** — firm free trial, then ONE paid evaluation
   ($25k-$50k tier). Max 2 paid attempts, ever, without a materially new
   strategy passing every prior gate.

## Quickstart

```bash
python3 -m pip install numpy pandas pyarrow scipy pytest
python3 -m pytest                          # 55 tests, ~6s
python3 scripts/run_falsification.py       # the truth-machine self-test
python3 scripts/download_data.py --pair EURUSD --days 60
python3 scripts/run_walkforward.py --strategy session_breakout \
    --pair EURUSD --start 2026-05-01 --end 2026-06-30 --train-days 20 --test-days 5
```

## Before ANY demo deployment

Complete The Assignment (design doc): pin the firm rulebook onto one page —
daily loss, total drawdown, profit target, min trading days, max lots,
permitted strategies, EA/news/weekend rules — update `config/ftmo_50k.json`
with `"verified": true`, and mirror the numbers into the EA inputs. The EA
refuses to run on demo/live while `InpRulesVerified=false`; the config gate
exists so urgency can't skip it.

## Known approximations (documented, deliberate)

- Swap charged at UTC midnight (real FX rollover is 17:00 New York); tripled
  Wednesdays. Recalibrated against the demo broker at the demo gate.
- Bar-granularity engine (M1) with per-bar recorded spread: right for
  minutes-to-days holding periods, wrong for sub-bar strategies — don't put
  sub-bar families through it.
- Stops fill at the stop price minus slippage, or at the bar OPEN when a bar
  gaps through the stop (gaps don't honor stops).
- Backtests assume a USD-quoted pair and USD account (pip value $10/lot).
  Extend `CostModel` before adding crosses.

This project is personal research software, not investment advice. Trading
involves substantial risk of loss.
