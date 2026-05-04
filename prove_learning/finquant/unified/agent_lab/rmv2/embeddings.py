"""
RMv2 — embedding backends for tiered pattern memory.

- ``deterministic``: fixed-dim hash projection (no network; weak semantics; tests / fallback).
- ``ollama``: ``POST /api/embeddings`` on the same host as chat LLM when available.

Learning: swap deterministic → ollama in production for meaningful similarity geometry.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import urllib.error
import urllib.request
from typing import Any


def embed_deterministic(text: str, dim: int = 256) -> list[float]:
    """L2-normalized pseudo-embedding — deterministic from ``text`` + ``dim``."""
    if dim < 8:
        dim = 8
    vec: list[float] = []
    chunk = hashlib.sha256(text.encode("utf-8")).digest()
    i = 0
    while len(vec) < dim:
        chunk = hashlib.sha256(chunk + str(i).encode()).digest()
        for j in range(0, 32, 4):
            if len(vec) >= dim:
                break
            v = int.from_bytes(chunk[j : j + 4], "big") / float(2**32) * 2.0 - 1.0
            vec.append(v)
        i += 1
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed_ollama(
    text: str,
    *,
    base_url: str,
    model: str,
    timeout_seconds: int = 30,
) -> list[float] | None:
    """Return embedding vector or None on failure."""
    url = base_url.rstrip("/") + "/api/embeddings"
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None
    emb = raw.get("embedding")
    if not isinstance(emb, list) or not emb:
        return None
    out = [float(x) for x in emb]
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


def embed_for_memory(
    text: str,
    config: dict[str, Any],
) -> tuple[list[float], str]:
    """
    Choose backend from config.

    Returns (vector, backend_name).
    """
    backend = str(config.get("memory_embedding_backend_v1") or "deterministic").lower()
    dim = int(config.get("memory_embedding_dim_v1") or 256)

    if backend == "ollama":
        base = str(config.get("ollama_base_url_v1") or "http://127.0.0.1:11434")
        model = str(config.get("ollama_embeddings_model_v1") or "nomic-embed-text")
        vec = embed_ollama(text, base_url=base, model=model, timeout_seconds=int(config.get("llm_timeout_seconds_v1") or 45))
        if vec is not None:
            return vec, "ollama"
    return embed_deterministic(text, dim=dim), "deterministic"


def floats_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def blob_to_floats(blob: bytes, dim: int) -> list[float]:
    return list(struct.unpack(f"{dim}f", blob[: dim * 4]))
