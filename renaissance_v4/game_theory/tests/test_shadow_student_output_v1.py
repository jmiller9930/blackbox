"""
Directive 03 — Shadow ``student_output_v1`` stub: schema, multi-unit, Referee isolation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.contracts_v1 import validate_student_output_v1
from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import (
    emit_shadow_stub_student_output_v1,
    shadow_stub_student_outputs_for_outcomes,
)
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
    validate_student_decision_packet_v1,
)


@pytest.fixture()
def synthetic_db(tmp_path: Path) -> Path:
    p = tmp_path / "shadow_t.sqlite3"
    _mk_synthetic_db(p)
    return p


def test_e2e_legal_decision_packet_to_valid_student_output(
    synthetic_db: Path,
) -> None:
    """
    End-to-end acceptance chain (one run):

    SQLite → ``build_student_decision_packet_v1`` → legal ``student_decision_packet_v1``
    → ``validate_student_decision_packet_v1`` (empty errors)
    → ``emit_shadow_stub_student_output_v1`` → ``student_output_v1``
    → ``validate_student_output_v1`` (empty errors).
    """
    pkt, err = build_student_decision_packet_v1(
        db_path=synthetic_db,
        symbol="TESTUSDT",
        decision_open_time_ms=8_000_000,
    )
    assert err is None and pkt is not None
    assert validate_student_decision_packet_v1(pkt) == []
    out, emit_errs = emit_shadow_stub_student_output_v1(
        pkt, graded_unit_id="e2e_trade_demo", decision_at_ms=8_000_000
    )
    assert emit_errs == [] and out is not None
    assert validate_student_output_v1(out) == []
    assert out["schema"] == "student_output_v1"


def test_emit_shadow_stub_validates(synthetic_db: Path) -> None:
    pkt, err = build_student_decision_packet_v1(
        db_path=synthetic_db,
        symbol="TESTUSDT",
        decision_open_time_ms=8_000_000,
    )
    assert err is None and pkt is not None
    out, errs = emit_shadow_stub_student_output_v1(pkt, graded_unit_id="graded_demo_001")
    assert errs == [], str(errs)
    assert out is not None
    assert validate_student_output_v1(out) == []


def test_multiple_graded_units_distinct_outputs(synthetic_db: Path) -> None:
    """Several decision times / ids → distinct validated outputs."""
    ids = ("gu_a", "gu_b", "gu_c")
    times = (3_000_000, 5_000_000, 9_000_000)
    seen_refs: set[str] = set()
    for gid, tms in zip(ids, times, strict=True):
        pkt, err = build_student_decision_packet_v1(
            db_path=synthetic_db,
            symbol="TESTUSDT",
            decision_open_time_ms=tms,
        )
        assert err is None and pkt is not None
        out, errs = emit_shadow_stub_student_output_v1(pkt, graded_unit_id=gid, decision_at_ms=tms)
        assert not errs and out
        assert validate_student_output_v1(out) == []
        assert out["graded_unit_id"] == gid
        seen_refs.add(out["student_decision_ref"])
    assert len(seen_refs) == 3


def test_shadow_outputs_for_outcome_records(synthetic_db: Path) -> None:
    outcomes = [
        OutcomeRecord(
            trade_id="t1",
            symbol="TESTUSDT",
            direction="long",
            entry_time=4_000_000,
            exit_time=5_000_000,
            entry_price=100.0,
            exit_price=100.5,
            pnl=1.0,
            mae=0.0,
            mfe=1.0,
            exit_reason="test",
        ),
        OutcomeRecord(
            trade_id="t2",
            symbol="TESTUSDT",
            direction="short",
            entry_time=6_000_000,
            exit_time=7_000_000,
            entry_price=100.5,
            exit_price=100.0,
            pnl=2.0,
            mae=0.0,
            mfe=1.0,
            exit_reason="test",
        ),
    ]
    outs, errs = shadow_stub_student_outputs_for_outcomes(outcomes, db_path=synthetic_db)
    assert not errs, errs
    assert len(outs) == 2
    assert {o["graded_unit_id"] for o in outs} == {"t1", "t2"}
    for o in outs:
        assert validate_student_output_v1(o) == []


def test_batch_path_never_appends_invalid_student_output(
    synthetic_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    If emit incorrectly returned a non-contract dict with no error list, the batch schema gate
    must still refuse to append (no silent invalid artifacts).
    """
    o = OutcomeRecord(
        trade_id="tamper",
        symbol="TESTUSDT",
        direction="long",
        entry_time=4_000_000,
        exit_time=5_000_000,
        entry_price=100.0,
        exit_price=100.5,
        pnl=1.0,
        mae=0.0,
        mfe=1.0,
        exit_reason="test",
    )

    def fake_emit(
        *_args: object, **_kwargs: object
    ) -> tuple[dict[str, object], list[str]]:
        return {"schema": "broken_not_student_output"}, []

    monkeypatch.setattr(
        "renaissance_v4.game_theory.student_proctor.shadow_student_v1.emit_shadow_stub_student_output_v1",
        fake_emit,
    )
    outs, errs = shadow_stub_student_outputs_for_outcomes([o], db_path=synthetic_db)
    assert outs == []
    assert any("post_emit_schema_gate" in e for e in errs)


def test_emit_rejects_illegal_decision_packet() -> None:
    out, errs = emit_shadow_stub_student_output_v1(
        {"schema": "not_decision_packet"}, graded_unit_id="x"
    )
    assert out is None
    assert errs


def test_emit_is_deterministic_for_same_inputs(synthetic_db: Path) -> None:
    pkt, err = build_student_decision_packet_v1(
        db_path=synthetic_db,
        symbol="TESTUSDT",
        decision_open_time_ms=5_000_000,
    )
    assert err is None and pkt is not None
    a, _ = emit_shadow_stub_student_output_v1(
        pkt, graded_unit_id="same_id", decision_at_ms=5_000_000
    )
    b, _ = emit_shadow_stub_student_output_v1(
        pkt, graded_unit_id="same_id", decision_at_ms=5_000_000
    )
    assert a == b


def test_committed_example_json_validates() -> None:
    ex = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "student_output_v1_shadow_stub_example.json"
    )
    doc = json.loads(ex.read_text(encoding="utf-8"))
    assert validate_student_output_v1(doc) == []


def test_referee_codepath_does_not_depend_on_shadow_student() -> None:
    """Shadow module must not be imported by replay / pattern-game Referee stack (static proof)."""
    root = Path(__file__).resolve().parents[2]  # renaissance_v4
    rr = (root / "research" / "replay_runner.py").read_text(encoding="utf-8")
    pg = (root / "game_theory" / "pattern_game.py").read_text(encoding="utf-8")
    wa = (root / "game_theory" / "web_app.py").read_text(encoding="utf-8")
    assert "shadow_student" not in rr
    assert "shadow_student" not in pg
    assert "student_output_v1" not in wa
    assert "emit_shadow_stub" not in wa


def test_execution_facing_modules_do_not_reference_shadow_student_outputs() -> None:
    """No core/research execution stack module references Shadow Student (repository search)."""
    root = Path(__file__).resolve().parents[2]
    for rel in (
        root / "core",
        root / "research" / "replay_runner.py",
        root / "game_theory" / "pattern_game.py",
    ):
        if rel.is_dir():
            for py in rel.rglob("*.py"):
                t = py.read_text(encoding="utf-8")
                assert "emit_shadow_stub" not in t, py
                assert "shadow_student_v1" not in t, py
                assert "shadow_stub_student_outputs_for_outcomes" not in t, py
        else:
            t = rel.read_text(encoding="utf-8")
            assert "emit_shadow_stub" not in t
            assert "shadow_student_v1" not in t
            assert "shadow_stub_student_outputs_for_outcomes" not in t
