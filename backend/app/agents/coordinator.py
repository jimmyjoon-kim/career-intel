"""Coordinator (plain code). Runs pipelines step by step, records each step, and stops cleanly at the spending cap.

daily   : sourcing (boards) -> requirement reader -> search index update (new/changed postings only)
weekly  : sourcing (boards + web) -> requirement reader -> index -> scoring -> evidence finder -> checker -> analyst
monthly : hire-research inbox -> company facts -> scoring
rescore : scoring only (profile change or Refresh)
"""

from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm import BudgetExceeded, check_budget, month_spend
from ..models import AgentRun, Profile, User
from . import analyst, checker, company_facts, evidence, inbox, level, requirements, snapshots, sourcing

log = logging.getLogger(__name__)
PIPELINES = {
    "daily": ["inbox", "sourcing", "reader", "level", "index_update"],
    "weekly": ["sourcing", "web_sourcing", "reader", "level", "index", "scoring", "evidence", "checker", "analyst"],
    "arrivals": ["inbox", "scoring"],  # a research file arrived: read it now, not at the next scheduled run
    "monthly": ["inbox", "refresh_pools", "company_facts", "company_levels", "scoring"],
    "rescore": ["scoring"],
    # Started when you change your locations (or ask the Ask agent to search): boards + location web search.
    "locations": ["sourcing", "web_sourcing", "reader", "level", "index_update", "scoring"],
}
USES_MODEL = {"web_sourcing", "reader", "level", "company_facts", "company_levels", "checker", "analyst", "evidence"}


def _profile_summary(db: Session) -> str:
    p = db.scalar(select(Profile).where(Profile.headline != ""))
    return p.headline if p else "Director+ commercial leader (partnerships, ad sales, growth), ad tech and mobile monetization"


def _step(db: Session, run: AgentRun, name: str, ctx: dict):
    rid = run.id
    if name == "sourcing":
        return sourcing.run_boards(db)
    if name == "web_sourcing":
        return sourcing.run_web(db, rid, _profile_summary(db), only_locations=run.kind == "locations")
    if name == "reader":
        return requirements.run(db, rid)
    if name == "index":
        from ..rag.index import rebuild_shared

        try:
            return {"chunks": rebuild_shared(db)}
        except Exception as err:  # noqa: BLE001 — search index is not critical to the run
            return {"skipped": f"index rebuild failed: {err}"}
    if name == "index_update":
        from ..rag.index import update_postings

        try:
            return update_postings(db)
        except Exception as err:  # noqa: BLE001 — search index is not critical to the run
            return {"skipped": f"index update failed: {err}"}
    if name == "refresh_pools":
        from ..v2.families import refresh_ready

        return {"requested": refresh_ready(db)}
    if name == "level":
        return level.run(db, rid)
    if name == "evidence":
        return evidence.run(db, rid)
    if name == "scoring":
        out = snapshots.run(db, rid)
        ctx["snapshots"] = {s.user_id: s for s in db.scalars(
            select(snapshots.ScoreSnapshot).where(snapshots.ScoreSnapshot.run_id == rid,
                                                  snapshots.ScoreSnapshot.family == "Partnerships"))}
        return out
    if name == "checker":
        from ..services import evaluate

        ctx["evals"] = {}
        per = []
        for u in db.scalars(select(User).join(Profile)):
            ev = evaluate(db, u)
            ctx["evals"][u.id] = ev
            per.append({"user_id": u.id, "passing": ev["passing"], "snapshot": ctx.get("snapshots", {}).get(u.id)})
        rep = checker.run(db, rid, per)
        ctx["check"] = rep
        return rep
    if name == "analyst":
        made = []
        steps = {s["agent"]: s.get("result") for s in run.steps}
        for u in db.scalars(select(User).join(Profile)):
            ev = ctx.get("evals", {}).get(u.id)
            if ev is None:
                from ..services import evaluate

                ev = evaluate(db, u)
            data = analyst.facts(db, u, ev, ctx.get("snapshots", {}).get(u.id), steps)
            data["system_check_passed"] = bool(ctx.get("check", {}).get("passed"))
            b = analyst.write(db, rid, u, data)
            made.append({"user_id": u.id, "brief_id": b.id, "check_passed": b.check.get("passed")})
        return {"briefs": made}
    if name == "inbox":
        return inbox.run(db, rid)
    if name == "company_facts":
        return company_facts.run(db, rid)
    if name == "company_levels":
        return company_facts.run_ladders(db, rid)
    raise ValueError(name)


def execute(db: Session, run: AgentRun) -> AgentRun:
    run.status, run.started_at, run.steps = "running", datetime.now(timezone.utc), []
    db.commit()
    ctx: dict = {}
    for name in PIPELINES[run.kind]:
        t0, spend0 = time.time(), month_spend(db)
        entry = {"agent": name, "status": "done"}
        try:
            if name in USES_MODEL:
                check_budget()
            entry["result"] = _step(db, run, name, ctx)
            if isinstance(entry["result"], dict) and entry["result"].get("stopped"):
                entry["status"] = "stopped"
        except BudgetExceeded as err:
            entry.update(status="stopped", error=str(err))
        except Exception as err:  # noqa: BLE001 — record and continue with the next step
            db.rollback()
            log.exception("step %s failed", name)
            entry.update(status="failed", error=f"{err}\n{traceback.format_exc(limit=3)}"[:2000])
        entry["seconds"] = round(time.time() - t0, 1)
        entry["cost_usd"] = round(month_spend(db) - spend0, 4)
        run.steps = [*run.steps, entry]
        db.commit()
        if entry["status"] == "stopped":
            run.status, run.error = "stopped", entry.get("error") or entry["result"].get("stopped", "")
            break
    else:
        run.status = "failed" if any(s["status"] == "failed" for s in run.steps) else "done"
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return run


def enqueue(db: Session, kind: str, trigger: str = "manual", user_id: int | None = None) -> AgentRun:
    if kind not in PIPELINES:
        raise ValueError(f"unknown pipeline {kind}")
    busy = db.scalar(select(AgentRun).where(AgentRun.kind == kind, AgentRun.status.in_(("queued", "running"))))
    if busy:
        return busy
    run = AgentRun(kind=kind, trigger=trigger, requested_by=user_id, status="queued")
    db.add(run)
    db.commit()
    return run
