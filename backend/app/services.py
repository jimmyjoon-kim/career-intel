from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Posting, Profile, User
from .scoring import PostingView, ProfileView, gap_summary, gate, market_stats, rank_key, score


def posting_view(p: Posting) -> PostingView:
    return PostingView(
        id=p.id, company=p.company, title=p.title, level_band=p.level_band, role_cluster=p.role_cluster,
        location=p.location, remote_flag=p.remote_flag, bay_area=p.bay_area, no_sponsorship=p.no_sponsorship,
        status=p.status, tags=list(p.tags or []), years_required=p.years_required,
    )


def profile_view(prof: Profile | None) -> ProfileView:
    if prof is None:
        return ProfileView()
    return ProfileView(
        min_level=prof.min_level, locations=list(prof.locations or []), remote_ok=prof.remote_ok,
        needs_sponsorship=prof.needs_sponsorship, excluded_title_terms=list(prof.excluded_title_terms or []),
        years_experience=prof.years_experience,
        matches={k: float(v.get("match", 0)) for k, v in (prof.tag_matches or {}).items()},
    )


def ensure_profile(db: Session, user: User) -> Profile:
    if user.profile is None:
        user.profile = Profile(user_id=user.id)
        db.add(user.profile)
        db.commit()
        db.refresh(user)
    return user.profile


def all_postings(db: Session) -> list[Posting]:
    return list(db.scalars(select(Posting).order_by(Posting.company, Posting.title)))


def current_market(db: Session) -> tuple[list[Posting], dict]:
    postings = all_postings(db)
    return postings, market_stats([posting_view(p) for p in postings])


def evaluate(db: Session, user: User) -> dict:
    """Gate and score every posting for this user."""
    postings, stats = current_market(db)
    prof = profile_view(user.profile)
    rows = []
    for p in postings:
        pv = posting_view(p)
        ok, reasons = gate(pv, prof)
        result = score(pv, prof, stats)
        rows.append({"posting": p, "gate_pass": ok, "gate_reasons": reasons, **result})
    passing = sorted((r for r in rows if r["gate_pass"]), key=rank_key)
    return {
        "stats": stats,
        "rows": rows,
        "passing": passing,
        "gap_summary": gap_summary(passing),
    }


def posting_dict(p: Posting) -> dict:
    return {
        "id": p.id, "company": p.company, "title": p.title, "level_band": p.level_band,
        "role_cluster": p.role_cluster, "location": p.location, "remote_flag": p.remote_flag,
        "bay_area": p.bay_area, "pay_range": p.pay_range, "auth_text": p.auth_text,
        "no_sponsorship": p.no_sponsorship, "scope": p.scope, "years_required": p.years_required,
        "tags": p.tags, "url": p.url, "posted": p.posted, "status": p.status,
        "verification": p.verification, "last_seen": p.last_seen,
    }


def row_dict(r: dict) -> dict:
    return {
        "posting": posting_dict(r["posting"]),
        "gate_pass": r["gate_pass"], "gate_reasons": r["gate_reasons"],
        "cluster": r["cluster"], "weighted_score": r["weighted_score"], "rank_score": r["rank_score"],
        "has_zero_hard_gap": r["has_zero_hard_gap"], "hard_gaps": r["hard_gaps"], "gaps": r["gaps"],
    }
