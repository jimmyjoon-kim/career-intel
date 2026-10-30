"""Ask agent. Answers a question with tools that return facts computed by code: your scorecard, what-if rescoring,
postings that pass your screen, market requirements, your documents and the agent team's status.
Claude reasons and writes; it never produces a number itself. A final check flags any number not found in tool data."""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..llm import BudgetExceeded, create, month_spend
from ..config import get_settings
from ..models import AgentRun, Brief, Proposal, Question, ScoreSnapshot, User
from ..rag.index import search
from ..services import ensure_profile, evaluate
from ..v2.model import MODEL_VERSION, public, what_if
from ..v2.reader import LEVEL_NAMES
from ..v2.service import scorecard
from .checker import NUM, numbers_in

log = logging.getLogger(__name__)
MAX_TURNS = 8

SYSTEM = """You are the Career Intel agent. You answer one person's questions about their competitiveness for
Director+ commercial roles (partnerships, ad sales, growth, revenue strategy) in US tech, using ONLY data returned by your tools.
How to work:
- Call the tools you need before answering. Prefer one well-chosen call over many. Use what_if for any "what would my score be if…".
- Every number you write must come from a tool result. Never estimate, extrapolate or do arithmetic of your own beyond simple differences shown in tool data.
- Cite documents from search_documents as [1], [2]. Name postings with company and title.
- State what is verified and what is not. If the tools do not hold the answer, say so plainly and stop.
Rules: no probabilities, odds or likelihoods of being hired; no advice, strategy or next steps unless asked; never suggest
contacting people above a counterpart; present gaps with evidence and whether they are closable, without over-weighting negatives;
Director+ only, never Country Manager or single-country roles. Style: concise, short bullets or a few tight lines,
no preamble, American spelling."""

TOOLS = [
    {"name": "get_scorecard", "description": "Your base score (0-100), percentile position among role holders with 95% interval, "
     "each factor's value, percentile, weight and points, the largest gaps and leads versus the median holder, how your level was read, and the benchmark.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "what_if", "description": "Rescore with factor values changed (others as read). Factors and ranges: YOE years 0-45, CT company tier & journey 1-4 "
     "(1 Tier 3, 2 Tier 2, 3 Tier 1, 4 Tier 1 with IPO/acquisition journey), LV level band 0-5 (0 Manager/IC, 1 Director, 2 Head/Sr Director, 3 VP/GM, 4 SVP/MD, 5 C-level), "
     "FN function evidence 0-1, DM domain 0-1, AC quantified outcomes count, ED degree 1-3 (1 bachelor, 2 master/MBA, 3 doctorate), AI 0-1, TK technical depth 0-1.",
     "input_schema": {"type": "object", "properties": {"changes": {"type": "object", "additionalProperties": {"type": "number"}}},
                      "required": ["changes"]}},
    {"name": "search_postings", "description": "Open postings that pass your screen (level, location, authorization, live status), ranked by requirement match. "
     "Optional text filter on company, title or requirement. Set include_failing to see postings that fail the screen and why.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "include_failing": {"type": "boolean"},
                                                       "limit": {"type": "integer"}}}},
    {"name": "get_market_requirements", "description": "Requirement frequency per role cluster across open postings: common minimum (>=70%), mid (30-70%), discriminator (<30%).",
     "input_schema": {"type": "object", "properties": {"cluster": {"type": "string"}}}},
    {"name": "search_documents", "description": "Semantic search over your CV, experience text, postings text, market summaries and method notes. Returns numbered excerpts to cite.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_agent_status", "description": "The agent team: latest weekly brief and its check, recent runs, decisions waiting for approval, API spend against the cap.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_score_history", "description": "Your stored scores over time with model version.",
     "input_schema": {"type": "object", "properties": {}}},
]


class Ctx:
    """Per-question cache so one answer computes the scorecard and evaluation at most once."""

    def __init__(self, db: Session, user: User):
        self.db, self.user = db, user
        self._card = self._ev = None
        self.sources: list[dict] = []

    def card(self):
        if self._card is None:
            self._card, self.feats, self.reason = scorecard(self.db, ensure_profile(self.db, self.user), n_boot=300)
        return self._card

    def ev(self):
        if self._ev is None:
            self._ev = evaluate(self.db, self.user)
        return self._ev


def _r(x, n=1):
    return round(x, n) if isinstance(x, (int, float)) else x


def run_tool(ctx: Ctx, name: str, args: dict) -> dict:
    if name == "get_scorecard":
        card = ctx.card()
        if card is None:
            return {"error": ctx.reason}
        pub = public(card)
        tw = sum(f["weight"] or 0 for f in pub["factors"] if f["you_pct"] is not None) or 1
        rr = ctx.feats.get("recent_role") or {}
        return {"model_version": MODEL_VERSION, "score": pub["base_score"], "position_percentile": pub["position"],
                "position_ci95": pub["position_ci95"], "n_role_holders": pub.get("n_reference"),
                "factors": [{"factor": f["factor"], "label": f["label"], "your_value": f["you_value"], "your_percentile": f["you_pct"],
                             "weight_pct": f["weight"], "points": _r((f["weight"] or 0) * (f["you_pct"] or 0) / tw, 1),
                             "median_holder_value": f["holder_median_value"], "share_of_holders_above_you": f["share_above_you"]}
                            for f in pub["factors"]],
                "largest_gaps": [{"factor": g["label"], "weighted_gap": g["delta"], "class": g.get("class")} for g in pub["gaps"][:4]],
                "leads": [{"factor": d["label"], "weighted_lead": d["delta"]} for d in pub["differentiators"][:4]],
                "level_read_from": {"title": rr.get("title"), "company": rr.get("company"),
                                    "band": LEVEL_NAMES.get(ctx.feats.get("LV")),
                                    "rule": "most recent role held 12+ months"},
                "benchmark": {k: pub["benchmark"][k] for k in ("max", "p90", "p75", "median", "p25", "min", "n_above")},
                "prepared_what_ifs": pub["benchmark"]["whatifs"]}
    if name == "what_if":
        card = ctx.card()
        return what_if(card, args.get("changes") or {}) if card else {"error": ctx.reason}
    if name == "search_postings":
        ev = ctx.ev()
        q = (args.get("query") or "").lower().strip()
        rows = ev["rows"] if args.get("include_failing") else ev["passing"]
        out = []
        for r in rows:
            p = r["posting"]
            hay = f"{p.company} {p.title} {' '.join(p.tags or [])} {p.role_cluster}".lower()
            if q and not all(w in hay for w in q.split()):
                continue
            out.append({"company": p.company, "title": p.title, "location": p.location, "status": p.status,
                        "level": p.level_band, "cluster": p.role_cluster, "match_score": round(r["rank_score"] * 100),
                        "passes_screen": r["gate_pass"], "screen_reasons": r["gate_reasons"],
                        "missing_minimums": [g["label"] for g in r["hard_gaps"]], "gaps": [g["label"] for g in r["gaps"][:4]],
                        "first_seen": p.first_seen, "source": p.source, "url": p.url})
            if len(out) >= min(int(args.get("limit") or 10), 25):
                break
        return {"count_passing_screen": len(ev["passing"]), "returned": len(out), "postings": out}
    if name == "get_market_requirements":
        st = ctx.ev()["stats"]
        want = (args.get("cluster") or "").lower()
        res = {}
        for cname, c in st["clusters"].items():
            if want and want not in cname.lower():
                continue
            tags = sorted(c["tags"].items(), key=lambda kv: -kv[1]["pct"])[:12]
            res[cname] = {"postings": c["n"], "requirements": [{"tag": t, "share_pct": v["pct"],
                                                                "class": v["cls"]} for t, v in tags]}
        return {"clusters": res}
    if name == "search_documents":
        hits = search(ctx.db, ctx.user.id, args.get("query") or "")
        out = []
        for c, sim in hits[:6]:
            n = len(ctx.sources) + 1
            ctx.sources.append({"n": n, "title": c.title, "type": c.source_type, "url": c.url, "similarity": sim, "excerpt": c.text[:400]})
            out.append({"n": n, "title": c.title, "type": c.source_type, "text": c.text[:1200]})
        return {"excerpts": out}
    if name == "get_agent_status":
        db = ctx.db
        b = db.scalar(select(Brief).where(Brief.user_id == ctx.user.id).order_by(Brief.id.desc()))
        runs = db.scalars(select(AgentRun).order_by(AgentRun.id.desc()).limit(5))
        s = get_settings()
        return {"latest_brief": {"date": str(b.created_at)[:10], "body": b.body, "checker_passed": b.check.get("passed"),
                                 "checker_issues": b.check.get("issues")} if b else None,
                "recent_runs": [{"kind": r.kind, "status": r.status, "finished": str(r.finished_at)[:16] if r.finished_at else None,
                                 "steps": [f'{x["agent"]}:{x["status"]}' for x in (r.steps or [])]} for r in runs],
                "waiting_for_approval": [p.title for p in db.scalars(select(Proposal).where(Proposal.status == "pending"))],
                "api_spend_month_usd": round(month_spend(db), 2), "api_cap_usd": s.monthly_cap_usd}
    if name == "get_score_history":
        rows = ctx.db.scalars(select(ScoreSnapshot).where(ScoreSnapshot.user_id == ctx.user.id).order_by(ScoreSnapshot.id))
        return {"points": [{"date": str(r.created_at)[:16], "score": r.score, "position": r.position, "model_version": r.model_version}
                           for r in rows][-20:]}
    return {"error": f"unknown tool {name}"}


def _history(db: Session, user_id: int) -> list[dict]:
    """Last 3 exchanges as short-term memory for follow-up questions."""
    qs = list(db.scalars(select(Question).where(Question.user_id == user_id).order_by(Question.id.desc()).limit(3)))[::-1]
    msgs = []
    for q in qs:
        msgs += [{"role": "user", "content": q.question}, {"role": "assistant", "content": q.answer[:1500]}]
    return msgs


def answer(db: Session, user: User, question: str) -> dict:
    ctx = Ctx(db, user)
    messages = _history(db, user.id) + [{"role": "user", "content": question}]
    steps, tool_data = [], []
    text = ""
    try:
        for _ in range(MAX_TURNS):
            msg, model = create(role="ask", agent="ask", system=SYSTEM, max_tokens=1500, tools=TOOLS, messages=messages)
            if msg is None:
                return {}
            messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in msg.content]})
            calls = [b for b in msg.content if getattr(b, "type", "") == "tool_use"]
            if not calls:
                text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
                break
            results = []
            for c in calls:
                try:
                    out = run_tool(ctx, c.name, c.input or {})
                except Exception as err:  # noqa: BLE001 — report tool failure to the model
                    log.exception("tool %s failed", c.name)
                    out = {"error": f"{type(err).__name__}: {err}"}
                steps.append({"tool": c.name, "input": c.input})
                tool_data.append(out)
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": json.dumps(out, default=str)[:30000]})
            messages.append({"role": "user", "content": results})
        else:
            text = text or "Stopped after the maximum number of lookups without a final answer."
        # Guardrail: every number must appear in tool data, the question or recent history.
        allowed = numbers_in([tool_data, question, [m["content"] for m in messages[:-1] if isinstance(m["content"], str)]])
        stray = sorted({n for n in NUM.findall(text) if n not in allowed and n.lstrip("-") not in allowed
                        and not re.fullmatch(r"20\d\d|[0-9]", n) and not re.fullmatch(r"\d", n.lstrip("-"))})
        stray = [n for n in stray if not re.fullmatch(r"\[?\d\]?", n)]
        if stray and tool_data:
            messages.append({"role": "user", "content": f"These numbers are not in the tool results: {', '.join(stray)}. "
                                                        "Rewrite the answer, removing or correcting them. Output the answer only."})
            msg, model = create(role="ask", agent="ask", system=SYSTEM, max_tokens=1500, tools=TOOLS, messages=messages,
                                tool_choice={"type": "none"})
            fixed = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
            text = fixed or text
            steps.append({"tool": "number_check", "input": {"removed_or_corrected": stray}})
        return {"answer": text, "sources": ctx.sources, "mode": "agent", "steps": steps, "model": model}
    except BudgetExceeded as err:
        return {"answer": f"The monthly API cap is reached, so the agent cannot answer now. {err}", "sources": [], "mode": "error", "steps": steps}
