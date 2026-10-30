from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import get_settings
from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    profile: Mapped["Profile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class Profile(Base):
    """One candidate profile per user: CV text, extracted tag matches and gate preferences."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    headline: Mapped[str] = mapped_column(String(300), default="")
    cv_text: Mapped[str] = mapped_column(Text, default="")
    # Full experience text (LinkedIn "Experience" page or CV roles) read by the v2 reader.
    experience_text: Mapped[str] = mapped_column(Text, default="")
    # Target month for applications, "YYYY-MM"; used to mark gaps closable in time.
    target_date: Mapped[str] = mapped_column(String(7), default="")
    # Your review of each role: {role_key: {"tags": {tag: 0|0.5|1}, "team_size": int|None, "confirmed": bool}}
    role_reviews: Mapped[dict] = mapped_column(JSON, default=dict)
    # Profile photo as a data URL (jpeg/png/webp, small); shown on your player card only.
    photo: Mapped[str] = mapped_column(Text, default="")
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # {tag: {"match": 0|0.5|1, "evidence": str, "source": "extracted"|"user"}}
    tag_matches: Mapped[dict] = mapped_column(JSON, default=dict)
    # Gate preferences — see scoring.gate()
    min_level: Mapped[str] = mapped_column(String(40), default="Director")
    locations: Mapped[list] = mapped_column(JSON, default=lambda: ["SF Bay Area"])
    remote_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    needs_sponsorship: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded_title_terms: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="profile")


class Posting(Base):
    """A job posting in the shared market dataset."""

    __tablename__ = "postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(300))
    level_band: Mapped[str] = mapped_column(String(40), default="")
    role_cluster: Mapped[str] = mapped_column(String(80), index=True, default="Other")
    location: Mapped[str] = mapped_column(String(300), default="")
    remote_flag: Mapped[str] = mapped_column(String(20), default="unstated")  # yes | hybrid | no | unstated
    bay_area: Mapped[bool] = mapped_column(Boolean, default=False)
    pay_range: Mapped[str] = mapped_column(String(300), default="")
    auth_text: Mapped[str] = mapped_column(Text, default="")
    no_sponsorship: Mapped[bool] = mapped_column(Boolean, default=False)
    scope: Mapped[str] = mapped_column(String(40), default="")
    years_required: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)  # requirement tags only
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    posted: Mapped[str] = mapped_column(String(60), default="unknown")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | closed | stale | unverified
    verification: Mapped[str] = mapped_column(Text, default="")
    first_seen: Mapped[str] = mapped_column(String(20), default="")
    last_seen: Mapped[str] = mapped_column(String(20), default="")
    # Fingerprint of title + description; the requirement reader re-reads only when it changes.
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(40), default="csv")  # csv | greenhouse | lever | ashby | web | manual
    # Requirement reader agreement: {"runs": 3, "agreed": [...], "disputed": [...], "model": str}
    read_check: Mapped[dict] = mapped_column(JSON, default=dict)


class Chunk(Base):
    """RAG chunk. owner_id NULL = shared corpus (postings, market stats, method docs)."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)  # posting | market | method | cv
    source_ref: Mapped[str] = mapped_column(String(300), index=True)
    title: Mapped[str] = mapped_column(String(400), default="")
    url: Mapped[str] = mapped_column(String(1000), default="")
    text: Mapped[str] = mapped_column(Text)
    embedding_model: Mapped[str] = mapped_column(String(60), index=True)
    embedding = mapped_column(Vector(get_settings().embedding_dim))
    # Fingerprint of the source text, so the daily update re-embeds only what changed.
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Question(Base):
    """Log of RAG questions per user (for history and future outcome learning)."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    mode: Mapped[str] = mapped_column(String(20))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReferenceProfile(Base):
    """A person who holds a target role, stored as derived factor values only (no name, URL or raw text)."""

    __tablename__ = "reference_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster: Mapped[str] = mapped_column(String(80), index=True)
    company: Mapped[str] = mapped_column(String(200), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    features: Mapped[dict] = mapped_column(JSON, default=dict)  # YOE, CT, LV, LV_max, FN, DM, AC, tags
    source: Mapped[str] = mapped_column(String(300), default="")
    as_of: Mapped[str] = mapped_column(String(20), default="")


# ---- Agent team -----------------------------------------------------------------------------------------

class UsageLog(Base):
    """One row per Claude call: which agent, which model, tokens and cost. Drives the monthly cap."""

    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    agent: Mapped[str] = mapped_column(String(40), index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(60))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write: Mapped[int] = mapped_column(Integer, default=0)
    cache_read: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class AgentRun(Base):
    """A pipeline run (daily | weekly | monthly | rescore). status: queued | running | done | failed | stopped."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="schedule")  # schedule | manual | event
    requested_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    steps: Mapped[list] = mapped_column(JSON, default=list)  # [{agent, status, seconds, result, error}]
    error: Mapped[str] = mapped_column(Text, default="")


class Brief(Base):
    """The analyst's weekly brief with the checker's verdict."""

    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    body: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # the facts the brief was written from
    model: Mapped[str] = mapped_column(String(60), default="")
    check: Mapped[dict] = mapped_column(JSON, default=dict)  # {passed, issues[], model}


class Proposal(Base):
    """A change an agent wants to make that needs your approval (new holders, company facts, reclassification)."""

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(40))  # holders | company_events | reclassify
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScoreSnapshot(Base):
    """A stored scorecard result, stamped with the model version, so scores have a history."""

    __tablename__ = "score_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    model_version: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)
    position: Mapped[float] = mapped_column(Float)
    factors: Mapped[list] = mapped_column(JSON, default=list)  # [{factor, percentile, weight, points}]


class Board(Base):
    """An employer job board read directly (Greenhouse, Lever or Ashby)."""

    __tablename__ = "boards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ats: Mapped[str] = mapped_column(String(20))  # greenhouse | lever | ashby
    slug: Mapped[str] = mapped_column(String(120))
    company: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_status: Mapped[str] = mapped_column(String(200), default="")
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvidenceSuggestion(Base):
    """A line from your own documents that may evidence a requirement postings ask for. You confirm or reject it."""

    __tablename__ = "evidence_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(200), default="")
    match: Mapped[float] = mapped_column(Float, default=1.0)  # 1 = clearly evidenced, 0.5 = partial
    quote: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(200), default="")  # e.g. "Your experience: General Manager @ Unity"
    postings: Mapped[int] = mapped_column(Integer, default=0)  # gate-passing postings that ask for this tag
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending | confirmed | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PoolRequest(Base):
    """A role family you asked to be scored against; hire research collects holders for it."""

    __tablename__ = "pool_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family: Mapped[str] = mapped_column(String(120), unique=True)
    pattern: Mapped[str] = mapped_column(String(300), default="")  # title keywords (regex) for a custom family
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | ready
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CompanyLevel(Base):
    """How a company's titles map to levels (from Levels.fyi via web search). A hint for the level assessor, not a rule."""

    __tablename__ = "company_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(200), unique=True)
    ladder: Mapped[str] = mapped_column(Text, default="")  # e.g. "Director = L8 (manages managers); Head of = L7-L8; VP = L9"
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
