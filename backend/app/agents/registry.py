"""Model registry: which model each agent runs on (registry.json). The app resolves every model call through it, so
no call can pick a model on its own, and the health check can compare the model that served with the one assigned."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


class UnknownAgent(KeyError):
    pass


@lru_cache
def load() -> dict:
    return json.loads((Path(__file__).with_name("registry.json")).read_text())


def spec(agent: str) -> dict:
    a = load()["agents"].get(agent)
    if a is None:
        raise UnknownAgent(f"agent '{agent}' is not in the model registry (backend/app/agents/registry.json)")
    return a


def model_id(tier: str | None) -> str | None:
    return load()["tiers"].get(tier, tier) if tier else None


def models_for(agent: str, escalate: bool = False) -> list[str]:
    """Models to try, in order: the assigned one (or its escalation model when a validation rule failed), then the
    fallback used only when the account cannot use the first."""
    a = spec(agent)
    if a.get("runner") != "api":
        raise UnknownAgent(f"agent '{agent}' does not run through the in-app API (runner: {a.get('runner')})")
    first = a.get("escalate_to") if escalate and a.get("escalate_to") else a["model"]
    out = [model_id(first)] + ([model_id(a["fallback"])] if a.get("fallback") else [])
    return [m for i, m in enumerate(out) if m and m not in out[:i]]


def allowed_models(agent: str) -> set[str]:
    a = load()["agents"].get(agent) or {}
    return {m for m in (model_id(a.get(k)) for k in ("model", "fallback", "escalate_to")) if m}


def top_tier() -> str:
    return load()["tiers"]["top"]


def table() -> list[dict]:
    return [{"agent": k, "job": v["job"], "runner": v["runner"], "model": model_id(v.get("model")) or "none (code)",
             "escalates_to": model_id(v.get("escalate_to")), "fallback": model_id(v.get("fallback"))}
            for k, v in load()["agents"].items()]
