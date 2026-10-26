"""Build and query the RAG corpus.

Shared corpus (owner_id NULL): one chunk per posting, one per role-cluster market summary,
and the method documents in backend/knowledge/. Private corpus (owner_id = user): the
user's CV chunks and a generated scorecard of their matches and gaps.
"""

from pathlib import Path

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Chunk, Posting, User
from ..taxonomy import TAGS
from .embeddings import embed

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"
CHUNK_CHARS = 1200
OVERLAP = 200


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP) -> list[str]:
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        while len(p) > size:  # hard-split very long paragraphs
            head, p = p[:size], p[size - overlap :]
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(head)
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur:
                chunks.append(cur)
            tail = cur[-overlap:] if cur else ""
            cur = f"{tail}\n\n{p}" if tail else p
    if cur:
        chunks.append(cur)
    return chunks


def _label(tag: str) -> str:
    t = TAGS.get(tag)
    return f"{t.label} ({tag})" if t else tag


def posting_text(p: Posting) -> str:
    lines = [
        f"{p.title} at {p.company}",
        f"Role cluster: {p.role_cluster}. Level: {p.level_band}. Location: {p.location} (remote: {p.remote_flag}).",
        f"Pay: {p.pay_range or 'not stated'}. Scope: {p.scope or 'not stated'}. Status: {p.status}. Posted: {p.posted}.",
        f"Work authorisation text: {p.auth_text or 'none stated'}.",
        f"Years required: {p.years_required or 'unstated'}.",
        "Requirements: " + ("; ".join(_label(t) for t in p.tags) or "not tagged"),
    ]
    if p.description:
        lines.append(p.description[:3000])
    return "\n".join(lines)


def market_texts(stats: dict) -> list[tuple[str, str]]:
    out = []
    for name, c in sorted(stats["clusters"].items()):
        rows = sorted(c["tags"].items(), key=lambda kv: -kv[1]["pct"])
        by_cls: dict[str, list[str]] = {}
        for tag, info in rows:
            by_cls.setdefault(info["cls"], []).append(f"{_label(tag)} {info['pct']}%")
        merged = f" (includes merged clusters: {', '.join(c['merged_from'])})" if c["merged_from"] else ""
        text = (
            f"Market requirements for the {name} role cluster{merged}, across {c['n']} open postings.\n"
            f"Common minimum (>=70% of postings): {'; '.join(by_cls.get('COMMON MINIMUM', [])) or 'none'}.\n"
            f"Mid (30-70%): {'; '.join(by_cls.get('MID', [])) or 'none'}.\n"
            f"Discriminators (<30%): {'; '.join(by_cls.get('DISCRIMINATOR', [])) or 'none'}."
        )
        out.append((f"Market: {name}", text))
    return out


def rebuild_shared(db: Session) -> int:
    from ..services import current_market

    s = get_settings()
    postings, stats = current_market(db)
    # (source_type, source_ref, title, url, text) for every shared chunk, embedded in one batched job
    items: list[tuple[str, str, str, str, str]] = []
    for p in postings:
        if p.status in ("open", "unverified"):
            items.append(("posting", str(p.id), f"{p.company} — {p.title}", p.url, posting_text(p)))
    for title, text in market_texts(stats):
        items.append(("market", title, title, "", text))
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text()
        title = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("#")), path.stem)
        items.extend(("method", path.name, title, "", t) for t in chunk_text(text))

    vecs = embed([it[4] for it in items], "document")  # before deleting, so a failure keeps the old index
    db.execute(delete(Chunk).where(Chunk.owner_id.is_(None)))
    for (stype, ref, title, url, text), v in zip(items, vecs):
        db.add(Chunk(owner_id=None, source_type=stype, source_ref=ref, title=title, url=url,
                     text=text, embedding_model=s.embedding_model_name, embedding=v))
    db.commit()
    return len(items)


def scorecard_text(evaluation: dict) -> str:
    lines = ["Your scorecard (generated from your profile against the current open postings)."]
    passing = evaluation["passing"]
    lines.append(f"Postings passing your gate: {len(passing)} of {len(evaluation['rows'])}.")
    lines.append("Top matches by rank score:")
    for r in passing[:10]:
        p = r["posting"]
        hard = ", ".join(f"{g['label']} ({g['match']})" for g in r["hard_gaps"]) or "none"
        lines.append(f"- {p.company} — {p.title}: rank {r['rank_score']}, weighted {r['weighted_score']}, hard gaps: {hard}")
    lines.append("Largest gaps across passing postings (impact = frequency x weight x shortfall):")
    for g in evaluation["gap_summary"]:
        lines.append(
            f"- {g['label']}: {g['cls']}, your match {g['match']}, in {g['postings']} postings, impact {g['impact']}, "
            f"closable before move: {'yes' if g['closable'] else 'no'}{'. ' + g['close_hint'] if g['close_hint'] else ''}"
        )
    return "\n".join(lines)


def rebuild_user(db: Session, user: User) -> int:
    from ..services import evaluate

    s = get_settings()
    prof = user.profile
    items: list[tuple[str, str, str]] = []  # (source_type, title, text)
    if prof and prof.cv_text.strip():
        items.extend(("cv", "Your CV", t) for t in chunk_text(prof.cv_text))
    if prof:
        items.append(("scorecard", "Your scorecard", scorecard_text(evaluate(db, user))))
    vecs = embed([t for _, _, t in items], "document")
    db.execute(delete(Chunk).where(Chunk.owner_id == user.id))
    for (stype, title, text), v in zip(items, vecs):
        db.add(Chunk(owner_id=user.id, source_type=stype, source_ref=stype, title=title, url="",
                     text=text, embedding_model=s.embedding_model_name, embedding=v))
    db.commit()
    return len(items)


def search(db: Session, user_id: int, query: str, k: int | None = None) -> list[tuple[Chunk, float]]:
    s = get_settings()
    k = k or s.rag_top_k
    qv = embed([query], "query")[0]
    dist = Chunk.embedding.cosine_distance(qv)
    stmt = (
        select(Chunk, dist.label("dist"))
        .where(Chunk.embedding_model == s.embedding_model_name)
        .where(or_(Chunk.owner_id.is_(None), Chunk.owner_id == user_id))
        .order_by(dist)
        .limit(k)
    )
    return [(c, round(1 - float(d), 4)) for c, d in db.execute(stmt).all()]
