"""GT_DIRECTIVE_016 — L1 road: grouping, LLM model split, A/B bands, fingerprint isolation, HTTP 200."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.student_panel_l1_road_v1 import (
    build_l1_road_payload_v1,
    read_batch_scorecard_file_order_v1,
    resolved_brain_profile_v1,
    scorecard_line_fingerprint_sha256_40_v1,
)
from renaissance_v4.game_theory.web_app import create_app

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "gt_directive_016_l1_road_scorecard_lines.json"
)


def _load_fixture_lines() -> list[dict]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_road_by_job_id_v1_maps_fixture_jobs() -> None:
    payload = build_l1_road_payload_v1(lines=_load_fixture_lines())
    byj = payload.get("road_by_job_id_v1") or {}
    assert "fixture_gt016_fpA_memory_002" in byj
    assert byj["fixture_gt016_fpA_memory_002"]["band"] == "A"
    assert byj["fixture_gt016_fpA_qwen_003"]["llm_model"] == "qwen2.5:7b"


def test_grouping_by_brain_profile_and_llm_split() -> None:
    payload = build_l1_road_payload_v1(lines=_load_fixture_lines())
    assert payload["ok"] is True
    groups = payload["groups"]
    keys = {(g["group_key"]["fingerprint_sha256_40"], g["group_key"]["student_brain_profile_v1"], g["group_key"]["llm_model"]) for g in groups}
    assert ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "baseline_no_memory_no_llm", None) in keys
    assert ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "memory_context_student", None) in keys
    assert ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "memory_context_llm_student", "qwen2.5:7b") in keys
    assert ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "memory_context_llm_student", "deepseek-r1:14b") in keys
    assert ("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "memory_context_student", None) in keys


def test_aggregation_metrics_and_ab_bands() -> None:
    payload = build_l1_road_payload_v1(lines=_load_fixture_lines())
    by_triple = {
        (
            g["group_key"]["fingerprint_sha256_40"],
            g["group_key"]["student_brain_profile_v1"],
            g["group_key"]["llm_model"],
        ): g
        for g in payload["groups"]
    }
    fp_a = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    mem = by_triple[(fp_a, "memory_context_student", None)]
    assert mem["run_count"] == 1
    assert mem["avg_e_expectancy_per_trade"] == 0.2
    assert mem["avg_p_process_score"] == 0.6
    assert mem["pass_rate_percent"] == 55.0
    assert mem["band"] == "A"
    assert mem["process_leg"] == "compared"

    qwen = by_triple[(fp_a, "memory_context_llm_student", "qwen2.5:7b")]
    assert qwen["band"] == "B"
    assert qwen["process_leg"] == "compared"

    ds = by_triple[(fp_a, "memory_context_llm_student", "deepseek-r1:14b")]
    assert ds["band"] == "A"
    assert ds["avg_e_expectancy_per_trade"] == 0.25

    bl = by_triple[(fp_a, "baseline_no_memory_no_llm", None)]
    assert bl["band"] == "baseline_ruler"


def test_second_fingerprint_no_baseline_anchor_data_gap() -> None:
    payload = build_l1_road_payload_v1(lines=_load_fixture_lines())
    fp_b_mem = next(
        g
        for g in payload["groups"]
        if g["group_key"]["fingerprint_sha256_40"] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    )
    assert fp_b_mem["band"] == "data_gap"
    assert "no_baseline_anchor_in_fingerprint_v1" in fp_b_mem["data_gaps"]


def test_mismatched_fingerprints_never_mixed() -> None:
    """Anchor on fp A must not affect fp B aggregates (separate bucket keys)."""
    payload = build_l1_road_payload_v1(lines=_load_fixture_lines())
    fp_b = next(
        g
        for g in payload["groups"]
        if g["group_key"]["fingerprint_sha256_40"] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    )
    assert fp_b["anchor_job_id"] is None


def test_empty_lines_clean_structure() -> None:
    payload = build_l1_road_payload_v1(lines=[])
    assert payload["ok"] is True
    assert payload["groups"] == []
    assert "no_completed_scorecard_lines_v1" in payload["data_gaps"]


def test_missing_fingerprint_row_skipped_with_gap() -> None:
    rows = _load_fixture_lines()
    bad = dict(rows[0])
    bad["job_id"] = "no_fp_row"
    bad["memory_context_impact_audit_v1"] = {}
    bad.pop("student_brain_profile_v1", None)
    bad["student_reasoning_mode"] = "memory_context_student"
    payload = build_l1_road_payload_v1(lines=rows + [bad])
    assert "scorecard_line_missing_fingerprint_v1" in payload["data_gaps"]


def test_e_only_band_when_p_absent() -> None:
    fp = "c" * 40
    lines = [
        {
            "job_id": "anchor_c",
            "status": "done",
            "started_at_utc": "2026-04-01T00:00:00Z",
            "memory_context_impact_audit_v1": {"run_config_fingerprint_sha256_40": fp},
            "student_brain_profile_v1": "baseline_no_memory_no_llm",
            "expectancy_per_trade": 0.1,
            "referee_win_pct": 50.0,
        },
        {
            "job_id": "mem_c",
            "status": "done",
            "started_at_utc": "2026-04-02T00:00:00Z",
            "memory_context_impact_audit_v1": {"run_config_fingerprint_sha256_40": fp},
            "student_brain_profile_v1": "memory_context_student",
            "expectancy_per_trade": 0.2,
            "referee_win_pct": 60.0,
        },
    ]
    payload = build_l1_road_payload_v1(lines=lines)
    g = next(x for x in payload["groups"] if x["group_key"]["student_brain_profile_v1"] == "memory_context_student")
    assert g["avg_p_process_score"] is None
    assert g["process_leg"] == "data_gap"
    assert g["band"] == "A"


def test_get_l1_road_http_200(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "mem"
    root.mkdir()
    monkeypatch.setenv("PATTERN_GAME_MEMORY_ROOT", str(root))
    sc = root / "batch_scorecard.jsonl"
    with sc.open("w", encoding="utf-8") as fh:
        for row in _load_fixture_lines():
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/api/student-panel/l1-road")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("schema") == "student_panel_l1_road_v1"
    assert body.get("ok") is True
    assert len(body.get("groups") or []) >= 4
    assert body.get("legend", {}).get("brain_profiles")


def test_get_docs_student_panel_dictionary_200() -> None:
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/docs/student-panel-dictionary")
    assert r.status_code == 200
    assert b"Student panel dictionary" in r.data
    assert b"Return to Pattern Machine" in r.data
    assert b"pgStudentTriangleDock" in r.data
    assert b"Sys BL %" in r.data or b"Sys BL" in r.data


def test_fixture_file_loads_for_read_order_helper(tmp_path: Path) -> None:
    sc = tmp_path / "batch_scorecard.jsonl"
    lines = _load_fixture_lines()
    with sc.open("w", encoding="utf-8") as fh:
        for row in lines:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    got = read_batch_scorecard_file_order_v1(path=sc)
    assert len(got) == len(lines)
    assert scorecard_line_fingerprint_sha256_40_v1(got[0]) == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert resolved_brain_profile_v1(got[1]) == "memory_context_student"
