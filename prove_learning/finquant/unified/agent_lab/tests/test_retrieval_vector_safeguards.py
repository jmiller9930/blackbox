"""Safeguards for vector pattern memory: thin-history gate, similarity boost, embedding trace."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from retrieval import effective_vector_min_similarity, retrieve_eligible
from rmv2.memory_index import ensure_db
from rmv2.memory_tiers import insert_stm


def test_effective_vector_min_similarity_boost_when_soft_thin():
    cfg = {
        "memory_vector_min_sim_v1": 0.18,
        "memory_vector_soft_history_rows_v1": 24,
        "memory_vector_thin_history_sim_boost_v1": 0.06,
    }
    assert effective_vector_min_similarity(cfg, 5) == min(0.52, 0.24)
    assert effective_vector_min_similarity(cfg, 24) == 0.18


def test_thin_history_skips_vector_merge():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "records.jsonl")
        db_path = os.path.join(tmpdir, "records.db")
        Path(store_path).write_text("")
        ensure_db(db_path)

        emb_cfg = {
            "memory_embedding_backend_v1": "deterministic",
            "memory_embedding_dim_v1": 128,
            "stm_ttl_hours_v1": 72,
        }
        for i in range(2):
            insert_stm(
                db_path,
                symbol="SOL-PERP",
                regime_v1="trending_up",
                bar_timestamp=f"2026-01-0{i+1}T00:00:00Z",
                narrative_text=f"stub narrative row {i} RSI context",
                config=emb_cfg,
            )

        cfg = {
            "retrieval_enabled_default_v1": False,
            "memory_store_path": store_path,
            "memory_vector_enabled_v1": True,
            "memory_vector_min_pattern_rows_v1": 8,
            "memory_vector_k_stm_v1": 3,
            "memory_vector_k_ltm_v1": 3,
            "memory_vector_min_sim_v1": 0.1,
            "memory_vector_max_extra_v1": 6,
            **emb_cfg,
        }
        case = {
            "symbol": "SOL-PERP",
            "regime_v1": "trending_up",
            "context_narrative_v1": "RSI rising volume expanding long bias",
        }
        eligible, trace = retrieve_eligible(store_path, case, cfg)
        reasons = [e["reason"] for e in trace]
        assert "pattern_memory_thin_history_skip" in reasons
        assert not any(r.get("reason") == "pattern_memory_merged" for r in trace)
        assert not any(r.get("memory_source_v1") == "pattern_memory_stm" for r in eligible)


def test_embedding_semantic_unavailable_trace_on_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "records.jsonl")
        db_path = os.path.join(tmpdir, "records.db")
        Path(store_path).write_text("")
        ensure_db(db_path)

        emb_cfg = {
            "memory_embedding_backend_v1": "ollama",
            "memory_embedding_fallback_v1": True,
            "memory_embedding_dim_v1": 128,
            "ollama_base_url_v1": "http://127.0.0.1:59999",
            "ollama_embeddings_model_v1": "nomic-embed-text",
            "llm_timeout_seconds_v1": 1,
            "stm_ttl_hours_v1": 72,
        }
        for i in range(8):
            insert_stm(
                db_path,
                symbol="SOL-PERP",
                regime_v1="trending_up",
                bar_timestamp=f"2026-02-{i+1:02d}T00:00:00Z",
                narrative_text=f"repeatable narrative slice {i}",
                config={"memory_embedding_backend_v1": "deterministic", "memory_embedding_dim_v1": 128, "stm_ttl_hours_v1": 72},
            )

        cfg = {
            "retrieval_enabled_default_v1": False,
            "memory_store_path": store_path,
            "memory_vector_enabled_v1": True,
            "memory_vector_min_pattern_rows_v1": 8,
            "memory_vector_k_stm_v1": 1,
            "memory_vector_k_ltm_v1": 1,
            "memory_vector_min_sim_v1": 0.0,
            "memory_vector_max_extra_v1": 4,
            **emb_cfg,
        }
        case = {
            "symbol": "SOL-PERP",
            "regime_v1": "trending_up",
            "context_narrative_v1": "RSI rising volume expanding long bias query",
        }
        _, trace = retrieve_eligible(store_path, case, cfg)
        assert any(e["reason"] == "embedding_semantic_unavailable" for e in trace)
