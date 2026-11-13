from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    # Columns added after first release (create_all does not alter existing tables).
    with engine.begin() as conn:
        for ddl in ("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS experience_text TEXT DEFAULT ''",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS target_date VARCHAR(7) DEFAULT ''",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS role_reviews JSON DEFAULT '{}'::json",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS photo TEXT DEFAULT ''",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS linkedin_url VARCHAR(300) DEFAULT ''",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS linkedin_import JSON DEFAULT '{}'::json",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS linkedin_text TEXT DEFAULT ''",
                    "ALTER TABLE score_snapshots ADD COLUMN IF NOT EXISTS family VARCHAR(120) DEFAULT 'Partnerships'",
                    "ALTER TABLE company_sectors ADD COLUMN IF NOT EXISTS size VARCHAR(10) DEFAULT ''",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS linkedin_education TEXT DEFAULT ''",
                    "ALTER TABLE reference_profiles ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ",
                    "ALTER TABLE usage_log ADD COLUMN IF NOT EXISTS requested_model VARCHAR(60) DEFAULT ''",
                    "ALTER TABLE usage_log ADD COLUMN IF NOT EXISTS escalated VARCHAR(200) DEFAULT ''",
                    "ALTER TABLE usage_log ADD COLUMN IF NOT EXISTS runner VARCHAR(12) DEFAULT 'api'",
                    "ALTER TABLE usage_log ADD COLUMN IF NOT EXISTS source_job VARCHAR(60)",
                    "CREATE UNIQUE INDEX IF NOT EXISTS usage_log_source_job ON usage_log (source_job)",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS target_roles JSON DEFAULT '[]'::json",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS target_industries JSON DEFAULT '[]'::json",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS target_companies JSON DEFAULT '[]'::json",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS work_auth JSON DEFAULT '{}'::json",
                    # profiles that existed before set-up keep their behavior: country-scoped roles out, set up done
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS exclude_country_scope BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE profiles ALTER COLUMN exclude_country_scope SET DEFAULT FALSE",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS relocating BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS onboarded BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE profiles ALTER COLUMN onboarded SET DEFAULT FALSE",
                    "ALTER TABLE postings ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64) DEFAULT ''",
                    "ALTER TABLE postings ADD COLUMN IF NOT EXISTS source VARCHAR(40) DEFAULT 'csv'",
                    "ALTER TABLE postings ADD COLUMN IF NOT EXISTS read_check JSON DEFAULT '{}'::json",
                    "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64) DEFAULT ''"):
            conn.execute(text(ddl))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
