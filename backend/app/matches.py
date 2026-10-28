"""Job matches: role types by industry vertical, ranked open positions, and web search for more.

Role types are built from the open postings themselves: postings grouped by role cluster and
industry vertical. Each group's requirement profile is the share of its postings asking for each
tag. Fit = share-weighted mean of your match on the tags that at least 30% of the group asks for.
Level relation compares the group's typical level with the band you have held longest
(career progression). No probabilities or hire likelihoods.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from collections import Counter

from .config import get_settings
from .taxonomy import TAGS
from .v2.reader import LEVEL_NAMES

log = logging.getLogger(__name__)

VERTICALS = [
    ("Semiconductors & compute", lambda p: bool(re.search(r"nvidia|amd|qualcomm|intel|broadcom|arm\b|micron|marvell", p.company, re.I))),
    ("Ad tech & ads platforms", lambda p: "domain_adtech" in p.tags or p.role_cluster == "Ad Sales"),
    ("Mobile & gaming", lambda p: "domain_mobile" in p.tags),
    ("AI platforms", lambda p: "domain_ai" in p.tags),
    ("SaaS & cloud", lambda p: "domain_saas" in p.tags),
    ("Marketplaces & commerce", lambda p: "domain_marketplace" in p.tags),
]
VERTICAL_DOMAIN = {"Ad tech & ads platforms": "domain_adtech", "Mobile & gaming": "domain_mobile", "AI platforms": "domain_ai",
                   "SaaS & cloud": "domain_saas", "Marketplaces & commerce": "domain_marketplace"}
POSTING_BAND = {"Director": 1, "Head": 2, "Sr Director": 2, "VP": 3, "SVP": 4, "C-level": 5}
PROFILE_SHARE = 0.30
_MONEY = re.compile(r"\$?\s?(\d{2,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?\s?[kK])")


def vertical_of(p) -> str:
    for name, test in VERTICALS:
        if test(p):
            return name
    return "Other industries"


def pay_mid(text: str) -> float | None:
    vals = []
    for m in _MONEY.finditer(text or ""):
        raw = m.group(1).replace(",", "").replace(" ", "")
        v = float(raw[:-1]) * 1000 if raw[-1] in "kK" else float(raw)
        if 80_000 <= v <= 2_000_000:
            vals.append(v)
    return (min(vals) + max(vals)) / 2 if len(vals) >= 2 else None


def progression(feats: dict | None) -> dict:
    """Established band = band held longest (months) among counted roles that ended in the last 10 years."""
    if not feats:
        return {"established": None, "recent": None, "label": "No roles read yet"}
    months: Counter = Counter()
    for r in feats["roles"]:
        if r["counted"] and r.get("level") is not None and r["recency_weight"] == 1.0:
            months[r["level"]] += r["months"]
    est = months.most_common(1)[0][0] if months else feats.get("LV_max")
    rec = feats["recent_role"]["level"] if feats.get("recent_role") else None
    return {"established": est, "established_label": LEVEL_NAMES.get(est) if est is not None else None,
            "established_months": months.get(est, 0), "recent": rec,
            "recent_label": LEVEL_NAMES.get(rec) if rec is not None else None}


def relation(group_band: float, est: int | None) -> str:
    if est is None:
        return "unknown"
    if group_band >= est + 0.5:
        return "above your level"
    if group_band <= est - 1:
        return "below your level"
    return "at your level"


def build(ev: dict, feats: dict | None, matches: dict[str, float]) -> dict:
    prog = progression(feats)
    est = prog["established"]
    open_rows = [r for r in ev["rows"] if r["posting"].status == "open"]
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in open_rows:
        p = r["posting"]
        groups.setdefault((p.role_cluster, vertical_of(p)), []).append(r)

    types = []
    for (cluster, vertical), rows in groups.items():
        n = len(rows)
        if n < 2:
            continue
        freq = Counter(t for r in rows for t in set(r["posting"].tags))
        profile = []
        num = den = 0.0
        for t, c in freq.most_common():
            share = c / n
            if share < PROFILE_SHARE or t not in TAGS:
                continue
            m = float(matches.get(t, 0.0))
            num += share * m
            den += share
            profile.append({"tag": t, "label": TAGS[t].label, "share": round(share, 2), "match": m,
                            "closable": TAGS[t].closable})
        fit = round(100 * num / den, 1) if den else None
        bands = [POSTING_BAND.get(r["posting"].level_band, 1) for r in rows]
        typical = statistics.median(bands)
        pays = [x for x in (pay_mid(r["posting"].pay_range) for r in rows) if x]
        opps = [r["opportunity"]["score"] for r in rows if r.get("opportunity")]
        dom = VERTICAL_DOMAIN.get(vertical)
        types.append({
            "id": f"{cluster}|{vertical}", "cluster": cluster, "vertical": vertical,
            "title": f"{cluster} · {vertical}", "n_open": n,
            "n_gate_pass": sum(1 for r in rows if r["gate_pass"]),
            "companies": [c for c, _ in Counter(r["posting"].company for r in rows).most_common(6)],
            "fit": fit, "profile": profile,
            "met": [x["label"] for x in profile if x["match"] >= 1][:5],
            "unmet": [x["label"] for x in profile if x["match"] < 1][:5],
            "typical_level": LEVEL_NAMES.get(round(typical)), "level_relation": relation(typical, est),
            "level_mix": dict(Counter(r["posting"].level_band for r in rows)),
            "median_pay_mid": round(statistics.median(pays)) if pays else None, "pay_n": len(pays),
            "opportunity_median": round(statistics.median(opps), 1) if opps else None,
            "domain_evidence": (feats["tags"].get(dom, 0) if (feats and dom) else None),
            "posting_ids": [r["posting"].id for r in rows],
        })
    types.sort(key=lambda t: (-(t["fit"] or 0), -t["n_open"]))

    positions = []
    for r in open_rows:
        if not r["gate_pass"]:
            continue
        p = r["posting"]
        band = POSTING_BAND.get(p.level_band, 1)
        positions.append({
            "id": p.id, "company": p.company, "title": p.title, "url": p.url, "location": p.location,
            "level_band": p.level_band, "vertical": vertical_of(p), "cluster": p.role_cluster,
            "pay_range": p.pay_range, "requirement_match": round(100 * r["weighted_score"], 1),
            "rank_score": r["rank_score"], "hard_gaps": [g["label"] for g in r["hard_gaps"]],
            "gaps": [g["label"] for g in r["gaps"][:4]],
            "opportunity": r["opportunity"]["score"] if r.get("opportunity") else None,
            "level_relation": relation(band, est),
        })
    positions.sort(key=lambda x: (bool(x["hard_gaps"]), -x["rank_score"], -(x["opportunity"] or 0)))
    return {"progression": prog, "role_types": types, "positions": positions[:15],
            "method": ["Role types = open postings grouped by role cluster and industry vertical (groups of 2 or more).",
                       "Fit = share-weighted match on requirements that at least 30% of the group's postings ask for.",
                       "Level relation compares the group's median level with the band you held longest in the last 10 years.",
                       "Open positions are gate-passing postings ranked by requirement match, then opportunity score."]}


SEARCH_SYSTEM = """You find currently open job postings on the web for one candidate.
Rules: only Director, Senior Director, Head of, VP or GM titles; US-based or US-remote; no Country Manager titles and no single-country scope outside the US.
Prefer the company's own careers page or its applicant-tracking board (Greenhouse, Lever, Ashby, Workday) over aggregators.
Never invent a posting or a URL; every item must come from a search result you saw.
Return JSON only: {"results":[{"company":"","title":"","location":"","url":"","source":"company page|ATS|aggregator","why":"one line on fit, citing the posting"}]}"""


def web_search(query: str, profile_summary: str, max_results: int = 8) -> dict:
    s = get_settings()
    if not s.anthropic_api_key:
        return {"available": False, "results": [], "note": "Web search needs an Anthropic API key (set in .env)."}
    import anthropic

    client = anthropic.Anthropic(api_key=s.anthropic_api_key)
    user = (f"Candidate summary: {profile_summary}\n\nFind up to {max_results} open postings for: {query}\n"
            "Search the companies' careers pages first.")
    try:
        msg = client.messages.create(
            model=s.anthropic_model, max_tokens=3000, system=SEARCH_SYSTEM,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
            messages=[{"role": "user", "content": user}],
        )
    except Exception as err:  # noqa: BLE001 — surface any API failure to the user
        log.warning("web search failed: %s", err)
        return {"available": True, "results": [], "note": f"Search failed: {err}"}
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    cited = set()
    for b in msg.content:
        for c in getattr(b, "citations", None) or []:
            if getattr(c, "url", None):
                cited.add(c.url)
        if getattr(b, "type", "") == "web_search_tool_result":
            for item in getattr(b, "content", None) or []:
                if getattr(item, "url", None):
                    cited.add(item.url)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        results = json.loads(m.group(0)).get("results", []) if m else []
    except json.JSONDecodeError:
        results = []
    for r in results:
        r["seen_in_search"] = r.get("url") in cited  # URL appeared in a search result, not invented
        r["status"] = "found by search · not checked against the live board"
    return {"available": True, "results": results[:max_results],
            "note": "Results come from a live web search. Check each posting is still open before applying."}
