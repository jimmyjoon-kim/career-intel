from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..db import get_db
from ..extract import extract_cv
from ..models import Profile, User
from ..parsing import file_to_text
from ..rag.index import safe_rebuild_user as rebuild_user
from ..schemas import ProfileIn, RoleReviewIn, TagMatchIn
from ..security import current_user
from ..services import ensure_profile
from ..taxonomy import LEVELS, TAGS
from ..v2.service import merge_experience_tags, user_features


def _refresh_experience(prof: Profile) -> None:
    merge_experience_tags(prof, user_features(prof))
    flag_modified(prof, "tag_matches")

router = APIRouter(prefix="/api/profile", tags=["profile"])

MAX_UPLOAD = 5 * 1024 * 1024


def profile_dict(p: Profile) -> dict:
    return {
        "headline": p.headline, "cv_text": p.cv_text, "experience_text": p.experience_text or "",
        "target_date": p.target_date or "", "has_photo": bool(p.photo), "years_experience": p.years_experience,
        "tag_matches": p.tag_matches or {}, "min_level": p.min_level, "locations": p.locations or [],
        "remote_ok": p.remote_ok, "needs_sponsorship": p.needs_sponsorship,
        "excluded_title_terms": p.excluded_title_terms or [],
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _apply_cv(db: Session, user: User, prof: Profile, text: str) -> dict:
    result = extract_cv(text)
    # User-confirmed matches survive re-extraction.
    kept = {k: v for k, v in (prof.tag_matches or {}).items() if v.get("source") == "user"}
    prof.cv_text = text
    prof.tag_matches = {**result["tags"], **kept}
    flag_modified(prof, "tag_matches")
    if result["headline"] and not prof.headline:
        prof.headline = result["headline"]
    if result["years_experience"] and prof.years_experience is None:
        prof.years_experience = int(result["years_experience"])
    _refresh_experience(prof)
    db.commit()
    rebuild_user(db, user)
    return {"profile": profile_dict(prof), "extraction_mode": result["mode"], "tags_found": len(result["tags"])}


@router.get("")
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return profile_dict(ensure_profile(db, user))


@router.get("/taxonomy")
def taxonomy():
    return {
        "levels": LEVELS,
        "tags": [{"key": t.key, "label": t.label, "group": t.group, "closable": t.closable} for t in TAGS.values()],
    }


@router.put("")
def update_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    prof = ensure_profile(db, user)
    data = body.model_dump(exclude_none=True)
    if "min_level" in data and data["min_level"] not in LEVELS:
        raise HTTPException(422, f"min_level must be one of {LEVELS}")
    cv = data.pop("cv_text", None)
    old_locations = list(prof.locations or [])
    for k, v in data.items():
        setattr(prof, k, v)
    search_note = None
    if "locations" in data and sorted(data["locations"]) != sorted(old_locations):
        from ..agents.coordinator import enqueue

        enqueue(db, "locations", trigger="event", user_id=user.id)
        search_note = "Locations changed: a search for postings in your locations has started; results appear in a few minutes."
    if "experience_text" in data:
        _refresh_experience(prof)
    db.commit()
    if cv is not None and cv.strip() != (prof.cv_text or "").strip():
        return _apply_cv(db, user, prof, cv.strip())
    rebuild_user(db, user)
    return {"profile": profile_dict(prof), **({"note": search_note} if search_note else {})}


@router.post("/cv")
async def upload_cv(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 5 MB)")
    text = file_to_text(file.filename or "", data)
    if len(text) < 200:
        raise HTTPException(422, "Could not read enough text from this file. Try a text-based PDF or DOCX.")
    return _apply_cv(db, user, ensure_profile(db, user), text)


@router.put("/tags/{tag}")
def set_tag(tag: str, body: TagMatchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if tag not in TAGS:
        raise HTTPException(404, "Unknown tag")
    prof = ensure_profile(db, user)
    m = 1.0 if body.match >= 1 else 0.5 if body.match >= 0.5 else 0.0
    matches = dict(prof.tag_matches or {})
    matches[tag] = {"match": m, "evidence": body.evidence[:500], "source": "user"}
    prof.tag_matches = matches
    flag_modified(prof, "tag_matches")
    db.commit()
    rebuild_user(db, user)
    return profile_dict(prof)


QUAL_GROUPS = [
    ("Function", ["func_partnerships", "func_channel", "func_bd", "func_sales_leadership"]),
    ("Management scope", ["team_mgmt", "team_large", "pnl_ownership"]),
    ("Domain", ["domain_adtech", "domain_mobile", "domain_ai", "domain_saas"]),
    ("Scarce experience", ["skill_0to1_build", "skill_hyperscaler", "skill_govtech", "skill_consulting_firm_background"]),
]


def _roles_payload(prof: Profile) -> dict:
    from ..v2.model import TAG_LABELS

    feats = user_features(prof)
    return {
        "qualifications": [{"group": g, "tags": [{"tag": t, "label": TAG_LABELS[t]} for t in tags]} for g, tags in QUAL_GROUPS],
        "roles": feats["roles"] if feats else [],
        "reviewed": sum(1 for r in (feats["roles"] if feats else []) if r["reviewed"]),
    }


@router.get("/roles")
def get_roles(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _roles_payload(ensure_profile(db, user))


@router.put("/roles/{key:path}")
def review_role(key: str, body: RoleReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..v2.reader import ALL_TAGS

    prof = ensure_profile(db, user)
    feats = user_features(prof)
    if not feats or key not in {r["key"] for r in feats["roles"]}:
        raise HTTPException(404, "Role not found in your experience text")
    bad = [t for t in body.tags if t not in ALL_TAGS]
    if bad:
        raise HTTPException(422, f"Unknown qualification: {', '.join(bad)}")
    reviews = dict(prof.role_reviews or {})
    reviews[key] = {"tags": {t: (None if v is None else (1.0 if v >= 1 else 0.5 if v >= 0.5 else 0.0)) for t, v in body.tags.items()},
                    "team_size": body.team_size, "confirmed": body.confirmed}
    prof.role_reviews = reviews
    flag_modified(prof, "role_reviews")
    _refresh_experience(prof)
    db.commit()
    rebuild_user(db, user)
    return _roles_payload(prof)


@router.post("/refresh")
def refresh(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Re-read your experience, re-apply your role review, rescore and rebuild your Ask index."""
    prof = ensure_profile(db, user)
    _refresh_experience(prof)
    db.commit()
    index = rebuild_user(db, user)
    feats = user_features(prof)
    from ..agents.snapshots import take

    snap = take(db, user, None)  # event-driven rescore: stored with the model version
    return {"ok": True, "roles_read": len(feats["roles"]) if feats else 0, "index": index,
            "score": snap.score if snap else None}


PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO = 600 * 1024


@router.post("/photo")
async def upload_photo(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    import base64

    data = await file.read()
    ctype = file.content_type or ""
    sig = data[:12]
    if sig.startswith(b"\xff\xd8"):
        ctype = "image/jpeg"
    elif sig.startswith(b"\x89PNG"):
        ctype = "image/png"
    elif sig[:4] == b"RIFF" and sig[8:12] == b"WEBP":
        ctype = "image/webp"
    if ctype not in PHOTO_TYPES:
        raise HTTPException(422, "Use a JPEG, PNG or WebP image.")
    if len(data) > MAX_PHOTO:
        raise HTTPException(413, "Image too large (max 600 KB). A square photo of about 400 pixels is enough.")
    prof = ensure_profile(db, user)
    prof.photo = f"data:{ctype};base64,{base64.b64encode(data).decode()}"
    db.commit()
    return profile_dict(prof)


@router.delete("/photo")
def delete_photo(user: User = Depends(current_user), db: Session = Depends(get_db)):
    prof = ensure_profile(db, user)
    prof.photo = ""
    db.commit()
    return profile_dict(prof)



@router.get("/evidence")
def list_evidence(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..models import EvidenceSuggestion

    rows = db.scalars(select(EvidenceSuggestion).where(EvidenceSuggestion.user_id == user.id)
                      .order_by(EvidenceSuggestion.status != "pending", EvidenceSuggestion.postings.desc()).limit(60))
    return [{"id": e.id, "tag": e.tag, "label": e.label, "match": e.match, "quote": e.quote, "source": e.source,
             "postings": e.postings, "status": e.status} for e in rows]


@router.post("/evidence/find")
def find_evidence(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..agents.evidence import run_for_user

    ensure_profile(db, user)
    return run_for_user(db, user)


class EvidenceDecision(BaseModel):
    confirm: bool


@router.post("/evidence/{sid}")
def decide_evidence(sid: int, body: EvidenceDecision, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..agents.evidence import decide
    from ..agents.snapshots import take

    try:
        s = decide(db, user, sid, body.confirm)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    snap = take(db, user, None) if body.confirm else None
    return {"ok": True, "status": s.status, "score": snap.score if snap else None}
