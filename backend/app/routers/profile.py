from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from ..db import get_db
from ..extract import extract_cv
from ..models import Profile, User
from ..parsing import file_to_text
from ..rag.index import rebuild_user
from ..schemas import ProfileIn, TagMatchIn
from ..security import current_user
from ..services import ensure_profile
from ..taxonomy import LEVELS, TAGS

router = APIRouter(prefix="/api/profile", tags=["profile"])

MAX_UPLOAD = 5 * 1024 * 1024


def profile_dict(p: Profile) -> dict:
    return {
        "headline": p.headline, "cv_text": p.cv_text, "years_experience": p.years_experience,
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
    for k, v in data.items():
        setattr(prof, k, v)
    db.commit()
    if cv is not None and cv.strip() != (prof.cv_text or "").strip():
        return _apply_cv(db, user, prof, cv.strip())
    rebuild_user(db, user)
    return {"profile": profile_dict(prof)}


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
