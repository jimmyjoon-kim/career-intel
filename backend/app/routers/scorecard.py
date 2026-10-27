from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import current_user
from ..services import ensure_profile
from ..v2.model import public
from ..v2.reader import LEVEL_NAMES
from ..v2.service import months_left, reference_meta, scorecard

router = APIRouter(prefix="/api/scorecard", tags=["scorecard"])


@router.get("")
def get_scorecard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    prof = ensure_profile(db, user)
    card, feats, reason = scorecard(db, prof)
    if card is None:
        return {"ready": False, "reason": reason}
    return {
        "ready": True,
        "card": public(card),
        "reference": reference_meta(db),
        "months_left": months_left(prof.target_date or ""),
        "reading": {
            "source": feats["source"], "format": feats["format"], "years": feats["YOE_raw"],
            "recent_role": feats["recent_role"], "level_max": LEVEL_NAMES.get(feats["LV_max"]) if feats["LV_max"] is not None else None,
            "level_names": LEVEL_NAMES, "roles": feats["roles"], "evidence": feats["evidence"],
            "achievements": feats["achievements"], "tags": feats["tags"], "team_size_max": feats["team_size_max"],
        },
        "notes": [
            "Reference = people recently hired into US Partnerships roles; the only cluster collected so far.",
            "Education is not scored: holder education coverage is 0%.",
            "Title-implied scope (a GM runs the unit's team and P&L) and employer context apply to holders and to you alike. "
            "Facts you state on a 'Scope:' line and CV lines exist only for you, so team size is shown but not scored.",
            "Company tiers come from a rule-based list, not a dated market-cap table.",
            "Market weights come from one run of 90 hires; they will update as more hires are read.",
            "No probabilities or hire likelihoods are produced.",
        ],
    }
