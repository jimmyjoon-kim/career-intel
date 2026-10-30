"""Role families: the comparison group you are scored against. Each family has its own holder pool; until a pool has
enough holders, the family shows a provisional assessment built from its open postings and a pool request is queued
for the hire-research task on your Mac. Any role you name can become a family."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import PoolRequest, Posting, ReferenceProfile
from ..taxonomy import TAGS

READY_AT = 20  # holders needed before a family gets a full scorecard
TARGET = 30

FAMILIES = [
    {"key": "Partnerships", "label": "Partnerships", "clusters": ["Partnerships"], "title": r"partner|alliance"},
    {"key": "Ad Sales", "label": "Ad sales / revenue", "clusters": ["Ad Sales", "Sales Leadership", "Rev Strategy"],
     "title": r"\bsales\b|revenue|account director|monetiz|advertis"},
    {"key": "GM / Regional lead", "label": "GM / regional or country lead", "clusters": ["GM / Business Lead"],
     "title": r"general manager|country manager|regional manager|managing director|\bgm\b|head of [^,]*(apac|emea|asia|region|korea|japan)"},
    {"key": "BD / Alliances", "label": "Business development / alliances", "clusters": [],
     "title": r"business development|alliances?|\bbd\b|strategic partnerships"},
    {"key": "Growth", "label": "Growth / strategy & operations", "clusters": ["Growth"],
     "title": r"\bgrowth\b|strategy (?:&|and) operations|biz ?ops"},
]


def _custom_pattern(name: str) -> str:
    words = [w for w in re.findall(r"[a-z][a-z&/]+", name.lower()) if w not in {"of", "the", "and", "head", "director", "vp", "senior", "sr"}]
    return "|".join(re.escape(w) for w in words) or re.escape(name.lower())


def all_families(db: Session) -> list[dict]:
    out = [dict(f, custom=False) for f in FAMILIES]
    known = {f["key"].lower() for f in out}
    for r in db.scalars(select(PoolRequest).order_by(PoolRequest.id)):
        if r.family.lower() not in known:
            out.append({"key": r.family, "label": r.family, "clusters": [], "title": r.pattern or _custom_pattern(r.family), "custom": True})
            known.add(r.family.lower())
    return out


def family(db: Session, key: str | None) -> dict:
    key = key or "Partnerships"
    return next((f for f in all_families(db) if f["key"].lower() == key.lower()), dict(FAMILIES[0], custom=False))


def in_family(p: Posting, fam: dict) -> bool:
    return p.role_cluster in fam["clusters"] or bool(re.search(fam["title"], p.title or "", re.I))


def holders(db: Session, key: str) -> int:
    return db.scalar(select(func.count(ReferenceProfile.id)).where(ReferenceProfile.cluster == key)) or 0


def status(db: Session) -> list[dict]:
    posts = list(db.scalars(select(Posting).where(Posting.status.in_(("open", "unverified")))))
    reqs = {r.family.lower(): r for r in db.scalars(select(PoolRequest))}
    out = []
    for f in all_families(db):
        n = holders(db, f["key"])
        r = reqs.get(f["key"].lower())
        out.append({"key": f["key"], "label": f["label"], "custom": f["custom"], "holders": n,
                    "postings": sum(1 for p in posts if in_family(p, f)),
                    "state": "ready" if n >= READY_AT else ("requested" if r and r.status == "pending" else "provisional"),
                    "requested_at": r.created_at if r else None})
    return out


def request_pool(db: Session, key: str, user_id: int | None, pattern: str = "") -> PoolRequest:
    r = db.scalar(select(PoolRequest).where(func.lower(PoolRequest.family) == key.lower()))
    if r is None:
        r = PoolRequest(family=key.strip()[:120], pattern=pattern or "", user_id=user_id)
        db.add(r)
    if r.status != "pending":  # a repeat press keeps the request's place in the queue
        r.status, r.created_at = "pending", datetime.now(timezone.utc)
    db.commit()
    write_requests_file(db)
    return r


def write_requests_file(db: Session) -> None:
    """The hire-research task on your Mac reads this file and collects holders for each pending family."""
    d = Path(get_settings().inbox_dir)
    if not d.exists():
        return
    pending = []
    for r in db.scalars(select(PoolRequest).where(PoolRequest.status == "pending")):
        f = family(db, r.family)
        pending.append({"family": r.family, "have": holders(db, r.family), "target": TARGET,
                        "title_keywords": f["title"], "requested_at": r.created_at.isoformat() if r.created_at else ""})
    (d / "requests.json").write_text(json.dumps({"pending": pending}, indent=1))


def provisional(db: Session, ev: dict, prof_view, fam: dict) -> dict:
    """Assessment from the family's open postings: what they require, your match on each, and your best postings."""
    rows = [r for r in ev["rows"] if in_family(r["posting"], fam) and r["posting"].status in ("open", "unverified")]
    n = len(rows)
    req = db.scalar(select(PoolRequest).where(func.lower(PoolRequest.family) == fam["key"].lower()))
    queue = [x.family for x in db.scalars(select(PoolRequest).where(PoolRequest.status == "pending").order_by(PoolRequest.created_at))]
    request = ({"status": req.status, "requested_at": req.created_at.isoformat() if req.created_at else "",
                "position": queue.index(req.family) + 1 if req.family in queue else None, "queue": len(queue)} if req else None)
    if not n:
        return {"family": fam["key"], "postings": 0, "requirements": [], "fit": None, "top_postings": [], "gaps": [], "request": request}
    from collections import Counter

    cnt = Counter(t for r in rows for t in set(r["posting"].tags or []) if t in TAGS)
    reqs, num, den = [], 0.0, 0.0
    for t, c in cnt.most_common():
        share = c / n
        m = float(prof_view.matches.get(t, 0))
        reqs.append({"tag": t, "label": TAGS[t].label, "share": round(share, 2), "match": m, "closable": TAGS[t].closable})
        if share >= 0.3:
            num += share * m
            den += share
    top = sorted(rows, key=lambda r: (not r["gate_pass"], bool(r["hard_reasons"]), -r["rank_score"]))[:8]
    return {
        "family": fam["key"], "request": request, "postings": n, "fit": round(100 * num / den, 1) if den else None,
        "requirements": reqs[:15],
        "gaps": [x for x in reqs if x["share"] >= 0.3 and x["match"] < 1][:6],
        "top_postings": [{"id": r["posting"].id, "company": r["posting"].company, "title": r["posting"].title,
                          "location": r["posting"].location, "url": r["posting"].url, "match": round(100 * r["rank_score"]),
                          "passes": r["gate_pass"], "outside": r.get("soft_reasons", [])} for r in top],
        "note": f"Provisional: based on {n} open postings for this role. No group of current role holders yet, so there is "
                f"no percentile score; fit is your match on requirements that at least 30% of these postings ask for.",
    }
