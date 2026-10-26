"""Embeddings: Voyage AI when VOYAGE_API_KEY is set, otherwise a local hashing embedder.

The local embedder (feature hashing of word unigrams + bigrams, L2-normalised) is a
deterministic offline fallback for development and tests; retrieval quality is lower.
Chunks record which model embedded them, and search only compares like with like.
"""

import hashlib
import logging
import math
import re
import time

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_BATCH = 64
MAX_ATTEMPTS = 8


def _hash_embed(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    words = re.findall(r"[a-z0-9&+]+", text.lower())
    feats = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
    for f in feats:
        h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "big")
        vec[h % dim] += 1.0 if (h >> 63) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _batches(texts: list[str], max_tokens: int) -> list[list[str]]:
    """Group texts so each request stays under a rough token budget (~3.5 chars per token)."""
    out, cur, cur_tok = [], [], 0
    for t in texts:
        tok = len(t) // 3 + 1
        if cur and (cur_tok + tok > max_tokens or len(cur) >= _BATCH):
            out.append(cur)
            cur, cur_tok = [], 0
        cur.append(t)
        cur_tok += tok
    if cur:
        out.append(cur)
    return out


def _post_with_retry(client: httpx.Client, payload: dict, api_key: str) -> httpx.Response:
    """POST to Voyage, waiting and retrying on rate limits (429) and transient 5xx errors."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        resp = client.post(VOYAGE_URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
        if resp.status_code != 429 and resp.status_code < 500:
            break
        if attempt == MAX_ATTEMPTS:
            break
        retry_after = resp.headers.get("retry-after")
        wait = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else min(65, 21 * attempt)
        log.warning("Voyage returned %s; waiting %.0fs (attempt %d/%d)", resp.status_code, wait, attempt, MAX_ATTEMPTS)
        time.sleep(wait)
    if resp.status_code == 401:
        raise RuntimeError("Voyage rejected the API key (401). Check VOYAGE_API_KEY in .env.")
    if resp.status_code == 429:
        raise RuntimeError(
            "Voyage rate limit still exceeded after retries (429). Accounts without a payment method have low limits; "
            "add a payment method in the Voyage dashboard, or wait a minute and run the seed again."
        )
    resp.raise_for_status()
    return resp


def _voyage(texts: list[str], input_type: str) -> list[list[float]]:
    s = get_settings()
    out: list[list[float]] = []
    batches = _batches(texts, s.voyage_max_batch_tokens)
    with httpx.Client(timeout=60) as client:
        for n, batch in enumerate(batches, 1):
            if len(batches) > 1:
                log.info("Embedding batch %d/%d (%d texts)", n, len(batches), len(batch))
            resp = _post_with_retry(client, {
                "input": batch,
                "model": s.voyage_model,
                "input_type": input_type,
                "output_dimension": s.embedding_dim,
            }, s.voyage_api_key)
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
    return out


def embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    s = get_settings()
    if not texts:
        return []
    if s.voyage_api_key:
        return _voyage(texts, input_type)
    return [_hash_embed(t, s.embedding_dim) for t in texts]
