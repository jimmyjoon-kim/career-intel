"""Gate -> discrimination-weighted scoring.

1. Gate (pass/fail, never a number): level, excluded title terms, location/remote,
   work authorisation, posting status.
2. Market stats per role cluster: tag frequency -> COMMON MINIMUM (>=70%, weight 0 but a
   threshold), MID (30-70%, weight 1), DISCRIMINATOR (<30%, weight 3). Clusters with fewer
   than MIN_CLUSTER_N postings are merged into the nearest larger cluster by tag overlap.
3. Score = sum(weight * match) / sum(weight) over the posting's MID and DISCRIMINATOR tags.
   Hard gaps = COMMON MINIMUM tags the candidate scores below 1. Ranking: postings with a
   hard gap scored 0 rank below all others; each hard gap scored 0.5 subtracts 0.10.
No probabilities or hire likelihoods are produced anywhere.
"""

import math
from collections import Counter
from dataclasses import dataclass, field

from .taxonomy import LEVEL_RANK, TAGS

COMMON_MIN_PCT = 70
MID_PCT = 30
WEIGHTS = {"COMMON MINIMUM": 0, "MID": 1, "DISCRIMINATOR": 3}
MIN_CLUSTER_N = 8
HARD_GAP_PARTIAL_PENALTY = 0.10


@dataclass
class PostingView:
    id: int
    company: str
    title: str
    level_band: str
    role_cluster: str
    location: str
    remote_flag: str
    bay_area: bool
    no_sponsorship: bool
    status: str
    tags: list[str]
    years_required: int | None = None


@dataclass
class ProfileView:
    min_level: str = "Director"
    locations: list[str] = field(default_factory=lambda: ["SF Bay Area"])
    remote_ok: bool = True
    needs_sponsorship: bool = False
    excluded_title_terms: list[str] = field(default_factory=list)
    years_experience: int | None = None
    matches: dict[str, float] = field(default_factory=dict)  # tag -> 0 | 0.5 | 1


def classify(pct: float) -> str:
    if pct >= COMMON_MIN_PCT:
        return "COMMON MINIMUM"
    if pct >= MID_PCT:
        return "MID"
    return "DISCRIMINATOR"


def _tag_table(postings: list[PostingView]) -> dict:
    n = len(postings)
    counts = Counter(t for p in postings for t in set(p.tags))
    table = {}
    for tag, c in counts.items():
        pct = round(100 * c / n) if n else 0
        cls = classify(pct)
        table[tag] = {"count": c, "n": n, "pct": pct, "cls": cls, "weight": WEIGHTS[cls]}
    return table


def _cosine(a: Counter, b: Counter) -> float:
    dot = sum(a[k] * b.get(k, 0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def market_stats(postings: list[PostingView]) -> dict:
    """Per-cluster requirement statistics over open postings.

    Returns {"clusters": {name: {n, tags, merged_from}}, "assignment": {raw_cluster: effective},
    "all": {n, tags}}.
    """
    open_p = [p for p in postings if p.status == "open"]
    by_cluster: dict[str, list[PostingView]] = {}
    for p in open_p:
        by_cluster.setdefault(p.role_cluster or "Other", []).append(p)

    large = {c for c, ps in by_cluster.items() if len(ps) >= MIN_CLUSTER_N}
    profiles = {c: Counter(t for p in ps for t in p.tags) for c, ps in by_cluster.items()}
    assignment: dict[str, str] = {}
    for c in by_cluster:
        if c in large:
            assignment[c] = c
        elif large:
            assignment[c] = max(large, key=lambda L: _cosine(profiles[c], profiles[L]))
        else:
            assignment[c] = "ALL"

    merged: dict[str, list[PostingView]] = {}
    merged_from: dict[str, list[str]] = {}
    for c, ps in by_cluster.items():
        target = assignment[c]
        merged.setdefault(target, []).extend(ps)
        if target != c:
            merged_from.setdefault(target, []).append(c)

    clusters = {
        name: {"n": len(ps), "tags": _tag_table(ps), "merged_from": sorted(merged_from.get(name, []))}
        for name, ps in merged.items()
    }
    return {"clusters": clusters, "assignment": assignment, "all": {"n": len(open_p), "tags": _tag_table(open_p)}}


def _location_ok(p: PostingView, prof: ProfileView) -> bool:
    if prof.remote_ok and p.remote_flag == "yes":
        return True
    loc = p.location.lower()
    for want in prof.locations:
        w = want.lower().strip()
        if not w:
            continue
        if w in ("sf bay area", "bay area") and p.bay_area:
            return True
        if w in loc:
            return True
        city = w.split(",")[0].strip()  # "Seoul, South Korea" matches a posting located in "Seoul"
        if len(city) >= 4 and city in loc:
            return True
        if w in ("remote", "remote us") and "remote" in loc and prof.remote_ok:
            return True
    return False


def gate(p: PostingView, prof: ProfileView) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if p.status != "open":
        reasons.append(f"posting status: {p.status}")
    if LEVEL_RANK.get(p.level_band, 0) < LEVEL_RANK.get(prof.min_level, LEVEL_RANK["Director"]):
        reasons.append(f"level {p.level_band or 'unknown'} below {prof.min_level}")
    title = p.title.lower()
    for term in prof.excluded_title_terms:
        if term.strip() and term.lower().strip() in title:
            reasons.append(f"title contains excluded term '{term}'")
    if not _location_ok(p, prof):
        reasons.append("location outside preferences and not remote-eligible")
    if prof.needs_sponsorship and p.no_sponsorship:
        reasons.append("no visa sponsorship and candidate needs sponsorship")
    return (not reasons, reasons)


def score(p: PostingView, prof: ProfileView, stats: dict) -> dict:
    cluster = stats["assignment"].get(p.role_cluster or "Other", "ALL")
    table = stats["clusters"].get(cluster, stats["all"])["tags"] if cluster != "ALL" else stats["all"]["tags"]

    num = den = 0.0
    gaps, hard_gaps = [], []
    for tag in p.tags:
        info = table.get(tag) or {"cls": "DISCRIMINATOR", "weight": 3, "pct": 0}
        m = float(prof.matches.get(tag, 0.0))
        t = TAGS.get(tag)
        entry = {
            "tag": tag,
            "label": t.label if t else tag,
            "cls": info["cls"],
            "pct": info.get("pct", 0),
            "match": m,
            "closable": bool(t and t.closable),
            "close_hint": t.close_hint if t else "",
        }
        if info["cls"] == "COMMON MINIMUM":
            if m < 1:
                hard_gaps.append(entry)
        else:
            num += info["weight"] * m
            den += info["weight"]
            if m < 1:
                gaps.append(entry)

    if p.years_required and prof.years_experience is not None and prof.years_experience < p.years_required:
        hard_gaps.append({
            "tag": "years_required", "label": f"{p.years_required}+ years experience", "cls": "COMMON MINIMUM",
            "pct": 100, "match": 0.5, "closable": False, "close_hint": "",
        })

    weighted = round(num / den, 3) if den else 1.0
    zero_hard = any(g["match"] == 0 for g in hard_gaps)
    partial_hard = sum(1 for g in hard_gaps if g["match"] == 0.5)
    rank_score = round(max(0.0, weighted - HARD_GAP_PARTIAL_PENALTY * partial_hard), 3)
    gaps.sort(key=lambda g: (-WEIGHTS[g["cls"]], g["match"]))
    return {
        "cluster": cluster,
        "weighted_score": weighted,
        "rank_score": rank_score,
        "has_zero_hard_gap": zero_hard,
        "hard_gaps": hard_gaps,
        "gaps": gaps,
    }


def rank_key(result: dict) -> tuple:
    return (result["has_zero_hard_gap"], -result["rank_score"])


def gap_summary(results: list[dict], top_n: int = 10) -> list[dict]:
    """Aggregate gaps across gate-passing postings, weighted by how often and how heavily they count."""
    agg: dict[str, dict] = {}
    for r in results:
        for g in r["hard_gaps"]:
            a = agg.setdefault(g["tag"], {**g, "postings": 0, "impact": 0.0, "hard": True})
            a["postings"] += 1
            a["impact"] += 5 * (1 - g["match"])
        for g in r["gaps"]:
            a = agg.setdefault(g["tag"], {**g, "postings": 0, "impact": 0.0, "hard": False})
            a["postings"] += 1
            a["impact"] += WEIGHTS[g["cls"]] * (1 - g["match"])
    out = sorted(agg.values(), key=lambda a: -a["impact"])
    for a in out:
        a["impact"] = round(a["impact"], 1)
    return out[:top_n]
