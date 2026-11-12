"""Hire research inbox. The monthly task on your Mac reads recent hires' profiles (read-only) and drops a JSON file
here. This step derives factor values only, discards the raw text, and files a proposal for your approval.
Screened batches join the pool automatically (AUTO_APPROVE_HOLDERS); each batch is logged as a proposal."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Proposal, ReferenceProfile
from ..v2.reader import TAGPAT, extract_features, months_between, parse_education, parse_linkedin
from ..v2.signals import combine

FORBIDDEN = {"name", "full_name", "first_name", "last_name", "linkedin_url", "profile_url", "url", "photo", "image", "email"}
AI_DEG = re.compile(r"artificial intelligence|machine learning|\bAI\b", re.I)


def derive(h: dict, now: tuple[int, int], cache: dict | None = None, sizes: dict | None = None) -> dict:
    from ..v2.geo import user_geo
    from ..v2.industry import path as industry_path
    from ..v2.pedigree import education_signals, employer_signal

    from ..v2.industry import sector_of
    from ..v2.geo import regions
    from ..v2.reader import company_tier, role_level

    all_roles = parse_linkedin(h.get("experience_text", ""), now)
    # Read the record as it was when the person was hired: drop every role at the current employer and measure
    # recency from the hire date (otherwise the seat itself counts toward tenure, level, tier and AI work).
    from ..v2.industry import _same

    dest = str(h.get("company") or "").split(" (")[0]
    at_dest = [r for r in all_roles if dest and _same(r["company"].split(" (")[0], dest)]
    if at_dest:  # latest stint only: an earlier stint at the same employer (boomerang) stays in the record
        latest = sorted(at_dest, key=lambda r: r["start"], reverse=True)
        run, at_dest = [latest[0]], latest[1:]
        for r in at_dest:  # consecutive roles in that stint (promotions) belong to the seat too
            if months_between(r["end"], run[-1]["start"]) <= 3:
                run.append(r)
            else:
                break
        at_dest = run
    hire = min((r["start"] for r in at_dest), default=None)
    if hire is None:
        return {"seat_not_found": True}  # the current employer is not in the text: not read as of hire
    roles = [r for r in all_roles if r not in at_dest and r["start"] < hire]
    for r in roles:
        if r["end"] > hire:
            r["end"] = hire
            r["months"] = max(1, months_between(r["start"], hire) + 1)
    g = user_geo(roles)
    f = extract_features(roles, use_cv_lines=True, now=hire)
    ed = parse_education("Education: " + h.get("education_text", "").replace("\n", "; "), hire) if h.get("education_text") else \
        {"ED": None, "technical": False, "degrees": []}
    ai_deg = 1.0 if any(AI_DEG.search(d["text"]) and not d["in_progress"] for d in ed["degrees"]) else 0.0
    combine(f, tech_degree=bool(ed["technical"]), ai_degree=ai_deg, now=hire)
    # Anonymized role list (no company names, titles or text) so factors can be recomputed when the model changes.
    from ..v2.reader import TAG_VERSION

    roles_anon = []
    for r in roles:
        lv, _ = role_level(r)
        from ..v2.industry import company_size

        roles_anon.append({"y0": r["start"][0], "y1": r["end"][0], "months": int(r.get("months") or 0), "tv": TAG_VERSION,
                           "size": company_size(r["company"], sizes),
                           "tier": company_tier(r["company"]), "lv": lv, "sector": sector_of(r["company"], cache)[0],
                           "regions": sorted(regions(r.get("location") or "")),
                           "tags": sorted(t for t, pat in TAGPAT.items() if re.search(pat, " ".join([r["title"]] + r["desc"]), re.I))})
        from ..v2.segment import runs_unified

        roles_anon[-1]["ugm"] = runs_unified(r["company"], lv, roles_anon[-1]["tags"], r["title"])
    row = {"company": h.get("company", "")[:200], "title": h.get("title", "")[:300],
           **{k: f.get(k) for k in ("YOE", "YOE_raw", "CT", "CT_tier_only", "tier", "LV", "LV_max", "FN", "DM", "AC", "AI", "TK")},
           "journey": bool(f.get("journey")), "ED": ed["ED"], "technical": bool(ed["technical"]),
           "mba": any(d.get("mba") and not d["in_progress"] for d in ed["degrees"]), "tags": f["tags"],
           # Geography of all roles read (months; recorded for a future peer comparison, not yet scored).
           "geo": {k: v for k, v in g["months"].items()}, "geo_us_months": g["us_role_months"],
           # Industry path: sectors of the roles before the current employer (who switched in, and from where).
           "ind": industry_path(all_roles, h.get("company"), cache),
           # Selection signals: major-company hires before this role, school tier and field of the best completed degree.
           **{k: v for k, v in employer_signal(roles, None, hire).items() if k != "PD_basis"},
           **{k: v for k, v in education_signals(ed["degrees"]).items() if k != "SCH_basis"},
           "rv": 2, "hired": f"{hire[0]}-{hire[1]:02d}", "roles_anon": roles_anon,
           # where the seat is (region of the current role), so market factors can compare with holders based there
           "seat_region": sorted(regions(at_dest[0].get("location") or "")),
           "LV_size": company_size((f.get("recent_role") or {}).get("company", ""), sizes)}
    return row


def process_file(db: Session, path: Path, run_id: int | None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    kind = data.get("kind", "holders")
    if kind == "holders":
        holders = data.get("holders", [])
        # A holder entry that carries a personal field is dropped (never stored); the rest of the file is still read.
        dropped_personal = sum(1 for h in holders if any(k.lower() in FORBIDDEN for k in h))
        holders = [h for h in holders if not any(k.lower() in FORBIDDEN for k in h)]
        if dropped_personal and not holders:
            return _finish(db, path, {"file": path.name, "rejected": "every entry carries personal fields; not processed and deleted"})
        why = {"personal_fields": dropped_personal, "incomplete": 0, "seat_not_found": 0, "duplicate": 0, "no_dated_roles": 0}
        ym = data.get("as_of") or date.today().strftime("%Y-%m")
        now = (int(ym[:4]), int(ym[5:7]))
        rows, skipped = [], 0
        from ..v2.industry import classify_companies

        names = [r["company"] for h in holders for r in parse_linkedin(h.get("experience_text", ""), now)] + \
                [h.get("company", "") for h in holders]
        cache = classify_companies(db, names, run_id)
        from ..v2.industry import load_sizes

        sizes = load_sizes(db)
        have = {(r.company.lower(), r.title.lower(), (r.features or {}).get("hired"), (r.features or {}).get("YOE"))
                for r in db.scalars(select(ReferenceProfile))}
        have |= {(x.get("company", "").lower(), x.get("title", "").lower(), x.get("hired"), x.get("YOE"))
                 for pr in db.scalars(select(Proposal).where(Proposal.kind == "holders", Proposal.status == "pending"))
                 for x in (pr.payload or {}).get("rows", [])}
        for h in holders:
            if not (h.get("experience_text") and h.get("company") and h.get("title")):
                skipped += 1
                why["incomplete"] += 1
                continue
            row = derive(h, now, cache, sizes)
            key = (h["company"].lower(), h["title"].lower(), row.get("hired"), row.get("YOE"))
            if row.get("seat_not_found") or key in have:  # same company, title, hire month and tenure = same person
                skipped += 1
                why["seat_not_found" if row.get("seat_not_found") else "duplicate"] += 1
                continue
            have.add(key)
            if not row.get("YOE"):  # no dated roles could be read (e.g. a short press bio): not usable as a peer
                skipped += 1
                why["no_dated_roles"] += 1
                continue
            row["source_type"] = h.get("source_type", "linkedin")
            rows.append(row)
        if rows:
            prop = Proposal(run_id=run_id, kind="holders", title=f"Add {len(rows)} role holders to {data.get('cluster', 'Partnerships')}",
                            detail=f"Read {ym} from {data.get('source', 'monthly hire research')}. Derived values only; raw text discarded. "
                                   f"{skipped} skipped: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in why.items() if v) + ".",
                            payload={"cluster": data.get("cluster", "Partnerships"), "as_of": ym,
                                     "source": data.get("source", "monthly hire research"), "rows": rows})
            db.add(prop)
            db.flush()
            if get_settings().auto_approve_holders:  # screened above: no personal fields, dated roles only, no duplicates
                from datetime import datetime, timezone

                apply(db, prop)
                prop.status, prop.decided_at = "approved", datetime.now(timezone.utc)
                prop.detail += " Added automatically after screening."
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
    if (prof.linkedin_import or {}).get("status") != "requested" or not prof.linkedin_url:
        return {"file": name, "rejected": "this user has no pending profile-link request"}
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
    results = []
    for f in files:
        try:
            results.append(process_file(db, f, run_id))
        except Exception as err:  # noqa: BLE001 — a bad file must not block the inbox or stay on disk
            db.rollback()
            results.append(_finish(db, f, {"file": f.name, "rejected": f"could not be read: {type(err).__name__}"}))
    if results:
        from ..v2 import families

        families.write_requests_file(db)  # the Mac task sees the new counts before its next run
    return {"files": len(results), "results": results}


def apply(db: Session, prop: Proposal) -> str:
    """Called when you approve a proposal."""
    if prop.kind == "holders":
        p = prop.payload
        for r in p["rows"]:
            feats = {k: r.get(k) for k in ("YOE", "YOE_raw", "CT", "tier", "LV", "LV_max", "FN", "DM", "AC", "ED", "mba",
                                           "technical", "AI", "TK", "CT_tier_only")}
            feats["tags"] = r["tags"]
            if "geo" in r:
                feats["geo"], feats["geo_us_months"] = r["geo"], r.get("geo_us_months")
            if r.get("ind"):
                feats["ind"] = r["ind"]
            for k in ("PD", "PD_t1", "SCH", "FLD", "rv", "hired", "roles_anon", "LV_size", "seat_region"):
                if r.get(k) is not None:
                    feats[k] = r[k]
            db.add(ReferenceProfile(cluster=p["cluster"], company=r["company"], title=r["title"], features=feats,
                                    source=p["source"], as_of=p["as_of"]))
        db.flush()
        from ..models import PoolRequest
        from ..v2 import families

        req = db.scalar(select(PoolRequest).where(PoolRequest.family == p["cluster"]))
        if req and families.holders_full(db, p["cluster"]) >= families.TARGET:
            req.status = "ready"
        families.write_requests_file(db)
        return f'{len(p["rows"])} holders added to {p["cluster"]}'
    return "recorded; takes effect in the next model release"
