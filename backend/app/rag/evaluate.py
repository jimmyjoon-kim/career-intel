"""Retrieval check (hit rate): can search find the right posting from a reworded line of it?
Run: python -m app.rag.evaluate   (uses whichever embedding model built the current index)."""

from __future__ import annotations

import random
import re

from sqlalchemy import select

from ..config import get_settings
from ..db import SessionLocal
from ..models import Chunk
from .embeddings import embed


def _degrade(text: str, rng: random.Random) -> str:
    """A line from the section with every fourth word removed and the clauses shuffled: a rough paraphrase."""
    lines = [ln for ln in text.split("\n")[2:] if len(ln.split()) >= 10] or [text]
    words = rng.choice(lines).split()[:40]
    kept = [w for i, w in enumerate(words) if i % 4 != 3]
    half = len(kept) // 2
    return " ".join(kept[half:] + kept[:half])


def hit_rate(n: int = 40, seed: int = 7) -> dict:
    s = get_settings()
    rng = random.Random(seed)
    with SessionLocal() as db:
        pool = [c for c in db.scalars(select(Chunk).where(Chunk.owner_id.is_(None), Chunk.source_type == "posting",
                                                          Chunk.embedding_model == s.embedding_model_name).order_by(Chunk.id))
                if "\nSection:" in c.text and len(c.text) > 300 and not re.search(r"Section: (Benefits|Compensation|Pay)", c.text, re.I)]
        if not pool:
            return {"model": s.embedding_model_name, "error": "no section chunks indexed with this model"}
        sample = rng.sample(pool, min(n, len(pool)))
        queries = [_degrade(c.text, rng) for c in sample]
        qv = embed(queries, "query")
        h1 = h3 = 0
        for c, v in zip(sample, qv):
            dist = Chunk.embedding.cosine_distance(v)
            top = [r for r in db.scalars(select(Chunk.source_ref).where(Chunk.owner_id.is_(None), Chunk.source_type == "posting",
                                                                        Chunk.embedding_model == s.embedding_model_name)
                                         .order_by(dist).limit(10))]
            ranked = list(dict.fromkeys(top))  # distinct postings in rank order
            h1 += ranked[:1] == [c.source_ref]
            h3 += c.source_ref in ranked[:3]
        return {"model": s.embedding_model_name, "queries": len(sample), "hit_at_1": round(h1 / len(sample), 2),
                "hit_at_3": round(h3 / len(sample), 2), "indexed_section_chunks": len(pool)}


if __name__ == "__main__":
    print(hit_rate())
