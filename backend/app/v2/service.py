"""Glue between the v2 model and the database."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Profile, ReferenceProfile
from .model import Reference, base_scorecard
from .reader import SOURCE_ORDER, extract_features, parse_roles

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
    prof.tag_matches = current


def import_reference_file(db: Session, path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    db.execute(delete(ReferenceProfile).where(ReferenceProfile.cluster == data["cluster"],
                                              ReferenceProfile.source == data["source"]))
    for r in data["rows"]:
        feats = {k: r.get(k) for k in ("YOE", "YOE_raw", "CT", "tier", "LV", "LV_max", "FN", "DM", "AC")}
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
    text, source = experience_source(prof)
    roles, fmt = parse_roles(text)
    if not roles:
        return None
    f = extract_features(roles, overrides=(prof.role_reviews or {}) if prof else None)
    f["source"], f["format"] = source, fmt
    return f


def months_left(target: str) -> int | None:
    try:
        y, m = (int(x) for x in target.split("-"))
    except (ValueError, AttributeError):
        return None
    t = date.today()
    return max(0, (y - t.year) * 12 + (m - t.month))


def scorecard(db: Session, prof: Profile | None, *, n_boot: int = 1000) -> tuple[dict | None, dict | None, str]:
    """(card, features, reason). card is None when there is no reference set or no readable experience."""
    ref = load_reference(db)
    if ref is None:
        return None, None, "No reference holders loaded. Run the seed step."
    feats = user_features(prof)
    if feats is None:
        return None, None, "No roles could be read. Paste your LinkedIn Experience text on the Profile page."
    card = base_scorecard(feats, ref, months_left=months_left(prof.target_date if prof else ""), n_boot=n_boot)
    return card, feats, ""
