"""Level assessor. Titles mislead ("Regional Manager" can run a region; "Director" can be a single-market seller), so the
real seniority is judged from the full description on the employer's own posting: scope, team, revenue ownership,
reporting line, experience required and pay. Evidence must be quoted verbatim; otherwise the title's band is kept."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm import BudgetExceeded, complete_json
from ..models import Posting
from ..taxonomy import LEVEL_RANK, LEVELS, infer_level

SYSTEM = f"""You judge the real seniority of a job from its description, not from its title.
Bands, lowest to highest: {", ".join(LEVELS)}. ("Head" sits with Director.)
Weigh: scope (one country, a multi-country region, or global); whether it leads a team and of whom (managers, or individual
contributors); ownership of revenue or P&L and its size; reporting line; years of experience required; stated pay;
decision rights (strategy, market entry, hiring). A role that runs a multi-country region with a team and regional revenue
is usually Director or above whatever its title says; a single-market individual seller is usually below Director.
Quote evidence exactly as written in the description (contiguous substrings). If the description is thin, use low confidence.
Return JSON only: {{"band": "<one band>", "scope": "country"|"regional"|"global"|"unknown", "confidence": "high"|"medium"|"low",
"evidence": ["<quote>", ...up to 4], "summary": "<one line, plain words>"}}"""


def _ladder(company: str) -> str:
    from ..db import SessionLocal
    from ..models import CompanyLevel

    with SessionLocal() as db:
        c = db.scalar(select(CompanyLevel).where(CompanyLevel.company == company))
        return c.ladder if c and c.ladder else ""


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


def assess(p: Posting, run_id: int | None = None) -> dict | None:
    if len((p.description or "").strip()) < 400:
        return None
    ladder = _ladder(p.company)
    hint = f"Company level ladder (Levels.fyi, a hint only): {ladder}\n" if ladder else ""
    res = complete_json(SYSTEM, f"Title: {p.title}\nCompany: {p.company}\nLocation: {p.location}\nPay: {p.pay_range or 'not stated'}\n{hint}\n"
                                f"{p.description[:20000]}", max_tokens=700, role="research", agent="level", run_id=run_id)
    if not res or res.get("band") not in LEVEL_RANK:
        return None
    desc = _norm(p.description)
    quotes = [q for q in (res.get("evidence") or []) if isinstance(q, str) and len(q) > 15 and _norm(q) in desc][:4]
    conf = res.get("confidence") if res.get("confidence") in ("high", "medium", "low") else "low"
    if not quotes:
        conf = "low"  # no verifiable evidence: do not override the title
    return {"band": res["band"], "scope": res.get("scope") if res.get("scope") in ("country", "regional", "global") else "unknown",
            "confidence": conf, "evidence": quotes, "summary": str(res.get("summary") or "")[:300],
            "title_band": infer_level(p.title), "hash": p.content_hash}


def apply(p: Posting, a: dict) -> None:
    rc = dict(p.read_check or {})
    rc["level"] = a
    p.read_check = rc
    if a["confidence"] in ("high", "medium"):
        p.level_band = a["band"]
        if a["scope"] != "unknown":
            p.scope = a["scope"]


def run(db: Session, run_id: int | None, limit: int = 60) -> dict:
    todo = [p for p in db.scalars(select(Posting).where(Posting.status.in_(("open", "unverified"))).order_by(Posting.id.desc()))
            if len((p.description or "").strip()) >= 400 and ((p.read_check or {}).get("level") or {}).get("hash") != p.content_hash][:limit]
    done = changed = 0
    for p in todo:
        before = p.level_band
        try:
            a = assess(p, run_id)
        except BudgetExceeded as err:
            db.commit()
            return {"assessed": done, "level_changed": changed, "stopped": str(err)}
        if a is None:
            continue
        apply(p, a)
        done += 1
        changed += p.level_band != before
        db.commit()
    return {"assessed": done, "level_changed": changed, "remaining": max(0, len(todo) - done)}
