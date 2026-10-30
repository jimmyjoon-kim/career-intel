"""Hire research inbox. The monthly task on your Mac reads recent hires' profiles (read-only) and drops a JSON file
here. This step derives factor values only, discards the raw text, and files a proposal for your approval.
Nothing enters the reference pool until you approve it."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Proposal, ReferenceProfile
from ..v2.reader import extract_features, parse_education, parse_linkedin
from ..v2.signals import combine

FORBIDDEN = {"name", "full_name", "first_name", "last_name", "linkedin_url", "profile_url", "url", "photo", "image", "email"}
AI_DEG = re.compile(r"artificial intelligence|machine learning|\bAI\b", re.I)


def derive(h: dict, now: tuple[int, int]) -> dict:
    f = extract_features(parse_linkedin(h.get("experience_text", ""), now), destination_company=h.get("company"),
                         use_cv_lines=True, now=now)
    ed = parse_education("Education: " + h.get("education_text", "").replace("\n", "; "), now) if h.get("education_text") else \
        {"ED": None, "technical": False, "degrees": []}
    ai_deg = 1.0 if any(AI_DEG.search(d["text"]) and not d["in_progress"] for d in ed["degrees"]) else 0.0
    combine(f, tech_degree=bool(ed["technical"]), ai_degree=ai_deg, now=now)
    row = {"company": h.get("company", "")[:200], "title": h.get("title", "")[:300],
           **{k: f.get(k) for k in ("YOE", "YOE_raw", "CT", "CT_tier_only", "tier", "LV", "LV_max", "FN", "DM", "AC", "AI", "TK")},
           "journey": bool(f.get("journey")), "ED": ed["ED"], "technical": bool(ed["technical"]),
           "mba": any(d.get("mba") and not d["in_progress"] for d in ed["degrees"]), "tags": f["tags"]}
    return row


def process_file(db: Session, path: Path, run_id: int | None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    kind = data.get("kind", "holders")
    if kind == "holders":
        holders = data.get("holders", [])
        bad = sorted({k for h in holders for k in h if k.lower() in FORBIDDEN})
        if bad:
            result = {"file": path.name, "rejected": f"file carries personal fields {bad}; not processed and deleted"}
            return _finish(db, path, result)
        ym = data.get("as_of") or date.today().strftime("%Y-%m")
        now = (int(ym[:4]), int(ym[5:7]))
        rows, skipped = [], 0
        have = {(r.company.lower(), r.title.lower()) for r in db.scalars(select(ReferenceProfile))}
        for h in holders:
            if not (h.get("experience_text") and h.get("company") and h.get("title")):
                skipped += 1
                continue
            if (h["company"].lower(), h["title"].lower()) in have:
                skipped += 1
                continue
            row = derive(h, now)
            if not row.get("YOE"):  # no dated roles could be read (e.g. a short press bio): not usable as a peer
                skipped += 1
                continue
            row["source_type"] = h.get("source_type", "linkedin")
            rows.append(row)
        if rows:
            db.add(Proposal(run_id=run_id, kind="holders", title=f"Add {len(rows)} role holders to {data.get('cluster', 'Partnerships')}",
                            detail=f"Read {ym} from {data.get('source', 'monthly hire research')}. Derived values only; raw text discarded. "
                                   f"{skipped} skipped (duplicate or incomplete). Approving changes everyone's percentiles.",
                            payload={"cluster": data.get("cluster", "Partnerships"), "as_of": ym,
                                     "source": data.get("source", "monthly hire research"), "rows": rows}))
        result = {"file": path.name, "proposed": len(rows), "skipped": skipped}
    elif kind == "self_profile":
        result = _self_profile(db, data, path.name)
    elif kind == "company_events":
        ev = [e for e in data.get("events", []) if e.get("company") and e.get("event") and e.get("date")]
        if ev:
            db.add(Proposal(run_id=run_id, kind="company_events", title=f"{len(ev)} company events from hire research",
                            detail="Dated IPO / acquisition events with sources. Applied to scoring only in a model release.",
                            payload={"events": ev}))
        result = {"file": path.name, "proposed": len(ev)}
    else:
        result = {"file": path.name, "rejected": f"unknown kind {kind}"}
    return _finish(db, path, result)


def _self_profile(db: Session, data: dict, name: str) -> dict:
    """Your own LinkedIn profile, read by the Mac task from the link you saved. Held for your review on Profile."""
    from ..models import Profile

    prof = db.scalar(select(Profile).where(Profile.user_id == int(data.get("user_id") or 0)))
    exp = (data.get("experience_text") or "").strip()
    if prof is None or not exp:
        return {"file": name, "rejected": "no matching profile or no experience text"}
    roles = parse_linkedin(exp)
    prof.linkedin_import = {"experience_text": exp[:60000], "education_text": (data.get("education_text") or "")[:5000],
                            "headline": (data.get("headline") or "")[:300], "roles": len(roles), "source": "link",
                            "read_at": data.get("read_at") or date.today().isoformat(), "status": "ready"}
    write_profile_requests(db)
    return {"file": name, "self_profile": prof.user_id, "roles": len(roles)}


def write_profile_requests(db: Session) -> None:
    """Profile links waiting to be read by the hire-research task on your Mac."""
    from ..models import Profile

    d = Path(get_settings().inbox_dir)
    if not d.exists():
        return
    pending = [{"user_id": p.user_id, "url": p.linkedin_url, "requested_at": (p.linkedin_import or {}).get("requested_at", "")}
               for p in db.scalars(select(Profile).where(Profile.linkedin_url != ""))
               if (p.linkedin_import or {}).get("status") == "requested"]
    (d / "profile_requests.json").write_text(json.dumps({"pending": pending}, indent=1))


def _finish(db: Session, path: Path, result: dict) -> dict:
    db.commit()
    path.unlink()  # raw text is never kept
    (path.parent / "processed").mkdir(exist_ok=True)
    (path.parent / "processed" / f"{path.stem}.receipt.json").write_text(json.dumps(result))
    return result


def run(db: Session, run_id: int | None) -> dict:
    d = Path(get_settings().inbox_dir)
    if not d.exists():
        return {"files": 0, "note": f"inbox folder {d} not found"}
    # Only research output; the request files the Mac task reads (requests.json, profile_requests.json) stay.
    files = [f for f in sorted(d.glob("*.json")) if not f.name.endswith("requests.json")]
    results = [process_file(db, f, run_id) for f in files]
    return {"files": len(results), "results": results}


def apply(db: Session, prop: Proposal) -> str:
    """Called when you approve a proposal."""
    if prop.kind == "holders":
        p = prop.payload
        for r in p["rows"]:
            feats = {k: r.get(k) for k in ("YOE", "YOE_raw", "CT", "tier", "LV", "LV_max", "FN", "DM", "AC", "ED", "mba",
                                           "technical", "AI", "TK", "CT_tier_only")}
            feats["tags"] = r["tags"]
            db.add(ReferenceProfile(cluster=p["cluster"], company=r["company"], title=r["title"], features=feats,
                                    source=p["source"], as_of=p["as_of"]))
        db.flush()
        from ..models import PoolRequest
        from ..v2 import families

        req = db.scalar(select(PoolRequest).where(PoolRequest.family == p["cluster"]))
        if req and families.holders(db, p["cluster"]) >= families.READY_AT:
            req.status = "ready"
        families.write_requests_file(db)
        db.flush()
        from ..models import PoolRequest
        from ..v2 import families

        req = db.scalar(select(PoolRequest).where(PoolRequest.family == p["cluster"]))
        if req and families.holders(db, p["cluster"]) >= families.READY_AT:
            req.status = "ready"
        families.write_requests_file(db)
        return f'{len(p["rows"])} holders added to {p["cluster"]}'
    return "recorded; takes effect in the next model release"
