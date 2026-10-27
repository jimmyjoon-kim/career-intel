from app.v2.model import Reference, base_scorecard, opportunity, public
from app.v2.reader import company_tier, extract_features, parse_roles

NOW = (2026, 10)
LINKEDIN = """Experience
Chief Revenue Officer
Acme AI
Jan 2025 - Jan 2026 · 1 yr 1 mo
Led partnerships with app publishers and AI platforms.
General Manager, Korea
Unity · Full-time
Nov 2019 - Dec 2024 · 5 yrs 2 mos
- Managed P&L for the advertising and monetization business; led business development and channel partners.
- Grew partner revenue 100% across 40 partners.
Consultant
Rexsoft · Full-time
Sep 2003 - Nov 2005 · 2 yrs 3 mos
- Ran channel marketing with ISV partners including Accenture.
Intern
Bigco
Jun 2002 - Aug 2002 · 3 mos
"""


def test_linkedin_reader_reads_descriptions_not_only_titles():
    roles, fmt = parse_roles(LINKEDIN, NOW)
    assert fmt == "linkedin" and [r["company"] for r in roles][:3] == ["Acme AI", "Unity", "Rexsoft"]
    f = extract_features(roles, now=NOW)
    assert f["LV"] == 5 and f["recent_role"]["company"] == "Acme AI" and f["tier"] == 3
    assert f["tags"]["func_bd"] == 1.0 and f["tags"]["func_channel"] == 1.0  # from the Unity description, not its title
    assert f["tags"]["domain_adtech"] == 1.0 and f["tags"]["domain_ai"] == 1.0
    assert f["tags"]["skill_consulting_firm_background"] == 0.0  # "Consultant" title + client mention do not count
    assert f["AC"] >= 1
    assert all(r["company"] != "Bigco" for r in f["roles"])  # intern roles never count


def test_consulting_requires_consulting_employer():
    roles, _ = parse_roles("Senior Manager\nDeloitte · Full-time\nJan 2020 - Jan 2024 · 4 yrs 1 mo\nStrategy work\n", NOW)
    assert extract_features(roles, now=NOW)["tags"]["skill_consulting_firm_background"] == 1.0


def test_tier_word_boundaries():
    assert company_tier("Meta") == 1 and company_tier("Metadata Inc") == 3
    assert company_tier("Unity") == 2 and company_tier("Community Labs") == 3


def test_inline_cv_format():
    roles, fmt = parse_roles("ironSource | General Manager, VP | Jan 2016 – Mar 2023\nBuilt the business from inception.\n", NOW)
    assert fmt == "inline" and roles[0]["company"] == "ironSource" and roles[0]["months"] == 87


def _ref():
    rows = []
    for i in range(20):
        rows.append({"company": f"C{i}", "title": "Head of Partnerships", "YOE": 10 + i % 8, "YOE_raw": 10 + i % 8,
                     "CT": 1 + i % 3, "LV": i % 4, "LV_max": i % 4, "FN": (i % 4) / 3, "DM": (i % 5) / 4, "AC": i % 3,
                     "tags": {"skill_hyperscaler": 1.0 if i % 5 == 0 else 0.0, "func_channel": 1.0 if i % 2 else 0.0}})
    return Reference("Partnerships", rows)


def test_base_scorecard_and_opportunity():
    roles, _ = parse_roles(LINKEDIN, NOW)
    card = base_scorecard(extract_features(roles, now=NOW), _ref(), months_left=8, n_boot=50)
    pub = public(card)
    assert 0 <= pub["base_score"] <= 100 and 0 <= pub["position"] <= 100
    assert pub["position_ci95"][0] <= pub["position"] <= pub["position_ci95"][1] + 1e-9
    assert sum(pub["holders"]["hist"]["counts"]) == 20 and len(pub["peers"]) == 8
    assert {g["class"] for g in pub["gaps"]} <= {"structural", "capability"}
    # A posting that asks for hyperscaler + channel + AI re-weights toward function, domain and scarce experience.
    opp = opportunity(card, ["skill_hyperscaler", "func_channel", "domain_ai"], {"skill_hyperscaler": 3, "func_channel": 1},
                      posting_level="VP", years_required=30)
    assert opp["weights"]["UQ"] > pub["weights"]["UQ"] and opp["weights"]["CT"] < pub["weights"]["CT"]
    assert any("30+ years" in t for t in opp["thresholds"])
    assert abs(sum(opp["weights"].values()) - 100) < 0.5


def test_title_scope_and_stated_team_size():
    text = """Experience
General Manager, Grow Korea
Unity · Full-time
Nov 2022 - Mar 2025 · 2 yrs 5 mos
Scope: Managed all operations of the business unit: 15 business people and 20+ engineers and product managers.
Partner Director
Bigco
Jan 2020 - Oct 2022 · 2 yrs 10 mos
Worked with partners.
"""
    roles, _ = parse_roles(text, NOW)
    f = extract_features(roles, now=NOW)
    assert f["tags"]["team_mgmt"] == 1 and f["tags"]["team_large"] == 1 and f["tags"]["pnl_ownership"] == 1
    assert f["team_size_max"]["size"] == 35 and f["team_size_max"]["source"] == "stated"
    srcs = {(e["tag"], e["source"]) for e in f["evidence"] if "Unity" in e["role"]}
    assert ("pnl_ownership", "implied by title") in srcs and ("domain_adtech", "employer context") in srcs
    # A Director title alone implies no people management
    assert not any(e["tag"] == "team_mgmt" and "Bigco" in e["role"] for e in f["evidence"])
