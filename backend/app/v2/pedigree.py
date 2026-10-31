"""Selection signals the first model did not read.

PD  — times hired into a major company: distinct employers at Tier 1 or Tier 2 (reader.company_tier) where a role was
      held 12+ months in the last 20 years. Each counts once. For a role holder, the current employer is excluded
      (the profile is read as it was when they were hired).
SCH — school tier of the best completed degree: 2 = QS World University Rankings top 30, 1 = ranks 31-100, 0 = other
      or unranked. List: QS 2027 as published by a secondary source (yocket.com, dated 2026-07-15); unverified against
      qs.com.
FLD — field of the best completed degree: 1 = engineering, computer science, math or natural science; 0.5 = economics,
      finance, business or statistics; 0 = other fields.
These enter the score only once at least 20 holders in the comparison group have a value (model.base_scorecard)."""

from __future__ import annotations

import re

from .reader import company_tier, months_between

QS_TOP30 = [
    r"massachusetts institute of technology|\bmit\b", r"imperial college", r"stanford", r"university of oxford|\boxford\b",
    r"harvard", r"university of cambridge|\bcambridge university\b", r"california institute of technology|caltech",
    r"eth zurich|\beth\b", r"university college london|\bucl\b", r"national university of singapore|\bnus\b",
    r"university of hong kong|\bhku\b", r"nanyang technological|\bntu\b", r"peking university", r"tsinghua",
    r"university of pennsylvania|\bupenn\b|wharton", r"cornell", r"\byale\b", r"chinese university of hong kong|\bcuhk\b",
    r"university of new south wales|\bunsw\b", r"johns hopkins", r"university of california,? berkeley|uc berkeley|\bberkeley\b",
    r"\bepfl\b|polytechnique f[ée]d[ée]rale de lausanne", r"university of melbourne", r"university of chicago|booth school",
    r"technical university of munich|\btum\b", r"fudan", r"princeton", r"university of sydney", r"australian national university",
    r"mcgill",
]
QS_31_100 = [
    r"monash", r"university of toronto", r"hong kong university of science|\bhkust\b", r"universit[ée] psl", r"university of edinburgh",
    r"shanghai jiao tong", r"king'?s college london", r"seoul national university", r"university of tokyo", r"university of manchester",
    r"university of queensland", r"yonsei", r"columbia university|columbia business school", r"institut polytechnique de paris",
    r"northwestern|kellogg", r"university of british columbia|\bubc\b", r"zhejiang university", r"delft",
    r"university of california,? los angeles|\bucla\b", r"hong kong polytechnic", r"university of michigan", r"city university of hong kong",
    r"korea university", r"national taiwan university", r"carnegie mellon", r"universiti malaya", r"university of bristol",
    r"new york university|\bnyu\b|stern school", r"ku leuven", r"university of amsterdam", r"ludwig-maximilians|\blmu\b",
    r"london school of economics|\blse\b", r"\bkfupm\b|king fahd", r"kyoto university", r"\bkaist\b|korea advanced institute",
    r"brown university", r"university of auckland", r"university of warwick", r"university of birmingham", r"duke university|fuqua",
    r"lund university", r"university of texas at austin|ut austin", r"sorbonne", r"university of illinois|urbana-champaign|\buiuc\b",
    r"trinity college dublin", r"paris-saclay", r"university of western australia", r"university of leeds", r"adelaide university|university of adelaide",
    r"university of glasgow", r"university of california,? san diego|\bucsd\b", r"\bkth\b", r"university of sheffield",
    r"universidad de buenos aires", r"durham university", r"heidelberg", r"politecnico di milano", r"university of technology sydney",
    r"uppsala", r"nanjing university", r"university of copenhagen", r"pennsylvania state|penn state", r"university of washington",
    r"boston university", r"osaka university|university of osaka", r"university of alberta", r"institute of science tokyo|tokyo institute of technology",
    r"university of nottingham", r"freie universit[äa]t berlin", r"university of zurich",
]
_T1 = re.compile("|".join(QS_TOP30), re.I)
_T2 = re.compile("|".join(QS_31_100), re.I)
STEM = re.compile(r"engineer|computer|software|information (?:systems|technology)|electrical|mechanical|physics|chemistr|"
                  r"mathemat|\bmath\b|biolog|data science|artificial intelligence|machine learning|\bb\.?s\.?e\b", re.I)
QUANT = re.compile(r"econom|financ|business|commerce|accounting|statistic|management|\bmba\b|\bbba\b", re.I)


def school_tier(text: str) -> int:
    if _T1.search(text or ""):
        return 2
    if _T2.search(text or ""):
        return 1
    return 0


def field_score(text: str) -> float:
    if STEM.search(text or ""):
        return 1.0
    if QUANT.search(text or ""):
        return 0.5
    return 0.0


def education_signals(degrees: list[dict]) -> dict:
    done = [d for d in degrees if not d.get("in_progress")]
    if not done:
        return {"SCH": None, "FLD": None, "SCH_basis": None}
    sch = max(done, key=lambda d: (school_tier(d["text"]), d["level"]))
    return {"SCH": school_tier(sch["text"]), "FLD": max(field_score(d["text"]) for d in done), "SCH_basis": sch["text"][:120]}


def employer_signal(roles: list[dict], exclude_company: str | None = None, now: tuple[int, int] | None = None) -> dict:
    """Distinct Tier 1 / Tier 2 employers with a role of 12+ months ending in the last 20 years."""
    seen: dict[str, int] = {}
    names: dict[str, str] = {}
    # A role reached through a merger or acquisition ("ironSource (merged with Unity)") is not a hiring decision.
    merged_into = []
    for r in roles:
        m = re.search(r"\((?:merged with|acquired by|now part of)\s+([^)]+)\)", r["company"], re.I)
        if m:
            merged_into.append((m.group(1).strip().lower()[:6], r["end"]))
    for r in roles:
        if exclude_company and r["company"].strip().lower()[:6] == exclude_company.strip().lower()[:6]:
            continue
        if int(r.get("months") or 0) < 12 or re.search(r"\bintern", r.get("title", ""), re.I):
            continue
        if now and months_between(r["end"], now) > 240:
            continue
        if any(r["company"].strip().lower().startswith(tgt) and abs(months_between(end, r["start"])) <= 6
               for tgt, end in merged_into):
            continue
        t = company_tier(r["company"])
        if t in (1, 2):
            key = re.sub(r"[^a-z0-9]", "", r["company"].lower())[:10]
            seen[key] = min(seen.get(key, 9), t)
            names.setdefault(key, r["company"])
    return {"PD": len(seen), "PD_t1": sum(1 for t in seen.values() if t == 1),
            "PD_basis": sorted(names.values())}
