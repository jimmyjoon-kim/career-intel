"""Industry context, built around peer comparison.

An industry is the sector of the employer (OpenAI = AI platforms, NVIDIA = cloud & semiconductors). For each role holder
the app records the sectors of the roles BEFORE the current one, so it can say who switched into a sector, from where,
and what they had when they did. You are compared with those people, not with a rule of thumb.

Sector of a company: a listed name first, then a cached classification (rules, or one model call per unknown company,
stored with its source), else "unclassified". Nothing here is a probability."""

from __future__ import annotations

import re
from collections import Counter

SECTORS = {
    "adtech": "Advertising, ad tech & marketing",
    "ai": "AI platforms & AI-native software",
    "cloud": "Cloud, infrastructure & semiconductors",
    "saas": "Enterprise software (SaaS)",
    "fintech": "Fintech & payments",
    "commerce": "Commerce, marketplaces & mobility",
    "consumer": "Consumer internet & social",
    "gaming": "Gaming & consumer apps",
    "media": "Media, streaming & entertainment",
    "devices": "Devices & telecom",
    "health": "Healthcare & life sciences",
    "gov": "Government & defense",
    "services": "Consulting & professional services",
    "other": "Other",
}

# Listed companies (lowercase substrings). Advertising units of non-ad companies are matched first.
KNOWN: list[tuple[str, str]] = [
    (r"\bads\b|ad solutions|advertising", "adtech"),
    (r"applovin|liftoff|moloco|ironsource|digital turbine|mintegral|trade desk|fiksu|vungle|inmobi|criteo|taboola|outbrain|"
     r"liveramp|zeta global|magnite|pubmatic|appsflyer|adjust\b|branch metrics|jellyfish|wpp|omnicom|publicis|dentsu|"
     r"tapjoy|chartboost|smaato|verve|is\.com|unity", "adtech"),
    (r"openai|anthropic|perplexity|mistral|cohere|scale ai|surge ai|gamma\b|asapp|pano ai|legion intelligence|wortal|"
     r"hugging ?face|character\.ai|runway|elevenlabs|harvey|glean|sierra|decagon|\(ai\)|\bai\b", "ai"),
    (r"nvidia|qualcomm|\bamd\b|\bintel\b|\barm\b|broadcom|ddn|amazon web services|\baws\b|google cloud|azure|corestack|"
     r"snowflake|databricks|cloudflare|coreweave|oracle cloud|cisco", "cloud"),
    (r"servicenow|salesforce|adobe|theta lake|persona\b|nachonacho|workday|\bsap\b|oracle|flexera|macrovision|autodesk|"
     r"rexsoft|atlassian|hubspot|zendesk|twilio|okta|crowdstrike|palo alto", "saas"),
    (r"airwallex|mastercard|\bvisa\b|stripe|paypal|\bblock\b|\bsquare\b|adyen|capital one|perseus|cora loyalty|plaid|revolut", "fintech"),
    (r"doordash|uber|instacart|lyft|airbnb|shopify|ebay|etsy|amazon\b|coupang|grab\b|wayfair", "commerce"),
    (r"\bmeta\b|facebook|instagram|pinterest|reddit|\bsnap\b|tiktok|bytedance|linkedin|google|youtube|x corp|twitter|"
     r"strava|discord|naver|kakao|line corp", "consumer"),
    (r"roblox|paramount games|se7en|duolingo|epic games|activision|electronic arts|take-two|playtika|scopely|supercell|"
     r"nexon|netmarble|krafton|zynga", "gaming"),
    (r"netflix|twitch|xumo|amc global|paramount|disney|warner|comcast|spotify|nbcuniversal|hulu", "media"),
    (r"apple\b|samsung|blackberry|sony|lg electronics|verizon|at&t|t-mobile|sk telecom|kt corp|nokia|ericsson", "devices"),
    (r"johnson & johnson|depuy|pfizer|suki|medtronic|epic systems|optum|unitedhealth", "health"),
    (r"paladin|anduril|palantir|lockheed|booz allen|federal", "gov"),
    (r"mckinsey|bain|boston consulting|bcg\b|deloitte|accenture|pwc|kpmg|ernst|newtonx|\bltm\b", "services"),
]
_KNOWN = [(re.compile(p, re.I), s) for p, s in KNOWN]

# Adjacency used only to label a switch "adjacent" or "distant" in the text; the numbers shown come from peers and postings.
ADJACENT = {
    "adtech": {"consumer", "gaming", "media", "commerce", "ai"},
    "ai": {"saas", "cloud", "adtech", "consumer"},
    "cloud": {"saas", "ai", "devices"},
    "saas": {"cloud", "ai", "fintech"},
    "fintech": {"saas", "commerce"},
    "commerce": {"consumer", "adtech", "fintech"},
    "consumer": {"adtech", "media", "gaming", "commerce", "ai"},
    "gaming": {"adtech", "consumer", "media"},
    "media": {"adtech", "consumer", "gaming"},
    "devices": {"cloud", "consumer"},
}


def sector_of(company: str, cache: dict[str, str] | None = None) -> tuple[str, str]:
    """(sector, source) where source is 'listed', 'classified' or 'unclassified'."""
    c = (company or "").strip()
    for rx, s in _KNOWN:
        if rx.search(c):
            return s, "listed"
    if cache and c.lower() in cache:
        return cache[c.lower()], "classified"
    return "other", "unclassified"


def classify_companies(db, names: list[str], run_id: int | None = None) -> dict[str, str]:
    """One model call for companies not listed or cached; results are stored with source 'model'."""
    from sqlalchemy import select

    from ..llm import BudgetExceeded, complete_json
    from ..models import CompanySector

    cache = {r.company: r.sector for r in db.scalars(select(CompanySector))}
    uniq: dict[str, str] = {}
    for n in names:  # one entry per company, ignoring case
        if n and n.strip() and sector_of(n)[1] == "unclassified" and n.strip().lower() not in cache:
            uniq.setdefault(n.strip().lower(), n.strip())
    todo = sorted(uniq.values())[:60]
    if todo:
        try:
            res = complete_json(
                "Classify each company into exactly one sector key: " + ", ".join(f"{k} ({v})" for k, v in SECTORS.items())
                + ". Use what the company is primarily known for. If you do not know the company, use \"other\". "
                  'Return {"sectors": {"<company>": "<key>"}}.',
                "\n".join(todo), max_tokens=1500, role="bulk", agent="industry", run_id=run_id) or {}
        except BudgetExceeded:
            res = {}
        for n, s in (res.get("sectors") or {}).items():
            if n in todo and s in SECTORS and n.lower() not in cache:
                db.add(CompanySector(company=n.lower()[:200], sector=s, source="model"))
                cache[n.lower()] = s
        db.commit()
    return cache


def load_cache(db) -> dict[str, str]:
    from sqlalchemy import select

    from ..models import CompanySector

    return {r.company: r.sector for r in db.scalars(select(CompanySector))}


def _same(a: str, b: str) -> bool:
    x, y = re.sub(r"[^a-z0-9]", "", (a or "").lower()), re.sub(r"[^a-z0-9]", "", (b or "").lower())
    return bool(x and y) and (x.startswith(y[:6]) or y.startswith(x[:6]))


def path(roles: list[dict], current_company: str | None = None, cache: dict | None = None) -> dict:
    """Industry path. With current_company (a role holder), roles at that company are the destination and the rest
    are 'before'; for you, the most recent employer is 'current'."""
    roles = [r for r in roles if int(r.get("months") or 0) >= 6 and not re.search(r"\bintern", r.get("title", ""), re.I)]
    if not roles:
        return {}
    roles = sorted(roles, key=lambda r: r["start"], reverse=True)
    cur_co = current_company or roles[0]["company"]
    cur = [r for r in roles if _same(r["company"], cur_co)]
    before = [r for r in roles if r not in cur]
    cur_sector = sector_of(cur_co, cache)[0]
    months: Counter = Counter()
    for r in before:
        months[sector_of(r["company"], cache)[0]] += int(r["months"])
    prior_sectors = {s for s, m in months.items() if m >= 12}
    last = before[0] if before else None
    return {
        "current_sector": cur_sector,
        "before_months": dict(months),
        "home_before": months.most_common(1)[0][0] if months else None,
        "switched_in": bool(before) and cur_sector not in prior_sectors,
        "entry_from": sector_of(last["company"], cache)[0] if last else None,
        "before_years": round(sum(months.values()) / 12, 1),
    }


def user_path(roles: list[dict], cache: dict | None = None) -> dict:
    months: Counter = Counter()
    recent: Counter = Counter()
    latest = max((r["end"][0] for r in roles), default=0)
    for r in roles:
        s = sector_of(r["company"], cache)[0]
        months[s] += int(r.get("months") or 0)
        if r["end"][0] >= latest - 10:
            recent[s] += int(r.get("months") or 0)
    return {"months": dict(months), "home": (recent or months).most_common(1)[0][0] if months else None,
            "sectors_12m": sorted(s for s, m in months.items() if m >= 12)}


DOMAIN_TAG = {"adtech": "domain_adtech", "ai": "domain_ai", "saas": "domain_saas", "commerce": "domain_marketplace",
              "gaming": "domain_mobile"}
MIN_PEERS = 10      # holders needed before a percentile against one sector's holders is shown
MIN_SWITCHERS = 5   # switchers needed before their profile is summarized


def _median(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    return round(xs[len(xs) // 2], 1) if xs else None


def industry_view(db, prof, feats: dict | None, ev: dict, family: str = "Partnerships", target: str | None = None) -> dict:
    from sqlalchemy import select

    from ..models import ReferenceProfile
    from ..taxonomy import TAGS
    from .focus import versus_peers
    from .model import Reference, base_scorecard
    from .service import months_left

    holders = list(db.scalars(select(ReferenceProfile).where(ReferenceProfile.cluster == family)))
    rows = ev["passing"] + ev.get("adjacent", [])
    cache = classify_companies(db, [h.company for h in holders] + [r["posting"].company for r in rows]
                               + [r["company"] for r in ((feats or {}).get("roles") or [])])
    you = (feats or {}).get("industry") or {}
    home = you.get("home")
    home_tag = DOMAIN_TAG.get(home or "")

    by: dict[str, dict] = {}
    for h in holders:
        s = sector_of(h.company, cache)[0]
        b = by.setdefault(s, {"holders": [], "postings": []})
        b["holders"].append(h)
    for r in rows:
        s = sector_of(r["posting"].company, cache)[0]
        by.setdefault(s, {"holders": [], "postings": []})["postings"].append(r)

    def summary(s: str, b: dict) -> dict:
        hs = b["holders"]
        with_path = [h for h in hs if (h.features or {}).get("ind")]
        sw = [h for h in with_path if h.features["ind"].get("switched_in")]
        from_home = [h for h in with_path if home and (h.features["ind"].get("before_months", {}).get(home, 0) >= 12)]
        ev_home = [h for h in hs if home_tag and float(((h.features or {}).get("tags") or {}).get(home_tag, 0)) > 0]
        ps = b["postings"]
        return {"sector": s, "label": SECTORS.get(s, s), "holders": len(hs), "with_path": len(with_path),
                "switched_in": len(sw), "from_your_industry": len(from_home),
                "your_industry_in_career": len(ev_home) if home_tag else None,
                "postings": len(ps), "your_avg_match": round(100 * sum(r["rank_score"] for r in ps) / len(ps), 1) if ps else None,
                "strong_matches": sum(1 for r in ps if r["rank_score"] >= 0.8),
                "relation": "your industry" if s == home else ("adjacent" if s in ADJACENT.get(home or "", set()) else "distant")}

    table = sorted((summary(s, b) for s, b in by.items()), key=lambda x: (-(x["holders"] + x["postings"])))
    choices = [t["sector"] for t in table if t["sector"] != home and (t["holders"] or t["postings"])]
    target = target if target in by else (choices[0] if choices else home)
    tb = by.get(target, {"holders": [], "postings": []})
    tsum = next((t for t in table if t["sector"] == target), None)

    # 1. You against the people who hold these roles in the target industry (same scoring model, filtered peer group).
    peer = {"n": len(tb["holders"]), "min": MIN_PEERS}
    if feats and len(tb["holders"]) >= MIN_PEERS:
        ref = Reference(f"{family} · {SECTORS.get(target, target)}",
                        [{"company": h.company, "title": h.title, **h.features} for h in tb["holders"]])
        card = base_scorecard(feats, ref, months_left=months_left(prof.target_date or ""), n_boot=300)
        sc = [s for s in card["holders"]["scores"] if s is not None]
        peer.update({"score": card["base_score"], "rank": sum(1 for s in sc if s > card["base_score"]) + 1, "of": len(sc) + 1,
                     "median": card["holders"]["median"], "factors": versus_peers(card)})

    # 2. Switchers into the target industry: where they came from and what they had.
    with_path = [h for h in tb["holders"] if (h.features or {}).get("ind")]
    sw = [h for h in with_path if h.features["ind"].get("switched_in")]
    switchers = {"with_path": len(with_path), "switched_in": len(sw), "min": MIN_SWITCHERS}
    if len(sw) >= MIN_SWITCHERS:
        switchers.update({
            "from": Counter(SECTORS.get(h.features["ind"].get("entry_from") or "other", "Other") for h in sw).most_common(6),
            "median_years_before": _median([h.features["ind"].get("before_years") for h in sw]),
            "median_level": _median([h.features.get("LV") for h in sw]),
            "share_ai_degree": round(sum(1 for h in sw if float(h.features.get("AI") or 0) >= 0.4) / len(sw), 2),
            "share_from_your_industry": round(sum(1 for h in sw if home and h.features["ind"].get("before_months", {}).get(home, 0) >= 12) / len(sw), 2),
        })
    evidence_now = None
    if home_tag and tb["holders"]:
        k = sum(1 for h in tb["holders"] if float(((h.features or {}).get("tags") or {}).get(home_tag, 0)) > 0)
        evidence_now = {"n": k, "of": len(tb["holders"]), "tag": TAGS[home_tag].label}

    # 3. Postings in the target industry: requirements asked more there than in your industry, and your match.
    def shares(rs):
        c = Counter(t for r in rs for t in set(r["posting"].tags or []) if t in TAGS)
        return {t: n / len(rs) for t, n in c.items()} if rs else {}
    ts, hs_ = shares(tb["postings"]), shares(by.get(home or "", {}).get("postings", []))
    from ..services import profile_view

    pv = profile_view(prof, feats)
    gaps = []
    for t, sh in sorted(ts.items(), key=lambda x: -x[1]):
        m = float(pv.matches.get(t, 0))
        if sh >= 0.3 and m < 1:
            gaps.append({"tag": t, "label": TAGS[t].label, "share_target": round(sh, 2), "share_home": round(hs_.get(t, 0), 2),
                         "specific": sh - hs_.get(t, 0) >= 0.2, "match": m, "closable": TAGS[t].closable, "how": TAGS[t].close_hint})
    # 4. Requirement overlap between your industry's postings and the target's (cosine of requirement shares).
    overlap = None
    if len(tb["postings"]) >= 5 and len(by.get(home or "", {}).get("postings", [])) >= 5:
        keys = set(ts) | set(hs_)
        num = sum(ts.get(k, 0) * hs_.get(k, 0) for k in keys)
        den = (sum(v * v for v in ts.values()) ** 0.5) * (sum(v * v for v in hs_.values()) ** 0.5)
        overlap = round(num / den, 2) if den else None

    # 5. Function bridge: target-industry postings in your own functions vs the rest (research: function carries over).
    mine = {t for t in ("func_partnerships", "func_bd", "func_ad_sales", "func_alliances_gsi", "func_channel", "func_sales_leadership")
            if float(pv.matches.get(t, 0)) >= 1}
    same = [r for r in tb["postings"] if set(r["posting"].tags or []) & mine]
    other = [r for r in tb["postings"] if r not in same]
    avg = lambda rs: round(100 * sum(r["rank_score"] for r in rs) / len(rs), 1) if rs else None  # noqa: E731
    bridge = {"same_function": len(same), "same_avg": avg(same), "other": len(other), "other_avg": avg(other),
              "best": [{"company": r["posting"].company, "title": r["posting"].title, "match": round(100 * r["rank_score"]),
                        "url": r["posting"].url} for r in sorted(same, key=lambda r: -r["rank_score"])[:4]]}

    import json
    from pathlib import Path

    ctx = {}
    f = Path(__file__).resolve().parents[2] / "seed" / "industry_cases.json"
    if not f.exists():
        f = Path("/app/seed/industry_cases.json")
    if f.exists():
        ctx = json.loads(f.read_text())
    cases = [c for c in ctx.get("cases", []) if c["to_sector"] == target]
    return {
        "overlap": overlap, "bridge": bridge, "cases": cases, "benchmarks": ctx.get("benchmarks", []),
        "not_found": ctx.get("not_found", []),
        "family": family, "you": {"home": home, "home_label": SECTORS.get(home or "", "unknown"),
                                  "months": {SECTORS.get(k, k): v for k, v in sorted(you.get("months", {}).items(), key=lambda x: -x[1])}},
        "sectors": table, "target": target, "target_label": SECTORS.get(target, target), "target_summary": tsum,
        "peer": peer, "switchers": switchers, "evidence_now": evidence_now, "gaps": gaps[:8],
        "method": [
            "Industry = the sector of the employer. Listed companies are fixed; others are classified once by a model and stored.",
            f"Peer score: the same scoring model, with the comparison group limited to {family} holders now in that industry (shown from {MIN_PEERS} holders).",
            "Switched in: the holder had no 12+ months in that industry before joining the current employer. Recorded for holders read from Oct 30, 2026 on; earlier holders have only their current employer.",
            "Your industry in career: the holder's text shows that domain anywhere, including the current role.",
            "Requirements: share of that industry's postings asking for each requirement vs your industry's postings; 'specific' when 20+ points higher.",
            "Requirement overlap: similarity (0-1) of the requirement mix of the target industry's postings and your industry's (5+ postings each).",
            "Function bridge: target-industry postings in functions you fully show (partnerships, BD, ad sales, alliances, channel, sales leadership).",
            "Cases and benchmarks are cited outside context; they do not enter any score.",
            "No probabilities or hire likelihoods.",
        ],
    }
