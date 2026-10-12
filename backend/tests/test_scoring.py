from app.scoring import (
    MIN_CLUSTER_N, PostingView, ProfileView, classify, gap_summary, gate, market_stats, rank_key, score,
)
from app.taxonomy import split_tags


def P(i, cluster="Partnerships", tags=(), **kw):
    base = dict(id=i, company=f"Co{i}", title="Director, Partnerships", level_band="Director",
                role_cluster=cluster, location="San Francisco, CA", remote_flag="hybrid", bay_area=True,
                no_sponsorship=False, status="open", tags=list(tags))
    base.update(kw)
    return PostingView(**base)


def test_classify_thresholds():
    assert classify(70) == "COMMON MINIMUM"
    assert classify(69) == "MID"
    assert classify(30) == "MID"
    assert classify(29) == "DISCRIMINATOR"


def test_split_tags_moves_attributes_out_of_requirements():
    reqs, attrs = split_tags(["func_bd", "scope_global", "tenure_15plus", "tenure_10plus", "auth_required", "market_us"])
    assert reqs == ["func_bd"]
    assert attrs["scope"] == "global"
    assert attrs["years_required"] == 15
    assert attrs["auth_required"] is True


def test_market_stats_classifies_and_merges_small_clusters():
    big = [P(i, tags=["func_partnerships"] + (["skill_si_gsi"] if i < 2 else [])) for i in range(MIN_CLUSTER_N)]
    small = [P(100 + i, cluster="Growth", tags=["func_partnerships", "func_growth"]) for i in range(2)]
    closed = [P(200, tags=["skill_payments"], status="closed")]
    stats = market_stats(big + small + closed)
    assert stats["assignment"]["Growth"] == "Partnerships"
    part = stats["clusters"]["Partnerships"]
    assert part["n"] == MIN_CLUSTER_N + 2
    assert part["merged_from"] == ["Growth"]
    assert part["tags"]["func_partnerships"]["cls"] == "COMMON MINIMUM"
    assert part["tags"]["skill_si_gsi"]["cls"] == "DISCRIMINATOR"
    assert "skill_payments" not in part["tags"]  # closed postings excluded


def test_gate_rules():
    prof = ProfileView(excluded_title_terms=["Country Manager"], needs_sponsorship=False)
    assert gate(P(1), prof) == (True, [])
    ok, reasons = gate(P(2, level_band="Manager"), prof)
    assert not ok and "below" in reasons[0]
    assert not gate(P(3, title="Country Manager, Korea"), prof)[0]
    assert not gate(P(4, location="New York, NY", bay_area=False, remote_flag="no"), prof)[0]
    assert gate(P(5, location="Remote, US", bay_area=False, remote_flag="yes"), prof)[0]
    assert not gate(P(6, status="unverified"), prof)[0]
    # No-sponsorship postings only fail when the candidate needs sponsorship.
    assert gate(P(7, no_sponsorship=True), prof)[0]
    assert not gate(P(8, no_sponsorship=True), ProfileView(needs_sponsorship=True))[0]
    # Head of is Director-equivalent.
    assert gate(P(9, level_band="Head"), prof)[0]


def test_score_weights_and_hard_gap_ranking():
    postings = [P(i, tags=["func_partnerships", "skill_exec_presence"] + (["skill_si_gsi"] if i == 0 else []))
                for i in range(10)]
    stats = market_stats(postings)
    strong = ProfileView(matches={"func_partnerships": 1, "skill_exec_presence": 1, "skill_si_gsi": 0})
    r = score(postings[0], strong, stats)
    # func_partnerships + exec_presence are common minimum; si_gsi is a discriminator scored 0.
    assert r["hard_gaps"] == []
    assert r["weighted_score"] == 0.0
    assert r["gaps"][0]["tag"] == "skill_si_gsi"

    partial = ProfileView(matches={"func_partnerships": 0.5, "skill_exec_presence": 1})
    rp = score(postings[1], partial, stats)
    assert rp["weighted_score"] == 1.0  # no weighted tags
    assert rp["rank_score"] == 0.9
    absent = ProfileView(matches={"skill_exec_presence": 1})
    ra = score(postings[1], absent, stats)
    assert ra["has_zero_hard_gap"]
    assert sorted([ra, rp], key=rank_key)[0] is rp


def test_years_required_is_a_partial_hard_gap():
    p = P(1, tags=["func_partnerships"], years_required=15)
    stats = market_stats([p] * 1)
    r = score(p, ProfileView(years_experience=10, matches={"func_partnerships": 1}), stats)
    assert any(g["tag"] == "years_required" for g in r["hard_gaps"])
    assert r["rank_score"] == 0.9


def test_gap_summary_orders_by_impact():
    rows = [{"hard_gaps": [], "gaps": [{"tag": "a", "cls": "DISCRIMINATOR", "match": 0, "label": "a", "pct": 10,
                                        "closable": True, "close_hint": ""}]},
            {"hard_gaps": [{"tag": "b", "cls": "COMMON MINIMUM", "match": 0.5, "label": "b", "pct": 90,
                            "closable": False, "close_hint": ""}], "gaps": []}]
    out = gap_summary(rows)
    assert [g["tag"] for g in out] == ["a", "b"]
    assert out[0]["impact"] == 3.0 and out[1]["impact"] == 2.5
