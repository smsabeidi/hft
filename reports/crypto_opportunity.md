# Crypto track — funding-capture opportunity memo

Decision support for the reassessment fork (README). Descriptive statistics,
NOT a strategy round: the track decision stays with the founder.

Data: full Binance perpetual funding history 2021-01..2026-06 (6,021 records
per symbol, fetched via `scripts/fetch_funding_binance.py` from the public
archive; reproducible).

## The numbers (delta-neutral: long spot / short perp collects funding)

| | BTCUSDT | ETHUSDT |
|---|---|---|
| mean funding | 1.00 bps/8h | 1.07 bps/8h |
| intervals positive | 86% | 84% |
| gross always-on carry | **11.0%/yr** | **11.8%/yr** |
| 2021 | 30.6% | 37.5% |
| 2022 | 4.2% | 0.8% |
| 2023 | 7.9% | 8.3% |
| 2024 | 11.9% | 13.0% |
| 2025 | 5.1% | 4.9% |
| 2026 H1 | 1.1% | 0.4% |
| worst 30-day stretch | -0.32% | -1.78% |

## Honest reading

1. **The edge is real but small and decaying.** This is the first positive
   expected-return number this project has produced — and it's a single-digit
   carry, not a rocket. The year-by-year decay (30%+ in 2021 to ~1% in 2026
   H1) is the signature of a crowded trade: every basis desk and yield
   product now harvests it. Assume the go-forward gross is closer to 2026
   than to 2021.
2. **Costs matter at this size.** Entry/exit runs ~0.1-0.2% across four legs
   (spot in/out, perp in/out); conditional capture (enter only when funding
   exceeds a threshold) preserves most of the carry at lower utilization.
   Margin on the short-perp leg caps deployable fraction (~60-70% of capital
   working).
3. **What it is good for at this project's scale:** a low-risk, always-on
   BASE yield and — more valuable — the forcing function to build
   exchange-native execution (websockets, order management, reconciliation)
   that the bigger crypto families (cross-exchange dislocation, passive MM)
   require. Those remain unquantified: they need L2 order-book data, which is
   exactly what the deferred phase-3 recorder was designed to collect.
4. **Risks that dwarf the math:** venue/counterparty failure (the account
   lives ON the exchange), de-peg events on the spot leg if a stable pair is
   used, and jurisdiction (Binance data used for research; the actual venue
   depends on where the founder can legally trade — Bybit/OKX/Kraken/Coinbase
   equivalents have similar but smaller funding markets).

## Bottom line for the fork

The crypto branch offers a small, real, verifiable carry plus optionality on
microstructure families — versus a forex branch whose first three families
are refuted and whose next test requires tick data. Neither branch promises
outsized returns today; the crypto branch is the one where positive expectancy
is already observable in public data.
