"""All Claude calls go through here: model routing by job, the monthly spending cap, prompt caching,
fallback when the account cannot use a model, and a usage log row per call."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from .config import get_settings

log = logging.getLogger(__name__)

# USD per million tokens (input, output, cache write 5m, cache read). Source: platform.claude.com pricing, Oct 2026.
PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 12.5, 0.25),
    "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
}
WEB_SEARCH_USD = 0.01  # per search


class BudgetExceeded(RuntimeError):
    pass


def llm_available() -> bool:
    return bool(get_settings().anthropic_api_key)


def model_for(role: str) -> str:
    s = get_settings()
    return {"bulk": s.model_bulk, "critical": s.model_critical}.get(role, s.anthropic_model)


def cost_usd(model: str, usage) -> float:
    pin, pout, pw, pr = PRICES.get(model, PRICES["claude-opus-5-5"])
    g = lambda k: getattr(usage, k, 0) or 0  # noqa: E731
    searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
    return round((g("input_tokens") * pin + g("output_tokens") * pout + g("cache_creation_input_tokens") * pw
                  + g("cache_read_input_tokens") * pr) / 1e6 + searches * WEB_SEARCH_USD, 6)


def month_spend(db=None) -> float:
    from sqlalchemy import func, select

    from .db import SessionLocal
    from .models import UsageLog

    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    own = db is None
    db = db or SessionLocal()
    try:
        return float(db.scalar(select(func.coalesce(func.sum(UsageLog.cost_usd), 0.0)).where(UsageLog.at >= start)) or 0.0)
    finally:
        if own:
            db.close()


def check_budget() -> None:
    s = get_settings()
    spent = month_spend()
    if spent >= s.monthly_cap_usd:
        raise BudgetExceeded(f"Monthly cap reached: ${spent:.2f} of ${s.monthly_cap_usd:.2f} "
                             f"({int(s.budget_share * 100)}% of ${s.api_monthly_allowance_usd:.2f}).")


def _log(agent: str, run_id: int | None, model: str, usage, requested: str = "", escalated: str = "") -> None:
    """`model` is the model that served (from the response); `requested` is the one the registry assigned."""
    from .db import SessionLocal
    from .models import UsageLog

    g = lambda k: getattr(usage, k, 0) or 0  # noqa: E731
    with SessionLocal() as db:
        db.add(UsageLog(agent=agent, run_id=run_id, model=model, requested_model=requested or model,
                        escalated=escalated[:200], input_tokens=g("input_tokens"),
                        output_tokens=g("output_tokens"), cache_write=g("cache_creation_input_tokens"),
                        cache_read=g("cache_read_input_tokens"), cost_usd=cost_usd(model, usage)))
        db.commit()


def create(*, role: str = "", agent: str = "ask", run_id: int | None = None, system: str = "",
           escalate: str = "", **kwargs):
    """messages.create with routing, cap, caching and logging. Returns (message, model_served) or (None, None).
    The model comes from the registry by agent id (`role` is accepted for older callers and ignored). `escalate` is
    the validation rule that failed (e.g. "quote not found"); only then is the agent's escalation model used."""
    from .agents import registry

    s = get_settings()
    if not s.anthropic_api_key:
        return None, None
    check_budget()
    import anthropic

    client = anthropic.Anthropic(api_key=s.anthropic_api_key)
    sys_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}] if system else []
    models = registry.models_for(agent, escalate=bool(escalate))  # raises for an agent that is not registered
    last = None
    for m in models:
        try:
            msg = client.messages.create(model=m, system=sys_blocks, **kwargs)
        except (anthropic.NotFoundError, anthropic.PermissionDeniedError) as err:
            log.warning("model %s not usable on this account (%s); trying fallback", m, err)
            last = err
            continue
        served = getattr(msg, "model", None) or m
        _log(agent, run_id, served, msg.usage, requested=m, escalated=escalate)
        return msg, served
    raise last  # type: ignore[misc]


def complete(system: str, user: str, max_tokens: int = 1500, *, role: str = "", agent: str = "ask",
             run_id: int | None = None, escalate: str = "") -> str | None:
    msg, _ = create(agent=agent, run_id=run_id, system=system, max_tokens=max_tokens, escalate=escalate,
                    messages=[{"role": "user", "content": user}])
    if msg is None:
        return None
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def parse_json(text: str | None) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        log.warning("LLM returned no JSON")
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        log.warning("LLM returned invalid JSON")
        return None


def complete_json(system: str, user: str, max_tokens: int = 3000, **kw) -> dict | None:
    return parse_json(complete(system + "\nRespond with a single JSON object and nothing else.", user, max_tokens, **kw))


def complete_json_checked(system: str, user: str, validate, max_tokens: int = 3000, *, agent: str,
                          run_id: int | None = None) -> tuple[dict | None, str]:
    """One read on the assigned model; `validate(result)` returns a reason when a rule fails (None when it passes).
    Only then one more read on the agent's escalation model, with the reason recorded. Returns (result, reason or "")."""
    res = complete_json(system, user, max_tokens, agent=agent, run_id=run_id)
    why = validate(res)
    if not why:
        return res, ""
    from .agents import registry

    if not registry.spec(agent).get("escalate_to"):
        return res, why
    res2 = complete_json(system, user, max_tokens, agent=agent, run_id=run_id, escalate=why)
    return (res2, why) if not validate(res2) else (res, why)
