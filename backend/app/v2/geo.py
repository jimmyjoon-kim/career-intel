"""Geography context for matching and scoring.

Postings: two requirement tags are read deterministically from the posting text, each with the verbatim phrase:
  geo_us_market    — the role asks for an existing US / North America market network or experience, or is scoped to the
                     US / North America in its title.
  geo_multi_region — the role asks for international / multi-region scope.
They enter the normal requirement weighting (common minimum / mid / discriminator by how many postings ask).

You: your roles' locations and descriptions give months by region and your match on both tags, with the evidence.
Nothing here is a probability; every value traces to a line of text."""

from __future__ import annotations

import re

US_LOC = re.compile(r"united states|\busa\b|\bu\.s\.|\bus\b|, (?:ca|ny|wa|tx|ma|il|de|ga|co|fl|nj|pa|or|dc|va|nc|az|ut|mn)\b|"
                    r"san francisco|bay area|new york|seattle|los angeles|boston|chicago|austin|palo alto|mountain view|"
                    r"sunnyvale|menlo park|redwood city|san jose|santa monica|washington, dc", re.I)
APAC_LOC = re.compile(r"korea|seoul|japan|tokyo|singapore|apac|asia|china|beijing|shanghai|hong kong|taiwan|india|"
                      r"australia|sydney|\banz\b|vietnam|thailand|indonesia|philippines|malaysia", re.I)
EMEA_LOC = re.compile(r"emea|europe|london|united kingdom|\buk\b|germany|berlin|paris|france|israel|tel aviv|amsterdam|"
                      r"dublin|ireland|madrid|stockholm|zurich|middle east|dubai", re.I)

# Posting: an existing US / North America network or experience asked for.
US_REQ = re.compile(
    r"(?:network|relationships?|reputation|experience|track record|presence|connections)\s+(?:with|within|in|across|throughout)\s+"
    r"(?:the\s+)?(?:u\.s\.|us|united states|north american?|americas)\b[^.;]{0,80}"
    r"|us market mastery[^.;]{0,80}", re.I)
US_TITLE = re.compile(r"north america|\bus&c\b|\bucan\b|\bu\.s\.\b|\bus\b(?! ?based)|\bamericas\b", re.I)
GLOBAL_REQ = re.compile(
    r"(?:global|international|multi-?region(?:al)?|multi-?national|cross-?border)\s+(?:operating\s+|business\s+|go-to-market\s+)?"
    r"(?:experience|scope|footprint)\b[^.;]{0,60}"
    r"|across (?:na|north america), emea,? and apac[^.;]{0,40}"
    r"|(?:experience|track record)[^.;]{0,40}(?:multiple|several) (?:international |global )?(?:markets|countries|regions)\b[^.;]{0,40}"
    r"|(?:scal|grow|lead|manag)\w*[^.;]{0,40}across (?:multiple|several) (?:international |global )?(?:markets|countries|regions)\b[^.;]{0,40}", re.I)
RELOC_YES = re.compile(r"(?:offer|provide)s?\s+relocation assistance|relocation (?:assistance|support|package) (?:is )?(?:available|offered|provided)", re.I)
RELOC_NO = re.compile(r"not eligible for relocation|no relocation|relocation (?:assistance )?(?:is )?not (?:offered|available|provided)", re.I)
ONSITE = re.compile(r"\b\d\s+days?\s+(?:a|per)\s+week\s+in\s+(?:the\s+)?office|\bon-?site\b|\bin-office\b|office-based", re.I)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"&nbsp;|<[^>]+>", " ", s or "")).strip()


def posting_geo(title: str, description: str) -> dict:
    d = _clean(description)
    out: dict = {"tags": {}, "relocation": None, "onsite": None}
    if len(d) >= 400:
        m = US_REQ.search(d)
        if m:
            out["tags"]["geo_us_market"] = m.group(0)[:200]
        m = GLOBAL_REQ.search(d)
        if m:
            out["tags"]["geo_multi_region"] = m.group(0)[:200]
        if RELOC_YES.search(d):
            out["relocation"] = "offered"
        elif RELOC_NO.search(d):
            out["relocation"] = "not offered"
        m = ONSITE.search(d)
        out["onsite"] = m.group(0)[:60] if m else None
    if "geo_us_market" not in out["tags"] and US_TITLE.search(title or ""):
        out["tags"]["geo_us_market"] = f"title: {title}"[:200]
    return out


_cache: dict[tuple[int, str], dict] = {}


def posting_geo_cached(p) -> dict:
    key = (p.id or 0, p.content_hash or str(len(p.description or "")))
    if key not in _cache:
        _cache[key] = posting_geo(p.title, p.description or "")
    return _cache[key]


def regions(loc: str) -> set[str]:
    out = set()
    if US_LOC.search(loc or ""):
        out.add("US")
    if APAC_LOC.search(loc or ""):
        out.add("APAC")
    if EMEA_LOC.search(loc or ""):
        out.add("EMEA")
    return out


US_WORK = re.compile(r"[^.;]{0,80}\b(?:u\.s\.|united states|north america(?:n)?|us-based|us-headquartered|silicon valley)\b[^.;]{0,80}", re.I)
MULTI = re.compile(r"[^.;]{0,60}(?:\bapac\b|asia[- ]pacific|\bemea\b|across the region|multi-country|"
                   r"global (?:accounts|business|partnerships|revenue|sales|go-to-market))[^.;]{0,80}", re.I)
COUNTRIES = re.compile(r"\b(japan|korea|singapore|china|taiwan|india|australia|vietnam|thailand|indonesia|philippines|malaysia|"
                       r"hong kong|anz|southeast asia|united states|europe)\b", re.I)


def user_geo(roles: list[dict], degrees: list[dict] | None = None) -> dict:
    """Months by region from each role's stated location, and your match on the two geography tags."""
    months = {"US": 0, "APAC": 0, "EMEA": 0, "multi": 0, "unknown": 0}
    us_ev, multi_ev = [], []
    us_only = 0
    for r in roles:
        loc = r.get("location") or ""
        reg = regions(loc) or regions(r.get("company", ""))
        n = int(r.get("months") or 0)
        if len(reg) > 1:
            months["multi"] += n
        elif reg:
            months[next(iter(reg))] += n
        else:
            months["unknown"] += n
        label = f'{r.get("title", "")} @ {r.get("company", "")}'
        if reg == {"US"}:
            us_only += n
            us_ev.append(f"{label}: located {loc or 'in the US'}")
        elif "US" in reg:
            us_ev.append(f"{label}: location stated as {loc}")
        text = " ".join([r.get("title", "")] + list(r.get("desc") or []))
        for m in US_WORK.finditer(text):
            us_ev.append(f'{label}: "{m.group(0).strip()}"')
        mm = MULTI.search(text + " " + loc)
        if mm and (len(set(c.lower() for c in COUNTRIES.findall(text))) >= 2 or re.search(r"apac|asia[- ]pacific|emea|global", mm.group(0), re.I)):
            best = next((ln for ln in (r.get("desc") or []) if len(set(c.lower() for c in COUNTRIES.findall(ln))) >= 2), None)
            q = (best or mm.group(0)).strip()[:160]
            multi_ev.append((0 if best else 1, f'{label}: "{q}"'))
    multi_ev = [x for _, x in sorted(multi_ev, key=lambda t: t[0])]
    us_edu = [d["text"] for d in (degrees or []) if US_LOC.search(d.get("text", ""))]
    matches = {}
    if us_only >= 12:
        matches["geo_us_market"] = (1.0, us_ev[0])
    elif us_ev:
        matches["geo_us_market"] = (0.5, us_ev[0])
    if multi_ev:
        matches["geo_multi_region"] = (1.0, multi_ev[0])
    return {"months": months, "us_role_months": us_only, "us_evidence": us_ev[:6], "multi_evidence": multi_ev[:6],
            "us_education": us_edu, "matches": matches}


def relocation_view(db, prof, feats: dict | None, ev: dict, family: str = "Partnerships") -> dict:
    """What a move from APAC to a US role changes in your matching, measured on the postings you are shown."""
    from dataclasses import replace

    from sqlalchemy import select

    from ..models import ReferenceProfile
    from ..scoring import score as score_posting
    from ..services import posting_view, profile_view

    pv_user = profile_view(prof, feats)
    stats = ev["stats"]
    rows = ev["passing"] + ev.get("adjacent", [])
    us = [r for r in rows if "US" in regions(r["posting"].location or "") or re.search(r"remote", r["posting"].location or "", re.I)
          and not APAC_LOC.search(r["posting"].location or "")]
    pvs = [(r, posting_view(r["posting"])) for r in us]

    def strong(view) -> tuple[int, float]:
        s = [score_posting(pv, view, stats)["rank_score"] for _, pv in pvs]
        return sum(1 for x in s if x >= 0.8), (round(100 * sum(s) / len(s), 1) if s else 0.0)

    now_n, now_avg = strong(pv_user)
    have_us = float(pv_user.matches.get("geo_us_market", 0))
    full_n, full_avg = strong(replace(pv_user, matches={**pv_user.matches, "geo_us_market": 1.0}))
    none_n, none_avg = strong(replace(pv_user, matches={**pv_user.matches, "geo_us_market": 0.0}))

    asks_us, asks_multi, reloc_yes, reloc_no, onsite = [], [], [], [], []
    for r, pv in pvs:
        p = r["posting"]
        g = posting_geo_cached(p)
        item = {"id": p.id, "company": p.company, "title": p.title, "match": round(100 * r["rank_score"]), "url": p.url}
        if "geo_us_market" in g["tags"]:
            asks_us.append({**item, "quote": g["tags"]["geo_us_market"]})
        if "geo_multi_region" in g["tags"]:
            asks_multi.append({**item, "quote": g["tags"]["geo_multi_region"]})
        if g["relocation"] == "offered":
            reloc_yes.append(item)
        elif g["relocation"] == "not offered":
            reloc_no.append(item)
        if g["onsite"]:
            onsite.append({**item, "quote": g["onsite"]})

    geo = (feats or {}).get("geo") or {}
    holders = list(db.scalars(select(ReferenceProfile).where(ReferenceProfile.cluster == family)))
    with_geo = [h for h in holders if (h.features or {}).get("geo") is not None]
    peers = {"holders": len(holders), "with_location_data": len(with_geo)}
    if len(with_geo) >= 20:
        us_m = sorted(int(h.features.get("geo_us_months") or 0) for h in with_geo)
        peers.update({"share_with_us_roles": round(sum(1 for m in us_m if m > 0) / len(us_m), 2),
                      "median_us_months": us_m[len(us_m) // 2]})
    multi_have = float(pv_user.matches.get("geo_multi_region", 0))
    no_spons = sum(1 for _, pv in pvs if pv.no_sponsorship)
    return {
        "us_postings": len(pvs),
        "you": {"months": geo.get("months", {}), "us_role_months": geo.get("us_role_months", 0),
                "us_evidence": geo.get("us_evidence", []), "multi_evidence": geo.get("multi_evidence", []),
                "us_education": geo.get("us_education", []), "us_market_match": have_us, "multi_region_match": multi_have},
        "authorization": {"needs_sponsorship": bool(prof.needs_sponsorship), "postings_without_sponsorship": no_spons,
                          "line": ("Your profile says you do not need sponsorship, so the US postings that state no "
                                   "sponsorship do not screen you out." if not prof.needs_sponsorship else
                                   f"Your profile says you need sponsorship: {no_spons} US postings state they do not sponsor.")},
        "effect": {"strong_now": now_n, "avg_now": now_avg, "strong_if_full": full_n, "avg_if_full": full_avg,
                   "strong_if_none": none_n, "avg_if_none": none_avg},
        "asks_us": sorted(asks_us, key=lambda x: -x["match"]), "asks_multi": sorted(asks_multi, key=lambda x: -x["match"]),
        "relocation_offered": reloc_yes, "relocation_not_offered": reloc_no, "onsite": onsite,
        "peers": peers, "target_date": prof.target_date or "",
        "method": ["US postings: those you are shown (passing your screen or missing only a preference) located in the US or remote-US.",
                   "A posting asks for US market experience only when its text says so (quoted) or its title is US / North America scoped.",
                   "Effects are measured by rescoring those postings with your US-market match set to full or none; nothing is estimated.",
                   "Peers' locations are recorded from new hire-research files only; there is no peer comparison until 20 holders have it."],
    }
