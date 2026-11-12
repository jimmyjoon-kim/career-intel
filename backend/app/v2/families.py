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

READY_AT = 10  # holders needed before a family gets a full scorecard (under 20 the page says so)
TARGET = 30
REFRESH = 5  # recent hires added per month to a group that is already full

# Titles that are never the role itself (assistants, chiefs of staff), whatever words they contain.
NOT_ROLE = r"executive business partner|business partner to|executive assistant|chief of staff|\bea to\b"
AD_CONTEXT = (r"\bads?\b|ad sales|advertis|media sales|monetiz|retail media|programmatic|\bagency\b|publisher sales|"
              r"brand partnerships|ad solutions|\bctv\b")
SALES_TITLE = r"\bsales\b|account director|revenue|commercial|go-to-market|\bgtm\b"
FAMILIES = [
    {"key": "Partnerships", "label": "Partnerships", "clusters": ["Partnerships"], "title": r"partner|alliance",
     "exclude": NOT_ROLE},
    # Ad sales needs advertising context: an ad title, or a sales/revenue title at an ad tech company.
    {"key": "Ad Sales", "label": "Ad sales / revenue", "clusters": ["Ad Sales"], "title": AD_CONTEXT,
     "sales_at_sector": ("adtech", "consumer", "media"), "exclude": NOT_ROLE,
     "collect_hint": "advertising sales leaders across all three sides, about a third each: demand side (advertiser, agency, "
                     "brand, UA / DSP sales), supply side (publisher, app monetization, SSP / mediation partnerships) and "
                     "unified (both); include retail media and CTV (not enterprise, cloud or semiconductor sales)"},
    {"key": "GM / Regional lead", "label": "GM / regional or country lead", "clusters": ["GM / Business Lead"],
     "title": r"general manager|country manager|regional manager|managing director|\bgm\b|head of [^,]*(apac|emea|asia|region|korea|japan)",
     "exclude": NOT_ROLE},
    # Sales leadership outside advertising (semiconductors, cloud, enterprise AI): assessed as its own role.
    {"key": "Enterprise / tech sales", "label": "Enterprise / tech sales", "clusters": ["Sales Leadership"],
     "title": SALES_TITLE, "not_title": AD_CONTEXT, "not_sector": ("adtech", "consumer", "media"), "exclude": NOT_ROLE,
     "collect_hint": "enterprise, cloud, semiconductor or AI-platform sales leaders (not advertising sales)"},
    {"key": "BD / Alliances", "label": "Business development / alliances", "clusters": [], "exclude": NOT_ROLE,
     "title": r"business development|alliances?|\bbd\b|strategic partnerships"},
    {"key": "Growth", "label": "Growth / strategy & operations", "clusters": ["Growth"], "exclude": NOT_ROLE,
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
    title = p.title or ""
    if fam.get("exclude") and re.search(fam["exclude"], title, re.I):
        return False
    sector = None
    if fam.get("sales_at_sector") or fam.get("not_sector"):
        from .industry import sector_of

        sector = sector_of(p.company)[0]
    if fam.get("not_title") and re.search(fam["not_title"], title, re.I):
        return False
    # consumer platforms and media earn from advertising: their sales roles are ad sales
    if fam.get("not_sector") and sector in fam["not_sector"]:
        return False
    if fam.get("sales_at_sector") and sector in fam["sales_at_sector"] and re.search(SALES_TITLE, title, re.I):
        return True
    return p.role_cluster in fam["clusters"] or bool(re.search(fam["title"], title, re.I))


def holders(db: Session, key: str) -> int:
    return db.scalar(select(func.count(ReferenceProfile.id)).where(ReferenceProfile.cluster == key)) or 0


def holders_full(db: Session, key: str) -> int:
    """Holders read with the full field set (major-company hires, school tier, degree field, industry path)."""
    return sum(1 for r in db.scalars(select(ReferenceProfile).where(ReferenceProfile.cluster == key))
               if (r.features or {}).get("rv") == 2)


def status(db: Session) -> list[dict]:
    posts = list(db.scalars(select(Posting).where(Posting.status.in_(("open", "unverified")))))
    reqs = {r.family.lower(): r for r in db.scalars(select(PoolRequest))}
    from ..models import Proposal

    waiting: dict[str, int] = {}
    for pr in db.scalars(select(Proposal).where(Proposal.kind == "holders", Proposal.status == "pending")):
        k = (pr.payload or {}).get("cluster", "").lower()
        waiting[k] = waiting.get(k, 0) + len((pr.payload or {}).get("rows", []))
    out = []
    changed = False
    # Every role is collected until it has TARGET holders read at hire (not merely READY_AT rows of any kind):
    # a missing request is created and a finished one is reopened. (Before 2026-11-13 a request closed for good once
    # any 10 rows existed, so collection stopped at 11-20 usable holders.)
    for f in all_families(db):
        k = f["key"].lower()
        if holders_full(db, f["key"]) + waiting.get(k, 0) >= TARGET:
            continue
        r = reqs.get(k)
        if r is None:
            r = PoolRequest(family=f["key"][:120], pattern="" if not f["custom"] else f["title"], user_id=None)
            db.add(r)
            reqs[k] = r
            changed = True
        elif r.status != "pending":
            r.status = "pending"
            changed = True
    if changed:
        db.commit()
        write_requests_file(db)
    for f in all_families(db):
        n = holders(db, f["key"])
        r = reqs.get(f["key"].lower())
        w = waiting.get(f["key"].lower(), 0)
        state = ("ready" if n >= READY_AT else "awaiting_approval" if w else
                 "requested" if r and r.status == "pending" else "provisional")
        out.append({"key": f["key"], "label": f["label"], "custom": f["custom"], "holders": n, "waiting": w,
                    "postings": sum(1 for p in posts if in_family(p, f)),
                    "state": state,
                    "requested_at": r.created_at if r else None})
    return out


def approve_waiting(db: Session, key: str) -> dict:
    """Approve every collected holder waiting for this family (each batch was screened on arrival: no personal fields,
    no holder without dated roles, no duplicates)."""
    from datetime import datetime as _dt

    from ..agents import inbox
    from ..models import Proposal

    props = [p for p in db.scalars(select(Proposal).where(Proposal.kind == "holders", Proposal.status == "pending"))
             if (p.payload or {}).get("cluster", "").lower() == key.lower()]
    added = 0
    for p in props:
        inbox.apply(db, p)
        p.status, p.decided_at = "approved", _dt.now(timezone.utc)
        added += len((p.payload or {}).get("rows", []))
    db.commit()
    return {"family": key, "proposals": len(props), "holders_added": added, "holders_now": holders(db, key)}


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


def refresh_ready(db: Session) -> list[str]:
    """Monthly: ask the Mac task for this month's recent hires in every family that already has a peer group, so all
    groups stay current and carry the full field set (not only Partnerships)."""
    out = []
    for f in status(db):
        if f["state"] == "ready":
            r = db.scalar(select(PoolRequest).where(func.lower(PoolRequest.family) == f["key"].lower()))
            if r is None:
                r = PoolRequest(family=f["key"], pattern="", user_id=None)
                db.add(r)
            r.status, r.created_at = "pending", datetime.now(timezone.utc)
            out.append(f["key"])
    db.commit()
    write_requests_file(db)
    return out


def _have(db: Session, key: str) -> int:
    """Holders counted toward a request: for a family that already has a group, this month's full-field reads."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = list(db.scalars(select(ReferenceProfile).where(ReferenceProfile.cluster == key)))
    full = [r for r in rows if (r.features or {}).get("rv") == 2]
    # Holders already collected and waiting for your approval count too, so the Mac task does not collect them again.
    from ..models import Proposal

    waiting = sum(len([x for x in (p.payload or {}).get("rows", []) if x.get("rv") == 2])
                  for p in db.scalars(select(Proposal).where(Proposal.kind == "holders", Proposal.status == "pending"))
                  if (p.payload or {}).get("cluster", "").lower() == key.lower())
    if len(full) >= TARGET:
        return sum(1 for r in full if r.as_of == month) + waiting
    return len(full) + waiting


def write_requests_file(db: Session) -> None:
    """The hire-research task on your Mac reads this file and collects holders for each pending family."""
    d = Path(get_settings().inbox_dir)
    if not d.exists():
        return
    pending = []
    for r in db.scalars(select(PoolRequest).where(PoolRequest.status == "pending")):
        f = family(db, r.family)
        full = holders_full(db, r.family)
        # a full group is only topped up: REFRESH recent hires a month, not another TARGET
        pending.append({"family": r.family, "have": _have(db, r.family), "target": TARGET if full < TARGET else REFRESH,
                        "title_keywords": f.get("collect_hint") or f["title"], "requested_at": r.created_at.isoformat() if r.created_at else ""})
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
