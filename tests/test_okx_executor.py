from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

import pytest

from hft.crypto.okx_executor import OKXClient, OKXCredentials, sign

CREDS = OKXCredentials(api_key="k", secret_key="s", passphrase="p")


class Capture:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or {"code": "0", "data": [{"ordId": "42"}]}

    def __call__(self, method, path, headers, body):
        self.calls.append({"method": method, "path": path, "headers": headers, "body": body})
        return self.response


def test_signature_is_deterministic_base64_hmac():
    s1 = sign("secret", "2026-07-07T00:00:00.000Z", "GET", "/api/v5/x", "")
    s2 = sign("secret", "2026-07-07T00:00:00.000Z", "GET", "/api/v5/x", "")
    assert s1 == s2
    assert len(base64.b64decode(s1)) == 32  # sha256 digest
    assert sign("secret", "2026-07-07T00:00:00.001Z", "GET", "/api/v5/x", "") != s1


def test_demo_header_present_by_default_absent_in_real():
    cap = Capture()
    OKXClient(CREDS, demo=True, transport=cap).request("GET", "/api/v5/account/balance")
    assert cap.calls[0]["headers"]["x-simulated-trading"] == "1"
    cap2 = Capture()
    OKXClient(CREDS, demo=False, transport=cap2).request("GET", "/api/v5/account/balance")
    assert "x-simulated-trading" not in cap2.calls[0]["headers"]


def test_get_params_enter_signed_path():
    cap = Capture()
    OKXClient(CREDS, transport=cap).request("GET", "/api/v5/account/balance", {"ccy": "USDT"})
    assert cap.calls[0]["path"] == "/api/v5/account/balance?ccy=USDT"


def test_post_only_order_payload():
    cap = Capture()
    client = OKXClient(CREDS, transport=cap)
    ord_id = client.place("BTC-USDT", "buy", "0.001", "post_only", px="50000", td_mode="cash")
    assert ord_id == "42"
    body = cap.calls[0]["body"]
    for fragment in ('"instId": "BTC-USDT"', '"ordType": "post_only"',
                     '"px": "50000"', '"tdMode": "cash"'):
        assert fragment in body


def test_api_error_raises():
    cap = Capture(response={"code": "51000", "msg": "param error", "data": []})
    with pytest.raises(RuntimeError, match="51000"):
        OKXClient(CREDS, transport=cap).request("GET", "/api/v5/account/balance")


def test_real_mode_is_locked_until_m0_promotes():
    """END-TO-END LADDER TEST: --real must refuse while the M0 promotion
    gate (paper_status.py) does not pass. No keys are needed to observe the
    refusal because the gate check runs first, by design."""
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, str(root / "scripts" / "rehearsal_funding.py"), "--real"],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 2
    assert "Real trading stays locked" in r.stdout
    assert "No override exists" in r.stdout
