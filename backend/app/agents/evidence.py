"""Evidence finder (RAG). For requirements that open postings ask for and your profile does not yet show, search your
own experience and CV text for supporting lines. A small model judges each candidate line; a suggestion is kept only
if its quote appears verbatim in your text. Nothing changes until you confirm it."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..llm import BudgetExceeded, complete_json, llm_available
from ..models import EvidenceSuggestion, Profile, User
from ..rag.index import search
from ..services import evaluate
from ..taxonomy import TAGS

MAX_TAGS = 12
JUDGE = """You check whether a candidate's own text evidences one job requirement.
Use ONLY the excerpts given. Quote the single most relevant line exactly as written (a contiguous substring).
match: 1 = clearly evidenced, 0.5 = partial or indirect, 0 = not evidenced. Never infer beyond the text.
Return JSON: {"match": 0|0.5|1, "quote": "<exact substring or empty>", "excerpt": <number of the excerpt quoted>}"""


def _norm(s: str) -> str:
    return " ".join(s.replace("•", " ").split()).lower()


def missing_tags(ev: dict, prof: Profile) -> list[tuple[str, int]]:
    """Requirement tags asked by gate-passing postings where your match is below 1, most-asked first."""
    have = {t: float(v.get("match", 0)) for t, v in (prof.tag_matches or {}).items()}
    c: Counter = Counter()
    for r in ev["passing"]:
        for t in r["posting"].tags or []:
            if t in TAGS and have.get(t, 0) < 1:
                c[t] += 1
    return c.most_common()


def run_for_user(db: Session, user: User, run_id: int | None = None) -> dict:
    prof = user.profile
    if not prof or not llm_available():
        return {"user_id": user.id, "skipped": "no profile" if not prof else "no API key"}
    ev = evaluate(db, user)
    decided = {(e.tag) for e in db.scalars(select(EvidenceSuggestion).where(EvidenceSuggestion.user_id == user.id))}
    todo = [(t, n) for t, n in missing_tags(ev, prof) if t not in decided][:MAX_TAGS]
    made, checked = 0, 0
    for tag, n in todo:
        t = TAGS[tag]
        hits = search(db, user.id, f"{t.label}. " + " ".join(p.replace("\\b", "") for p in t.patterns[:6]), k=4,
                      types=("experience", "cv", "linkedin"), own_only=True)
        if not hits:
            continue
        excerpts = "\n\n".join(f"[{i}] {c.title}\n{c.text}" for i, (c, _) in enumerate(hits, 1))
        try:
            res = complete_json(JUDGE, f"Requirement: {t.label} ({tag})\n\nExcerpts:\n{excerpts}", max_tokens=300,
                                role="bulk", agent="evidence", run_id=run_id) or {}
        except BudgetExceeded as err:
            return {"user_id": user.id, "checked": checked, "suggested": made, "stopped": str(err)}
        checked += 1
        quote, match = (res.get("quote") or "").strip(), float(res.get("match") or 0)
        # Guardrail: keep only a real quote from your own text, attributed to the excerpt that contains it.
        src = next((c for c, _ in hits if _norm(quote) in _norm(c.text)), None) if len(quote) >= 12 else None
        if match <= 0 or src is None:
            continue
        db.add(EvidenceSuggestion(user_id=user.id, tag=tag, label=t.label, match=1.0 if match >= 1 else 0.5,
                                  quote=quote[:600], source=src.title[:200], postings=n))
        made += 1
    db.commit()
    return {"user_id": user.id, "missing_tags": len(todo), "checked": checked, "suggested": made}


def run(db: Session, run_id: int | None) -> dict:
    return {"users": [run_for_user(db, u, run_id) for u in db.scalars(select(User).join(Profile))]}


def decide(db: Session, user: User, sid: int, confirm: bool) -> EvidenceSuggestion:
    s = db.get(EvidenceSuggestion, sid)
    if not s or s.user_id != user.id or s.status != "pending":
        raise LookupError("no pending suggestion with that id")
    s.status = "confirmed" if confirm else "rejected"
    if confirm:
        prof = user.profile
        tm = dict(prof.tag_matches or {})
        if float((tm.get(s.tag) or {}).get("match", 0)) < s.match:
            tm[s.tag] = {"match": s.match, "source": "user", "evidence": f'Confirmed from {s.source}: "{s.quote}"'[:500]}
            prof.tag_matches = tm
            flag_modified(prof, "tag_matches")
    db.commit()
    return s
