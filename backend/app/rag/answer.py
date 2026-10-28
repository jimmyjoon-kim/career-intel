"""Grounded answers: retrieve, then have Claude answer only from the retrieved sources."""

from sqlalchemy.orm import Session

from ..llm import complete
from .index import search

SYSTEM = """You are Career Intel, an analyst that answers questions about a candidate's competitiveness
for commercial leadership roles, using ONLY the numbered sources provided.
Rules:
- Cite sources inline as [1], [2]. Every factual claim needs a citation.
- If the sources do not contain the answer, say so plainly and state what is missing. Do not fill gaps with inference.
- Separate what is verified in the sources from anything unverified.
- Never state probabilities, odds or likelihoods of being hired.
- Present gaps with the evidence and whether each is closable; do not over-weight negatives.
- Be concise: short bullets or a few tight lines. No preamble."""


def _format_sources(hits) -> str:
    return "\n\n".join(f"[{i}] {c.title} ({c.source_type})\n{c.text}" for i, (c, _) in enumerate(hits, 1))


def answer(db: Session, user_id: int, question: str) -> dict:
    hits = search(db, user_id, question)
    sources = [
        {"n": i, "title": c.title, "type": c.source_type, "url": c.url, "similarity": sim, "excerpt": c.text[:400]}
        for i, (c, sim) in enumerate(hits, 1)
    ]
    if not hits:
        return {"answer": "No indexed sources yet. Ask an admin to import postings and rebuild the index.",
                "sources": [], "mode": "empty"}
    try:
        text = complete(SYSTEM, f"Sources:\n{_format_sources(hits)}\n\nQuestion: {question}", max_tokens=1200)
    except Exception as err:  # noqa: BLE001 — show the reason instead of a server error
        lines = [f"Claude could not answer ({type(err).__name__}: {str(err)[:300]}). Check ANTHROPIC_API_KEY, "
                 "the model name and your API credit. The most relevant sources are below."]
        lines += [f"[{s['n']}] {s['title']}: " + " ".join(s["excerpt"].split("\n")[1:])[:220] + "…" for s in sources[:5]]
        return {"answer": "\n".join(lines), "sources": sources, "mode": "error"}
    if text is None:
        lines = ["Offline mode (no ANTHROPIC_API_KEY): showing the most relevant sources instead of a written answer."]
        lines += [f"[{s['n']}] {s['title']}: " + " ".join(s["excerpt"].split("\n")[1:])[:220] + "…" for s in sources[:5]]
        return {"answer": "\n".join(lines), "sources": sources, "mode": "extractive"}
    return {"answer": text.strip(), "sources": sources, "mode": "llm"}
