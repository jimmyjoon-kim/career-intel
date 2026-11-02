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


def sides_from_tags(tagsets: list[set], unified_gm: bool = False) -> dict:
    demand = unified_gm or any({"func_demand_side", "func_brand_agency_sales"} & s for s in tagsets)
    supply = unified_gm or any("func_supply_side" in s for s in tagsets)
    return {"demand": demand, "supply": supply, "SG": float(demand) + float(supply),
            "label": "unified (demand and supply)" if demand and supply else "demand side" if demand else
                     "supply side" if supply else "not shown"}
