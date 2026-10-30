from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents import ask_agent
from ..db import get_db
from ..llm import llm_available
from ..models import Question, User
from ..rag.answer import answer
from ..schemas import AskIn
from ..security import current_user

router = APIRouter(prefix="/api/ask", tags=["ask"])


@router.post("")
def ask(body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    question = body.question.strip()
    result, note = {}, ""
    if llm_available():
        try:
            result = ask_agent.answer(db, user, question)
        except Exception as err:  # noqa: BLE001 — fall back to the cited-sources answer
            db.rollback()
            note = f"(The agent could not answer: {type(err).__name__}: {str(err)[:200]}. Answer from cited sources instead.)\n"
    if not result:
        result = answer(db, user.id, question)
        result["answer"] = note + result["answer"]
    steps = result.get("steps") or []
    q = Question(user_id=user.id, question=question, answer=result["answer"],
                 sources=result["sources"] + ([{"steps": steps}] if steps else []), mode=result["mode"])
    db.add(q)
    db.commit()
    return {"id": q.id, **result}


@router.get("/history")
def history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    qs = db.scalars(select(Question).where(Question.user_id == user.id).order_by(Question.id.desc()).limit(30))
    out = []
    for q in qs:
        src = [s for s in (q.sources or []) if "steps" not in s]
        steps = next((s["steps"] for s in (q.sources or []) if "steps" in s), [])
        out.append({"id": q.id, "question": q.question, "answer": q.answer, "sources": src, "steps": steps, "mode": q.mode,
                    "created_at": q.created_at.isoformat()})
    return out
