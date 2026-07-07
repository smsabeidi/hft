//+------------------------------------------------------------------+
//| SignalHost.mq5 — the strategy-agnostic host EA.                   |
//|                                                                   |
//| The honest "combination of all strategies, improved": it combines |
//| every INFRASTRUCTURE lesson this project has validated — firm     |
//| limits generated from config (FirmConfig.mqh, never hand-typed),  |
//| the risk engine with permanent breach halts, server-side SL/TP on |
//| every order from birth, one-position discipline, restart resync,  |
//| parity CSV logging, push notifications — around a pluggable       |
//| signal slot. It does NOT combine signals: a portfolio's           |
//| expectancy is the weighted mean of its parts', and no refuted     |
//| part improves by company.                                         |
//|                                                                   |
//| The signal slot ships as a NULL PROVIDER: this EA places no       |
//| trades until a family that PASSED the harness gauntlet and the    |
//| parity gate is implemented in GetSignal() below. That is the only |
//| edit a passing strategy needs — everything else is done.          |
//+------------------------------------------------------------------+
#property copyright "HFT harness"
#property version   "1.00"
#property description "Host shell: full live-ops discipline, pluggable signal, ships empty."
#property strict

#include <Trade\Trade.mqh>
#include <RiskEngine.mqh>
#include <FirmConfig.mqh>

input long   InpMagic      = 20260800;
input string InpParityLog  = "parity_signal_host.csv";

//+------------------------------------------------------------------+
//| SIGNAL SLOT — the only section a validated family may edit.       |
//| Contract: return true at most once per completed bar, with        |
//| dir = +1/-1, and stop/target distances in pips. The host does     |
//| sizing, risk, execution, logging, and alerts. Families that have  |
//| not passed the gauntlet + parity gate MUST NOT be wired in here — |
//| that rule is the entire reason this repo's numbers can be trusted.|
//+------------------------------------------------------------------+
struct HostSignal { int dir; double sl_pips; double tp_pips; };

bool GetSignal(HostSignal &s)
  {
   // NULL PROVIDER — no family has passed for MT5 yet (rounds.log).
   return(false);
  }
//+------------------------------------------------------------------+

CTrade      trade;
CRiskEngine risk;
double      g_pip;
datetime    g_last_bar = 0;

int OnInit()
  {
   if(!FIRM_RULES_VERIFIED && !MQLInfoInteger(MQL_TESTER))
     {
      Alert("SignalHost: firm rules unverified (config/ftmo_50k.json). ",
            "Pin the rulebook, regenerate FirmConfig.mqh, redeploy.");
      return(INIT_FAILED);
     }
   g_pip = (_Digits == 5 || _Digits == 3) ? 10.0 * _Point : _Point;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);
   if(!risk.Init(FIRM_ACCOUNT_TIER_USD, FIRM_DAILY_LOSS_FRAC, FIRM_TOTAL_DD_FRAC,
                 OWN_RISK_PER_TRADE, OWN_SAFETY_FACTOR, FIRM_MAX_LOTS,
                 "HOST_" + (string)InpMagic))
      return(INIT_FAILED);
   PrintFormat("SignalHost up on %s: firm=%s verified=%s, signal slot: NULL "
               "(no validated MT5 family yet — this EA will not trade). "
               "daily_floor=%.2f total_floor=%.2f",
               _Symbol, FIRM_NAME, FIRM_RULES_VERIFIED ? "true" : "false",
               risk.DailyLossFloor(), risk.TotalDDFloor());
   return(INIT_SUCCEEDED);
  }

void OnTick()
  {
   if(risk.OnTickUpdate())               // breach: close ours, halt forever
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket > 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic)
            trade.PositionClose(ticket);
        }
      return;
     }
   if(risk.Halted())
      return;

   // evaluate once per completed bar; one position at a time
   const datetime bar = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(bar == g_last_bar)
      return;
   g_last_bar = bar;
   if(PositionsTotal() > 0)
      return;
   if(!(bool)TerminalInfoInteger(TERMINAL_CONNECTED))
      return;                            // no new entries while disconnected

   HostSignal s;
   if(!GetSignal(s) || s.dir == 0 || s.sl_pips <= 0.0 || s.tp_pips <= 0.0)
      return;

   const double tick_val  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   const double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_val <= 0.0 || tick_size <= 0.0)
      return;
   const double pip_value_per_lot = tick_val * (g_pip / tick_size);
   const double lots = risk.AllowedLots(s.sl_pips,
                                        AccountInfoDouble(ACCOUNT_EQUITY),
                                        pip_value_per_lot);
   if(lots <= 0.0)
      return;                            // blocked by headroom: normal operation

   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   bool ok;
   if(s.dir > 0)
      ok = trade.Buy(lots, _Symbol, 0.0, bid - s.sl_pips * g_pip,
                     ask + s.tp_pips * g_pip, "SignalHost");
   else
      ok = trade.Sell(lots, _Symbol, 0.0, ask + s.sl_pips * g_pip,
                      bid - s.tp_pips * g_pip, "SignalHost");
   if(ok)
      SendNotification(StringFormat("SignalHost %s %s %.2f lots (SL %.0fp TP %.0fp)",
                                    s.dir > 0 ? "BUY" : "SELL", _Symbol, lots,
                                    s.sl_pips, s.tp_pips));
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD || !HistoryDealSelect(trans.deal))
      return;
   if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != InpMagic)
      return;
   int fh = FileOpen(InpParityLog, FILE_WRITE | FILE_READ | FILE_CSV | FILE_COMMON);
   if(fh == INVALID_HANDLE)
      return;                            // logging must never break trading
   FileSeek(fh, 0, SEEK_END);
   FileWrite(fh, TimeToString(TimeCurrent()),
             HistoryDealGetString(trans.deal, DEAL_SYMBOL),
             (string)HistoryDealGetInteger(trans.deal, DEAL_ENTRY),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_VOLUME), 2),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_PRICE), _Digits),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_PROFIT), 2));
   FileClose(fh);
  }
