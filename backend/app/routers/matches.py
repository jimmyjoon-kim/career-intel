from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..matches import build, web_search
from ..models import User
from ..security import current_user
from ..services import ensure_profile, evaluate, profile_view
from ..v2.model import TAG_LABELS
from ..v2.service import user_features

router = APIRouter(prefix="/api/matches", tags=["matches"])


class SearchIn(BaseModel):
    query: str = Field(min_length=3, max_length=300)


@router.get("")
def get_matches(user: User = Depends(current_user), db: Session = Depends(get_db)):
    prof = ensure_profile(db, user)
    ev = evaluate(db, user)
    feats = user_features(prof)
    out = build(ev, feats, profile_view(prof, feats).matches)
    base = ev.get("base")
    for t in out["role_types"]:
        t["holders"] = ({"n": base["n_reference"], "position": base["position"], "median": base["holders"]["median"],
                         "your_score": base["base_score"]} if base and t["cluster"] == base["cluster"] else None)
    return out


@router.post("/search")
def search(body: SearchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    prof = ensure_profile(db, user)
    f = user_features(prof)
    if f:
        strengths = ", ".join(TAG_LABELS[t] for t, v in f["tags"].items() if v >= 1 and t in TAG_LABELS)
        rr = f["recent_role"]
        summary = (f"{f['YOE_raw']} years; recent role {rr['title']} at {rr['company']}; " if rr else "") + f"strengths: {strengths}."
    else:
        summary = prof.headline or "No profile text."
    prefs = f" Locations: {', '.join(prof.locations or [])}; remote {'OK' if prof.remote_ok else 'not OK'}; minimum level {prof.min_level}."
    return web_search(body.query, summary + prefs)


STAGES = ("saved", "dismissed", "applied", "interview", "offer", "rejected")


class OutcomeIn(BaseModel):
    posting_id: int
    stage: str
    fit: float | None = None
    note: str = Field(default="", max_length=300)


@router.get("/outcomes")
def list_outcomes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Your latest recorded stage per posting."""
    from sqlalchemy import select

    from ..models import Outcome

    latest: dict[int, dict] = {}
    for o in db.scalars(select(Outcome).where(Outcome.user_id == user.id).order_by(Outcome.at)):
        latest[o.posting_id] = {"posting_id": o.posting_id, "stage": o.stage, "at": o.at.isoformat(timespec="minutes"), "note": o.note}
    return {"stages": STAGES, "outcomes": list(latest.values())}


@router.post("/outcomes")
def record_outcome(body: OutcomeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Record what you did with a posting. Each stage is kept (a history), with the fit and model version at the time."""
    from fastapi import HTTPException

    from ..models import Outcome, Posting
    from ..v2.model import MODEL_VERSION

    if body.stage not in STAGES:
        raise HTTPException(422, f"stage must be one of {STAGES}")
    if db.get(Posting, body.posting_id) is None:
        raise HTTPException(404, "Posting not found")
    db.add(Outcome(user_id=user.id, posting_id=body.posting_id, stage=body.stage, fit=body.fit,
                   model_version=MODEL_VERSION, note=body.note))
    db.commit()
    return {"recorded": body.stage}
