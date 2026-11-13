"""Hand-off to the Mac dispatcher (scripts/dispatcher.py): queue an agent session, and record what came back.
A job names only the agent; its model, tools and limits come from the registry on the Mac side."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..llm import PRICES
from ..models import UsageLog
from . import registry


def _dir() -> Path:
    return Path(get_settings().inbox_dir) / "jobs"


def enqueue(agent: str, trigger: str = "schedule", run_id: int | None = None, input_text: str = "") -> str:
    if registry.spec(agent).get("runner") != "cli":
        raise registry.UnknownAgent(f"agent '{agent}' is not run by the Mac dispatcher")
    jid = f"{agent}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    d = _dir() / "pending"
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{jid}.tmp"
    tmp.write_text(json.dumps({"id": jid, "agent": agent, "run_id": run_id, "trigger": trigger, "attempt": 1,
                               "input": input_text[:20000], "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
    tmp.rename(d / f"{jid}.json")
    return jid


def ingest(db: Session) -> dict:
    """Record finished jobs: one usage row per model that actually served (runner = cli). Safe to run twice."""
    done, kept = _dir() / "done", _dir() / "done" / "ingested"
    if not done.exists():
        return {"ingested": 0}
    kept.mkdir(parents=True, exist_ok=True)
    n, results = 0, []
    for f in sorted(done.glob("*.json")):
        try:
            r = json.loads(f.read_text())
        except ValueError:
            f.rename(kept / (f.name + ".bad"))
            continue
        for model, u in (r.get("model_usage") or {}).items():
            key = f'{r["id"]}:{model}'[:60]
            if db.scalar(select(UsageLog.id).where(UsageLog.source_job == key)):
                continue
            db.add(UsageLog(agent=str(r.get("agent"))[:40], run_id=r.get("run_id"), model=model[:60],
                            requested_model=str(r.get("requested_model") or "")[:60], runner="cli", source_job=key,
                            input_tokens=int(u.get("inputTokens") or 0), output_tokens=int(u.get("outputTokens") or 0),
                            cache_write=int(u.get("cacheCreationInputTokens") or 0), cache_read=int(u.get("cacheReadInputTokens") or 0),
                            # an estimate from the session; sessions run on the Claude subscription, not the API budget
                            cost_usd=0.0))
        db.commit()
        results.append({"id": r.get("id"), "agent": r.get("agent"), "status": r.get("status"), "models_served": r.get("models_served"),
                        "requested_model": r.get("requested_model")})
        f.rename(kept / f.name)
        n += 1
    return {"ingested": n, "jobs": results}


assert PRICES  # models named in the registry must be priced (checked in tests)
