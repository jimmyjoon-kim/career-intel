import os

import pytest

# Offline mode for tests: no external AI calls.
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["VOYAGE_API_KEY"] = ""
os.environ.setdefault("DATABASE_URL", os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://career:career@localhost:5432/career_test"))


def _db_available() -> bool:
    try:
        from sqlalchemy import create_engine, text

        with create_engine(os.environ["DATABASE_URL"]).connect() as c:
            c.execute(text("select 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def client():
    if not _db_available():
        pytest.skip("Postgres not available; set TEST_DATABASE_URL")
    from fastapi.testclient import TestClient

    from app.db import Base, engine, init_db
    from app.main import app

    init_db()
    Base.metadata.drop_all(engine)
    init_db()
    with TestClient(app) as c:
        yield c
