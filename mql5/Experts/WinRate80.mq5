//+------------------------------------------------------------------+
//| WinRate80.mq5 — the 80%+ win-rate bot, delivered honestly.        |
//|                                                                   |
//| Win rate is a stop:target geometry dial: with TP=10 / SL=50 the   |
//| no-skill win rate is sl/(tp+sl) = 83.3%. Measured on 5.5y of real |
//| EURUSD M1 in this repo's harness: 82.9% across 5,907 trades —     |
//| with NEGATIVE expectancy after costs (-1.30 pips/trade), because  |
//| each stop erases five wins. Win rate and profitability are        |
//| different axes. This EA exists to make that measurable in the     |
//| founder's own Strategy Tester.                                    |
//|                                                                   |
//| Entries are SIGNAL-FREE by construction (strict alternation on a  |
//| fixed clock) so the win rate shown is pure geometry, not skill.   |
//|                                                                   |
//| SCOPE (2026-07-09, founder-directed demo unlock): Strategy Tester |
//| and true DEMO accounts only. Hard-refused: any real/live account   |
//| (unconditionally) and any firm server where EAs are banned          |
//| (EABannedHere — the FundedNext trial registers as demo but bans    |
//| EAs). On demo it doubles as a LOAD TEST of the execution/journal/  |
//| alert stack at high order rates. Expected drift is printed on the |
//| chart while it runs; the win rate is geometry, not edge.           |
//+------------------------------------------------------------------+
#property copyright "HFT harness"
#property version   "1.00"
#property description "GEOMETRY DEMONSTRATION: ~83% win rate, expectancy <= 0. Tester only."
#property strict

#include <Trade\Trade.mqh>
#include <FirmConfig.mqh>   // EABannedHere(): blocks EA-banned firm servers

// defaults set to the founder's 85% goal (2026-07-07): sl/(tp+sl) = 85.7%,
// measured 86.3% on 5,089 real trades — at -0.65 pips/trade after costs.
// Turn the dial higher at will; the menu with prices is in
// reports/win_rate_illusion.md. Expectancy stays negative at every setting.
input double InpTakeProfitPips = 10.0;
input double InpStopLossPips   = 60.0;
input int    InpEverySeconds   = 60;    // entry cadence (clamped >= 5s)
input int    InpMaxOpen        = 5;     // concurrent positions (clamped 1..20)
input double InpLots           = 1.0;   // 1 lot: EURUSD $10/pip; size scales
                                        // wins AND stops linearly, never the sign
input long   InpMagic          = 20260780;

CTrade trade;
double g_pip;
int    g_dir = 1;               // strict alternation: +1, -1, +1, ...
int    g_wins = 0, g_losses = 0;
double g_net = 0.0;

//+------------------------------------------------------------------+
int OnInit()
  {
   const bool is_tester = (bool)MQLInfoInteger(MQL_TESTER);
   const bool is_demo =
      (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)
      == ACCOUNT_TRADE_MODE_DEMO;
   if(!is_tester)
     {
      if(!is_demo)
        {
         Alert("WinRate80 runs in the Strategy Tester and on true DEMO ",
               "accounts only. Real/live accounts: never — its expectancy ",
               "is negative by measurement.");
         return(INIT_FAILED);
        }
      if(EABannedHere())   // FundedNext trial = 'demo' mode but EAs banned
         return(INIT_FAILED);
     }
   g_pip = (_Digits == 5 || _Digits == 3) ? 10.0 * _Point : _Point;
   trade.SetExpertMagicNumber(InpMagic);
   EventSetTimer(MathMax(InpEverySeconds, 5));
   PrintFormat("WinRate80 up (%s): TP %.0fp / SL %.0fp -> theoretical win rate %.1f%%, "
               "cadence %ds, max %d concurrent. Expectancy after costs is NEGATIVE "
               "(measured -0.65 pips/trade at this geometry). Dial, not edge.",
               is_tester ? "tester" : "DEMO", InpTakeProfitPips, InpStopLossPips,
               100.0 * InpStopLossPips / (InpTakeProfitPips + InpStopLossPips),
               (int)MathMax(InpEverySeconds, 5),
               (int)MathMax(MathMin(InpMaxOpen, 20), 1));
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason) { EventKillTimer(); }

int OurOpenPositions()
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      const ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic)
         n++;
     }
   return(n);
  }
//+------------------------------------------------------------------+
void OnTimer()
  {
   if(OurOpenPositions() >= (int)MathMax(MathMin(InpMaxOpen, 20), 1))
      return;

   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask <= 0.0 || bid <= 0.0)
      return;
   const double tp_d = InpTakeProfitPips * g_pip;
   const double sl_d = InpStopLossPips * g_pip;

   // strict alternation: the win rate shown is geometry, never direction skill
   if(g_dir > 0)
      trade.Buy(InpLots, _Symbol, 0.0, bid - sl_d, ask + tp_d, "WR80 demo long");
   else
      trade.Sell(InpLots, _Symbol, 0.0, ask + sl_d, bid - tp_d, "WR80 demo short");
   g_dir = -g_dir;
  }
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;
   if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY) != DEAL_ENTRY_OUT)
      return;
   const double p = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
                  + HistoryDealGetDouble(trans.deal, DEAL_SWAP)
                  + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
   g_net += p;
   if(p > 0) g_wins++; else g_losses++;
   const int n = g_wins + g_losses;
   Comment(StringFormat(
      "WinRate80 — GEOMETRY DEMO, NOT AN EDGE\n"
      "trades %d | wins %d | WIN RATE %.1f%% | net %.2f\n"
      "each stop erases %.0f wins; expectancy <= 0 by measurement",
      n, g_wins, n > 0 ? 100.0 * g_wins / n : 0.0, g_net,
      InpStopLossPips / InpTakeProfitPips));
  }
//+------------------------------------------------------------------+
double OnTester()
  {
   const int n = g_wins + g_losses;
   const double wr = n > 0 ? 100.0 * g_wins / n : 0.0;
   PrintFormat("WinRate80 FINAL: %d trades, win rate %.1f%%, net %.2f — "
               "the win rate was free; the net is the truth.", n, wr, g_net);
   return(wr);   // custom result column shows the win rate
  }
//+------------------------------------------------------------------+
