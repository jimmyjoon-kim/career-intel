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
