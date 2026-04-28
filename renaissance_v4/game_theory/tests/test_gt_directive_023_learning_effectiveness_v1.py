"""GT_DIRECTIVE_023 — learning effectiveness report: grouping, order, deltas, API, determinism."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    legal_example_student_learning_record_v1,
    legal_example_student_output_v1,
    validate_student_learning_record_v1,
)
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_HOLD,
    GOVERNANCE_PROMOTE,
    build_learning_governance_v1,
)
from renaissance_v4.game_theory.student_proctor.learning_effectiveness_report_v1 import (
    MATERIALIZE_LEARNING_EFFECTIVENESS_CONFIRM_V1,
    SCHEMA_LEARNING_EFFECTIVENESS_REPORT_V1,
    build_learning_effectiveness_report_v1,
    materialize_learning_effectiveness_report_v1,
    summarize_learning_effectiveness_report_v1,
)
from renaissance_v4.game_theory.web_app import create_app


def _write_scorecard(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in lines) + "\n", encoding="utf-8")


def _write_store(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in rows) + "\n", encoding="utf-8")


def _oba(*, recipe: str) -> dict:
    return {
        "operator_recipe_id": recipe,
        "evaluation_window_effective_calendar_months": "12",
        "manifest_path_primary": "/tmp/manifest.json",
        "policy_framework_id": "pf1",
    }


def _gov(dec: str, job: str, fp: str | None = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") -> dict:
    return build_learning_governance_v1(
        decision=dec,
        reason_codes=["test_reason_v1"],
        source_job_id=job,
        fingerprint=fp,
        timestamp_utc="2026-04-24T12:00:00Z",
    )


def _learning_row(*, record_id: str, run_id: str, graded_unit_id: str, gov: dict) -> dict:
    so = legal_example_student_output_v1()
    so["graded_unit_id"] = graded_unit_id
    r = legal_example_student_learning_record_v1()
    r["record_id"] = record_id
    r["run_id"] = run_id
    r["graded_unit_id"] = graded_unit_id
    r["student_output"] = so
    r["learning_governance_v1"] = gov
    assert validate_student_learning_record_v1(r) == []
    return r


def _populate_023_fixtures(sc: Path, st: Path) -> None:
    oba1 = _oba(recipe="recipe_fp1_v1")
    # File order intentionally not chronological for fingerprint A (proves sort by started_at_utc).
    _write_scorecard(
        sc,
        [
            {
                "job_id": "job_fp1_late",
                "status": "done",
                "started_at_utc": "2026-12-01T00:00:00Z",
                "operator_batch_audit": oba1,
                "student_brain_profile_v1": "memory_context_llm_student",
                "student_llm_v1": {"llm_model": "qwen2.5:7b"},
                "exam_e_score_v1": 0.9,
                "exam_p_score_v1": 0.95,
                "exam_pass_v1": True,
            },
            {
                "job_id": "job_fp1_early",
                "status": "done",
                "started_at_utc": "2026-01-01T00:00:00Z",
                "operator_batch_audit": oba1,
                "student_brain_profile_v1": "baseline_no_memory_no_llm",
                "exam_e_score_v1": 0.1,
                "exam_p_score_v1": 0.2,
                "exam_pass_v1": False,
            },
            {
                "job_id": "job_fp1_mid",
                "status": "done",
                "started_at_utc": "2026-06-01T00:00:00Z",
                "operator_batch_audit": oba1,
                "student_brain_profile_v1": "memory_context_student",
                "exam_e_score_v1": 0.5,
                "exam_p_score_v1": 0.6,
                "exam_pass_v1": True,
            },
            {
                "job_id": "job_fp2_only",
                "status": "done",
                "started_at_utc": "2026-03-01T00:00:00Z",
                "operator_batch_audit": _oba(recipe="recipe_fp2_v1"),
                "student_brain_profile_v1": "baseline_no_memory_no_llm",
                "exam_e_score_v1": 0.33,
                "exam_p_score_v1": 0.44,
                "exam_pass_v1": True,
            },
        ],
    )
    rows = [
        _learning_row(
            record_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            run_id="job_fp1_early",
            graded_unit_id="t_early",
            gov=_gov(GOVERNANCE_PROMOTE, "job_fp1_early"),
        ),
        _learning_row(
            record_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            run_id="job_fp1_mid",
            graded_unit_id="t_mid",
            gov=_gov(GOVERNANCE_HOLD, "job_fp1_mid"),
        ),
        _learning_row(
            record_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
            run_id="job_fp1_late",
            graded_unit_id="t_late",
            gov=_gov(GOVERNANCE_PROMOTE, "job_fp1_late"),
        ),
    ]
    _write_store(st, rows)


@pytest.fixture()
def scorecard_and_store(tmp_path: Path) -> tuple[Path, Path]:
    sc = tmp_path / "batch_scorecard.jsonl"
    st = tmp_path / "student_learning_records_v1.jsonl"
    _populate_023_fixtures(sc, st)
    return sc, st


def test_grouping_by_fingerprint_and_run_counts(scorecard_and_store: tuple[Path, Path]) -> None:
    sc, st = scorecard_and_store
    rep = build_learning_effectiveness_report_v1(scorecard_path=sc, store_path=st)
    assert rep["schema"] == SCHEMA_LEARNING_EFFECTIVENESS_REPORT_V1
    fps = rep["fingerprints_v1"]
    counts = sorted(x["n_runs_done_v1"] for x in fps)
    assert counts == [1, 3]


def test_time_ordering_within_fingerprint(scorecard_and_store: tuple[Path, Path]) -> None:
    sc, st = scorecard_and_store
    rep = build_learning_effectiveness_report_v1(scorecard_path=sc, store_path=st)
    fp3 = next(x for x in rep["fingerprints_v1"] if x["n_runs_done_v1"] == 3)
    order = [r["job_id"] for r in fp3["runs_ordered_v1"]]
    assert order == ["job_fp1_early", "job_fp1_mid", "job_fp1_late"]
    ordinals = [r["ordinal_in_fingerprint_v1"] for r in fp3["runs_ordered_v1"]]
    assert ordinals == [0, 1, 2]
    starts = [r["started_at_utc"] for r in fp3["runs_ordered_v1"]]
    assert starts == ["2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z", "2026-12-01T00:00:00Z"]


def test_slopes_and_deltas_and_promotion_next_run(scorecard_and_store: tuple[Path, Path]) -> None:
    sc, st = scorecard_and_store
    rep = build_learning_effectiveness_report_v1(scorecard_path=sc, store_path=st)
    fp3 = next(x for x in rep["fingerprints_v1"] if x["n_runs_done_v1"] == 3)
    tt = fp3["time_trends_v1"]
    assert tt["slope_e_over_ordinal_v1"] == pytest.approx(0.4)
    assert tt["slope_p_over_ordinal_v1"] == pytest.approx(0.375)
    assert tt["pass_trend_label_v1"] == "increasing"
    d = fp3["deltas_v1"]
    assert d["delta_mean_e_memory_student_vs_baseline_v1"] == pytest.approx(0.4)
    assert d["delta_mean_p_memory_student_vs_baseline_v1"] == pytest.approx(0.4)
    assert d["delta_mean_pass_memory_student_vs_baseline_v1"] == pytest.approx(1.0)
    assert d["delta_mean_e_llm_vs_memory_student_v1"] == pytest.approx(0.4)
    assert d["delta_mean_p_llm_vs_memory_student_v1"] == pytest.approx(0.35)
    assert d["delta_mean_pass_llm_vs_memory_student_v1"] == pytest.approx(0.0)
    pr = fp3["promotion_next_run_v1"]
    assert pr["mean_e_next_run_after_promoted_source_v1"] == pytest.approx(0.5)
    assert pr["mean_e_next_run_after_non_promoted_source_v1"] == pytest.approx(0.9)
    stb = fp3["stability_v1"]
    assert stb["variance_e_across_runs_v1"] == pytest.approx(32 / 300, rel=1e-9, abs=1e-9)


def test_deterministic_serialized_report(monkeypatch: pytest.MonkeyPatch, scorecard_and_store: tuple[Path, Path]) -> None:
    sc, st = scorecard_and_store
    import renaissance_v4.game_theory.student_proctor.learning_effectiveness_report_v1 as le_mod

    monkeypatch.setattr(le_mod, "_utc_iso", lambda: "2026-04-24T00:00:00Z")
    a = json.dumps(build_learning_effectiveness_report_v1(scorecard_path=sc, store_path=st), sort_keys=True)
    b = json.dumps(build_learning_effectiveness_report_v1(scorecard_path=sc, store_path=st), sort_keys=True)
    assert a == b


def test_materialize_confirm(scorecard_and_store: tuple[Path, Path], tmp_path: Path) -> None:
    sc, st = scorecard_and_store
    out_p = tmp_path / "learning_effectiveness_report_v1.json"
    bad = materialize_learning_effectiveness_report_v1(
        scorecard_path=sc, store_path=st, output_path=out_p, confirm="nope"
    )
    assert bad.get("ok") is False
    good = materialize_learning_effectiveness_report_v1(
        scorecard_path=sc,
        store_path=st,
        output_path=out_p,
        confirm=MATERIALIZE_LEARNING_EFFECTIVENESS_CONFIRM_V1,
    )
    assert good.get("ok") is True
    loaded = json.loads(out_p.read_text(encoding="utf-8"))
    assert loaded["schema"] == SCHEMA_LEARNING_EFFECTIVENESS_REPORT_V1


def test_http_learning_effectiveness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sc = tmp_path / "batch_scorecard.jsonl"
    st = tmp_path / "student_learning_records_v1.jsonl"
    _populate_023_fixtures(sc, st)
    monkeypatch.setenv("PATTERN_GAME_MEMORY_ROOT", str(tmp_path))
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LEARNING_STORE", str(st))
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.get("/api/training/learning-effectiveness")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("ok") is True
    assert body.get("schema") == SCHEMA_LEARNING_EFFECTIVENESS_REPORT_V1
    assert isinstance(body.get("fingerprints_v1"), list)
    assert body["fingerprints_v1"][0].get("runs_ordered_v1") is not None

    with app.test_client() as c:
        rs = c.get("/api/training/learning-effectiveness?summary=1")
    assert rs.status_code == 200
    sm = rs.get_json()
    assert sm.get("ok") is True
    assert sm.get("schema") == "learning_effectiveness_report_summary_v1"
    for fp in sm["fingerprints_v1"]:
        assert "runs_ordered_v1" not in fp
        assert "n_runs_in_series_v1" in fp
