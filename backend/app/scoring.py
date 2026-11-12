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

import re
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
    scope: str = ""


@dataclass
class ProfileView:
    min_level: str = "Director"
    locations: list[str] = field(default_factory=list)
    remote_ok: bool = True
    needs_sponsorship: bool = False
    excluded_title_terms: list[str] = field(default_factory=list)
    work_auth: dict[str, str] = field(default_factory=dict)  # market -> "authorized" | "needs_sponsorship"
    exclude_country_scope: bool = False
    target_roles: list[str] = field(default_factory=list)
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


REGION_WORDS = {"us": "US", "usa": "US", "united states": "US", "north america": "US", "americas": "US",
                "apac": "APAC", "asia": "APAC", "asia pacific": "APAC", "asia-pacific": "APAC",
                "emea": "EMEA", "europe": "EMEA", "middle east": "EMEA", "latam": "LATAM", "latin america": "LATAM"}


def _location_ok(p: PostingView, prof: ProfileView) -> bool:
    if prof.remote_ok and p.remote_flag == "yes":
        return True
    if not [w for w in prof.locations if w.strip()]:
        return True  # no location preference: every location passes
    loc = p.location.lower()
    from .v2.market import regions

    for want in prof.locations:
        w = want.lower().strip()
        if not w:
            continue
        if w in REGION_WORDS and REGION_WORDS[w] in regions(p.location):  # a region you named ("APAC", "Europe")
            return True
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


ROLE_STOP = {"head", "director", "senior", "vice", "president", "lead", "manager", "the", "and", "for"}


def gate_split(p: PostingView, prof: ProfileView) -> tuple[list[str], list[str]]:
    """(hard, soft). Hard rules end the match: closed posting, sponsorship you need but it rules out, words you excluded.
    Soft rules are your stated preferences: level, location, single-country scope, function, unconfirmed listing.
    Postings that miss only soft rules are still scored and shown as 'worth a look' with the reason."""
    from .agents.sourcing import EXCLUDE, NON_COMMERCIAL

    hard: list[str] = []
    soft: list[str] = []
    if p.status in ("closed", "stale"):
        hard.append(f"posting status: {p.status}")
    elif p.status != "open":
        soft.append("not yet confirmed on the employer's job board")
    needs = prof.needs_sponsorship
    if getattr(prof, "work_auth", None):  # authorization by market, when you gave it
        from .v2.market import posting_market

        mk = posting_market(p.title, p.location).get("market")
        if mk in prof.work_auth:
            needs = prof.work_auth[mk] == "needs_sponsorship"
    if needs and p.no_sponsorship:
        hard.append("no visa sponsorship and candidate needs sponsorship")
    title = p.title.lower()
    for term in prof.excluded_title_terms:
        if term.strip() and term.lower().strip() in title:
            hard.append(f"title contains excluded term '{term}'")
    words = [[w for w in re.findall(r"[a-z]{3,}", r.lower()) if w not in ROLE_STOP] for r in getattr(prof, "target_roles", [])]
    in_target = any(ws and all(w in title for w in ws) for ws in words)
    if NON_COMMERCIAL.search(p.title or "") and not in_target:
        soft.append("outside your target functions" if getattr(prof, "target_roles", None)
                    else "not a commercial role (finance, legal, engineering or similar)")
    # Your own stated limits are strict: a posting below your lowest accepted level, or single-country when you asked
    # to leave those out, is screened out (not shown under "worth a look"). An unread level stays a soft flag.
    if p.level_band and LEVEL_RANK.get(p.level_band, 0) < LEVEL_RANK.get(prof.min_level, LEVEL_RANK["Director"]):
        hard.append(f"level {p.level_band} below your minimum ({prof.min_level})")
    elif not p.level_band:
        soft.append("level not read")
    if getattr(prof, "exclude_country_scope", False) and ((p.scope or "").lower() == "country" or EXCLUDE.search(p.title or "")):
        hard.append("single-country scope or Country Manager title")
    if not _location_ok(p, prof):
        soft.append("location outside your locations and not remote")
    return hard, soft


def gate(p: PostingView, prof: ProfileView) -> tuple[bool, list[str]]:
    hard, soft = gate_split(p, prof)
    return (not (hard or soft), hard + soft)


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

    # Few requirements read say little: the fit is pulled toward 50% by a prior worth one discriminator requirement.
    # A posting with nothing read gets no fit at all (shown as "requirements not read"), never 100%.
    if den:
        weighted = round((num + FIT_PRIOR_W * 0.5) / (den + FIT_PRIOR_W), 3)
    elif p.tags:  # only common minimums read: fit = minimums met, pulled toward 50% the same way
        cm = [float(prof.matches.get(t, 0.0)) for t in p.tags]
        weighted = round((sum(cm) + FIT_PRIOR_W * 0.5) / (len(cm) + FIT_PRIOR_W), 3)
    else:
        weighted = 0.0
    zero_hard = any(g["match"] == 0 for g in hard_gaps)
    # continuous: a minimum met at m (0 < m < 1) costs 2 x penalty x (1 - m), so 0.5 costs the full penalty as before
    partial_hard = sum(2 * (1 - g["match"]) for g in hard_gaps if 0 < g["match"] < 1)
    rank_score = round(max(0.0, weighted - HARD_GAP_PARTIAL_PENALTY * partial_hard), 3)
    gaps.sort(key=lambda g: (-WEIGHTS[g["cls"]], g["match"]))
    return {
        "cluster": cluster,
        "weighted_score": weighted,
        "rank_score": rank_score,
        "requirements_read": len(p.tags),
        "not_read": not p.tags,
        "has_zero_hard_gap": zero_hard,
        "hard_gaps": hard_gaps,
        "gaps": gaps,
        "tags": list(p.tags),
    }


FIT_PRIOR_W = 3.0


def rank_key(result: dict) -> tuple:
    """Postings without hard gaps first, then by match; ties go to the posting with more tagged requirements,
    since a full match on two requirements says less than a full match on ten."""
    return (bool(result.get("not_read")), result["has_zero_hard_gap"], -result["rank_score"], -len(result.get("tags") or []))


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
