from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Posting, Profile, User
from .v2.model import opportunity, public
from .v2.service import SHARED_TAGS, scorecard
from .scoring import gate_split, PostingView, ProfileView, gap_summary, gate, market_stats, rank_key, score


def _tags_with_geo(p: Posting) -> list[str]:
    from .v2.geo import posting_geo_cached

    from .v2.segment import posting_segment_cached

    tags = [t for t in (p.tags or []) if not t.startswith(("geo_", "seg_"))]
    extra = list(posting_geo_cached(p)["tags"]) + list(posting_segment_cached(p))
    return tags + [t for t in extra if t not in tags]


def posting_view(p: Posting) -> PostingView:
    return PostingView(
        id=p.id, company=p.company, title=p.title, level_band=p.level_band, role_cluster=p.role_cluster,
        location=p.location, remote_flag=p.remote_flag, bay_area=p.bay_area, no_sponsorship=p.no_sponsorship,
        status=p.status, tags=_tags_with_geo(p), years_required=p.years_required, scope=p.scope or "",
    )


def profile_view(prof: Profile | None, feats: dict | None = None) -> ProfileView:
    if prof is None:
        return ProfileView()
    # A requirement shown only by a keyword somewhere in the CV counts as partial; full credit needs a role description
    # (reader evidence), Role review, or your own confirmation.
    matches = {k: (min(0.5, float(v.get("match", 0))) if v.get("source") == "keyword" else float(v.get("match", 0)))
               for k, v in (prof.tag_matches or {}).items()}
    user_set = {k for k, v in (prof.tag_matches or {}).items() if v.get("source") == "user"}
    if feats:  # evidence read from full experience text raises (never lowers) CV keyword matches
        for t in SHARED_TAGS:
            if t not in user_set and feats["tags"].get(t, 0) > matches.get(t, 0):
                matches[t] = feats["tags"][t]
    years = prof.years_experience
    if years is None and feats:
        years = int(feats["YOE_raw"])
    return ProfileView(
        min_level=prof.min_level, locations=list(prof.locations or []), remote_ok=prof.remote_ok,
        needs_sponsorship=prof.needs_sponsorship, excluded_title_terms=list(prof.excluded_title_terms or []),
        work_auth=dict(prof.work_auth or {}), exclude_country_scope=bool(prof.exclude_country_scope),
        target_roles=list(prof.target_roles or []),
        years_experience=years,
        matches=matches,
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
    from .v2 import families

    postings, stats = current_market(db)
    card, feats, _ = scorecard(db, user.profile, n_boot=0)
    # One peer group per role family that has enough holders; each posting is scored against its own family's group.
    fams = [f for f in families.all_families(db)]
    ready = {f["key"] for f in families.status(db) if f["state"] == "ready"}
    cards = {"Partnerships": card} if card else {}
    for k in ready - set(cards):
        c, _, _ = scorecard(db, user.profile, n_boot=0, cluster=k)
        if c:
            cards[k] = c
    prof = profile_view(user.profile, feats)
    from dataclasses import replace as _replace

    from .v2.market import adjust as market_adjust, effective_months, posting_market

    mroles, R, eff_cache = (feats or {}).get("_market_roles") or [], int((feats or {}).get("multi_months") or 0), {}
    rows = []
    for p in postings:
        pv = posting_view(p)
        hard, soft = gate_split(pv, prof)
        ok, reasons = not (hard or soft), hard + soft
        pm = posting_market(p.title, p.location or "", "geo_multi_region" in pv.tags)
        key = (pm["market"], pm["country"])
        if key not in eff_cache:
            eff_cache[key] = effective_months(mroles, pm["market"], pm["country"])
        eff = eff_cache[key]
        has_us_req = "geo_us_market" in pv.tags
        view = prof
        if has_us_req and pm["market"] == "US" and eff.get("E") is not None:
            # a stated US-market requirement is scored from your effective US months, not a keyword
            view = _replace(prof, matches={**prof.matches, "geo_us_market": round(min(eff["E"] / 24, 1.0), 2)})
        result = score(pv, view, stats)
        result["rank_score"], result["market_fit"] = market_adjust(result["rank_score"], pm, eff, has_us_req, R,
                                                                         multi_scored="geo_multi_region" in pv.tags)
        opp = None
        own = [f["key"] for f in fams if families.in_family(p, f)]
        fam = next((k for k in own if k in cards), None)
        use = cards.get(fam) if fam else card
        if use:
            ctab = stats["clusters"].get(result["cluster"], stats["all"])["tags"]
            opp = opportunity(use, pv.tags, {t: i["weight"] for t, i in ctab.items()},
                              posting_level=pv.level_band, years_required=pv.years_required)
            opp["peer_group"] = fam or "Partnerships"
            opp["peer_group_note"] = ("" if fam else f"No peer group for {own[0] if own else 'this role'} yet; "
                                      "scored against Partnerships holders.")
        rows.append({"posting": p, "gate_pass": ok, "gate_reasons": reasons, "hard_reasons": hard, "soft_reasons": soft,
                     "opportunity": opp, **result})
    passing = sorted((r for r in rows if r["gate_pass"]), key=rank_key)
    # Outside your stated preferences (level, location, scope, function, unconfirmed) but not ruled out: ranked by fit.
    adjacent = sorted((r for r in rows if not r["gate_pass"] and not r["hard_reasons"]), key=rank_key)
    return {
        "stats": stats,
        "rows": rows,
        "passing": passing,
        "adjacent": adjacent,
        "gap_summary": gap_summary(passing),
        "base": public(card) if card else None,
        "_cards": cards,
    }


def for_family(db: Session, ev: dict, family: str | None) -> dict:
    """The same evaluation limited to one role family's postings: its screen results, adjacent postings and gaps."""
    if not family:
        return ev
    from .v2.families import family as get_family, in_family

    fam = get_family(db, family)
    keep = lambda r: in_family(r["posting"], fam)  # noqa: E731
    passing = [r for r in ev["passing"] if keep(r)]
    c = ev.get("_cards", {}).get(fam["key"])
    return {**ev, "base": public(c) if c else None, "rows": [r for r in ev["rows"] if keep(r)], "passing": passing,
            "adjacent": [r for r in ev["adjacent"] if keep(r)], "gap_summary": gap_summary(passing), "family": fam["key"]}


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
        "opportunity": r.get("opportunity"), "market_fit": r.get("market_fit"),
        "not_read": r.get("not_read", False), "requirements_read": r.get("requirements_read", 0),
    }
