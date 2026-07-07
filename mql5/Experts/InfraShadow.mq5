//+------------------------------------------------------------------+
//| InfraShadow.mq5 — infrastructure bring-up EA. TRADES NOTHING.     |
//|                                                                   |
//| Purpose: the design doc's VPS phase (watchdog + alerting + risk   |
//| telemetry) is its own gate, independent of any strategy. This EA  |
//| exercises the full deployment pipeline — risk engine, heartbeat,  |
//| push notifications, common-file logging, connectivity tracking —  |
//| so that the day a strategy passes the gauntlet, deployment is     |
//| turnkey. No order-placement call of any kind exists in this file  |
//| (grep it against the MQL5 trade API). It cannot trade, period.    |
//|                                                                   |
//| Runs fine with FIRM_RULES_VERIFIED=false because it never trades; |
//| it LOGS the flag loudly so the missing rulebook pin stays visible.|
//+------------------------------------------------------------------+
#property copyright "HFT harness"
#property version   "0.10"
#property strict

#include <RiskEngine.mqh>
#include <FirmConfig.mqh>

input long InpMagic = 20260707;            // identity for GlobalVariables/logs

CRiskEngine g_risk;
bool        g_connected  = true;
int         g_heartbeats = 0;
string      g_csv;

//+------------------------------------------------------------------+
int OnInit()
  {
   const double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   if(!g_risk.Init(bal, FIRM_DAILY_LOSS_FRAC, FIRM_TOTAL_DD_FRAC,
                   OWN_RISK_PER_TRADE, OWN_SAFETY_FACTOR, FIRM_MAX_LOTS,
                   "SHADOW_" + (string)InpMagic))
      return(INIT_FAILED);

   PrintFormat("InfraShadow up: firm=%s verified=%s balance=%.2f "
               "daily_floor=%.2f total_floor=%.2f",
               FIRM_NAME, FIRM_RULES_VERIFIED ? "true" : "FALSE (pin the rulebook!)",
               bal, g_risk.DailyLossFloor(), g_risk.TotalDDFloor());

   g_csv = "shadow_" + (string)InpMagic + ".csv";
   int fh = FileOpen(g_csv, FILE_WRITE | FILE_READ | FILE_CSV | FILE_COMMON);
   if(fh == INVALID_HANDLE)
     {
      Print("InfraShadow: COMMON file open failed — parity logging would be broken");
      return(INIT_FAILED);
     }
   FileSeek(fh, 0, SEEK_END);
   FileWrite(fh, TimeToString(TimeCurrent()), "init", AccountInfoDouble(ACCOUNT_EQUITY));
   FileClose(fh);

   SendNotification("InfraShadow: deployment pipeline live on " +
                    AccountInfoString(ACCOUNT_SERVER) + " (trades nothing).");
   EventSetTimer(60);
   return(INIT_SUCCEEDED);
  }
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   PrintFormat("InfraShadow down (reason %d) after %d heartbeats", reason, g_heartbeats);
  }
//+------------------------------------------------------------------+
void OnTick()
  {
   // full risk telemetry runs exactly as it would under a live strategy;
   // a breach here is a config/telemetry event, not a trading event.
   if(g_risk.OnTickUpdate())
      Print("InfraShadow: risk engine registered a breach on SHADOW telemetry — "
            "verify floors/config before any real EA deploys.");
  }
//+------------------------------------------------------------------+
void OnTimer()
  {
   g_heartbeats++;
   GlobalVariableSet("HB_SHADOW_" + (string)InpMagic, (double)TimeCurrent());

   const bool now_connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   if(now_connected != g_connected)
     {
      g_connected = now_connected;
      Print(now_connected ? "InfraShadow: reconnected" :
                            "InfraShadow: DISCONNECTED (no-new-entries policy would hold)");
      if(!now_connected)
         SendNotification("InfraShadow: terminal disconnected");
     }

   if(g_heartbeats % 60 == 0)  // hourly line to the common CSV
     {
      int fh = FileOpen(g_csv, FILE_WRITE | FILE_READ | FILE_CSV | FILE_COMMON);
      if(fh != INVALID_HANDLE)
        {
         FileSeek(fh, 0, SEEK_END);
         FileWrite(fh, TimeToString(TimeCurrent()), "heartbeat",
                   AccountInfoDouble(ACCOUNT_EQUITY));
         FileClose(fh);
        }
     }
  }
//+------------------------------------------------------------------+
