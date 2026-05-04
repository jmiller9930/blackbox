"""Tests for RMv2 tiered pattern memory (STM/LTM + cosine retrieval)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rmv2.embeddings import embed_deterministic
from rmv2.memory_index import ensure_db
from rmv2.memory_tiers import (
    cosine_similarity,
    insert_stm,
    pattern_hits_to_synthetic_records,
    promote_stm_to_ltm,
    search_similar_patterns,
)


def test_cosine_identity():
    v = embed_deterministic("hello", dim=64)
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-5


def test_stm_insert_and_similar_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "m.jsonl")
        # companion path convention: use jsonl stem → create db path manually
        db_path = db.replace(".jsonl", ".db")
        ensure_db(db_path)
        cfg = {
            "memory_embedding_backend_v1": "deterministic",
            "memory_embedding_dim_v1": 128,
            "stm_ttl_hours_v1": 72,
            "ollama_base_url_v1": "",
        }
        mid = insert_stm(
            db_path,
            symbol="SOL-PERP",
            regime_v1="trending_up",
            bar_timestamp="2026-01-01T00:00:00Z",
            narrative_text="RSI rising volume expanding long bias",
            config=cfg,
            decision_action="NO_TRADE",
        )
        assert mid

        q = embed_deterministic("RSI rising volume expanding long bias", dim=128)
        hits, trace = search_similar_patterns(
            db_path,
            q,
            symbol="SOL-PERP",
            case_regime="trending_up",
            k_stm=2,
            k_ltm=2,
            min_similarity=0.5,
        )
        assert len(hits) >= 1
        assert any(t["reason"] == "pattern_memory_hit" for t in trace)

        synth = pattern_hits_to_synthetic_records(hits)
        assert synth[0]["memory_source_v1"] == "pattern_memory_stm"

        promote_stm_to_ltm(db_path, mid, outcome_hint="no_trade_correct")
        hits2, _ = search_similar_patterns(
            db_path,
            q,
            symbol="SOL-PERP",
            case_regime="trending_up",
            k_stm=0,
            k_ltm=2,
            min_similarity=0.5,
        )
        assert any(h["tier"] == "ltm" for h in hits2)
