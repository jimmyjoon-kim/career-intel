"""Build and query the RAG corpus.

Shared corpus (owner_id NULL): one chunk per posting, one per role-cluster market summary,
and the method documents in backend/knowledge/. Private corpus (owner_id = user): the
user's CV chunks and a generated scorecard of their matches and gaps.
"""

import hashlib
import logging
import re
from pathlib import Path

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Chunk, Posting, User
from ..taxonomy import TAGS
from .embeddings import embed

log = logging.getLogger(__name__)
_STOP = {"the", "and", "for", "what", "which", "are", "how", "why", "with", "that", "this", "does", "have", "from", "into",
         "about", "you", "your", "can", "should", "will", "there", "their", "they", "them", "who", "where", "when", "fit"}
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


SECTION_HEAD = re.compile(
    r"^(?:#+\s*)?(about (?:the|this) (?:role|team|job|opportunity)|about us|about [A-Z][\w ]{0,30}|the role|overview|"
    r"(?:what|things) you(?:'ll| will) (?:do|own|work on)|responsibilities|key responsibilities|in this role|your impact|"
    r"(?:what|who) you(?:'ll| will)? (?:bring|need|have|are)|requirements|qualifications|minimum qualifications|"
    r"preferred qualifications|basic qualifications|you may be a good fit|nice to haves?|bonus points|"
    r"compensation|pay|benefits|what we offer|why join)\s*:?\s*$", re.I)


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def posting_sections(description: str) -> list[tuple[str, str]]:
    """Split a posting into (section name, text) by its own headings; content-aware chunking."""
    out, name, buf = [], "Description", []
    for ln in (description or "").splitlines():
        if SECTION_HEAD.match(ln.strip()) and len(ln.strip()) < 70:
            if buf:
                out.append((name, "\n".join(buf)))
            name, buf = ln.strip().rstrip(":"), []
        elif ln.strip():
            buf.append(ln.strip())
    if buf:
        out.append((name, "\n".join(buf)))
    return out


def posting_chunks(p: Posting) -> list[tuple[str, str]]:
    """(title, text) chunks for one posting: a summary chunk, then one chunk per section (long ones split)."""
    head = f"{p.company} — {p.title}"
    chunks = [(head, posting_text(p, with_description=False))]
    for name, body in posting_sections(p.description or ""):
        for part in chunk_text(body.replace("\n", "\n\n"), 1000, 150):
            chunks.append((f"{head} · {name}", f"{head}\nSection: {name}\n{part}"))
    return chunks


def posting_text(p: Posting, with_description: bool = True) -> str:
    lines = [
        f"{p.title} at {p.company}",
        f"Role cluster: {p.role_cluster}. Level: {p.level_band}. Location: {p.location} (remote: {p.remote_flag}).",
        f"Pay: {p.pay_range or 'not stated'}. Scope: {p.scope or 'not stated'}. Status: {p.status}. Posted: {p.posted}.",
        f"Work authorisation text: {p.auth_text or 'none stated'}.",
        f"Years required: {p.years_required or 'unstated'}.",
        "Requirements: " + ("; ".join(_label(t) for t in p.tags) or "not tagged"),
    ]
    if with_description and p.description:
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
            items.extend(("posting", str(p.id), t, p.url, x) for t, x in posting_chunks(p))
    for title, text in market_texts(stats):
        items.append(("market", title, title, "", text))
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text()
        title = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("#")), path.stem)
        items.extend(("method", path.name, title, "", t) for t in chunk_text(text))

    vecs = embed([it[4] for it in items], "document")  # before deleting, so a failure keeps the old index
    db.execute(delete(Chunk).where(Chunk.owner_id.is_(None)))
    for (stype, ref, title, url, text), v in zip(items, vecs):
        db.add(Chunk(owner_id=None, source_type=stype, source_ref=ref, title=title, url=url, text=text,
                     content_hash=_h(text), embedding_model=s.embedding_model_name, embedding=v))
    db.commit()
    return len(items)


def update_postings(db: Session) -> dict:
    """Daily: embed only new or changed postings, drop chunks of postings no longer open."""
    s = get_settings()
    live = {str(p.id): p for p in db.scalars(select(Posting).where(Posting.status.in_(("open", "unverified"))))}
    have: dict[str, set[str]] = {}
    for c in db.scalars(select(Chunk).where(Chunk.owner_id.is_(None), Chunk.source_type == "posting")):
        have.setdefault(c.source_ref, set()).add(c.content_hash or "")
    gone = [ref for ref in have if ref not in live]
    if gone:
        db.execute(delete(Chunk).where(Chunk.owner_id.is_(None), Chunk.source_type == "posting", Chunk.source_ref.in_(gone)))
    todo = []
    for ref, p in live.items():
        chunks = posting_chunks(p)
        if {_h(x) for _, x in chunks} != have.get(ref, set()):
            todo.append((ref, p, chunks))
    flat = [x for _, _, ch in todo for _, x in ch]
    vecs = embed(flat, "document") if flat else []
    i = 0
    for ref, p, chunks in todo:
        db.execute(delete(Chunk).where(Chunk.owner_id.is_(None), Chunk.source_type == "posting", Chunk.source_ref == ref))
        for t, x in chunks:
            db.add(Chunk(owner_id=None, source_type="posting", source_ref=ref, title=t, url=p.url, text=x,
                         content_hash=_h(x), embedding_model=s.embedding_model_name, embedding=vecs[i]))
            i += 1
    db.commit()
    return {"postings_reindexed": len(todo), "chunks_added": len(flat), "postings_removed": len(gone),
            "postings_indexed": len(live)}


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


def base_text(card: dict) -> str:
    lines = [f"Your v2 base score against {card['n_reference']} people who hold {card['cluster']} roles "
             f"(full experience text read with the same rules for you and for them).",
             f"Base score {card['base_score']} (holder median {card['holders']['median']}); position among holders "
             f"{card['position']}th percentile.",
             "Factors (your percentile vs median holder, weighted gap; + means holders ahead):"]
    for f in card["factors"]:
        lines.append(f"- {f['label']}: you {f['you_pct']} vs {f['holder_median_pct']}, weight {f['weight']}, gap {f['delta']}")
    for g in card["gaps"]:
        lines.append(f"Gap: {g['label']} ({g['class']}). {g['action']} Months to close: {g['months_to_close']}.")
    for d in card["differentiators"]:
        lines.append(f"Differentiator: {d['label']} (you {d['you_pct']} vs median {d['holder_median_pct']}).")
    for x in card["focus_areas"]:
        lines.append(f"Focus area: {x['label']}: {round(100 * x['holder_share'])}% of holders; yours {x['status']}.")
    for p in card["peers"]:
        lines.append(f"Nearest holder: {p['company']} — {p['title']}, score {p['score']}; ahead on "
                     f"{', '.join(p['ahead_on']) or 'nothing'}; you lead on {', '.join(p['you_lead_on']) or 'nothing'}.")
    return "\n".join(lines)


def rebuild_user(db: Session, user: User) -> int:
    from ..services import evaluate

    s = get_settings()
    prof = user.profile
    items: list[tuple[str, str, str]] = []  # (source_type, title, text)
    if prof and (prof.experience_text or "").strip():
        from ..v2.reader import parse_roles

        roles, _ = parse_roles(prof.experience_text)
        for r in roles:
            head = f'{r["title"]} @ {r["company"]} ({r["start_raw"]} – {r["end_raw"]})'
            body = "\n".join(r.get("desc") or [])
            for part in chunk_text(f"{head}\n{body}", 1200, 150):
                items.append(("experience", f"Your experience: {r['title']} @ {r['company']}"[:400], part))
    if prof and (prof.linkedin_text or "").strip():
        from ..v2.reader import parse_linkedin

        for r in parse_linkedin(prof.linkedin_text):
            head = f'{r["title"]} @ {r["company"]} ({r["start_raw"]} – {r["end_raw"]})'
            for part in chunk_text(f"{head}\n" + "\n".join(r.get("desc") or []), 1200, 150):
                items.append(("linkedin", f"Your LinkedIn: {r['title']} @ {r['company']}"[:400], part))
    if prof and prof.cv_text.strip() and prof.cv_text.strip() != (prof.experience_text or "").strip():
        items.extend(("cv", "Your CV", t) for t in chunk_text(prof.cv_text))
    if prof:
        ev = evaluate(db, user)
        items.append(("scorecard", "Your scorecard", scorecard_text(ev)))
        if ev.get("base"):
            items.append(("scorecard", "Your base score (v2)", base_text(ev["base"])))
    vecs = embed([t for _, _, t in items], "document")
    db.execute(delete(Chunk).where(Chunk.owner_id == user.id))
    for (stype, title, text), v in zip(items, vecs):
        db.add(Chunk(owner_id=user.id, source_type=stype, source_ref=stype, title=title, url="", text=text,
                     content_hash=_h(text), embedding_model=s.embedding_model_name, embedding=v))
    db.commit()
    return len(items)


def safe_rebuild_user(db: Session, user: User) -> str:
    """Rebuild the private index without failing the request that triggered it."""
    try:
        rebuild_user(db, user)
        return "ok"
    except Exception as err:  # noqa: BLE001 — a rate limit must not block saving a profile
        db.rollback()
        log.warning("private index rebuild failed: %s", err)
        return f"Your data was saved, but the Ask index was not refreshed: {err}"


def keyword_search(db: Session, user_id: int, query: str, k: int) -> list[tuple[Chunk, float]]:
    """Fallback when the embedding service is unavailable: rank chunks by query-word hits."""
    words = [w for w in re.findall(r"[a-z0-9&]{3,}", query.lower()) if w not in _STOP][:12]
    if not words:
        return []
    rows = list(db.scalars(select(Chunk).where(or_(Chunk.owner_id.is_(None), Chunk.owner_id == user_id))))
    scored = []
    for c in rows:
        low = c.text.lower()
        hits = sum(low.count(w) for w in words)
        if hits:
            scored.append((c, hits))
    scored.sort(key=lambda x: -x[1])
    top = scored[:k]
    mx = top[0][1] if top else 1
    return [(c, round(h / mx, 4)) for c, h in top]


def search(db: Session, user_id: int, query: str, k: int | None = None, *, types: tuple[str, ...] | None = None,
           own_only: bool = False) -> list[tuple[Chunk, float]]:
    """Semantic search. types limits source types (e.g. ("experience", "cv")); own_only searches only your documents."""
    s = get_settings()
    k = k or s.rag_top_k
    try:
        qv = embed([query], "query", quick=True)[0]
    except Exception as err:  # noqa: BLE001
        log.warning("query embedding failed, using keyword search: %s", err)
        return [h for h in keyword_search(db, user_id, query, k * 3)
                if (not types or h[0].source_type in types) and (not own_only or h[0].owner_id == user_id)][:k]
    dist = Chunk.embedding.cosine_distance(qv)
    owner = Chunk.owner_id == user_id if own_only else or_(Chunk.owner_id.is_(None), Chunk.owner_id == user_id)
    stmt = select(Chunk, dist.label("dist")).where(Chunk.embedding_model == s.embedding_model_name).where(owner)
    if types:
        stmt = stmt.where(Chunk.source_type.in_(types))
    stmt = stmt.order_by(dist).limit(k)
    return [(c, round(1 - float(d), 4)) for c, d in db.execute(stmt).all()]
