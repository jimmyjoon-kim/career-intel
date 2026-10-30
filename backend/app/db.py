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
