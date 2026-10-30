"""Requirement reader agent. Reads each new or changed posting three times with the bulk model and keeps the
majority answer (self-consistency). Tags found in only one reading are recorded as disputed, not used."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..extract import extract_posting
from ..importer import check_cluster
from ..llm import BudgetExceeded, llm_available
from ..models import Posting

READS = 3


def majority(results: list[dict]) -> dict:
    n = len(results)
    need = n // 2 + 1
    counts = Counter(t for r in results for t in set(r["tags"]))
    agreed = sorted(t for t, c in counts.items() if c >= need)
    disputed = sorted(t for t, c in counts.items() if c < need)
    mode = lambda k: Counter(r.get(k) for r in results if r.get(k)).most_common(1)[0][0] if any(r.get(k) for r in results) else ""  # noqa: E731
    yrs = sorted(r["years_required"] for r in results if isinstance(r.get("years_required"), int))
    return {"tags": agreed, "disputed": disputed, "level_band": mode("level_band"), "role_cluster": mode("role_cluster"),
            "scope": mode("scope"), "years_required": yrs[len(yrs) // 2] if yrs else None,
            "no_sponsorship": sum(bool(r.get("no_sponsorship")) for r in results) >= need,
            "unanimous": not disputed and len({r.get("level_band") for r in results}) == 1}


def pending(db: Session, limit: int) -> list[Posting]:
    rows = db.scalars(select(Posting).where(Posting.status.in_(("open", "unverified"))).order_by(Posting.id.desc()))
    return [p for p in rows if not (p.read_check or {}).get("hash") or p.read_check["hash"] != p.content_hash][:limit]


def run(db: Session, run_id: int | None, limit: int = 150) -> dict:
    todo = pending(db, limit)
    reads = READS if llm_available() else 1
    done = disputed = 0
    stopped = ""
    for p in todo:
        if not (p.description or "").strip():
            p.read_check = {"hash": p.content_hash, "runs": 0, "note": "no description text; title only"}
            continue
        try:
            results = [extract_posting(p.title, p.description, role="bulk", agent="reader", run_id=run_id) for _ in range(reads)]
        except BudgetExceeded as err:
            stopped = str(err)
            break
        m = majority(results)
        p.tags = m["tags"]
        p.level_band = m["level_band"] or p.level_band
        p.role_cluster = check_cluster(m["role_cluster"] or "Other", m["tags"], p.title)
        p.scope = m["scope"] or p.scope
        p.years_required = m["years_required"]
        p.no_sponsorship = m["no_sponsorship"] or p.no_sponsorship
        p.read_check = {"hash": p.content_hash, "runs": reads, "mode": results[0].get("mode"), "disputed": m["disputed"],
                        "unanimous": m["unanimous"]}
        done += 1
        disputed += bool(m["disputed"])
        db.commit()
    db.commit()
    return {"read": done, "with_disputed_tags": disputed, "remaining": max(0, len(todo) - done), "reads_each": reads,
            **({"stopped": stopped} if stopped else {})}
