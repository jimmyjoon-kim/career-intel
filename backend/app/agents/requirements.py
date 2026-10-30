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
EXAMPLES = 2


def is_test(p: Posting) -> bool:
    """Every fifth labeled posting is held out: never shown as an example, used only to measure the reader."""
    return p.id % 5 == 0


def labeled(db: Session) -> list[Posting]:
    return [p for p in db.scalars(select(Posting)) if (p.read_check or {}).get("labels")]


def examples_for(db: Session, p: Posting, pool: list[Posting]) -> str:
    """The most similar labeled postings (training split only), found through the search index."""
    train = {str(x.id): x for x in pool if not is_test(x) and x.id != p.id}
    if not train:
        return ""
    from ..models import Chunk
    from ..rag.embeddings import embed

    try:
        qv = embed([f"{p.title}\n{(p.description or '')[:2000]}"], "query", quick=True)[0]
    except Exception:  # noqa: BLE001 — examples are optional
        return ""
    dist = Chunk.embedding.cosine_distance(qv)
    refs, out = [], []
    for c in db.scalars(select(Chunk).where(Chunk.owner_id.is_(None), Chunk.source_type == "posting",
                                            Chunk.source_ref.in_(list(train))).order_by(dist).limit(12)):
        if c.source_ref not in refs:
            refs.append(c.source_ref)
        if len(refs) >= EXAMPLES:
            break
    for ref in refs:
        x = train[ref]
        lab = x.read_check["labels"]
        out.append(f"- {x.company} — {x.title}: tags {sorted(t for t, v in lab.items() if v)}; "
                   f"not required: {sorted(t for t, v in lab.items() if not v)}")
    return "\n".join(out)


def apply_labels(p: Posting) -> None:
    """Your settled tags override the reader's for that posting."""
    lab = (p.read_check or {}).get("labels") or {}
    tags = set(p.tags or [])
    tags |= {t for t, v in lab.items() if v}
    tags -= {t for t, v in lab.items() if not v}
    p.tags = sorted(tags)


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
    pool = labeled(db) if llm_available() else []
    done = disputed = 0
    stopped = ""
    for p in todo:
        if not (p.description or "").strip():
            p.read_check = {"hash": p.content_hash, "runs": 0, "note": "no description text; title only"}
            continue
        try:
            ex = examples_for(db, p, pool) if pool and not is_test(p) else ""
            results = [extract_posting(p.title, p.description, ex, role="bulk", agent="reader", run_id=run_id)
                       for _ in range(reads)]
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
        labels = (p.read_check or {}).get("labels")
        p.read_check = {"hash": p.content_hash, "runs": reads, "mode": results[0].get("mode"), "disputed": m["disputed"],
                        "unanimous": m["unanimous"], "model_tags": m["tags"], "examples": bool(ex),
                        **({"labels": labels} if labels else {})}
        apply_labels(p)
        done += 1
        disputed += bool(m["disputed"])
        db.commit()
    db.commit()
    return {"read": done, "with_disputed_tags": disputed, "remaining": max(0, len(todo) - done), "reads_each": reads,
            **({"stopped": stopped} if stopped else {})}


def evaluate_reader(db: Session) -> dict:
    """Held-out test: compare the reader's own tags with your settled labels (no model calls)."""
    tp = fp = fn = 0
    per: dict[str, list[int]] = {}
    n = 0
    for p in labeled(db):
        if not is_test(p) or "model_tags" not in (p.read_check or {}):
            continue
        n += 1
        got = set(p.read_check["model_tags"])
        for t, v in p.read_check["labels"].items():
            hit = t in got
            tp += hit and v
            fp += hit and not v
            fn += (not hit) and v
            per.setdefault(t, [0, 0])[0 if hit == v else 1] += 1
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    worst = sorted(((t, w) for t, (r, w) in per.items() if w), key=lambda x: -x[1])[:5]
    return {"test_postings": n, "precision": round(prec, 2) if prec is not None else None,
            "recall": round(rec, 2) if rec is not None else None, "most_missed_tags": worst,
            "labeled_postings": len(labeled(db))}
