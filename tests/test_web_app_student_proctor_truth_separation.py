"""Directive 08 — Scorecard / engine reset vs Student Proctor store (backend + API truth)."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.game_theory.pattern_game_operator_reset import RESET_PATTERN_GAME_LEARNING_CONFIRM
from renaissance_v4.game_theory.student_proctor.contracts_v1 import legal_example_student_learning_record_v1
from renaissance_v4.game_theory.student_proctor.student_learning_operator_v1 import (
    RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    default_student_learning_store_path_v1,
)
from renaissance_v4.game_theory.web_app import create_app


def _seed_student_store(path_store: Path) -> None:
    rec = legal_example_student_learning_record_v1()
    rec["record_id"] = "d08-proof-row"
    rec["run_id"] = "run_d08"
    append_student_learning_record_v1(path_store, rec)


def test_api_get_student_proctor_store_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BLACKBOX_PML_RUNTIME_ROOT", str(tmp_path / "rt"))
    p = default_student_learning_store_path_v1()
    _seed_student_store(p)
    app = create_app()
    r = app.test_client().get("/api/student-proctor/learning-store")
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("ok") is True
    assert j.get("line_count") == 1
    assert "student_learning" in (j.get("path") or "")


def test_batch_scorecard_clear_does_not_touch_student_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BLACKBOX_PML_RUNTIME_ROOT", str(tmp_path / "rt"))
    p = default_student_learning_store_path_v1()
    _seed_student_store(p)
    before = p.read_text(encoding="utf-8")

    app = create_app()
    c = app.test_client()
    r = c.post("/api/batch-scorecard/clear", json={"confirm": True})
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("student_proctor_learning_store_unchanged") is True
    assert j.get("student_proctor_learning_store", {}).get("line_count") == 1
    assert p.read_text(encoding="utf-8") == before


def test_engine_reset_does_not_touch_student_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BLACKBOX_PML_RUNTIME_ROOT", str(tmp_path / "rt"))
    p = default_student_learning_store_path_v1()
    _seed_student_store(p)
    before = p.read_text(encoding="utf-8")

    app = create_app()
    c = app.test_client()
    r = c.post(
        "/api/pattern-game/reset-learning",
        json={"confirm": RESET_PATTERN_GAME_LEARNING_CONFIRM},
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("student_proctor_learning_store_unchanged") is True
    assert p.read_text(encoding="utf-8") == before


def test_student_store_clear_requires_confirm() -> None:
    app = create_app()
    r = app.test_client().post("/api/student-proctor/learning-store/clear", json={"confirm": "nope"})
    assert r.status_code == 400


def test_student_store_clear_truncates_store_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BLACKBOX_PML_RUNTIME_ROOT", str(tmp_path / "rt"))
    p = default_student_learning_store_path_v1()
    _seed_student_store(p)
    app = create_app()
    c = app.test_client()
    r = c.post(
        "/api/student-proctor/learning-store/clear",
        json={"confirm": RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM},
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("ok") is True
    assert p.read_text(encoding="utf-8") == ""
    st = c.get("/api/student-proctor/learning-store").get_json()
    assert st.get("line_count") == 0
