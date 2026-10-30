"""Focus plan: what your score means in plain words, where you lead or trail the people who hold these roles,
and a ranked list of actions with their measured effect (score points, postings that become strong matches).
Every number comes from the scorecard, the posting matches or a rescore; nothing is estimated by a model."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from ..scoring import score as score_posting
from ..taxonomy import TAGS

STRONG = 0.8  # requirement match at which a posting counts as a strong match


def _ord(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def standing(card: dict) -> dict:
    """Plain-language reading of the score."""
    sc = [s for s in card["holders"]["scores"] if s is not None]
    you = card["base_score"]
    above = sum(1 for s in sc if s > you)
    rank, n = above + 1, len(sc) + 1
    med = card["holders"]["median"]
    lines = [
        f"Your score is {you} out of 100. It is the weighted average of where you rank among {len(sc)} people who "
        f"hold {card['cluster']} roles on {len(card['factors'])} factors; 50 means the median holder on every factor.",
        f"You rank {_ord(rank)} of {n} (you plus {len(sc)} holders). The median holder scores {med}; the highest holder scores {max(sc)}.",
    ]
    lo, hi = card["position_ci95"]
    if lo is not None:
        lines.append(f"Because the holder group is small, your position could reasonably sit anywhere between the "
                     f"{_ord(round(lo))} and {_ord(round(hi))} percentile.")
    lines.append("The score compares you with people already in these roles. It does not predict hiring decisions.")
    return {"score": you, "rank": rank, "of": n, "median": med, "top": max(sc), "lines": lines}


def versus_peers(card: dict) -> list[dict]:
    """Each factor: your percentile against the median holder's, and what that difference is worth in score points."""
    out = []
    tw = sum(f["weight"] or 0 for f in card["factors"] if f["you_pct"] is not None) or 1
    for f in card["factors"]:
        if f["you_pct"] is None or f["holder_median_pct"] is None:
            continue
        diff = f["you_pct"] - f["holder_median_pct"]
        pts = round((f["weight"] or 0) * diff / tw, 1)
        state = "lead" if pts >= 0.5 else "gap" if pts <= -0.5 else "level"
        out.append({"factor": f["factor"], "label": f["label"], "you_pct": f["you_pct"], "median_pct": f["holder_median_pct"],
                    "weight": f["weight"], "points": pts, "state": state,
                    "share_above_you": f["share_above_you"],
                    "plain": (f"{abs(pts)} points ahead of the median holder" if state == "lead" else
                              f"{abs(pts)} points behind the median holder" if state == "gap" else "level with the median holder")})
    return sorted(out, key=lambda x: x["points"])


def _strong_count(rows: list[dict], prof_view, stats) -> int:
    return sum(1 for r in rows if score_posting(r["pv"], prof_view, stats)["rank_score"] >= STRONG)


def posting_moves(ev: dict, prof_view, rows_pv: list[dict], limit: int = 8) -> list[dict]:
    """Requirements that open postings ask for and you do not fully show: how many postings each would turn into
    strong matches if evidenced (rescored, not estimated)."""
    stats = ev["stats"]
    base = _strong_count(rows_pv, prof_view, stats)
    c: Counter = Counter()
    for r in rows_pv:
        for t in r["pv"].tags:
            if t in TAGS and prof_view.matches.get(t, 0) < 1:
                c[t] += 1
    out = []
    for tag, asked in c.most_common(20):
        alt = replace(prof_view, matches={**prof_view.matches, tag: 1.0})
        gain = _strong_count(rows_pv, alt, stats) - base
        t = TAGS[tag]
        out.append({"tag": tag, "label": t.label, "asked_by": asked, "strong_matches_gained": gain,
                    "have": prof_view.matches.get(tag, 0), "closable": t.closable, "how": t.close_hint})
    out.sort(key=lambda x: (-x["strong_matches_gained"], -x["asked_by"]))
    return out[:limit], base


def build(card: dict, ev: dict, prof_view, gap_plan: list[dict], evidence_pending: list[dict],
          months_left: int | None, target_date: str) -> dict:
    from ..services import posting_view

    considered = ev["passing"] + ev.get("adjacent", [])
    rows_pv = [{"pv": posting_view(r["posting"]), "row": r} for r in considered]
    moves, strong_now = posting_moves(ev, prof_view, rows_pv)

    actions = []
    # 1. Quick wins: facts you already have that the app has not recorded.
    for e in evidence_pending[:5]:
        mv = next((m for m in moves if m["tag"] == e["tag"]), None)
        actions.append({"kind": "quick", "title": f"Confirm: {e['label']}",
                        "why": f'Your own text says: "{e["quote"][:160]}"', "where": "Profile → Evidence from your documents",
                        "effect": (f"+{mv['strong_matches_gained']} strong posting matches" if mv and mv["strong_matches_gained"] else
                                   f"asked for by {e['postings']} postings"), "months": 0, "by_target": True})
    if not target_date:
        actions.append({"kind": "quick", "title": "Set your target date",
                        "why": "Without it, degrees in progress and time-bound gaps cannot be checked against your move date.",
                        "where": "Profile → Experience", "effect": "shows what is closable in time", "months": 0, "by_target": True})
    # 2. Requirements postings ask for (biggest effect on matches first).
    for m in moves:
        if m["strong_matches_gained"] <= 0:
            continue
        if any(a["title"].endswith(m["label"]) for a in actions):
            continue
        actions.append({"kind": "requirement" if m["closable"] else "evidence",
                        "title": f"{'Build' if m['closable'] else 'Show evidence'}: {m['label']}",
                        "why": f"Asked for by {m['asked_by']} of the {len(considered)} postings you are shown"
                               + (" (partly evidenced now)" if m["have"] else ""),
                        "where": m["how"] if m["closable"] and m["how"] else
                                 ("If you have done this, state it on Profile (requirements) or Role review. "
                                  "If you have not, it is not something current work closes before your move."),
                        "effect": f"+{m['strong_matches_gained']} strong posting matches (from {strong_now})",
                        "months": 6 if m["closable"] else None, "by_target": (months_left is None or months_left >= 6) if m["closable"] else False})
    # 3. Score factors (what-ifs from the scorecard and the gap plan).
    seen = set()
    for g in gap_plan:
        if g.get("factor") and g.get("score_effect") and g["factor"] not in seen and g["score_effect"] > 0:
            seen.add(g["factor"])
            actions.append({"kind": "score" if g["kind"] != "structural" else "structural", "title": f"Raise: {g['gap']}",
                            "why": g["evidence"], "where": g["action"],
                            "effect": f"+{g['score_effect']} score points", "months": g["months"], "by_target": g["by_target"]})
    for w in card["benchmark"]["whatifs"]:
        if w.get("scheduled") and w["delta"] > 0:
            actions.append({"kind": "scheduled", "title": w["change"], "why": "Already under way; counts automatically on completion.",
                            "where": "Nothing to do", "effect": f"+{w['delta']} score points (to {w['score']})",
                            "months": None, "by_target": True})
    order = {"quick": 0, "scheduled": 1, "evidence": 2, "requirement": 3, "score": 4, "structural": 5}
    actions.sort(key=lambda a: (order[a["kind"]], a["by_target"] is False))

    # Your edge: factor leads and rare strengths, with the open postings where they count.
    edge = []
    for f in [x for x in versus_peers(card) if x["state"] == "lead"][::-1][:4]:
        edge.append({"label": f["label"], "detail": f["plain"], "postings": []})
    for s in card.get("rare_strengths", [])[:4]:
        hits = [r["row"]["posting"] for r in rows_pv if s["tag"] in r["pv"].tags][:3]
        edge.append({"label": s["label"], "detail": f"held by {round(100 * s['holder_share'])}% of role holders; you have it",
                     "postings": [f"{p.company} — {p.title}" for p in hits]})
    return {"standing": standing(card), "versus_peers": versus_peers(card), "actions": actions[:12],
            "edge": edge, "strong_matches_now": strong_now, "postings_considered": len(considered),
            "method": ["Score points: the score is rerun with that one change; everything else stays as read.",
                       "Strong posting matches: postings whose requirements you would match at 80% or more, rescored with the requirement added.",
                       "Postings considered: those passing your screen plus those missing only a stated preference."]}
