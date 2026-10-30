"""Scoring step (plain code, no model). Computes each user's scorecard and stores it with the model version."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Profile, ScoreSnapshot, User
from ..v2.model import MODEL_VERSION
from ..v2.service import scorecard


def factor_rows(card: dict) -> list[dict]:
    tw = sum(f["weight"] or 0 for f in card["factors"] if f["you_pct"] is not None) or 1
    return [{"factor": f["factor"], "label": f["label"], "percentile": f["you_pct"], "weight": f["weight"],
             "points": round((f["weight"] or 0) * (f["you_pct"] or 0) / tw, 2) if f["you_pct"] is not None else None}
            for f in card["factors"]]


def take(db: Session, user: User, run_id: int | None) -> ScoreSnapshot | None:
    card, _, _ = scorecard(db, user.profile, n_boot=200)
    if card is None:
        return None
    snap = ScoreSnapshot(user_id=user.id, run_id=run_id, model_version=MODEL_VERSION, score=card["base_score"],
                         position=card["position"], factors=factor_rows(card))
    db.add(snap)
    db.commit()
    return snap


def run(db: Session, run_id: int | None) -> dict:
    users = list(db.scalars(select(User).join(Profile)))
    made = [s for s in (take(db, u, run_id) for u in users) if s]
    return {"users": len(users), "snapshots": len(made), "model_version": MODEL_VERSION}


def previous(db: Session, user_id: int, before_id: int) -> ScoreSnapshot | None:
    return db.scalar(select(ScoreSnapshot).where(ScoreSnapshot.user_id == user_id, ScoreSnapshot.id < before_id)
                     .order_by(ScoreSnapshot.id.desc()))
