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
