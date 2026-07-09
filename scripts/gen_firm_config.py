#!/usr/bin/env python3
"""Generate mql5/Include/FirmConfig.mqh from config/<firm>.json.

Why this exists: the design doc requires prop-firm limits to be frozen
config, excluded from any optimization loop. The old deploy flow had a human
transcribe JSON numbers into EA inputs on the VPS — and a transcription typo
in a drawdown constant is precisely the failure mode the risk engine exists
to prevent. This generator makes the JSON the single source of truth; the
.mqh is a build artifact (regenerate, never hand-edit).

The EA must check FIRM_RULES_VERIFIED at OnInit and refuse demo/live when
false — same contract as the JSON's "verified" flag.

Usage:
    python3 scripts/gen_firm_config.py                 # config/ftmo_50k.json
    python3 scripts/gen_firm_config.py --config config/other_firm.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "ftmo_50k.json"
OUT = ROOT / "mql5" / "Include" / "FirmConfig.mqh"

REQUIRED = [
    "firm", "verified", "account_tier_usd", "daily_loss_frac",
    "total_drawdown_frac", "max_lots", "own_policy",
]


def render(cfg: dict, source_name: str) -> str:
    own = cfg["own_policy"]
    verified = bool(cfg["verified"])
    banner = "" if verified else (
        "//| *** UNVERIFIED PLACEHOLDER NUMBERS ***                           |\n"
        "//| The founder has NOT pinned the firm rulebook yet (The           |\n"
        "//| Assignment). EAs must refuse demo/live while this is false.     |\n"
    )
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""//+------------------------------------------------------------------+
//| FirmConfig.mqh — GENERATED FILE, DO NOT EDIT BY HAND.             |
//| Source: config/{source_name} (single source of truth).            |
//| Regenerate: python3 scripts/gen_firm_config.py                    |
//| Generated: {stamp}                                    |
{banner}//+------------------------------------------------------------------+
#ifndef FIRMCONFIG_MQH
#define FIRMCONFIG_MQH
#property strict

#define FIRM_NAME              "{cfg["firm"]}"
#define FIRM_RULES_VERIFIED    {"true" if verified else "false"}
#define FIRM_EA_PERMITTED      {"true" if bool(cfg.get("ea_permitted", False)) else "false"}
#define FIRM_ACCOUNT_TIER_USD  {float(cfg["account_tier_usd"]):.1f}
#define FIRM_DAILY_LOSS_FRAC   {float(cfg["daily_loss_frac"]):.6f}
#define FIRM_TOTAL_DD_FRAC     {float(cfg["total_drawdown_frac"]):.6f}
#define FIRM_MAX_LOTS          {float(cfg["max_lots"]):.2f}

// own policy (stricter than the firm; also frozen at deploy)
#define OWN_RISK_PER_TRADE     {float(own["risk_per_trade_frac"]):.6f}
#define OWN_SAFETY_FACTOR      {float(own["daily_headroom_safety_factor"]):.2f}
#define OWN_MAX_POSITIONS      {int(own["max_concurrent_positions"])}

// EA-permission guard: refuse to run on THIS firm's own server when the
// firm bans EAs for the account type (prevents an account-breach), while
// leaving other brokers/demos untouched. Tester always allowed. Every EA
// calls this in OnInit and returns INIT_FAILED when it is true.
bool EABannedHere()
  {{
   if(MQLInfoInteger(MQL_TESTER) || FIRM_EA_PERMITTED)
      return(false);
   if(StringFind(AccountInfoString(ACCOUNT_SERVER), FIRM_NAME) < 0)
      return(false);   // not this firm's server -> guard does not apply
   Alert("EAs are NOT permitted on ", FIRM_NAME, " for this account "
         "(config ea_permitted=false). Running here risks a rule breach — "
         "remove the EA. Enable only via the firm's paid EA add-on.");
   return(true);
  }}
#endif // FIRMCONFIG_MQH
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = ap.parse_args()

    config_path = args.config.resolve()
    cfg = json.loads(config_path.read_text())
    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        print(f"config is missing required keys: {missing}")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(cfg, config_path.name))
    print(f"wrote {OUT.relative_to(ROOT)} from config/{config_path.name}")
    if not cfg["verified"]:
        print("WARNING: verified=false — placeholder numbers. EAs must refuse "
              "demo/live until the rulebook is pinned and verified flips true.")
    print("\nvalues for manual cross-check on the VPS:")
    for line in render(cfg, args.config.name).splitlines():
        if line.startswith("#define"):
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
