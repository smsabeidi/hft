//+------------------------------------------------------------------+
//| FirmConfig.mqh — GENERATED FILE, DO NOT EDIT BY HAND.             |
//| Source: config/fundednext_100k.json (single source of truth).            |
//| Regenerate: python3 scripts/gen_firm_config.py                    |
//| Generated: 2026-07-09 14:20 UTC                                    |
//+------------------------------------------------------------------+
#ifndef FIRMCONFIG_MQH
#define FIRMCONFIG_MQH
#property strict

#define FIRM_NAME              "FundedNext"
#define FIRM_RULES_VERIFIED    true
#define FIRM_EA_PERMITTED      false
#define FIRM_ACCOUNT_TIER_USD  100000.0
#define FIRM_DAILY_LOSS_FRAC   0.050000
#define FIRM_TOTAL_DD_FRAC     0.100000
#define FIRM_MAX_LOTS          10.00

// own policy (stricter than the firm; also frozen at deploy)
#define OWN_RISK_PER_TRADE     0.005000
#define OWN_SAFETY_FACTOR      2.00
#define OWN_MAX_POSITIONS      1

// EA-permission guard: refuse to run on THIS firm's own server when the
// firm bans EAs for the account type (prevents an account-breach), while
// leaving other brokers/demos untouched. Tester always allowed. Every EA
// calls this in OnInit and returns INIT_FAILED when it is true.
bool EABannedHere()
  {
   if(MQLInfoInteger(MQL_TESTER) || FIRM_EA_PERMITTED)
      return(false);
   if(StringFind(AccountInfoString(ACCOUNT_SERVER), FIRM_NAME) < 0)
      return(false);   // not this firm's server -> guard does not apply
   Alert("EAs are NOT permitted on ", FIRM_NAME, " for this account "
         "(config ea_permitted=false). Running here risks a rule breach — "
         "remove the EA. Enable only via the firm's paid EA add-on.");
   return(true);
  }
#endif // FIRMCONFIG_MQH
