"""Embeddings: Voyage AI when VOYAGE_API_KEY is set, otherwise a local hashing embedder.

The local embedder (feature hashing of word unigrams + bigrams, L2-normalised) is a
deterministic offline fallback for development and tests; retrieval quality is lower.
Chunks record which model embedded them, and search only compares like with like.
"""

import hashlib
import math
import re

import httpx

from ..config import get_settings

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_BATCH = 64


def _hash_embed(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    words = re.findall(r"[a-z0-9&+]+", text.lower())
    feats = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
    for f in feats:
        h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "big")
        vec[h % dim] += 1.0 if (h >> 63) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _voyage(texts: list[str], input_type: str) -> list[list[float]]:
    s = get_settings()
    out: list[list[float]] = []
    with httpx.Client(timeout=60) as client:
        for i in range(0, len(texts), _BATCH):
            resp = client.post(
                VOYAGE_URL,
                headers={"Authorization": f"Bearer {s.voyage_api_key}"},
                json={
                    "input": texts[i : i + _BATCH],
                    "model": s.voyage_model,
                    "input_type": input_type,
                    "output_dimension": s.embedding_dim,
                },
            )
            resp.raise_for_status()
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
