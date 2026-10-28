"""Import postings from the career-intel weekly CSV format (postings_<date>.csv)."""

import csv
import io
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Posting
from .taxonomy import TAGS, infer_level, split_tags

_NO_SPONSOR = re.compile(r"(not|unable to|cannot|won't|will not)\s+(be able to\s+)?(sponsor|support)", re.I)


def _status(row: dict) -> tuple[str, str]:
    listed = (row.get("listed") or "").strip()
    head = listed.split("|")[0].strip().upper()
    if row.get("status"):
        return row["status"].strip().lower(), listed
    gate = (row.get("gate") or "").lower()
    if head == "LISTED":
        return "open", listed
    if head in ("DELISTED", "CLOSED") or "not on" in gate or "closed" in gate:
        return "closed", listed
    if head in ("UNVERIFIABLE", "AMBIGUOUS", "UNVERIFIED") or "unverified" in (row.get("verified") or "").lower():
        return "unverified", listed
    if (row.get("verified") or "").upper().startswith("VERIFIED"):
        return "open", listed
    return "unverified", listed


AD_TAGS = {"domain_adtech", "func_ad_sales", "skill_programmatic", "skill_retail_media", "skill_measurement_attribution",
           "skill_performance_marketing"}
AD_TITLE = re.compile(r"\bads?\b|advertis|media|brand partnerships|monetiz", re.I)


def check_cluster(label: str, tags: list[str], title: str) -> str:
    """An 'Ad Sales' label needs advertising evidence; general sales roles go to Sales Leadership."""
    if label == "Ad Sales" and not (AD_TAGS & set(tags)) and not AD_TITLE.search(title):
        return "Sales Leadership"
    return label


def import_csv(db: Session, content: str, source_date: str | None = None) -> dict:
    source_date = source_date or date.today().isoformat()
    reader = csv.DictReader(io.StringIO(content))
    created = updated = skipped = 0
    for row in reader:
        url = (row.get("url") or "").strip()
        company = (row.get("company") or "").strip()
        title = (row.get("title") or "").strip()
        if not (url and company and title):
            skipped += 1
            continue
        reqs, attrs = split_tags((row.get("requirement_tags") or "").split())
        reqs = [t for t in reqs if t in TAGS]
        auth_text = (row.get("sponsorship_text") or row.get("auth_text") or "").strip()
        status, verification = _status(row)
        values = dict(
            company=company,
            title=title,
            level_band=(row.get("level_band") or "").strip() or infer_level(title),
            role_cluster=check_cluster((row.get("role_cluster") or "Other").strip() or "Other", reqs, title),
            location=(row.get("location") or "").strip(),
            remote_flag=(row.get("remote_flag") or "unstated").strip().lower() or "unstated",
            bay_area=(row.get("bay_area") or "").strip() in ("1", "true", "True", "yes"),
            pay_range=(row.get("pay_range") or "").strip(),
            auth_text=auth_text,
            no_sponsorship=bool(_NO_SPONSOR.search(auth_text)) or (row.get("auth_status") or "").upper() == "NEGATIVE",
            scope=(row.get("scope") or attrs["scope"] or "").strip(),
            years_required=attrs["years_required"],
            tags=reqs,
            posted=(row.get("posted") or "unknown").strip(),
            status=status,
            verification=verification,
            last_seen=source_date,
        )
        existing = db.scalar(select(Posting).where(Posting.url == url))
        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(Posting(url=url, first_seen=source_date, **values))
            created += 1
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}
