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
