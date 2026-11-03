"""Ad tech segment: demand side (advertisers, agencies, brands, UA / DSP), supply side (publishers, app developers'
monetization, SSP, mediation), or unified (both). Read the same way from postings, from your roles and from holders'
anonymized roles. Postings get requirement tags seg_demand_side / seg_supply_side (both = a unified role); holders and
you get SG = sides covered in the last 10 years (0, 1 or 2)."""

from __future__ import annotations

import re

DEMAND = re.compile(r"\badvertisers?\b|\bagenc(?:y|ies)\b|\bbrands?\b|user acquisition|\bua\b|\bdsp\b|media buy|"
                    r"performance (?:advertis|marketers?)|app marketers?|demand[- ]side|\bdemand\b", re.I)
SUPPLY = re.compile(r"\bpublishers?\b|monetiz|monetis|\bssp\b|mediation|supply[- ]side|\bsupply\b|inventory|\byield\b|"
                    r"app developers?|offerwall|\bexchange\b", re.I)
AD_CONTEXT = re.compile(r"\bads?\b|advertis|monetiz|programmatic|ad tech|adtech|media sales|retail media", re.I)


def posting_segment(title: str, description: str) -> dict:
    """Tags only for advertising postings; a side counts when it is named at least twice (or in the title)."""
    t, d = title or "", re.sub(r"\s+", " ", description or "")
    if not AD_CONTEXT.search(t + " " + d[:4000]):
        return {}
    out = {}
    nd, ns = len(DEMAND.findall(d)), len(SUPPLY.findall(d))
    if DEMAND.search(t) or nd >= 2:
        out["seg_demand_side"] = f"{nd} demand-side mentions"
    if SUPPLY.search(t) or ns >= 2:
        out["seg_supply_side"] = f"{ns} supply-side mentions"
    return out


GM_TITLE = re.compile(r"general manager|\bgm\b|managing director|country (?:manager|head|lead)|\bhead of\b|founder", re.I)


def runs_unified(company: str, lv: int | None, tags, title: str = "") -> bool:
    """A general-management role (VP/GM band or P&L owner) at a researched unified ad platform (one that sells to
    advertisers and buys from publishers, e.g. AppLovin, Unity, ironSource) covers both sides by design."""
    from .industry import segment_of

    return any(s["segment"] == "unified" for s in segment_of(company)) and ((lv or 0) >= 3 or "pnl_ownership" in set(tags or []) or bool(GM_TITLE.search(title or "")))


_cache: dict = {}


def posting_segment_cached(p) -> dict:
    key = (p.id or 0, p.content_hash or str(len(p.description or "")))
    if key not in _cache:
        _cache[key] = posting_segment(p.title, p.description or "")
    return _cache[key]


# What a general-management role at a researched unified ad platform covers by design (docs/sectors/adtech.md):
# the business sells user acquisition to advertisers, agencies and DSP / UA buyers (demand) and buys or mediates
# inventory from app publishers, networks and SSPs (supply); the GM owns revenue growth and the P&L across both.
UNIFIED_GM_COVERS = {
    "seg_demand_side": "demand side (advertisers, agencies, UA platforms, DSPs)",
    "seg_supply_side": "supply side (app publishers, ad networks, SSPs, mediation)",
    "func_growth": "revenue growth ownership",
    "skill_performance_marketing": "performance (UA) advertising sold to app marketers",
    "func_product_strategy": "local product and go-to-market strategy for the platform",
    "skill_exec_presence": "C-level relationships with advertisers and publishers",
    "pnl_ownership": "P&L of the business",
}


def role_implied(roles: list[dict], level_of) -> dict[str, dict]:
    """Requirements a role covers by its definition, not by keywords: GM / country head / founder of a unified ad
    platform in the last 10 years. Each carries the role as evidence."""
    from .industry import segment_of

    out: dict[str, dict] = {}
    for r in roles:
        if not runs_unified(r["company"], level_of(r), [], r.get("title", "")):
            continue
        for t, what in UNIFIED_GM_COVERS.items():
            out.setdefault(t, {"match": 1.0, "source": "role", "evidence":
                               f'{r.get("title", "")} at {r["company"]} (unified ad platform): covers {what}'[:500]})
    from .industry import sector_of

    ai = [r for r in roles if sector_of(r["company"])[0] == "ai"]
    for r in ai[:1]:
        out.setdefault("skill_llm_ai_products", {"match": 0.5, "source": "role", "evidence":
                       f'{r.get("title", "")} at {r["company"]} (AI company); hands-on product work not stated'[:500]})
    return out


def sides_from_tags(tagsets: list[set], unified_gm: bool = False) -> dict:
    demand = unified_gm or any({"func_demand_side", "func_brand_agency_sales"} & s for s in tagsets)
    supply = unified_gm or any("func_supply_side" in s for s in tagsets)
    return {"demand": demand, "supply": supply, "SG": float(demand) + float(supply),
            "label": "unified (demand and supply)" if demand and supply else "demand side" if demand else
                     "supply side" if supply else "not shown"}
