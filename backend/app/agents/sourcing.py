"""Job sourcing agent. Reads employer job boards directly (Greenhouse, Lever, Ashby public APIs; no model calls),
keeps commercial Director+ titles in the US or US-remote, fingerprints each posting and marks vanished ones closed.
A weekly web search (Claude, capped) covers employers that use other systems."""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Board, Posting

log = logging.getLogger(__name__)
SEED_BOARDS = Path(__file__).resolve().parents[2] / "seed" / "ats_boards.json"

LEVEL = re.compile(r"\b(director|head of|head,|vp|vice president|chief|general manager|svp|evp|gm)\b", re.I)
FUNC = re.compile(r"partner|alliance|business development|\bbd\b|sales|revenue|growth|monetiz|advertis|commercial|"
                  r"\bads?\b|go[- ]to[- ]market|\bgtm\b|strategy|publisher|developer relations", re.I)
EXCLUDE = re.compile(r"country manager|\b(korea|japan|china|germany|france|italy|spain|uk|united kingdom|india|brazil|"
                     r"mexico|canada|australia|singapore|dach|nordics|benelux)\b", re.I)
US = re.compile(r"united states|\bu\.?s\.?a?\b|\bremote\b(?![^,]*(uk|europe|emea|canada|india|apac))|san francisco|bay area|"
                r"palo alto|mountain view|menlo park|san mateo|redwood city|sunnyvale|san jose|oakland|foster city|"
                r"new york|seattle|los angeles|austin|boston|chicago|denver|atlanta|miami|washington|"
                r",\s*(ca|ny|wa|tx|ma|il|co|ga|fl|dc|or|nc|va|nj|ut)\b", re.I)
NON_US = re.compile(r"london|dublin|paris|berlin|munich|amsterdam|toronto|vancouver|tokyo|seoul|singapore|sydney|"
                    r"bangalore|bengaluru|tel aviv|sao paulo|mexico city|\buk\b|united kingdom|ireland|germany|france|"
                    r"canada|japan|korea|india|australia|israel|brazil|emea|apac|latam", re.I)
BAY = re.compile(r"san francisco|bay area|palo alto|mountain view|menlo park|san mateo|redwood city|sunnyvale|"
                 r"san jose|oakland|foster city|south san francisco|burlingame|santa clara|cupertino", re.I)
PAY = re.compile(r"\$\s?\d[\d,]{2,}(?:\.\d+)?\s?(?:k|K)?\s?(?:[-–—]|to)\s?\$?\s?\d[\d,]{2,}(?:\.\d+)?\s?(?:k|K)?")
URL_SLUG = [("greenhouse", re.compile(r"(?:job-boards|boards)\.greenhouse\.io/([A-Za-z0-9_-]+)")),
            ("lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.-]+)")),
            ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"))]


def text_of(raw: str) -> str:
    t = html.unescape(raw or "")
    t = re.sub(r"<(br|/p|/li|/h\d)\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def fingerprint(title: str, description: str) -> str:
    return hashlib.sha256(f"{title.strip()}\n{re.sub(r'\s+', ' ', description).strip()}".encode()).hexdigest()


US_NAMES = {"sf bay area", "bay area", "remote", "remote us", "united states", "us", "usa"}


def profile_locations(db: Session) -> list[str]:
    """Locations on any profile beyond the US default (e.g. "Seoul, South Korea", "Singapore")."""
    from ..models import Profile

    out: list[str] = []
    for locs in db.scalars(select(Profile.locations)):
        for loc in locs or []:
            name = (loc or "").strip()
            if name and name.lower() not in US_NAMES and not US.search(name) and name not in out:
                out.append(name)
    return out


def _loc_pattern(names: list[str]) -> re.Pattern | None:
    cities = [re.escape(n.split(",")[0].strip()) for n in names if len(n.split(",")[0].strip()) >= 4]
    return re.compile("|".join(cities), re.I) if cities else None


def keep(title: str, location: str, extra: re.Pattern | None = None) -> tuple[bool, str]:
    """Title and location screen before any model reads the posting. extra: profile locations outside the US."""
    if not (LEVEL.search(title) and FUNC.search(title)):
        return False, "not a Director+ commercial title"
    if EXCLUDE.search(title):
        return False, "country-scoped or Country Manager title"
    loc = location or ""
    if extra is not None and extra.search(loc):
        return True, ""
    if NON_US.search(loc) and not US.search(loc):
        return False, "outside your locations"
    return True, ""


def fetch_board(client: httpx.Client, ats: str, slug: str) -> list[dict]:
    """Returns [{title, url, location, description, remote, pay, posted}]. Raises on HTTP errors."""
    out = []
    if ats == "greenhouse":
        r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            desc = text_of(j.get("content", ""))
            loc = (j.get("location") or {}).get("name", "")
            out.append({"title": j.get("title", ""), "url": j.get("absolute_url", ""), "location": loc, "description": desc,
                        "remote": "yes" if re.search(r"remote", loc, re.I) else "unstated",
                        "pay": (PAY.search(desc) or [""])[0], "posted": (j.get("updated_at") or "")[:10]})
    elif ats == "lever":
        r = client.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
        r.raise_for_status()
        for j in r.json():
            parts = [j.get("descriptionPlain", "")] + [f'{x.get("text", "")}\n{text_of(x.get("content", ""))}' for x in j.get("lists", [])]
            desc = "\n".join(p for p in parts + [j.get("additionalPlain", "")] if p)
            cat = j.get("categories") or {}
            sal = j.get("salaryRange") or {}
            pay = f'${sal["min"]:,}–${sal["max"]:,}' if sal.get("min") and sal.get("max") else (PAY.search(desc) or [""])[0]
            out.append({"title": j.get("text", ""), "url": j.get("hostedUrl", ""), "location": cat.get("location", ""),
                        "description": desc, "remote": "yes" if j.get("workplaceType") == "remote" else
                        "hybrid" if j.get("workplaceType") == "hybrid" else "unstated", "pay": pay,
                        "posted": datetime.fromtimestamp(j["createdAt"] / 1000, timezone.utc).date().isoformat() if j.get("createdAt") else ""})
    elif ats == "ashby":
        r = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", params={"includeCompensation": "true"})
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            desc = j.get("descriptionPlain") or text_of(j.get("descriptionHtml", ""))
            comp = (j.get("compensation") or {}).get("compensationTierSummary") or (PAY.search(desc) or [""])[0]
            out.append({"title": j.get("title", ""), "url": j.get("jobUrl", ""), "location": j.get("location", ""),
                        "description": desc, "remote": "yes" if j.get("isRemote") else "unstated", "pay": comp,
                        "posted": (j.get("publishedAt") or "")[:10]})
    else:
        raise ValueError(f"unknown board type {ats}")
    return [j for j in out if j["title"] and j["url"]]


def seed_boards(db: Session) -> int:
    """Board list = seed file + every Greenhouse/Lever/Ashby board seen in posting URLs."""
    have = {(b.ats, b.slug.lower()) for b in db.scalars(select(Board))}
    found: dict[tuple[str, str], str] = {}
    if SEED_BOARDS.exists():
        for b in json.loads(SEED_BOARDS.read_text()):
            found[(b["ats"], b["slug"])] = b.get("company", "")
    for url, company in db.execute(select(Posting.url, Posting.company)):
        for ats, pat in URL_SLUG:
            m = pat.search(url or "")
            if m:
                found.setdefault((ats, m.group(1)), company)
    added = 0
    for (ats, slug), company in found.items():
        if (ats, slug.lower()) not in have:
            db.add(Board(ats=ats, slug=slug, company=company or slug))
            added += 1
    db.commit()
    return added


def upsert(db: Session, company: str, src: str, j: dict, today: str) -> str:
    """'new' | 'changed' | 'same'. A changed fingerprint clears the reader's check so it is read again."""
    fp = fingerprint(j["title"], j["description"])
    p = db.scalar(select(Posting).where(Posting.url == j["url"]))
    base = dict(company=company, title=j["title"][:300], location=j["location"][:300], remote_flag=j["remote"],
                bay_area=bool(BAY.search(j["location"] or "")), pay_range=(j["pay"] or "")[:300],
                description=j["description"], posted=j["posted"] or "unknown", status="open", last_seen=today,
                source=src, verification=f"listed on {src} board, checked {today}")
    if p is None:
        db.add(Posting(url=j["url"][:1000], first_seen=today, content_hash=fp, read_check={}, **base))
        return "new"
    changed = p.content_hash != fp
    for k, v in base.items():
        setattr(p, k, v)
    if changed:
        p.content_hash, p.read_check = fp, {}
    return "changed" if changed else "same"


def run_boards(db: Session, client: httpx.Client | None = None) -> dict:
    seed_boards(db)
    extra = _loc_pattern(profile_locations(db))
    today = date.today().isoformat()
    own = client is None
    client = client or httpx.Client(timeout=30, headers={"User-Agent": "career-intel/1.0"})
    tally = {"boards_ok": 0, "boards_failed": [], "new": 0, "changed": 0, "same": 0, "screened_out": 0, "closed": 0}
    try:
        for b in db.scalars(select(Board).where(Board.active.is_(True))):
            try:
                jobs = fetch_board(client, b.ats, b.slug)
            except Exception as err:  # noqa: BLE001 — one bad board must not stop the others
                b.last_status, b.last_checked = f"failed: {str(err)[:150]}", datetime.now(timezone.utc)
                tally["boards_failed"].append(f"{b.ats}/{b.slug}")
                continue
            seen = set()
            for j in jobs:
                ok, _ = keep(j["title"], j["location"], extra)
                if not ok:
                    tally["screened_out"] += 1
                    continue
                seen.add(j["url"])
                tally[upsert(db, b.company, b.ats, j, today)] += 1
            # Postings from this board that are no longer listed are closed.
            for p in db.scalars(select(Posting).where(Posting.source == b.ats, Posting.status == "open",
                                                      Posting.url.like(f"%{b.slug}%"))):
                if p.url not in seen:
                    p.status, p.verification = "closed", f"no longer on {b.ats} board, checked {today}"
                    tally["closed"] += 1
            b.last_status, b.last_checked = f"ok: {len(seen)} kept of {len(jobs)}", datetime.now(timezone.utc)
            tally["boards_ok"] += 1
            db.commit()
    finally:
        if own:
            client.close()
    return tally


WEB_QUERIES = ["Director or VP of Partnerships, US or US-remote, ad tech or mobile app monetization",
               "Head of Business Development or Strategic Partnerships at AI companies, San Francisco Bay Area or US-remote",
               "Director or VP of Ad Sales or Revenue, US, ad tech, retail media or gaming"]


def location_queries(names: list[str]) -> list[str]:
    return [f"Director, Head of or VP of Partnerships, Business Development or Ad Sales with regional (APAC or global) scope, "
            f"based in {n}; not Country Manager and not single-country roles" for n in names]


def run_web(db: Session, run_id: int | None, profile_summary: str, only_locations: bool = False) -> dict:
    """Web search for employers whose boards are not readable directly, and for profile locations outside the US.
    Results are kept as 'unverified'."""
    from ..matches import web_search

    names = profile_locations(db)
    extra = _loc_pattern(names)
    queries = location_queries(names) + ([] if only_locations else WEB_QUERIES)
    today, added, notes = date.today().isoformat(), 0, []
    for q in queries:
        res = web_search(q, profile_summary, max_results=8, agent="sourcing", run_id=run_id, max_uses=3)
        if res.get("note", "").startswith("Search failed"):
            notes.append(res["note"])
            if "Monthly cap" in res["note"]:
                break
            continue
        for r in res.get("results", []):
            if not (r.get("url") and r.get("seen_in_search")):
                continue  # only URLs that appeared in actual search results
            ok, _ = keep(r.get("title", ""), r.get("location", ""), extra)
            if not ok or db.scalar(select(Posting.id).where(Posting.url == r["url"])):
                continue
            db.add(Posting(company=r.get("company", "")[:200], title=r.get("title", "")[:300], url=r["url"][:1000],
                           location=r.get("location", "")[:300], bay_area=bool(BAY.search(r.get("location", ""))),
                           status="unverified", source="web", first_seen=today, last_seen=today,
                           verification=f"found by web search {today}; not checked on the live board", read_check={}))
            added += 1
    db.commit()
    return {"added_unverified": added, "queries": len(queries), "locations": names, "notes": notes}
