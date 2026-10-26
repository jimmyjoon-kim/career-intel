from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..extract import extract_posting
from ..importer import import_csv
from ..llm import llm_available
from ..models import Chunk, Posting, User
from ..config import get_settings
from ..rag.index import rebuild_shared, rebuild_user
from ..schemas import PostingIn
from ..security import admin_user, current_user
from ..services import current_market, evaluate, posting_dict, row_dict
from ..taxonomy import TAGS

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ev = evaluate(db, user)
    rows = ev["rows"]
    prof = user.profile
    return {
        "counts": {
            "postings": len(rows),
            "open": sum(1 for r in rows if r["posting"].status == "open"),
            "gate_pass": len(ev["passing"]),
            "no_zero_hard_gap": sum(1 for r in ev["passing"] if not r["has_zero_hard_gap"]),
        },
        "profile_ready": bool(prof and prof.tag_matches),
        "top": [row_dict(r) for r in ev["passing"][:10]],
        "gaps": ev["gap_summary"],
        "gate_fail_reasons": _reason_counts(rows),
        "base": ({k: ev["base"][k] for k in ("base_score", "position", "cluster", "n_reference", "holders")}
                 | {"gaps": [g["label"] for g in ev["base"]["gaps"]],
                    "differentiators": [d["label"] for d in ev["base"]["differentiators"]]}) if ev["base"] else None,
    }


def _reason_counts(rows) -> list[dict]:
    counts: dict[str, int] = {}
    for r in rows:
        for reason in r["gate_reasons"]:
            key = reason.split("'")[0].split(" below ")[0].strip()
            counts[key] = counts.get(key, 0) + 1
    return [{"reason": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


@router.get("/postings")
def postings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ev = evaluate(db, user)
    rows = sorted(ev["rows"], key=lambda r: (not r["gate_pass"], r["has_zero_hard_gap"], -r["rank_score"]))
    return [row_dict(r) for r in rows]


@router.get("/postings/{posting_id}")
def posting_detail(posting_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ev = evaluate(db, user)
    for r in ev["rows"]:
        if r["posting"].id == posting_id:
            return row_dict(r)
    raise HTTPException(404, "Posting not found")


@router.get("/market")
def market(user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, stats = current_market(db)
    def table(tags: dict):
        return sorted(
            ({"tag": k, "label": TAGS[k].label if k in TAGS else k, **v} for k, v in tags.items()),
            key=lambda x: -x["pct"],
        )
    return {
        "clusters": [
            {"name": name, "n": c["n"], "merged_from": c["merged_from"], "tags": table(c["tags"])}
            for name, c in sorted(stats["clusters"].items(), key=lambda kv: -kv[1]["n"])
        ],
        "all": {"n": stats["all"]["n"], "tags": table(stats["all"]["tags"])},
    }


# ---- admin ----

@router.post("/admin/import")
async def admin_import(file: UploadFile = File(...), source_date: str | None = None,
                       _: User = Depends(admin_user), db: Session = Depends(get_db)):
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    result = import_csv(db, content, source_date)
    result["chunks"] = rebuild_shared(db)
    return result


@router.post("/admin/postings")
def admin_add_posting(body: PostingIn, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    if db.scalar(select(Posting).where(Posting.url == body.url)):
        raise HTTPException(409, "A posting with this URL already exists")
    ex = extract_posting(body.title, body.description)
    p = Posting(
        company=body.company, title=body.title, url=body.url, location=body.location,
        remote_flag=body.remote_flag, bay_area=body.bay_area, pay_range=body.pay_range,
        description=body.description, tags=ex["tags"], years_required=ex["years_required"],
        level_band=ex["level_band"], role_cluster=ex["role_cluster"], scope=ex["scope"],
        no_sponsorship=ex["no_sponsorship"], status="open", verification="added manually",
    )
    db.add(p)
    db.commit()
    rebuild_shared(db)
    return posting_dict(p)


@router.patch("/admin/postings/{posting_id}")
def admin_set_status(posting_id: int, status: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    if status not in ("open", "closed", "stale", "unverified"):
        raise HTTPException(422, "Invalid status")
    p = db.get(Posting, posting_id)
    if not p:
        raise HTTPException(404, "Posting not found")
    p.status = status
    db.commit()
    rebuild_shared(db)
    return posting_dict(p)


@router.post("/admin/reference/reload")
def admin_reload_reference(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    from ..v2.service import import_reference_seed

    return {"loaded": import_reference_seed(db)}


@router.post("/admin/reindex")
def admin_reindex(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    n = rebuild_shared(db)
    users = list(db.scalars(select(User)))
    for u in users:
        n += rebuild_user(db, u)
    return {"chunks": n, "users": len(users)}


@router.get("/status")
def system_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_settings()
    return {
        "llm": llm_available(),
        "llm_model": s.anthropic_model if llm_available() else None,
        "embedding_model": s.embedding_model_name,
        "postings": db.scalar(select(func.count(Posting.id))),
        "chunks": db.scalar(select(func.count(Chunk.id)).where(Chunk.embedding_model == s.embedding_model_name)),
        "is_admin": user.is_admin,
    }
