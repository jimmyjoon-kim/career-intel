"""Analyst agent. Assembles the week's facts in code, then a top-tier model writes a short brief from them.
It reports; it does not recommend, and any model change it sees is filed for your approval elsewhere."""

from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..llm import BudgetExceeded, complete, model_for, month_spend
from ..models import Brief, Posting, Proposal, User
from . import checker, snapshots

SYSTEM = """You write a weekly career-market brief for one candidate from DATA only.
Format: plain Markdown, under 220 words, four short sections: Score, Top matches, Market this week, Waiting for your decision.
Rules: every number must appear in DATA; mark postings with status "unverified" as (unverified); no probabilities,
likelihoods or chances; no advice, strategy or next steps; American spelling; short bullets; no preamble."""


def facts(db: Session, user: User, ev: dict, snap, steps: dict) -> dict:
    prev = snapshots.previous(db, user.id, snap.id) if snap else None
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    score = None
    if snap:
        pf = {f["factor"]: f for f in (prev.factors if prev else [])}
        moved = [{"factor": f["label"], "points_now": f["points"], "points_before": pf[f["factor"]]["points"]}
                 for f in snap.factors if f["factor"] in pf and f["points"] is not None and pf[f["factor"]]["points"] is not None
                 and abs(f["points"] - pf[f["factor"]]["points"]) >= 0.1]
        score = {"now": snap.score, "position_percentile": snap.position, "model_version": snap.model_version,
                 "before": prev.score if prev else None, "before_model_version": prev.model_version if prev else None,
                 "factor_changes": moved}
    top = [{"company": r["posting"].company, "title": r["posting"].title, "location": r["posting"].location,
            "status": r["posting"].status, "first_seen": r["posting"].first_seen, "match_score": round(r["rank_score"] * 100),
            "missing_minimums": [g["label"] for g in r["hard_gaps"]], "url": r["posting"].url}
           for r in ev["passing"][:5]]
    base = ev.get("base") or {}
    gaps = [{"factor": g["label"], "weighted_gap": g["delta"]} for g in (base.get("gaps") or [])[:3]]
    s = get_settings()
    return {
        "date": date.today().isoformat(), "score": score, "top_matches": top,
        "passing_total": len(ev["passing"]),
        "new_postings_7d": db.scalar(select(func.count(Posting.id)).where(Posting.first_seen >= week_ago)),
        "sourcing": steps.get("sourcing"), "web_sourcing": steps.get("web_sourcing"),
        "largest_gaps_vs_median_holder": gaps,
        "pending_decisions": [p.title for p in db.scalars(select(Proposal).where(Proposal.status == "pending"))],
        "api_spend_month_usd": round(month_spend(db), 2), "api_cap_usd": s.monthly_cap_usd,
    }


def fallback_text(d: dict) -> str:
    lines = ["**Score**"]
    if d["score"]:
        sc = d["score"]
        lines.append(f'- {sc["now"]} ({sc["model_version"]}), {sc["position_percentile"]}th percentile'
                     + (f'; previous {sc["before"]}' if sc["before"] is not None else ""))
    else:
        lines.append("- no stored score yet (add experience text on Profile)")
    lines.append("**Top matches**")
    lines += [f'- {m["company"]} — {m["title"]} ({m["location"]}){" (unverified)" if m["status"] == "unverified" else ""}'
              for m in d["top_matches"]] or ["- none passing the screen"]
    lines.append("**Market this week**")
    lines.append(f'- {d["new_postings_7d"]} new postings in 7 days; {d["passing_total"]} pass your screen')
    lines.append("**Waiting for your decision**")
    lines += [f"- {t}" for t in d["pending_decisions"]] or ["- nothing"]
    return "\n".join(lines)


def write(db: Session, run_id: int | None, user: User, data: dict) -> Brief:
    body, model = None, ""
    try:
        body = complete(SYSTEM, "DATA:\n" + json.dumps(data, default=str), max_tokens=900, role="critical", agent="analyst", run_id=run_id)
        model = model_for("critical") if body else ""
    except BudgetExceeded:
        body = None
    if not body:
        body, model = fallback_text(data), "template (no model)"
    check = checker.check_brief(body, data, run_id)
    b = Brief(run_id=run_id or 0, user_id=user.id, body=body, data=data, model=model, check=check)
    db.add(b)
    db.commit()
    return b
