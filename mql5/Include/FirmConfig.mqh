//+------------------------------------------------------------------+
//| FirmConfig.mqh — GENERATED FILE, DO NOT EDIT BY HAND.             |
//| Source: config/ftmo_50k.json (single source of truth).            |
//| Regenerate: python3 scripts/gen_firm_config.py                    |
//| Generated: 2026-07-07 13:50 UTC                                    |
//| *** UNVERIFIED PLACEHOLDER NUMBERS ***                           |
//| The founder has NOT pinned the firm rulebook yet (The           |
//| Assignment). EAs must refuse demo/live while this is false.     |
//+------------------------------------------------------------------+
#property strict

#define FIRM_NAME              "FTMO"
#define FIRM_RULES_VERIFIED    false
#define FIRM_ACCOUNT_TIER_USD  50000.0
#define FIRM_DAILY_LOSS_FRAC   0.050000
#define FIRM_TOTAL_DD_FRAC     0.100000
#define FIRM_MAX_LOTS          5.00

// own policy (stricter than the firm; also frozen at deploy)
#define OWN_RISK_PER_TRADE     0.005000
#define OWN_SAFETY_FACTOR      2.00
#define OWN_MAX_POSITIONS      1
