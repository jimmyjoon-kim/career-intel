"""Normalise CVs and job descriptions into the shared taxonomy.

With an Anthropic key: Claude reads the text and returns evidence-backed tags.
Without one: deterministic keyword matching (offline mode).
"""

import re

from .llm import complete_json
from .taxonomy import TAGS, infer_level, keyword_tags, split_tags, taxonomy_for_prompt

CV_SYSTEM = """You map a candidate's CV onto a fixed requirement taxonomy for commercial leadership roles.
Rules:
- Score each tag 1 (clearly evidenced), 0.5 (partial or indirect evidence) or 0 (absent). Omit tags scored 0.
- Every scored tag must quote or closely paraphrase its evidence from the CV. Never infer beyond the text.
- years_experience = total years of professional experience stated or computable from dates; null if unclear.
Return: {"headline": str, "years_experience": int|null, "tags": {"<tag>": {"match": 1|0.5, "evidence": str}}}"""

JD_SYSTEM = """You map a job description onto a fixed requirement taxonomy.
Return only requirements the posting actually states.
Return: {"tags": [str], "years_required": int|null, "level_band": str, "role_cluster": str,
"scope": "global"|"regional"|"na"|"country"|"unknown", "no_sponsorship": bool}
role_cluster is one of: Partnerships, Ad Sales, Sales Leadership, Growth, Rev Strategy, GM / Business Lead, Other.
level_band is one of: IC, Manager, Senior Manager, Director, Head, Sr Director, VP, SVP, C-level."""


def _years_from_text(text: str) -> int | None:
    m = re.findall(r"(\d{1,2})\+?\s+years", text.lower())
    nums = [int(x) for x in m if 1 <= int(x) <= 45]
    if nums:
        return max(nums)
    years = [int(y) for y in re.findall(r"\b(19[89]\d|20[0-2]\d)\b", text)]
    if len(years) >= 2:
        return max(years) - min(years)
    return None


def extract_cv(cv_text: str) -> dict:
    """Returns {"headline", "years_experience", "tags": {tag: {match, evidence, source}}, "mode"}."""
    result = complete_json(CV_SYSTEM, f"Taxonomy:\n{taxonomy_for_prompt()}\n\nCV:\n{cv_text[:60000]}")
    if result and isinstance(result.get("tags"), dict):
        tags = {}
        for k, v in result["tags"].items():
            if k in TAGS and isinstance(v, dict):
                match = v.get("match", 0)
                match = 1.0 if match >= 1 else 0.5 if match >= 0.5 else 0.0
                if match > 0:
                    tags[k] = {"match": match, "evidence": str(v.get("evidence", ""))[:500], "source": "extracted"}
        return {
            "headline": str(result.get("headline", ""))[:300],
            "years_experience": result.get("years_experience"),
            "tags": tags,
            "mode": "llm",
        }
    found = keyword_tags(cv_text)
    first_line = next((ln.strip() for ln in cv_text.splitlines() if ln.strip()), "")
    return {
        "headline": first_line[:300],
        "years_experience": _years_from_text(cv_text),
        "tags": {k: {"match": 1.0, "evidence": ev, "source": "keyword"} for k, ev in found.items()},
        "mode": "keyword",
    }


def extract_posting(title: str, description: str, examples: str = "", **kw) -> dict:
    """Tag a posting from its title + description. examples: labeled postings shown as references.
    kw: role/agent/run_id for llm routing."""
    kw.setdefault("role", "bulk")
    ref = (f"Reference examples (similar postings with confirmed tags; use them to calibrate, do not copy):\n{examples}\n\n"
           if examples else "")
    result = complete_json(JD_SYSTEM, f"Taxonomy:\n{taxonomy_for_prompt()}\n\n{ref}Title: {title}\n\n{description[:30000]}", **kw)
    if result and isinstance(result.get("tags"), list):
        reqs, _ = split_tags([t for t in result["tags"] if isinstance(t, str)])
        return {
            "tags": [t for t in reqs if t in TAGS],
            "years_required": result.get("years_required"),
            "level_band": result.get("level_band") or infer_level(title),
            "role_cluster": result.get("role_cluster") or "Other",
            "scope": result.get("scope") or "",
            "no_sponsorship": bool(result.get("no_sponsorship")),
            "mode": "llm",
        }
    text = f"{title}\n{description}"
    low = text.lower()
    return {
        "tags": sorted(keyword_tags(text)),
        "years_required": _years_from_text(description),
        "level_band": infer_level(title),
        "role_cluster": _guess_cluster(title),
        "scope": "global" if "global" in low else "",
        "no_sponsorship": bool(re.search(r"(not|unable to) (be able to )?sponsor", low)),
        "mode": "keyword",
    }


def _guess_cluster(title: str) -> str:
    t = title.lower()
    if "partner" in t or "alliance" in t or "business development" in t:
        return "Partnerships"
    if "ad sales" in t or "advertis" in t:
        return "Ad Sales"
    if "revenue" in t or "strategy" in t:
        return "Rev Strategy"
    if "growth" in t:
        return "Growth"
    if "general manager" in t:
        return "GM / Business Lead"
    if "sales" in t:
        return "Sales Leadership"
    return "Other"
