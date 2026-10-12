from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Question, User
from ..rag.answer import answer
from ..schemas import AskIn
from ..security import current_user

router = APIRouter(prefix="/api/ask", tags=["ask"])


@router.post("")
def ask(body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    result = answer(db, user.id, body.question.strip())
    q = Question(user_id=user.id, question=body.question.strip(), answer=result["answer"],
                 sources=result["sources"], mode=result["mode"])
    db.add(q)
    db.commit()
    return {"id": q.id, **result}


@router.get("/history")
def history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    qs = db.scalars(select(Question).where(Question.user_id == user.id).order_by(Question.id.desc()).limit(30))
    return [{"id": q.id, "question": q.question, "answer": q.answer, "sources": q.sources, "mode": q.mode,
             "created_at": q.created_at.isoformat()} for q in qs]
