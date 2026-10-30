"""Checker agent. Works only from stored outputs, never from the other agents' reasoning.
Deterministic checks first (rules, arithmetic, regression cases, reader quality); then a top-tier model reviews
the analyst's brief against the facts it was written from."""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..llm import BudgetExceeded, complete_json, llm_available
from ..models import Posting
from ..taxonomy import LEVEL_RANK
from ..v2.reader import extract_features, parse_linkedin

GOLDEN = Path(__file__).resolve().parents[2] / "seed" / "golden_reader.json"
COUNTRY_TITLE = re.compile(r"country manager|\bcountry (lead|head|director)\b", re.I)


def rule_violations(passing: list[dict]) -> list[str]:
    """Director+ only; no Country Manager titles; no single-country scope."""
    out = []
    for r in passing:
        p = r["posting"]
        if COUNTRY_TITLE.search(p.title):
            out.append(f"Country Manager title passed the screen: {p.company} — {p.title}")
        if (p.scope or "").lower() == "country":
            out.append(f"Single-country scope passed the screen: {p.company} — {p.title}")
        if LEVEL_RANK.get(p.level_band, 0) < LEVEL_RANK["Director"]:
            out.append(f"Below Director passed the screen: {p.company} — {p.title} ({p.level_band or 'unknown'})")
    return out


def arithmetic(snap) -> list[str]:
    if snap is None:
        return []
    pts = sum(f["points"] or 0 for f in snap.factors)
    return [] if abs(pts - snap.score) <= 0.3 else [f"Factor points sum to {pts:.1f} but the stored score is {snap.score:.1f}"]


def golden() -> dict:
    """Pinned regression cases for the experience reader (expected values were checked by hand when added)."""
    if not GOLDEN.exists():
        return {"cases": 0, "failed": []}
    cases = json.loads(GOLDEN.read_text())
    failed = []
    for c in cases:
        f = extract_features(parse_linkedin(c["text"], tuple(c["now"])), now=tuple(c["now"]))
        for k, v in c["expect"].items():
            got = f.get(k)
            if (round(got, 2) if isinstance(got, float) else got) != v:
                failed.append(f'{c["id"]}: {k} expected {v}, got {got}')
    return {"cases": len(cases), "failed": failed}


def reader_quality(db: Session) -> dict:
    open_q = select(Posting).where(Posting.status == "open")
    rows = list(db.scalars(open_q))
    unread = sum(1 for p in rows if not (p.read_check or {}).get("hash"))
    disputed = sum(1 for p in rows if (p.read_check or {}).get("disputed"))
    keyword = sum(1 for p in rows if (p.read_check or {}).get("mode") == "keyword") if llm_available() else 0
    return {"open": len(rows), "unread": unread, "with_disputed_tags": disputed, "keyword_only": keyword}


NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


def numbers_in(obj) -> set[str]:
    s = json.dumps(obj, default=str)
    out = set()
    for n in NUM.findall(s):
        out.add(n)
        try:
            x = float(n)
            out.update({f"{x:.0f}", f"{x:.1f}", f"{abs(x):.0f}", f"{abs(x):.1f}"})
        except ValueError:
            pass
    return out


REVIEW = """You check a weekly brief against the DATA it was written from. List every problem:
- a statement not supported by DATA, or a number not in DATA;
- any probability, likelihood or chance of being hired;
- advice, strategy or next steps (the brief must report facts only);
- a recommended role that is Country Manager, single-country, or below Director;
- a posting presented as verified when DATA marks it unverified.
Return JSON only: {"issues": [str], "passed": bool}"""


def check_brief(body: str, data: dict, run_id: int | None) -> dict:
    allowed = numbers_in(data)
    stray = sorted({n for n in NUM.findall(body) if n not in allowed and n.lstrip("-") not in allowed and len(n) > 0
                    and not re.fullmatch(r"20\d\d|[1-9]", n)})
    issues = [f"number not found in the data: {n}" for n in stray]
    model_used = None
    if llm_available():
        try:
            from ..llm import model_for

            res = complete_json(REVIEW, f"DATA:\n{json.dumps(data, default=str)[:60000]}\n\nBRIEF:\n{body}",
                                max_tokens=1500, role="critical", agent="checker", run_id=run_id) or {}
            issues += [str(i) for i in res.get("issues", [])]
            model_used = model_for("critical")
        except BudgetExceeded as err:
            issues.append(f"model review skipped: {err}")
    return {"passed": not issues, "issues": issues, "model": model_used}


def run(db: Session, run_id: int | None, per_user: list[dict]) -> dict:
    """per_user: [{"user_id", "passing", "snapshot"}] from the coordinator."""
    from .requirements import evaluate_reader

    report = {"golden": golden(), "reader": reader_quality(db), "reader_test": evaluate_reader(db), "users": []}
    for u in per_user:
        report["users"].append({"user_id": u["user_id"], "rule_violations": rule_violations(u["passing"]),
                                "arithmetic": arithmetic(u["snapshot"])})
    report["passed"] = (not report["golden"]["failed"]
                        and all(not x["rule_violations"] and not x["arithmetic"] for x in report["users"]))
    report["postings_total"] = db.scalar(select(func.count(Posting.id)))
    return report
