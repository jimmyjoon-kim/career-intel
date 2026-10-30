"""Agent team: status, spend against the cap, runs, briefs, proposals awaiting approval, score history."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents import inbox
from ..agents.coordinator import PIPELINES, enqueue
from ..config import get_settings
from ..db import get_db
from ..llm import month_spend
from ..models import AgentRun, Board, Brief, Proposal, ScoreSnapshot, UsageLog, User
from ..security import admin_user, current_user

router = APIRouter(prefix="/api/agents", tags=["agents"])

TEAM = [
    {"key": "coordinator", "name": "Coordinator", "model": "none (code)", "job": "Runs the schedule and job queue, enforces the spending cap, retries failures."},
    {"key": "sourcing", "name": "Job sourcing", "model": "none for boards; research model for weekly web search",
     "job": "Reads Greenhouse, Lever and Ashby boards directly; keeps Director+ commercial US roles; marks closed postings."},
    {"key": "reader", "name": "Requirement reader", "model": "bulk", "job": "Reads each new or changed posting 3 times; keeps the majority tags."},
    {"key": "hire_research", "name": "Hire research", "model": "monthly task on your Mac", "job": "Reads recent hires' profiles (read-only); derived values only, filed for approval."},
    {"key": "company_facts", "name": "Company facts", "model": "research", "job": "Checks unverified IPO and acquisition dates by web search; files confirmations for approval."},
    {"key": "level", "name": "Level assessor", "model": "research", "job": "Reads each posting's full description and judges its real level from scope, team, revenue ownership and experience required, quoting the evidence; titles alone are not trusted."},
    {"key": "evidence", "name": "Evidence finder", "model": "bulk", "job": "Searches your own documents for lines that evidence requirements you are marked as missing; you confirm each."},
    {"key": "scoring", "name": "Scoring engine", "model": "none (code)", "job": "Scores every profile and stores the result with the model version."},
    {"key": "checker", "name": "Checker", "model": "critical", "job": "Rules, arithmetic, regression cases, and a review of every brief against its data."},
    {"key": "analyst", "name": "Analyst", "model": "critical", "job": "Writes the weekly brief from facts assembled in code. Reports only."},
]


def _run(r: AgentRun) -> dict:
    return {"id": r.id, "kind": r.kind, "status": r.status, "trigger": r.trigger, "created_at": r.created_at,
            "started_at": r.started_at, "finished_at": r.finished_at, "steps": r.steps, "error": r.error,
            "cost_usd": round(sum((s.get("cost_usd") or 0) for s in r.steps or []), 4)}


@router.get("/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_settings()
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    by_agent: dict = defaultdict(float)
    by_model: dict = defaultdict(float)
    calls = 0
    for u in db.scalars(select(UsageLog).where(UsageLog.at >= start)):
        by_agent[u.agent] += u.cost_usd
        by_model[u.model] += u.cost_usd
        calls += 1
    from ..llm import model_for

    models = {"bulk": model_for("bulk"), "research": s.anthropic_model, "critical": model_for("critical"),
              "critical_fallback": s.model_critical_fallback}
    last_used = {u.agent: u.model for u in db.scalars(select(UsageLog).order_by(UsageLog.id.desc()).limit(200))}
    runs = list(db.scalars(select(AgentRun).order_by(AgentRun.id.desc()).limit(15)))
    boards = list(db.scalars(select(Board).order_by(Board.company)))
    return {
        "team": TEAM, "models": models, "critical_model_last_used": last_used.get("analyst") or last_used.get("checker"),
        "budget": {"allowance_usd": s.api_monthly_allowance_usd, "share": s.budget_share, "cap_usd": s.monthly_cap_usd,
                   "spent_usd": round(month_spend(db), 4), "calls": calls,
                   "by_agent": {k: round(v, 4) for k, v in sorted(by_agent.items(), key=lambda x: -x[1])},
                   "by_model": {k: round(v, 4) for k, v in sorted(by_model.items(), key=lambda x: -x[1])}},
        "schedule": ["Daily 06:00 KST — job boards, requirement reader, search index update",
                     "Mondays 09:00 KST — full run: sourcing, reader, index, scoring, evidence finder, checker, brief",
                     "First Monday 08:40 KST — hire research on your Mac (scheduled task)",
                     "First Monday 10:00 KST — hire-research inbox, company facts, rescoring"],
        "runs": [_run(r) for r in runs],
        "boards": [{"ats": b.ats, "slug": b.slug, "company": b.company, "active": b.active, "last_status": b.last_status,
                    "last_checked": b.last_checked} for b in boards],
        "pending": db.query(Proposal).filter(Proposal.status == "pending").count(),
        "pipelines": list(PIPELINES),
    }


@router.get("/brief")
def latest_brief(user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.scalar(select(Brief).where(Brief.user_id == user.id).order_by(Brief.id.desc()))
    if not b:
        return {"brief": None}
    return {"brief": {"id": b.id, "run_id": b.run_id, "created_at": b.created_at, "body": b.body, "model": b.model,
                      "check": b.check, "data": b.data}}


@router.get("/history")
def history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=400)
    rows = db.scalars(select(ScoreSnapshot).where(ScoreSnapshot.user_id == user.id, ScoreSnapshot.created_at >= since)
                      .order_by(ScoreSnapshot.id))
    return {"points": [{"at": r.created_at, "score": r.score, "position": r.position, "model_version": r.model_version,
                        "factors": r.factors} for r in rows]}


@router.get("/proposals")
def proposals(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Proposal).order_by(Proposal.status != "pending", Proposal.id.desc()).limit(50))
    return {"proposals": [{"id": p.id, "kind": p.kind, "title": p.title, "detail": p.detail, "status": p.status,
                           "created_at": p.created_at, "decided_at": p.decided_at,
                           "count": len(p.payload.get("rows") or p.payload.get("events") or []),
                           "preview": (p.payload.get("rows") or p.payload.get("events") or [])[:10]} for p in rows]}


class Decision(BaseModel):
    decision: str  # approve | reject


@router.post("/proposals/{pid}")
def decide(pid: int, body: Decision, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    p = db.get(Proposal, pid)
    if not p or p.status != "pending":
        raise HTTPException(404, "No pending proposal with that id")
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be approve or reject")
    note = inbox.apply(db, p) if body.decision == "approve" else "rejected"
    p.status, p.decided_at = ("approved" if body.decision == "approve" else "rejected"), datetime.now(timezone.utc)
    db.commit()
    if body.decision == "approve" and p.kind == "holders":
        enqueue(db, "rescore", trigger="event", user_id=user.id)
    return {"ok": True, "note": note}


class RunReq(BaseModel):
    kind: str


@router.post("/run")
def run_now(body: RunReq, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    if body.kind not in PIPELINES:
        raise HTTPException(400, f"kind must be one of {list(PIPELINES)}")
    r = enqueue(db, body.kind, trigger="manual", user_id=user.id)
    return {"run": _run(r), "note": "Queued. The worker picks it up within 30 seconds."}


class BoardReq(BaseModel):
    ats: str
    slug: str
    company: str = ""


@router.post("/boards")
def add_board(body: BoardReq, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    if body.ats not in ("greenhouse", "lever", "ashby"):
        raise HTTPException(400, "ats must be greenhouse, lever or ashby")
    db.add(Board(ats=body.ats, slug=body.slug.strip(), company=body.company.strip() or body.slug.strip()))
    db.commit()
    return {"ok": True}



# ---- Tag review: settle the requirement reader's disputed tags; settled postings become labeled examples ----

@router.get("/tag-review")
def tag_review(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    from ..agents.requirements import evaluate_reader, is_test
    from ..models import Posting
    from ..taxonomy import TAGS

    rows = []
    for p in db.scalars(select(Posting).where(Posting.status.in_(("open", "unverified"))).order_by(Posting.id.desc())):
        rc = p.read_check or {}
        if not rc.get("disputed") or rc.get("labels"):
            continue
        lab = lambda t: TAGS[t].label if t in TAGS else t  # noqa: E731
        rows.append({"id": p.id, "company": p.company, "title": p.title, "url": p.url, "test_split": is_test(p),
                     "agreed": [{"tag": t, "label": lab(t)} for t in rc.get("model_tags", p.tags or [])],
                     "disputed": [{"tag": t, "label": lab(t)} for t in rc["disputed"]]})
    return {"postings": rows[:40], "remaining": len(rows), "reader_test": evaluate_reader(db)}


class TagLabels(BaseModel):
    labels: dict[str, bool]  # tag -> required by this posting?


@router.post("/tag-review/{pid}")
def settle_tags(pid: int, body: TagLabels, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    from ..agents.requirements import apply_labels
    from ..models import Posting
    from ..taxonomy import TAGS

    p = db.get(Posting, pid)
    if not p:
        raise HTTPException(404, "No such posting")
    labels = {t: bool(v) for t, v in body.labels.items() if t in TAGS}
    p.read_check = {**(p.read_check or {}), "labels": labels}
    apply_labels(p)
    db.commit()
    return {"ok": True, "tags": p.tags}
