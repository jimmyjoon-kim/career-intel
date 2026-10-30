"""Company facts agent. Each month, checks up to 8 unverified company events (IPO, acquisition dates) by web search
and files the confirmations as a proposal. It never edits the scoring tables itself."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..llm import BudgetExceeded, create, parse_json
from ..models import Proposal
from ..v2.signals import COMPANY_EVENTS

SYSTEM = """You verify dated corporate events. For each event, search for a primary or reputable source
(exchange notice, company press release, SEC filing, major newspaper). Report the month the event completed.
Never guess: if you cannot find a source, set confirmed to false.
Return JSON only: {"events":[{"company":"","event":"","claimed":"YYYY-MM","found":"YYYY-MM"|null,"confirmed":bool,"source_url":"","note":""}]}"""


def run(db: Session, run_id: int | None, limit: int = 8) -> dict:
    todo = [e for e in COMPANY_EVENTS if e[3] == "unverified"][:limit]
    if not todo:
        return {"checked": 0}
    clean = lambda pat: re.sub(r"\\b", "", pat).replace("|", " / ")  # noqa: E731
    lines = "\n".join(f"- {clean(pat)}: {kind} {y}-{m:02d} ({note})" for pat, kind, (y, m), _, note in todo)
    try:
        msg, model = create(role="research", agent="company_facts", run_id=run_id, system=SYSTEM, max_tokens=3000,
                            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
                            messages=[{"role": "user", "content": f"Verify these events:\n{lines}"}])
    except BudgetExceeded as err:
        return {"checked": 0, "stopped": str(err)}
    if msg is None:
        return {"checked": 0, "note": "no API key"}
    data = parse_json("".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")) or {}
    ev = data.get("events", [])
    if ev:
        db.add(Proposal(run_id=run_id, kind="company_events", title=f"Company event check: {sum(bool(e.get('confirmed')) for e in ev)} of {len(ev)} confirmed",
                        detail=f"Checked by web search ({model}). Approving marks them verified in the next model release.",
                        payload={"events": ev}))
        db.commit()
    return {"checked": len(ev), "confirmed": sum(bool(e.get("confirmed")) for e in ev)}


LADDER = """You summarize how one company's job titles map to its internal levels, using Levels.fyi pages from web search.
Focus on business, sales, partnerships and general-management ladders (not engineering) where Levels.fyi has them.
Only report what a search result you saw states; never guess. If nothing relevant is found, set found to false.
Return JSON only: {"found": bool, "ladder": "<one or two lines: title -> level, e.g. 'Director = L8; Senior Director = L9; Head of = varies by org size'>",
"source_url": "<levels.fyi URL you used>"}"""


def run_ladders(db: Session, run_id: int | None, limit: int = 6) -> dict:
    """Monthly: Levels.fyi title ladders for the companies with the most open postings that have none yet."""
    from collections import Counter

    from sqlalchemy import select

    from ..models import CompanyLevel, Posting

    have = {c.lower() for c in db.scalars(select(CompanyLevel.company))}
    counts = Counter(p.company for p in db.scalars(select(Posting).where(Posting.status == "open")) if p.company)
    todo = [c for c, _ in counts.most_common() if c.lower() not in have][:limit]
    found = 0
    for company in todo:
        try:
            msg, _ = create(role="research", agent="company_facts", run_id=run_id, system=LADDER, max_tokens=600,
                            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3,
                                    "allowed_domains": ["levels.fyi"]}],
                            messages=[{"role": "user", "content": f"Company: {company}. How do its titles map to levels "
                                                                  "(Director, Senior Director, Head of, VP) per Levels.fyi?"}])
        except BudgetExceeded as err:
            return {"checked": len(todo), "found": found, "stopped": str(err)}
        if msg is None:
            break
        cited = set()
        for b in msg.content:
            for item in getattr(b, "content", None) or []:
                if getattr(item, "url", None):
                    cited.add(item.url)
        data = parse_json("".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")) or {}
        url = data.get("source_url", "")
        if data.get("found") and data.get("ladder") and url in cited:  # only ladders backed by a page actually returned
            db.add(CompanyLevel(company=company, ladder=str(data["ladder"])[:600], source_url=url[:1000]))
            found += 1
        else:
            db.add(CompanyLevel(company=company, ladder="", source_url=""))  # checked; nothing usable
        db.commit()
    return {"checked": len(todo), "found": found}
