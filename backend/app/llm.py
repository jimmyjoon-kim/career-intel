"""Thin wrapper around the Anthropic Messages API. Returns None when no key is configured."""

import json
import logging
import re

from .config import get_settings

log = logging.getLogger(__name__)


def llm_available() -> bool:
    return bool(get_settings().anthropic_api_key)


def complete(system: str, user: str, max_tokens: int = 1500) -> str | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    import anthropic

    client = anthropic.Anthropic(api_key=s.anthropic_api_key)
    msg = client.messages.create(
        model=s.anthropic_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def complete_json(system: str, user: str, max_tokens: int = 3000) -> dict | None:
    text = complete(system + "\nRespond with a single JSON object and nothing else.", user, max_tokens)
    if text is None:
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
