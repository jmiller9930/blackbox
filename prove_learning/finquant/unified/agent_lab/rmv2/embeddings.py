"""
RMv2 — embedding backends for tiered pattern memory.

- ``deterministic``: fixed-dim hash projection (fallback / offline tests).
- ``ollama``: prefers ``POST /api/embed`` (``input`` + ``embeddings``); falls back to
  legacy ``POST /api/embeddings`` (``prompt`` + ``embedding``) for older servers.

Strongest setup: ``memory_embedding_backend_v1`` = ``ollama`` with a dedicated embed model
on the same host as chat (e.g. ``nomic-embed-text``). Install on server::
  ollama pull nomic-embed-text
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


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any] | None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None


def embed_ollama(
    text: str,
    *,
    base_url: str,
    model: str,
    timeout_seconds: int = 45,
) -> list[float] | None:
    """
    Return L2-normalized embedding or None.

    Tries modern ``/api/embed`` first, then legacy ``/api/embeddings``.
    """
    base = base_url.rstrip("/")
    snippet = text[:12000]

    # --- Ollama >= modern: /api/embed, response.embeddings[] ---
    raw = _post_json(
        f"{base}/api/embed",
        {"model": model, "input": snippet, "truncate": True},
        timeout_seconds,
    )
    if raw:
        embs = raw.get("embeddings")
        if isinstance(embs, list) and embs:
            first = embs[0]
            if isinstance(first, list) and first:
                try:
                    return _normalize([float(x) for x in first])
                except (TypeError, ValueError):
                    pass

    # --- Legacy: /api/embeddings, response.embedding ---
    raw2 = _post_json(
        f"{base}/api/embeddings",
        {"model": model, "prompt": snippet},
        timeout_seconds,
    )
    if raw2:
        emb = raw2.get("embedding")
        if isinstance(emb, list) and emb:
            try:
                return _normalize([float(x) for x in emb])
            except (TypeError, ValueError):
                pass

    return None


def embed_for_memory(
    text: str,
    config: dict[str, Any],
) -> tuple[list[float], str]:
    """
    Returns (vector, backend_label).

    ``backend_label``: ``ollama`` | ``deterministic`` | ``deterministic_fallback``
    (fallback when Ollama requested but unreachable / wrong response).
    """
    backend = str(config.get("memory_embedding_backend_v1") or "deterministic").lower()
    dim = int(config.get("memory_embedding_dim_v1") or 256)
    allow_fallback = bool(config.get("memory_embedding_fallback_v1", True))

    if backend == "ollama":
        base = str(config.get("ollama_base_url_v1") or "http://127.0.0.1:11434")
        model = str(config.get("ollama_embeddings_model_v1") or "nomic-embed-text")
        timeout = int(config.get("llm_timeout_seconds_v1") or 45)
        vec = embed_ollama(text, base_url=base, model=model, timeout_seconds=timeout)
        if vec is not None:
            return vec, "ollama"
        if allow_fallback:
            return embed_deterministic(text, dim=dim), "deterministic_fallback"

    return embed_deterministic(text, dim=dim), "deterministic"


def floats_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def blob_to_floats(blob: bytes, dim: int) -> list[float]:
    return list(struct.unpack(f"{dim}f", blob[: dim * 4]))
