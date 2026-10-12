"""CLI: python -m app.seed [csv ...]  — import postings CSVs and rebuild the RAG index."""

import sys
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal, init_db
from .importer import import_csv
from .models import User
from .rag.index import rebuild_shared, rebuild_user

DEFAULT = Path(__file__).resolve().parents[1] / "seed"


def main(paths: list[str]) -> None:
    init_db()
    files = [Path(p) for p in paths] or sorted(DEFAULT.glob("postings_*.csv"))
    with SessionLocal() as db:
        for f in files:
            date = f.stem.removeprefix("postings_")[:10]
            print(f"{f.name}: {import_csv(db, f.read_text(encoding='utf-8-sig'), date)}")
        print(f"shared chunks: {rebuild_shared(db)}")
        for u in db.scalars(select(User)):
            rebuild_user(db, u)


if __name__ == "__main__":
    main(sys.argv[1:])
