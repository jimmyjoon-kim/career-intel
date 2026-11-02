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
