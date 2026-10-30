from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import current_user
from ..services import ensure_profile, evaluate
from ..v2.gapplan import build_gap_plan
from ..v2.model import public
from ..v2.reader import LEVEL_NAMES
from ..v2.service import months_left, reference_meta, scorecard

router = APIRouter(prefix="/api/scorecard", tags=["scorecard"])


def _months_to_degree(feats: dict) -> int | None:
    from datetime import date

    ends = [d["end"] for d in feats.get("degrees", []) if d["in_progress"] and d["level"] >= 2 and d["end"]]
    if not ends:
        return None
    y, m = (int(x) for x in min(ends).split("-"))
    t = date.today()
    return max(0, (y - t.year) * 12 + (m - t.month))


@router.get("")
def get_scorecard(family: str = "Partnerships", user: User = Depends(current_user), db: Session = Depends(get_db)):
    prof = ensure_profile(db, user)
    card, feats, reason = scorecard(db, prof, cluster=family)
    if card is None:
        return {"ready": False, "reason": reason}
    left = months_left(prof.target_date or "")
    ev = evaluate(db, user)
    pub = public(card)
    pub["cards"]["you"]["photo"] = prof.photo or None
    pub["cards"]["you"]["name"] = user.name or "You"
    return {
        "ready": True,
        "card": pub,
        "gap_plan": build_gap_plan(card, ev["gap_summary"], left, _months_to_degree(feats)),
        "reference": reference_meta(db, family),
        "months_left": months_left(prof.target_date or ""),
        "reading": {
            "source": feats["source"], "format": feats["format"], "years": feats["YOE_raw"],
            "recent_role": feats["recent_role"], "level_max": LEVEL_NAMES.get(feats["LV_max"]) if feats["LV_max"] is not None else None,
            "level_names": LEVEL_NAMES, "roles": feats["roles"], "evidence": feats["evidence"],
            "achievements": feats["achievements"], "tags": feats["tags"], "team_size_max": feats["team_size_max"],
            "degrees": feats.get("degrees", []), "education_by_target": feats.get("ED_target"),
            "journey": feats.get("journey", []), "ct_basis": feats.get("CT_basis"), "ct_tier_only": feats.get("CT_tier_only"),
            "ai_work": [{"role": s["_label"], **s["ai"]} for s in feats.get("_signals", []) if s.get("ai")],
            "ai_degrees": feats.get("AI_degrees", []), "tk_parts": feats.get("TK_parts", {}),
        },
        "notes": [
            "Reference = people recently hired into US Partnerships roles; the only cluster collected so far.",
            "Education counts at a 5% weight by highest degree completed (bachelor's 1, master's/MBA/JD 2, doctorate 3); degrees in progress count from their completion date. School and graduation year are not scored.",
            "Title-implied scope (a GM runs the unit's team and P&L) and employer context apply to holders and to you alike. "
            "Facts you state on a 'Scope:' line and CV lines exist only for you, so team size is shown but not scored.",
            "Company tiers come from a rule-based list, not a dated market-cap table. Company tier & journey adds one step for a role that spanned an IPO or acquisition (joined 6+ months before); event dates are verified for ironSource, unverified for others.",
            "Current AI relevance: AI work counts fully only within the last 24 months (half at 24-36 months, 0.1 if older); an AI graduate degree adds up to 0.4 (half while in progress). Technical depth: technical degree, technical role in the last 15 years, technical product work. These weights are expert-set and not yet validated against hiring outcomes.",
            "Market weights come from one run of 90 hires; they will update as more hires are read.",
            "No probabilities or hire likelihoods are produced.",
        ],
    }


@router.get("/focus")
def get_focus(family: str = "Partnerships", user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Plain-language standing, you vs holders per factor, ranked actions with measured effect, and your edge."""
    from sqlalchemy import select

    from ..models import EvidenceSuggestion
    from ..services import profile_view
    from ..v2.focus import build

    prof = ensure_profile(db, user)
    card, feats, reason = scorecard(db, prof, n_boot=300, cluster=family)
    if card is None:
        return {"ready": False, "reason": reason}
    ev = evaluate(db, user)
    left = months_left(prof.target_date or "")
    plan = build_gap_plan(card, ev["gap_summary"], left, _months_to_degree(feats))
    pending = [{"tag": e.tag, "label": e.label, "quote": e.quote, "postings": e.postings}
               for e in db.scalars(select(EvidenceSuggestion).where(EvidenceSuggestion.user_id == user.id,
                                                                    EvidenceSuggestion.status == "pending"))]
    out = build(card, ev, profile_view(prof, feats), plan, pending, left, prof.target_date or "")
    return {"ready": True, **out}



@router.get("/relocation")
def get_relocation(family: str = "Partnerships", user: User = Depends(current_user), db: Session = Depends(get_db)):
    """APAC → US context: which US postings ask for US-market experience or value multi-region scope, measured effect."""
    from ..v2.geo import relocation_view
    from ..v2.service import user_features

    prof = ensure_profile(db, user)
    return relocation_view(db, prof, user_features(prof), evaluate(db, user), family)


@router.get("/families")
def list_families(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..v2 import families

    return {"families": families.status(db), "ready_at": families.READY_AT, "target": families.TARGET}


@router.get("/provisional")
def provisional(family: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..services import profile_view
    from ..v2 import families
    from ..v2.service import user_features

    prof = ensure_profile(db, user)
    fam = families.family(db, family)
    out = families.provisional(db, evaluate(db, user), profile_view(prof, user_features(prof)), fam)
    out["holders"] = families.holders(db, fam["key"])
    return out


class FamilyIn(BaseModel):
    name: str


@router.post("/families")
def add_family(body: FamilyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Name any role or position: it becomes a family with a provisional assessment, and holders are requested."""
    from ..v2 import families

    name = body.name.strip()
    if len(name) < 3:
        raise HTTPException(422, "Name the role, e.g. 'Head of Developer Relations'")
    fam = families.family(db, name)
    key = fam["key"] if fam["key"].lower() == name.lower() else name
    r = families.request_pool(db, key, user.id, "" if fam["key"].lower() == name.lower() else families._custom_pattern(name))
    return {"family": r.family, "status": r.status,
            "note": "Added. A provisional assessment from open postings is shown now; role holders will be collected by the "
                    "hire-research task on your Mac, and the full scorecard appears once you approve them."}
