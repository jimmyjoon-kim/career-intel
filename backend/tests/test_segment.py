from app.v2.segment import posting_segment, sides_from_tags
from app.v2 import model


def test_posting_segment():
    d = "Lead publisher partnerships for our SSP and mediation; grow app monetization. Work with advertisers and agencies on demand."
    s = posting_segment("Director, Ad Partnerships", d)
    assert "seg_supply_side" in s and "seg_demand_side" in s
    assert posting_segment("Director, Cloud Sales", "Sell GPUs to enterprises and publishers of software.") == {}


def test_sides():
    assert sides_from_tags([{"func_supply_side"}, {"func_demand_side"}])["label"].startswith("unified")
    assert sides_from_tags([{"func_supply_side"}])["SG"] == 1.0


def test_sg_needs_new_tag_version():
    old = {"roles_anon": [{"y0": 2018, "y1": 2024, "months": 72, "tier": 2, "lv": 4, "tags": ["func_supply_side"]}]}
    assert model.family_view(old, "Ad Sales").get("SG") is None
    new = {"roles_anon": [{"y0": 2018, "y1": 2024, "months": 72, "tier": 2, "lv": 4, "tv": 2,
                           "tags": ["func_supply_side", "func_demand_side"]}]}
    assert model.family_view(new, "Ad Sales")["SG"] == 2.0


def test_short_tiny_stint_keeps_earlier_level():
    f = {"LV": 5, "LV_size": "tiny", "roles_anon": [
        {"y1": 2026, "months": 12, "lv": 5, "size": "tiny"},
        {"y1": 2025, "months": 24, "lv": 4, "size": "large"}]}
    out = model.effective_level(f)
    assert out["LV"] == 4 and out.get("LV_from_earlier")


def test_gm_at_unified_platform_covers_both_sides():
    from app.v2.segment import runs_unified
    assert runs_unified("Unity Technologies", 4, [])
    assert not runs_unified("Unity Technologies", 2, ["func_supply_side"], "Partner Manager")
    assert runs_unified("Unity Technologies", 2, [], "GM, Grow Korea")
    assert not runs_unified("Snowflake", 4, ["pnl_ownership"])
