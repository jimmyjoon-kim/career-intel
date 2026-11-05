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
