"""Daily health check (the steward's eyes). Plain code, no model. Each invariant writes one HealthCheck row; a failed
severity-1 check raises one alert (a Proposal of kind "alert") that stays until it passes again. Checks read stored
facts only. Thresholds are in the table below so the weekly audit can read and question them."""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AgentRun, Board, HealthCheck, PoolRequest, Posting, Proposal, ReferenceProfile, ScoreSnapshot

FORBIDDEN_KEYS = {"name", "url", "profile_url", "linkedin", "email", "photo", "phone", "experience_text", "education_text"}
WINDOWS = {"daily": 26, "weekly": 8 * 24, "monthly": 35 * 24}  # hours


def _now():
    return datetime.now(timezone.utc)


def version() -> str:
    f = Path("/app/VERSION")
    return (f.read_text().strip()[:12] if f.exists() else os.environ.get("GIT_COMMIT", "")[:12]) or "unknown"


def checks(db: Session) -> list[dict]:
    from ..v2 import families
    from ..llm import month_spend

    s, now, out = get_settings(), _now(), []

    def add(cid, ok, sev, value, threshold, detail=""):
        out.append({"check_id": cid, "ok": bool(ok), "severity": sev, "value": str(value)[:300], "threshold": threshold, "detail": detail[:1000]})

    # 1. every scheduled pipeline finished inside its window
    for kind, hours in WINDOWS.items():
        last = db.scalar(select(func.max(AgentRun.finished_at)).where(AgentRun.kind == kind, AgentRun.status == "done"))
        age = (now - last).total_seconds() / 3600 if last else None
        first = db.scalar(select(func.min(AgentRun.created_at)))
        young = first is None or (now - first).total_seconds() / 3600 < hours  # app younger than the window
        add(f"run_{kind}", young or (age is not None and age <= hours), 1, f"{age:.0f}h ago" if age is not None else "never", f"<= {hours}h")
    # 2. no failed step in 24 hours
    bad = [f'{r.kind}:{st.get("agent")}' for r in db.scalars(select(AgentRun).where(AgentRun.created_at >= now - timedelta(hours=24)))
           for st in (r.steps or []) if st.get("status") in ("failed", "error")]
    add("steps_failed_24h", not bad, 2, len(bad), "0", ", ".join(bad[:8]))
    # 3-4. peer collection is not stalled
    fams = [f["key"] for f in families.all_families(db)]
    under = [k for k in fams if families.holders_full(db, k) < families.TARGET]
    pending = {r.family for r in db.scalars(select(PoolRequest).where(PoolRequest.status == "pending"))}
    if s.peer_collection:
        add("collection_requested", not [k for k in under if k not in pending], 1,
            f"{len(under)} roles under target, {len(pending)} requested", "every role under target has an open request",
            ", ".join(k for k in under if k not in pending))
        new7 = db.scalar(select(func.count(ReferenceProfile.id)).where(ReferenceProfile.read_at >= now - timedelta(days=7))) or 0
        add("collection_progress_7d", (not under) or new7 > 0, 1, f"{new7} new holders in 7 days", "> 0 while any role is under target",
            f"under target: {', '.join(under)}")
    else:
        add("collection_requested", True, 2, "paused by PEER_COLLECTION=false", "n/a")
    # 5. inbox files not left unread
    d = Path(s.inbox_dir)
    old = [f.name for f in d.glob("*.json") if not f.name.endswith("requests.json")
           and now.timestamp() - f.stat().st_mtime > 3600] if d.exists() else []
    add("inbox_unread_1h", not old, 2, len(old), "0", ", ".join(old[:5]))
    # 6. postings fresh; boards answering
    op = list(db.scalars(select(Posting).where(Posting.status == "open", Posting.source.in_(("greenhouse", "lever", "ashby")))))
    cut = (now - timedelta(days=2)).date().isoformat()
    fresh = sum(1 for p in op if (p.last_seen or "") >= cut)
    add("postings_fresh_2d", not op or fresh / len(op) >= 0.9, 2, f"{fresh}/{len(op)}", ">= 90% of board postings seen in 2 days")
    boards = list(db.scalars(select(Board).where(Board.active.is_(True))))
    okb = sum(1 for b in boards if (b.last_status or "").startswith("ok"))
    add("boards_ok", not boards or okb / len(boards) >= 0.8, 2, f"{okb}/{len(boards)}", ">= 80% of boards answered")
    # 7. web-found postings not left unverified
    lim = (now - timedelta(days=30)).date().isoformat()
    stale = db.scalar(select(func.count(Posting.id)).where(Posting.status == "unverified", Posting.first_seen < lim)) or 0
    add("unverified_over_30d", stale == 0, 2, stale, "0")
    # 8. job coverage is not one company
    c = Counter(p.company for p in db.scalars(select(Posting).where(Posting.status == "open")))
    n = sum(c.values())
    top = c.most_common(1)[0] if c else ("", 0)
    add("posting_concentration", not n or top[1] / n <= 0.15, 2, f"{top[0]} {top[1]}/{n}", "largest company <= 15% of open postings")
    # 9. comparison groups balanced (5+ employers, none above 25%) and large enough
    thin = []
    for k in fams:
        rows = [r for r in db.scalars(select(ReferenceProfile).where(ReferenceProfile.cluster == k)) if (r.features or {}).get("rv") == 2]
        emp = Counter((r.company or "").lower() for r in rows)
        if len(rows) < 20 or len(emp) < 5 or (rows and max(emp.values()) / len(rows) > 0.25):
            thin.append(f"{k} n={len(rows)} employers={len(emp)}")
    add("peer_groups_balanced", not thin, 2, f"{len(thin)} of {len(fams)} roles thin or concentrated", "n >= 20, employers >= 5, largest <= 25%", "; ".join(thin))
    # 10. privacy: no personal fields stored with holders
    leak = sum(1 for r in db.scalars(select(ReferenceProfile)) if FORBIDDEN_KEYS & {str(x).lower() for x in (r.features or {})})
    add("privacy_no_personal_fields", leak == 0, 1, leak, "0 holders carrying personal fields")
    # 11. a score does not move more than 3 points without a model-version change
    moved = []
    snaps = list(db.scalars(select(ScoreSnapshot).order_by(ScoreSnapshot.user_id, ScoreSnapshot.family, ScoreSnapshot.created_at.desc())))
    seen: dict = {}
    for sn in snaps:
        seen.setdefault((sn.user_id, sn.family), []).append(sn)
    for (uid, fam), ss in seen.items():
        if len(ss) >= 2 and ss[0].created_at >= now - timedelta(days=2) and ss[0].model_version == ss[1].model_version \
                and abs(ss[0].score - ss[1].score) > 3:
            moved.append(f"user {uid} {fam}: {ss[1].score:.1f} -> {ss[0].score:.1f} ({ss[0].model_version})")
    add("score_drift_same_model", not moved, 1, len(moved), "<= 3 points between snapshots on one model version", "; ".join(moved[:6]))
    # 12. spend against the cap
    spend, cap = month_spend(db), s.monthly_cap_usd
    add("llm_spend", spend < 0.8 * cap, 1, f"${spend:.2f} of ${cap:.2f}", "< 80% of the monthly cap")
    # 12b. every model call in 24 hours ran on the model the registry assigns (or its recorded escalation / fallback);
    #      the top-tier model appears only under agents allowed to use it
    from ..models import UsageLog
    from . import registry

    wrong, top = [], registry.top_tier()
    rows24 = list(db.scalars(select(UsageLog).where(UsageLog.at >= now - timedelta(hours=24))))
    by_job: dict = {}
    for u in rows24:
        if u.runner == "cli" and u.source_job:
            by_job.setdefault(u.source_job.rsplit(":", 1)[0], []).append(u)
    for jid, us in by_job.items():
        main = max(us, key=lambda x: x.output_tokens)
        if main.requested_model and not (main.model.startswith(main.requested_model) or main.requested_model.startswith(main.model)):
            wrong.append(f"{main.agent} session {jid}: most output from {main.model}, assigned {main.requested_model}")
    for u in [x for x in rows24 if x.runner != "cli"]:
        try:
            allowed = registry.allowed_models(u.agent)
            registry.spec(u.agent)
        except registry.UnknownAgent:
            wrong.append(f"{u.agent}: not in the registry")
            continue
        served = (u.model or "")
        if not any(served.startswith(m) or m.startswith(served) for m in allowed):
            wrong.append(f"{u.agent}: served {served}, assigned {sorted(allowed)}")
        elif served.startswith(top) and not registry.spec(u.agent).get("top_tier_triggers"):
            wrong.append(f"{u.agent}: top-tier model used without a trigger")
    add("model_matches_registry", not wrong, 1, len(wrong), "0 calls on a model other than the one assigned", "; ".join(sorted(set(wrong))[:6]))
    # 12c. the Mac dispatcher is alive (it starts agent sessions on their assigned model)
    hb = Path(s.inbox_dir) / "jobs" / "heartbeat.json"
    if hb.exists():
        age = (now.timestamp() - hb.stat().st_mtime) / 60
        add("dispatcher_heartbeat", age <= 30, 2, f"{age:.0f} min ago", "<= 30 min")
    # 13. recorded outcomes (information: validation needs them)
    from ..models import Outcome

    no = db.scalar(select(func.count(Outcome.id))) or 0
    add("outcomes_recorded", True, 2, no, "information: 30 for a first look, 100 for fitted weights")
    return out


def run(db: Session, run_id: int | None) -> dict:
    res = checks(db)
    for r in res:
        db.add(HealthCheck(run_id=run_id, **r))
    open_alerts = {(p.payload or {}).get("check_id"): p for p in db.scalars(select(Proposal).where(Proposal.kind == "alert", Proposal.status == "pending"))}
    for r in res:
        a = open_alerts.get(r["check_id"])
        if r["severity"] == 1 and not r["ok"] and a is None:
            db.add(Proposal(run_id=run_id, kind="alert", title=f"Health check failed: {r['check_id'].replace('_', ' ')}",
                            detail=f"Now: {r['value']}. Expected: {r['threshold']}. {r['detail']}", payload={"check_id": r["check_id"]}))
        elif r["ok"] and a is not None:  # passes again: the alert closes itself
            a.status, a.decided_at, a.detail = "approved", _now(), a.detail + " Resolved: the check passes again."
    db.commit()
    failed = [r["check_id"] for r in res if not r["ok"]]
    return {"checks": len(res), "failed": failed, "sev1_failed": [r["check_id"] for r in res if not r["ok"] and r["severity"] == 1]}


def status(db: Session, days: int = 7) -> dict:
    """Numbers only (no personal data): the latest result of each check and how often it failed in the period."""
    since = _now() - timedelta(days=days)
    rows = list(db.scalars(select(HealthCheck).where(HealthCheck.at >= since).order_by(HealthCheck.at)))
    latest, fails = {}, Counter()
    for r in rows:
        latest[r.check_id] = r
        fails[r.check_id] += 0 if r.ok else 1
    return {"version": version(), "as_of": _now().isoformat(timespec="minutes"), "days": days,
            "overall": "red" if any(not r.ok and r.severity == 1 for r in latest.values()) else
                       "amber" if any(not r.ok for r in latest.values()) else "green" if latest else "no data",
            "checks": [{"check": k, "ok": r.ok, "severity": r.severity, "value": r.value, "expected": r.threshold,
                        "failed_runs": fails[k], "detail": r.detail[:300], "at": r.at.isoformat(timespec="minutes")}
                       for k, r in sorted(latest.items())]}
