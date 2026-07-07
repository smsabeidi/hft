"""Production executor for the delta-neutral funding book — OKX v5 REST.

This is the M2 execution layer: real signed orders for the spot + perp pair,
post-only entries (the fee-engineering finding: worth ~+4% of book return),
reconciliation queries, and a kill switch. It serves two environments with
one code path:

- DEMO TRADING (default): OKX's simulated-trading environment via the
  `x-simulated-trading: 1` header with demo API keys — the dress rehearsal
  required before any real order (reports/m1_venue_brief.md, Branch B note).
- REAL (opt-in): same code, real keys, no simulation header. The runner
  (scripts/rehearsal_funding.py) refuses this mode unless the M0 promotion
  gate (scripts/paper_status.py) actually passes — the ladder is enforced
  in code, not memory. Venue caveat: OKX real trading requires a non-US
  KYC (Branch B). If the founder is Branch A (US), the real-money venue is
  Coinbase/Kraken per the M1 brief and needs its own adapter at M2 — this
  executor still provides the rehearsal environment either way.

Keys come from the environment, never from disk or git:
  OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import ssl
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

OKX_REST = "https://www.okx.com"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def iso_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sign(secret: str, timestamp: str, method: str, path: str, body: str) -> str:
    msg = f"{timestamp}{method}{path}{body}".encode()
    return base64.b64encode(hmac.new(secret.encode(), msg, hashlib.sha256).digest()).decode()


@dataclass(frozen=True)
class OKXCredentials:
    api_key: str
    secret_key: str
    passphrase: str

    @classmethod
    def from_env(cls) -> "OKXCredentials":
        try:
            return cls(
                api_key=os.environ["OKX_API_KEY"],
                secret_key=os.environ["OKX_SECRET_KEY"],
                passphrase=os.environ["OKX_PASSPHRASE"],
            )
        except KeyError as e:
            raise RuntimeError(
                f"missing {e.args[0]} in environment — create DEMO-trading keys in the "
                "OKX web UI (Trade -> Demo trading -> API) and export all three vars"
            ) from None


class OKXClient:
    """Thin signed transport. `transport` is injectable for tests."""

    def __init__(self, creds: OKXCredentials, demo: bool = True, transport=None):
        self.creds = creds
        self.demo = demo
        self._transport = transport or self._http

    def _http(self, method: str, path: str, headers: dict, body: str) -> dict:
        req = urllib.request.Request(
            OKX_REST + path, data=body.encode() if body else None,
            headers=headers, method=method,
        )
        with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as r:
            return json.loads(r.read())

    def request(self, method: str, path: str, params: dict | None = None) -> dict:
        body = json.dumps(params) if params and method == "POST" else ""
        if params and method == "GET":
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            path = f"{path}?{qs}"
        ts = iso_timestamp()
        headers = {
            "OK-ACCESS-KEY": self.creds.api_key,
            "OK-ACCESS-SIGN": sign(self.creds.secret_key, ts, method, path, body),
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.creds.passphrase,
            "Content-Type": "application/json",
        }
        if self.demo:
            headers["x-simulated-trading"] = "1"
        out = self._transport(method, path, headers, body)
        if out.get("code") not in ("0", 0, None):
            raise RuntimeError(f"OKX error {out.get('code')}: {out.get('msg')} "
                               f"({json.dumps(out.get('data', ''))[:200]})")
        return out

    # --- account / market ------------------------------------------------
    def balance(self, ccy: str = "USDT") -> float:
        out = self.request("GET", "/api/v5/account/balance", {"ccy": ccy})
        details = out["data"][0]["details"]
        return float(details[0]["availBal"]) if details else 0.0

    def instrument(self, inst_id: str) -> dict:
        inst_type = "SWAP" if inst_id.endswith("-SWAP") else "SPOT"
        out = self.request("GET", "/api/v5/account/instruments",
                           {"instType": inst_type, "instId": inst_id})
        return out["data"][0]

    def positions(self, inst_id: str | None = None) -> list[dict]:
        params = {"instId": inst_id} if inst_id else {}
        return self.request("GET", "/api/v5/account/positions", params)["data"]

    # --- orders ------------------------------------------------------------
    def place(self, inst_id: str, side: str, sz: str, ord_type: str = "post_only",
              px: str | None = None, td_mode: str = "cash", reduce_only: bool = False) -> str:
        params = {
            "instId": inst_id, "tdMode": td_mode, "side": side,
            "ordType": ord_type, "sz": sz,
        }
        if px is not None:
            params["px"] = px
        if reduce_only:
            params["reduceOnly"] = "true"
        out = self.request("POST", "/api/v5/trade/order", params)
        return out["data"][0]["ordId"]

    def order(self, inst_id: str, ord_id: str) -> dict:
        return self.request("GET", "/api/v5/trade/order",
                            {"instId": inst_id, "ordId": ord_id})["data"][0]

    def cancel(self, inst_id: str, ord_id: str) -> None:
        self.request("POST", "/api/v5/trade/cancel-order",
                     {"instId": inst_id, "ordId": ord_id})

    # --- the kill switch ----------------------------------------------------
    def close_all_positions(self, inst_ids: list[str]) -> None:
        """Market-close every open position on the given instruments.
        The one method that is ALLOWED to cross the spread."""
        for inst in inst_ids:
            for p in self.positions(inst):
                if float(p.get("pos", 0)) == 0:
                    continue
                self.request("POST", "/api/v5/trade/close-position",
                             {"instId": inst, "mgnMode": p.get("mgnMode", "cross")})
