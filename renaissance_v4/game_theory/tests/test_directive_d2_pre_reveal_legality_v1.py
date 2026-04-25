"""
Directive 02 — Pre-reveal legality (integrity floor).

Every key in ``PRE_REVEAL_FORBIDDEN_KEYS_V1`` is rejected **anywhere** in nested dicts/lists
(``validate_pre_reveal_bundle_v1``). ``validate_student_decision_packet_v1`` extends that check
for decision packets; ``validate_student_output_v1`` extends it for shadow output.

This module locks the **key set** and end-to-end paths so new forbidden fields cannot be added to
``contracts_v1`` without failing CI here.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    PRE_REVEAL_FORBIDDEN_KEYS_V1,
    SCHEMA_STUDENT_OUTPUT_V1,
    validate_pre_reveal_bundle_v1,
    validate_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import emit_shadow_stub_student_output_v1
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
    validate_student_decision_packet_v1,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


def _valid_packet(synthetic_db: Path) -> dict:
    pkt, err = build_student_decision_packet_v1(
        db_path=synthetic_db, symbol="TESTUSDT", decision_open_time_ms=5_000_000, candle_timeframe_minutes=5
    )
    assert err is None and pkt is not None
    return pkt


@pytest.mark.parametrize("forbidden_key", sorted(PRE_REVEAL_FORBIDDEN_KEYS_V1))
def test_every_forbidden_key_nested_rejected_by_pre_reveal_scan(
    forbidden_key: str, tmp_path: Path
) -> None:
    db = tmp_path / "d2.sqlite3"
    _mk_synthetic_db(db)
    base = _valid_packet(db)
    poisoned = deepcopy(base)
    poisoned.setdefault("_d2_probe", {})[forbidden_key] = 0

    pre_msgs = validate_pre_reveal_bundle_v1(poisoned)
    assert pre_msgs, f"expected violation for nested key {forbidden_key!r}"
    pkt_msgs = validate_student_decision_packet_v1(poisoned)
    assert pkt_msgs, f"decision packet validator must reject nested key {forbidden_key!r}"


def test_built_packet_passes_pre_reveal_scan(tmp_path: Path) -> None:
    db = tmp_path / "ok.sqlite3"
    _mk_synthetic_db(db)
    pkt = _valid_packet(db)
    assert validate_pre_reveal_bundle_v1(pkt) == []
    assert validate_student_decision_packet_v1(pkt) == []


def test_shadow_stub_from_legal_packet_emits_valid_output(tmp_path: Path) -> None:
    db = tmp_path / "sh.sqlite3"
    _mk_synthetic_db(db)
    pkt = _valid_packet(db)
    out, errs = emit_shadow_stub_student_output_v1(pkt, graded_unit_id="tr_d2_1")
    assert not errs and out is not None
    assert out.get("schema") == SCHEMA_STUDENT_OUTPUT_V1
    assert validate_student_output_v1(out) == []
    assert validate_pre_reveal_bundle_v1(out) == []


def test_forbidden_key_count_stable() -> None:
    """If this fails, update the parametrized coverage and review architect boundary."""
    assert len(PRE_REVEAL_FORBIDDEN_KEYS_V1) == 18
