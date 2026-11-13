"""Guards for mistakes that reached the user (Nov 2-3, 2026). Synthetic CV; no real person's data."""
from app.models import Profile
from app.services import profile_view
from app.v2.service import merge_experience_tags, user_features

CV = """Alex Example
SUMMARY
Partnerships and general management executive.
EXPERIENCE
General Manager, Grow Korea — Unity Technologies, Seoul, South Korea
January 2023 – June 2025
• Ran the advertising and monetization business.
Director, Channel Sales — BlackBerry, Seoul, South Korea
January 2011 – January 2013
• Full commercial ownership: enterprise accounts, retail distribution channel sales and reseller partners.
EDUCATION
Boston University — Bachelor of Science, Mechanical Engineering
1995
"""


def _view(keyword_first: bool):
    prof = Profile(cv_text=CV, tag_matches={})
    if keyword_first:  # an earlier CV upload stored keyword (partial) matches
        prof.tag_matches = {t: {"match": 1.0, "source": "keyword", "evidence": "x"}
                            for t in ("func_channel", "edu_bachelors", "edu_technical", "func_growth")}
    f = user_features(prof)
    merge_experience_tags(prof, f)
    return profile_view(prof, f).matches


def test_role_text_beats_old_keyword_matches():
    m = _view(keyword_first=True)
    assert m.get("func_channel") == 1.0
    assert m.get("edu_bachelors") == 1.0 and m.get("edu_technical") == 1.0


def test_unified_gm_reads_both_sides_and_growth():
    m = _view(keyword_first=False)
    for t in ("seg_demand_side", "seg_supply_side", "func_growth", "skill_performance_marketing", "pnl_ownership"):
        assert m.get(t) == 1.0, t


def test_market_fit_bounded_and_multi_bonus():
    from app.v2.market import adjust, effective_months, posting_market
    roles = [{"title": "General Manager, Grow Korea", "company": "Unity Technologies", "location": "Seoul, South Korea",
              "months": 30, "desc": ["Ran the business across Korea and Japan."]}]
    pm = posting_market("Director, Partnerships", "San Francisco, CA", False)
    assert pm["market"] == "US"
    eff = effective_months(roles, "US")
    assert eff["hq"] == 30 and eff["E"] == 7.5  # Unity is headquartered in San Francisco: a quarter of the months
    s, d = adjust(0.8, pm, eff, False, 0)
    assert 0.8 * 0.85 <= s < 0.8 and d["reduction_pct"] <= 15
    g = posting_market("Head of Global Partnerships", "San Francisco, CA", True)
    s2, d2 = adjust(0.8, g, effective_months(roles, g["market"]), False, 36)
    assert g["market"] == "global" and round(s2, 4) == 0.85
    apac = posting_market("Head of APAC Partnerships", "Singapore", False)
    assert apac["market"] == "APAC" and effective_months(roles, "APAC")["E"] == 30


def test_gate_is_not_tied_to_one_person():
    """A new user's defaults: no location preference, country-scoped roles allowed, their own functions."""
    from types import SimpleNamespace as NS
    from app.scoring import ProfileView, gate_split
    eng = ProfileView(target_roles=["Director of Engineering"], work_auth={"EMEA": "needs_sponsorship", "US": "authorized"})
    p = NS(title="Director of Engineering", status="open", no_sponsorship=True, level_band="Director", scope="country",
           location="Berlin, Germany", remote_flag="no", bay_area=False)
    hard, soft = gate_split(p, eng)
    assert hard and not soft  # needs sponsorship in EMEA; engineering is in target; Germany-only scope allowed
    p.location, p.title = "Seattle, WA", "Director of Engineering"
    assert gate_split(p, eng) == ([], [])  # authorized in the US
    apac = ProfileView(locations=["APAC"])
    p.location, p.no_sponsorship, p.title = "Singapore", False, "Head of Partnerships"
    assert gate_split(p, apac)[1] == []  # a region name matches cities in it


# ---- council review, 2026-11-12 ----
def _ref30(cluster="Partnerships"):
    from app.v2.model import Reference
    names = ["Google", "Meta", "Apple", "Amazon", "Microsoft", "Unity", "Salesforce"] + [f"C{i}" for i in range(23)]
    rows = [{"company": names[i], "title": "Head of Partnerships", "YOE": 10 + i % 8, "YOE_raw": 10 + i % 8,
             "CT": 1 + i % 3, "LV": i % 4, "LV_max": i % 4, "FN": (i % 4) / 3, "DM": (i % 5) / 4, "AC": i % 6,
             "tags": {"func_partnerships": 1.0 if i % 2 else 0.0, "func_bd": 1.0, "func_channel": 0.0}} for i in range(30)]
    return Reference(cluster, rows)


def test_every_path_uses_the_same_percentile_rule():
    from app.v2 import model
    uf = {"YOE": 30, "YOE_raw": 30, "CT": 3, "LV": 3, "LV_max": 3, "FN": 1.0, "DM": 1.0, "AC": 20, "tags": {"func_bd": 1.0}}
    card = model.base_scorecard(uf, _ref30(), n_boot=20)
    same = model.what_if(card, {"AC": card["_internal"]["user"]["AC"]})
    assert abs(same["delta"]) < 0.05  # an unchanged what-if moves nothing
    assert abs(model.opportunity(card, [], {})["position"] - card["position"]) < 0.05


def test_top_tier_is_defined_outside_the_score():
    from app.v2 import model
    uf = {"YOE": 12, "YOE_raw": 12, "CT": 2, "LV": 2, "LV_max": 2, "FN": 0.5, "DM": 0.5, "AC": 2, "tags": {}}
    tt = model.base_scorecard(uf, _ref30(), n_boot=20)["top_tier"]
    assert tt["n"] == 5 and "Tier 1" in tt["basis"]
    from app.v2.model import Reference
    few = Reference("Partnerships", _ref30().rows[7:])  # no holders at major employers
    card = model.base_scorecard(uf, few, n_boot=20)
    assert card["top_tier"]["n"] == 0 and card["top_tier"]["entry_score"] is None


def test_unknown_role_has_no_function_factor():
    from app.v2 import model
    uf = {"YOE": 12, "YOE_raw": 12, "CT": 2, "LV": 2, "LV_max": 2, "FN": 0.5, "DM": 0.5, "AC": 2, "tags": {"func_partnerships": 1.0}}
    card = model.base_scorecard(uf, _ref30("Director of Engineering"), n_boot=20)
    fn = next(f for f in card["factors"] if f["factor"] == "FN")
    assert fn["you_value"] is None and fn["you_pct"] is None


def test_reader_council_cases():
    from app.v2.reader import parse_roles, title_level, role_level, keyword_list
    from app.v2.pedigree import school_tier, education_signals
    from app.v2.market import regions, posting_market
    cv = "EXPERIENCE\nDirector, Partnerships — Salesforce, San Francisco, CA\nJanuary 2016 – Present\n• Led partner program.\n" \
         "Keywords: channel, resellers, AWS, Azure, government, AI, LLM, advertisers, publishers, monetization, SaaS.\n"
    roles, _ = parse_roles(cv, (2026, 11))
    assert roles[0]["company"] == "Salesforce" and roles[0]["title"].startswith("Director")
    assert all("Keywords" not in d for d in roles[0]["desc"]) and keyword_list("Python, SQL, AWS, GCP, Azure, Spark")
    assert title_level("Country Manager, Korea") == 3 and title_level("Vice-President, Sales") == 3 and title_level("AVP, Sales") == 1
    assert role_level({"title": "Country Manager, Korea", "desc": []})[0] >= 1  # not below a Director
    assert school_tier("Cornell College") == 0 and school_tier("Cornell University") == 2
    done = [{"text": "MBA, Business", "level": 2, "in_progress": False}, {"text": "MS Computer Science", "level": 2, "in_progress": False}]
    assert education_signals(done)["FLD"] == 1.0
    assert regions("Toronto, CA") == set() and regions("Berlin, DE") == {"EMEA"} and regions("Atlanta, Georgia") == {"US"}
    assert posting_market("Head of Sales, EMEA & APAC", "London")["market"] == "global"


def test_every_model_call_is_in_the_registry():
    """No code path may pick a model on its own: every agent id used in a model call is registered with a priced model."""
    import pathlib, re
    from app.agents import registry
    from app.llm import PRICES
    ids = set()
    for f in pathlib.Path("app").rglob("*.py"):
        ids |= set(re.findall(r'agent="([a-z_]+)"', f.read_text()))
    ids -= {"app"}
    for a in ids:
        assert registry.spec(a)["runner"] == "api", a
        for m in registry.models_for(a) + registry.models_for(a, escalate=True):
            assert m in PRICES, (a, m)
    assert registry.models_for("reader") == ["claude-haiku-5-5"] and registry.models_for("reader", escalate=True) == ["claude-sonnet-5-5"]
    import pytest
    with pytest.raises(registry.UnknownAgent):
        registry.models_for("made_up")
    with pytest.raises(registry.UnknownAgent):
        registry.models_for("council_synth")  # not an in-app agent
    # the top-tier model is reachable only by the agent that is allowed to use it
    tops = [k for k, v in registry.load()["agents"].items() if registry.model_id(v.get("model")) == registry.top_tier()]
    assert tops == ["council_synth"]
