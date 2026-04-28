"""GT_DIRECTIVE_022 — training export: promoted-only, deterministic, schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    legal_example_student_learning_record_v1,
    legal_example_student_output_v1,
    legal_example_student_output_with_thesis_v1,
    validate_student_learning_record_v1,
)
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_HOLD,
    GOVERNANCE_PROMOTE,
    build_learning_governance_v1,
)
from renaissance_v4.game_theory.student_proctor.training_export_v1 import (
    MATERIALIZE_TRAINING_DATASET_CONFIRM_V1,
    SCHEMA_TRAINING_RECORD_V1,
    build_training_export_payload_v1,
    iter_training_record_lines_v1,
    learning_row_eligible_for_training_export_v1,
    materialize_training_dataset_v1,
)
from renaissance_v4.game_theory.web_app import create_app


def _write_scorecard(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in lines) + "\n", encoding="utf-8")


def _write_store(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in rows) + "\n", encoding="utf-8")


def _gov(dec: str, job: str, fp: str | None = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") -> dict:
    return build_learning_governance_v1(
        decision=dec,
        reason_codes=["test_reason_v1"],
        source_job_id=job,
        fingerprint=fp,
        timestamp_utc="2026-04-24T12:00:00Z",
    )


def _learning_row(
    *,
    record_id: str,
    run_id: str,
    graded_unit_id: str,
    student_output: dict,
    gov: dict,
) -> dict:
    r = legal_example_student_learning_record_v1()
    r["record_id"] = record_id
    r["run_id"] = run_id
    r["graded_unit_id"] = graded_unit_id
    r["student_output"] = student_output
    r["student_output"]["graded_unit_id"] = graded_unit_id
    r["learning_governance_v1"] = gov
    errs = validate_student_learning_record_v1(r)
    assert errs == [], errs
    return r


def _populate_022_fixtures(sc: Path, st: Path) -> None:
    _write_scorecard(
        sc,
        [
            {
                "job_id": "run_promote_llm",
                "status": "done",
                "student_brain_profile_v1": "memory_context_llm_student",
                "student_llm_v1": {"llm_model": "qwen2.5:7b"},
                "exam_e_score_v1": 0.8125,
                "exam_p_score_v1": 0.9,
                "exam_pass_v1": True,
                "expectancy_per_trade": 0.05,
            },
            {
                "job_id": "run_promote_baseline",
                "status": "done",
                "student_brain_profile_v1": "baseline_no_memory_no_llm",
                "exam_e_score_v1": None,
                "exam_p_score_v1": None,
                "exam_pass_v1": None,
                "expectancy_per_trade": 0.02,
            },
            {"job_id": "run_running", "status": "running"},
            {"job_id": "run_hold", "status": "done"},
        ],
    )
    so_thesis = legal_example_student_output_with_thesis_v1()
    so_thesis["graded_unit_id"] = "trade_llm_1"
    so_plain = legal_example_student_output_v1()
    so_plain["graded_unit_id"] = "trade_llm_bad"
    so_base = legal_example_student_output_v1()
    so_base["graded_unit_id"] = "trade_base_1"
    rows = [
        _learning_row(
            record_id="11111111-1111-1111-1111-111111111111",
            run_id="run_promote_llm",
            graded_unit_id="trade_llm_1",
            student_output=so_thesis,
            gov=_gov(GOVERNANCE_PROMOTE, "run_promote_llm"),
        ),
        _learning_row(
            record_id="22222222-2222-2222-2222-222222222222",
            run_id="run_hold",
            graded_unit_id="trade_hold_1",
            student_output=so_thesis,
            gov=_gov(GOVERNANCE_HOLD, "run_hold"),
        ),
        _learning_row(
            record_id="33333333-3333-3333-3333-333333333333",
            run_id="run_running",
            graded_unit_id="trade_run_1",
            student_output=so_thesis,
            gov=_gov(GOVERNANCE_PROMOTE, "run_running"),
        ),
        _learning_row(
            record_id="44444444-4444-4444-4444-444444444444",
            run_id="run_promote_llm",
            graded_unit_id="trade_llm_bad",
            student_output=so_plain,
            gov=_gov(GOVERNANCE_PROMOTE, "run_promote_llm"),
        ),
        _learning_row(
            record_id="55555555-5555-5555-5555-555555555555",
            run_id="run_promote_baseline",
            graded_unit_id="trade_base_1",
            student_output=so_base,
            gov=_gov(GOVERNANCE_PROMOTE, "run_promote_baseline"),
        ),
    ]
    leg = legal_example_student_learning_record_v1()
    leg["record_id"] = "66666666-6666-6666-6666-666666666666"
    leg["run_id"] = "run_promote_baseline"
    leg["graded_unit_id"] = "trade_legacy_1"
    leg["student_output"] = so_base
    leg["student_output"]["graded_unit_id"] = "trade_legacy_1"
    assert validate_student_learning_record_v1(leg) == []
    rows.append(leg)
    _write_store(st, rows)


@pytest.fixture()
def scorecard_and_store(tmp_path: Path) -> tuple[Path, Path]:
    sc = tmp_path / "batch_scorecard.jsonl"
    st = tmp_path / "student_learning_records_v1.jsonl"
    _populate_022_fixtures(sc, st)
    return sc, st


def test_promoted_included_hold_rejected_running_excluded(scorecard_and_store: tuple[Path, Path]) -> None:
    sc, st = scorecard_and_store
    payload = build_training_export_payload_v1(store_path=st, scorecard_path=sc, preview_limit=10)
    assert payload["ok"] is True
    assert payload["eligible_count"] == 2
    stats = payload["filter_stats_v1"]
    assert stats["filtered_not_promote"] == 1
    assert stats["filtered_run_not_done"] == 1
    assert stats["filtered_thesis_incomplete"] == 1
    assert stats["filtered_missing_governance"] == 1
    ids = {r["source_learning_record_id"] for r in payload["preview"]}
    assert "11111111-1111-1111-1111-111111111111" in ids
    assert "55555555-5555-5555-5555-555555555555" in ids


def test_training_record_schema_and_thesis(scorecard_and_store: tuple[Path, Path]) -> None:
    sc, st = scorecard_and_store
    payload = build_training_export_payload_v1(store_path=st, scorecard_path=sc, preview_limit=10)
    for r in payload["preview"]:
        assert r["schema"] == SCHEMA_TRAINING_RECORD_V1
        assert r["promotion_decision"] == GOVERNANCE_PROMOTE
        assert r["student_output_v1"]["schema"] == "student_output_v1"
        assert "directional_thesis_v1" in r
        if r["student_brain_profile_v1"] == "memory_context_llm_student":
            dt = r["directional_thesis_v1"]
            assert dt.get("student_action_v1") == "enter_long"


def test_deterministic_lines_twice_identical(scorecard_and_store: tuple[Path, Path]) -> None:
    sc, st = scorecard_and_store
    a = "\n".join(iter_training_record_lines_v1(store_path=st, scorecard_path=sc, exported_at_utc="FIXED_TS")) + "\n"
    b = "\n".join(iter_training_record_lines_v1(store_path=st, scorecard_path=sc, exported_at_utc="FIXED_TS")) + "\n"
    assert a == b
    assert "FIXED_TS" in a


def test_materialize_writes_and_confirm_required(scorecard_and_store: tuple[Path, Path], tmp_path: Path) -> None:
    sc, st = scorecard_and_store
    out_p = tmp_path / "training_dataset_v1.jsonl"
    bad = materialize_training_dataset_v1(
        store_path=st, scorecard_path=sc, output_path=out_p, confirm="wrong"
    )
    assert bad.get("ok") is False
    good = materialize_training_dataset_v1(
        store_path=st,
        scorecard_path=sc,
        output_path=out_p,
        confirm=MATERIALIZE_TRAINING_DATASET_CONFIRM_V1,
    )
    assert good.get("ok") is True
    assert good["line_count"] == 2
    loaded = [json.loads(ln) for ln in out_p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(loaded) == 2


def test_eligibility_guards_direct() -> None:
    so = legal_example_student_output_v1()
    row = legal_example_student_learning_record_v1()
    row["learning_governance_v1"] = _gov(GOVERNANCE_PROMOTE, "x")
    row["student_output"] = so
    ok, _ = learning_row_eligible_for_training_export_v1(row, scorecard_entry=None)
    assert ok is False


def test_http_get_training_export(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sc = tmp_path / "batch_scorecard.jsonl"
    st = tmp_path / "student_learning_records_v1.jsonl"
    _populate_022_fixtures(sc, st)
    monkeypatch.setenv("PATTERN_GAME_MEMORY_ROOT", str(tmp_path))
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LEARNING_STORE", str(st))
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/api/training/export?preview=3")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("ok") is True
    assert body.get("eligible_count") == 2
    assert len(body.get("preview") or []) <= 3
