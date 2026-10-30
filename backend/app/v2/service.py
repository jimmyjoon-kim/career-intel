"""Glue between the v2 model and the database."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Profile, ReferenceProfile
from .model import Reference, base_scorecard
from .reader import CV_PREFIX, SOURCE_ORDER, education_by, extract_features, parse_education, parse_roles

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
DEFAULT_CLUSTER = "Partnerships"
# Reader tags that are also posting-requirement tags: experience evidence feeds posting matches.
SHARED_TAGS = ["func_partnerships", "func_bd", "func_channel", "domain_adtech", "domain_ai", "domain_saas", "domain_mobile",
               "skill_hyperscaler", "skill_govtech", "skill_consulting_firm_background", "skill_0to1_build",
               "team_mgmt", "team_large", "pnl_ownership", "func_sales_leadership"]


def merge_experience_tags(prof: Profile, feats: dict | None) -> None:
    """Store reader evidence as requirement matches (source 'experience'); never overrides your own settings."""
    current = dict(prof.tag_matches or {})
    for k in [k for k, v in current.items() if v.get("source") == "experience"]:
        current.pop(k)
    if feats:
        best: dict[str, dict] = {}
        for e in feats["evidence"]:
            key = (e["weight"], -SOURCE_ORDER.get(e["source"], 9))
            if e["tag"] in SHARED_TAGS and (e["tag"] not in best or key > best[e["tag"]][0]):
                best[e["tag"]] = (key, e)
        best = {t: v[1] for t, v in best.items()}
        for t, e in best.items():
            prev = current.get(t)
            if prev and (prev.get("source") == "user" or float(prev.get("match", 0)) >= e["weight"]):
                continue
            current[t] = {"match": e["weight"], "source": "experience",
                          "evidence": f'{e["role"]}: "{e["phrase"]}" ({e["source"]})'[:500]}
    # Wider requirement taxonomy (deal structuring, executive presence, etc.): keyword pass over the same text.
    text, _ = experience_source(prof)
    if text:
        from ..taxonomy import keyword_tags

        for t, snip in keyword_tags(text.replace(CV_PREFIX, "")).items():
            if t not in current:
                current[t] = {"match": 1.0, "source": "experience", "evidence": f'keyword in experience text: "{snip}"'[:500]}
    if feats and feats.get("geo"):
        for t, (m, ev) in feats["geo"]["matches"].items():
            prev = current.get(t)
            if prev and (prev.get("source") == "user" or float(prev.get("match", 0)) >= m):
                continue
            current[t] = {"match": m, "source": "experience", "evidence": ev[:500]}
    prof.tag_matches = current


def import_reference_file(db: Session, path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    # A reference file replaces its whole cluster, so a re-read never leaves the previous rows behind.
    db.execute(delete(ReferenceProfile).where(ReferenceProfile.cluster == data["cluster"]))
    for r in data["rows"]:
        feats = {k: r.get(k) for k in ("YOE", "YOE_raw", "CT", "tier", "LV", "LV_max", "FN", "DM", "AC", "ED", "mba", "technical", "AI", "TK", "CT_tier_only")}
        feats["tags"] = r["tags"]
        db.add(ReferenceProfile(cluster=data["cluster"], company=r["company"], title=r["title"], features=feats,
                                source=data["source"], as_of=data.get("as_of", "")))
    db.commit()
    return len(data["rows"])


def import_reference_seed(db: Session) -> dict[str, int]:
    return {f.name: import_reference_file(db, f) for f in sorted(SEED_DIR.glob("reference_*.json"))}


def load_reference(db: Session, cluster: str = DEFAULT_CLUSTER) -> Reference | None:
    rows = list(db.scalars(select(ReferenceProfile).where(ReferenceProfile.cluster == cluster)))
    if not rows:
        return None
    return Reference(cluster, [{"company": r.company, "title": r.title, **r.features} for r in rows])


def reference_meta(db: Session, cluster: str = DEFAULT_CLUSTER) -> dict:
    r = db.scalars(select(ReferenceProfile).where(ReferenceProfile.cluster == cluster)).first()
    return {"source": r.source, "as_of": r.as_of} if r else {}


def experience_source(prof: Profile | None) -> tuple[str, str]:
    if prof is None:
        return "", "none"
    if (prof.experience_text or "").strip():
        return prof.experience_text, "experience"
    if (prof.cv_text or "").strip():
        return prof.cv_text, "cv"
    return "", "none"


def user_features(prof: Profile | None) -> dict | None:
    from .reader import merge_education, merge_roles, parse_linkedin

    text, source = experience_source(prof)
    roles, fmt = parse_roles(text)
    li_text = (prof.linkedin_text or "") if prof else ""
    li_roles = parse_linkedin(li_text) if li_text.strip() else []
    merge = None
    if li_roles:
        roles, merge = merge_roles(roles, li_roles)  # CV stays the base; LinkedIn adds detail and missing roles
        source = f"{source}+linkedin" if source != "none" else "linkedin"
    if not roles:
        return None
    f = extract_features(roles, overrides=(prof.role_reviews or {}) if prof else None)
    f["source"], f["format"], f["merge"] = source, fmt, merge
    edu = parse_education(text)
    if edu["ED"] is None and prof and prof.cv_text and text is not prof.cv_text:
        edu = parse_education(prof.cv_text) if parse_education(prof.cv_text)["degrees"] else edu
    if prof and (prof.linkedin_education or "").strip():
        edu = merge_education(edu, parse_education("Education: " + prof.linkedin_education.replace("\n", "; ")))
    f["ED"], f["degrees"] = edu["ED"], edu["degrees"]
    from .geo import user_geo

    f["geo"] = user_geo(roles, edu["degrees"])
    from .industry import user_path

    try:
        from ..db import SessionLocal
        from .industry import load_cache

        with SessionLocal() as s:
            cache = load_cache(s)
    except Exception:  # noqa: BLE001  (no database: listed companies only)
        cache = {}
    f["industry"] = user_path(roles, cache)
    from .pedigree import education_signals, employer_signal

    f.update(employer_signal(roles, now=_now_ym()))
    f.update(education_signals(edu["degrees"]))
    target = (prof.target_date if prof else "") or ""
    f["target_date"] = target
    f["ED_target"] = education_by(edu["degrees"], target) if target else None
    from .signals import AI_DEGREE, combine

    ai_deg = [d for d in edu["degrees"] if AI_DEGREE.search(d["text"]) and d["level"] >= 2]
    ai_now = 1.0 if any(not d["in_progress"] for d in ai_deg) else 0.5 if ai_deg else 0.0
    tech_deg = any(d["technical"] and not d["in_progress"] for d in edu["degrees"])
    combine(f, tech_degree=tech_deg, ai_degree=ai_now, now=_now_ym())
    f["AI_degrees"] = [d["text"] for d in ai_deg]
    if ai_deg and target and all(d["end"] and d["end"] <= target for d in ai_deg):
        f["AI_target"] = round(min(1.0, 0.6 * f["AI_work"] + 0.4), 3)
    else:
        f["AI_target"] = None
    return f


def _now_ym() -> tuple[int, int]:
    t = date.today()
    return (t.year, t.month)


def months_left(target: str) -> int | None:
    try:
        y, m = (int(x) for x in target.split("-"))
    except (ValueError, AttributeError):
        return None
    t = date.today()
    return max(0, (y - t.year) * 12 + (m - t.month))


def scorecard(db: Session, prof: Profile | None, *, n_boot: int = 1000,
              cluster: str = DEFAULT_CLUSTER) -> tuple[dict | None, dict | None, str]:
    """(card, features, reason). card is None when there is no reference set or no readable experience."""
    ref = load_reference(db, cluster)
    if ref is None or len(ref.rows) < 20:
        return None, None, (f"No group of {cluster} role holders yet." if cluster != DEFAULT_CLUSTER
                            else "No reference holders loaded. Run the seed step.")
    feats = user_features(prof)
    if feats is None:
        return None, None, "No roles could be read. Paste your LinkedIn Experience text on the Profile page."
    card = base_scorecard(feats, ref, months_left=months_left(prof.target_date if prof else ""), n_boot=n_boot)
    return card, feats, ""
