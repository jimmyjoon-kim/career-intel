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
