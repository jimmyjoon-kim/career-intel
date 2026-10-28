"""Context-aware signals (v3): current AI relevance, technical depth, company journey.

Rules (same for every person; expert-set, not yet validated against hiring outcomes):
- AI relevance decays fast: AI work counts 1.0 if the role was active in the last 24 months, 0.5 for 24-36 months,
  0.1 if older. Generic "AI" from before that window carries almost no weight.
  AI = 0.6 x best recent AI work + 0.4 x AI graduate degree (1.0 completed, 0.5 in progress).
- Technical depth = mean of: technical degree; a technical role in the last 15 years (engineer, solutions/presales, developer, data scientist);
  technical product work (SDK/API, mediation, programmatic, platform, ML/LLM) in the last 8 years.
- Company journey: a role that spanned an IPO or acquisition of its company, joined at least 6 months before the event,
  or a role whose description states it. Company tier & journey = max(tier of recent role, best role in the last 10 years
  as tier + 1 for a journey), on the 1-4 scale (1 = Tier 3 ... 3 = Tier 1, 4 = Tier 1 with a journey).
"""

from __future__ import annotations

import re

# Dated company events. status: "verified" = checked against a source in this project; "unverified" = widely reported,
# not yet checked against filings. Applied to everyone's roles alike.
COMPANY_EVENTS = [
    (r"ironsource", "IPO", (2021, 6), "verified", "NYSE listing at $11.1B (Globes)"),
    (r"ironsource", "merger", (2022, 11), "verified", "Merger with Unity completed (unity.com)"),
    (r"\bunity\b", "IPO", (2020, 9), "unverified", "NYSE IPO"),
    (r"\bsnap\b", "IPO", (2017, 3), "unverified", "NYSE IPO"),
    (r"\bokta\b", "IPO", (2017, 4), "unverified", "Nasdaq IPO"),
    (r"pinterest", "IPO", (2019, 4), "unverified", "NYSE IPO"),
    (r"trade desk", "IPO", (2016, 9), "unverified", "Nasdaq IPO"),
    (r"dropbox", "IPO", (2018, 3), "unverified", "Nasdaq IPO"),
    (r"\bslack\b", "IPO", (2019, 6), "unverified", "NYSE direct listing"),
    (r"\bslack\b", "acquisition", (2021, 7), "unverified", "Acquired by Salesforce"),
    (r"pubmatic", "IPO", (2020, 12), "unverified", "Nasdaq IPO"),
    (r"facebook|\bmeta\b", "IPO", (2012, 5), "unverified", "Nasdaq IPO"),
    (r"linkedin", "IPO", (2011, 5), "unverified", "NYSE IPO"),
    (r"linkedin", "acquisition", (2016, 12), "unverified", "Acquired by Microsoft"),
    (r"oculus", "acquisition", (2014, 3), "unverified", "Acquired by Facebook"),
    (r"smartthings", "acquisition", (2014, 8), "unverified", "Acquired by Samsung"),
    (r"lacework", "acquisition", (2024, 8), "unverified", "Acquired by Fortinet"),
    (r"pure storage", "IPO", (2015, 10), "unverified", "NYSE IPO"),
    (r"zeta global", "IPO", (2021, 6), "unverified", "NYSE IPO"),
    (r"\broblox\b", "IPO", (2021, 3), "unverified", "NYSE direct listing"),
    (r"duolingo", "IPO", (2021, 7), "unverified", "Nasdaq IPO"),
    (r"applovin", "IPO", (2021, 4), "unverified", "Nasdaq IPO"),
    (r"reddit", "IPO", (2024, 3), "unverified", "NYSE IPO"),
    (r"\buber\b", "IPO", (2019, 5), "unverified", "NYSE IPO"),
    (r"datalogix", "acquisition", (2014, 12), "unverified", "Acquired by Oracle"),
    (r"youtube", "acquisition", (2006, 11), "unverified", "Acquired by Google"),
    (r"myspace", "acquisition", (2005, 7), "unverified", "Acquired by News Corp"),
    (r"docasap", "acquisition", (2021, 2), "unverified", "Acquired by Optum"),
    (r"chaotic moon", "acquisition", (2015, 7), "unverified", "Acquired by Accenture"),
    (r"vmware", "IPO", (2007, 8), "unverified", "NYSE IPO"),
    (r"turn\b", "acquisition", (2017, 4), "unverified", "Acquired by Amobee"),
]
JOURNEY_TEXT = re.compile(r"(?:through|to|led|took|prepared|supported)[^.;]{0,40}\b(?:ipo|public listing|went public|acquisition|exit)\b|"
                          r"pre-ipo|pre ipo|until (?:its|the) (?:ipo|acquisition)|\bacquired by\b", re.I)
AI_STRONG = re.compile(r"\bllm|generative|genai|gen ai|agentic|\bagents?\b|foundation model|openai|anthropic|gpt|claude|"
                       r"\bai\b|artificial intelligence|machine learning|\bml\b|copilot|gemini|llmops", re.I)
AI_COMPANY = re.compile(r"openai|anthropic|cohere|mistral|hugging ?face|scale ai|perplexity|character\.ai|\bxai\b|\.ai\b|\bai\b", re.I)
TECH_ROLE = re.compile(r"engineer|architect|developer|data scientist|solutions consultant|presales|pre-sales|sales engineer|"
                       r"technical|product manager|cto\b", re.I)
TECH_PRODUCT = re.compile(r"\bsdk|\bapis?\b|integration|mediation|programmatic|\bdsp\b|\bssp\b|platform|infrastructure|cloud|"
                          r"machine learning|\bllm|data pipeline|analytics", re.I)
AI_DEGREE = re.compile(r"\bai\b|artificial intelligence|machine learning|data science", re.I)


def _months(a, b) -> int:
    return (b[0] - a[0]) * 12 + (b[1] - a[1])


def ai_recency_weight(end: tuple[int, int], now: tuple[int, int]) -> float:
    m = _months(end, now)
    return 1.0 if m <= 24 else 0.5 if m <= 36 else 0.1


def role_signals(r: dict, now: tuple[int, int]) -> dict:
    """Per-role evidence. r has title, company, desc (list), start, end."""
    blob = " ".join([r["title"], r["company"]] + r["desc"])
    ai = None
    m = AI_STRONG.search(blob) or AI_COMPANY.search(r["company"])
    if m:
        ai = {"weight": ai_recency_weight(r["end"], now), "phrase": m.group(0)}
    journey = []
    for pat, kind, when, status, note in COMPANY_EVENTS:
        if re.search(pat, r["company"].lower()) and r["start"] <= when <= r["end"] and _months(r["start"], when) >= 6:
            journey.append({"event": kind, "date": f"{when[0]}-{when[1]:02d}", "status": status, "note": note})
    jt = JOURNEY_TEXT.search(" ".join(r["desc"]))
    if jt and not journey:
        journey.append({"event": "stated in profile", "date": None, "status": "self-described", "note": jt.group(0)[:80]})
    recent8 = _months(r["end"], now) <= 96
    return {"ai": ai, "journey": journey,
            "tech_role": bool(TECH_ROLE.search(r["title"])) and _months(r["end"], now) <= 180,  # technical role in the last 15 years
            "tech_product": bool(recent8 and TECH_PRODUCT.search(" ".join(r["desc"] + [r["title"]])))}


def combine(feats: dict, *, tech_degree: bool, ai_degree: float, now: tuple[int, int]) -> dict:
    """Adds AI, TK and the journey-adjusted CT to a feature dict built by reader.extract_features."""
    per = feats.get("_signals", [])
    ai_work = max((s["ai"]["weight"] for s in per if s["ai"]), default=0.0)
    feats["AI_work"] = ai_work
    feats["AI_degree"] = ai_degree
    feats["AI"] = round(min(1.0, 0.6 * ai_work + 0.4 * ai_degree), 3)
    tech_role = any(s["tech_role"] for s in per)
    tech_product = any(s["tech_product"] for s in per)
    feats["TK"] = round((float(tech_degree) + float(tech_role) + float(tech_product)) / 3, 3)
    feats["TK_parts"] = {"technical degree": tech_degree, "technical role": tech_role, "technical product work": tech_product}
    best = feats.get("CT") or 0
    best_role = None
    for s in per:
        if _months(s["_end"], now) > 120:
            continue
        pts = {1: 3, 2: 2, 3: 1}.get(s["_tier"], 1) + (1 if s["journey"] else 0)
        if pts > best:
            best, best_role = pts, s
    feats["CT_tier_only"] = feats.get("CT")
    feats["CT"] = best or feats.get("CT")
    feats["journey"] = [{"role": s["_label"], **j} for s in per for j in s["journey"]]
    feats["CT_basis"] = best_role["_label"] if best_role else "most recent role held 12+ months"
    return feats
