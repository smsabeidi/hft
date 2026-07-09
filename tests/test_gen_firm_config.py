from __future__ import annotations

import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from gen_firm_config import REQUIRED, render

CFG = {
    "firm": "FTMO",
    "verified": False,
    "account_tier_usd": 50000,
    "daily_loss_frac": 0.05,
    "total_drawdown_frac": 0.10,
    "max_lots": 5.0,
    "own_policy": {
        "risk_per_trade_frac": 0.005,
        "daily_headroom_safety_factor": 2.0,
        "max_concurrent_positions": 1,
    },
}


def test_render_emits_all_defines():
    out = render(CFG, "ftmo_50k.json")
    for name in ["FIRM_NAME", "FIRM_RULES_VERIFIED", "FIRM_DAILY_LOSS_FRAC",
                 "FIRM_TOTAL_DD_FRAC", "FIRM_MAX_LOTS", "OWN_RISK_PER_TRADE",
                 "OWN_SAFETY_FACTOR", "OWN_MAX_POSITIONS"]:
        assert name in out
    assert "#define FIRM_DAILY_LOSS_FRAC   0.050000" in out
    assert "#define FIRM_RULES_VERIFIED    false" in out


def test_unverified_banner_present_only_when_unverified():
    assert "UNVERIFIED PLACEHOLDER" in render(CFG, "x.json")
    verified = dict(CFG, verified=True)
    assert "UNVERIFIED PLACEHOLDER" not in render(verified, "x.json")
    assert "#define FIRM_RULES_VERIFIED    true" in render(verified, "x.json")


def test_repo_config_has_required_keys():
    cfg = json.loads(
        (Path(__file__).resolve().parents[1] / "config" / "ftmo_50k.json").read_text()
    )
    assert all(k in cfg for k in REQUIRED)
    assert cfg["verified"] is False  # flips true only when the founder pins the rulebook


def test_ea_permitted_define_defaults_false_and_toggles():
    assert "#define FIRM_EA_PERMITTED      false" in render(CFG, "x.json")  # default
    permitted = dict(CFG, ea_permitted=True)
    assert "#define FIRM_EA_PERMITTED      true" in render(permitted, "x.json")


def test_ea_guard_and_include_guard_emitted():
    out = render(CFG, "x.json")
    assert "#ifndef FIRMCONFIG_MQH" in out and "#endif" in out
    assert "bool EABannedHere()" in out
    assert "ACCOUNT_SERVER" in out and "FIRM_EA_PERMITTED" in out


def test_fundednext_config_is_verified_but_ea_banned():
    cfg = json.loads(
        (Path(__file__).resolve().parents[1] / "config" / "fundednext_100k.json").read_text()
    )
    assert all(k in cfg for k in REQUIRED)
    assert cfg["verified"] is True                    # rules pinned from research
    assert cfg["ea_permitted"] is False               # Free Trial bans EAs
    assert cfg["account_tier_usd"] == 100000
    assert cfg["daily_loss_frac"] == 0.05 and cfg["total_drawdown_frac"] == 0.10
    out = render(cfg, "fundednext_100k.json")
    assert "#define FIRM_EA_PERMITTED      false" in out
    assert "#define FIRM_RULES_VERIFIED    true" in out
