"""Agent worker: runs queued pipelines and the schedule (Asia/Seoul).
  daily   06:00   job boards + requirement reader
  weekly  Mon 09:00  full pipeline with checker and brief
  monthly first Mon 10:00  hire-research inbox + company facts (the Mac task drops its file before this)
Start: python -m app.worker   (docker compose runs it as the 'worker' service)"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from .config import get_settings
from .db import SessionLocal, engine, init_db
from .models import AgentRun

log = logging.getLogger("worker")
TZ = ZoneInfo("Asia/Seoul")
LOCK_ID = 7_402_611


def due(now: datetime) -> list[str]:
    kinds = []
    if (now.hour, now.minute) >= (6, 0):
        kinds.append("daily")
    if now.weekday() == 0 and (now.hour, now.minute) >= (9, 0):
        kinds.append("weekly")
    if now.weekday() == 0 and now.day <= 7 and (now.hour, now.minute) >= (10, 0):
        kinds.append("monthly")
    return kinds


def schedule(db, now: datetime) -> None:
    from .agents.coordinator import enqueue

    start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    for kind in due(now):
        done_today = db.scalar(select(AgentRun.id).where(AgentRun.kind == kind, AgentRun.trigger == "schedule",
                                                         AgentRun.created_at >= start))
        if not done_today:
            enqueue(db, kind, trigger="schedule")


def tick() -> None:
    from .agents.coordinator import execute

    with SessionLocal() as db:
        schedule(db, datetime.now(TZ))
        run = db.scalar(select(AgentRun).where(AgentRun.status == "queued").order_by(AgentRun.id))
        if run:
            log.info("run %s (%s) starting", run.id, run.kind)
            execute(db, run)
            log.info("run %s finished: %s", run.id, run.status)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    init_db()
    if not get_settings().agents_enabled:
        log.info("agents disabled (AGENTS_ENABLED=false)")
        return
    with engine.connect() as conn:
        if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_ID}).scalar():
            log.info("another worker holds the lock; exiting")
            return
        with SessionLocal() as db:  # a run left 'running' by a crash is marked failed
            for r in db.scalars(select(AgentRun).where(AgentRun.status == "running")):
                r.status, r.error = "failed", "worker restarted during the run"
            db.commit()
        while True:
            try:
                tick()
            except Exception:  # noqa: BLE001
                log.exception("tick failed")
            time.sleep(30)


if __name__ == "__main__":
    main()
