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


def sides_from_tags(tagsets: list[set]) -> dict:
    demand = any({"func_demand_side", "func_brand_agency_sales"} & s for s in tagsets)
    supply = any("func_supply_side" in s for s in tagsets)
    return {"demand": demand, "supply": supply, "SG": float(demand) + float(supply),
            "label": "unified (demand and supply)" if demand and supply else "demand side" if demand else
                     "supply side" if supply else "not shown"}
