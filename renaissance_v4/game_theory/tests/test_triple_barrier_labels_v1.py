"""GT055 — triple-barrier label mapping and enrichment."""

from __future__ import annotations

import os

import pytest

from renaissance_v4.game_theory.triple_barrier_labels_v1 import (
    triple_barrier_label_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    build_student_learning_record_v1_from_reveal,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import legal_example_reveal_v1


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("target", 1),
        ("stop", -1),
        ("stop_loss", -1),
        ("take_profit", 1),
        ("", 0),
        ("session_timeout", 0),
    ],
)
def test_triple_barrier_label_v1_mapping(reason: str, expected: int) -> None:
    assert triple_barrier_label_v1(reason) == expected


def test_build_learning_record_with_labels_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GT055_TRIPLE_BARRIER_LABELS_V1", "1")
    reveal = legal_example_reveal_v1()
    rt = reveal["referee_truth_v1"]
    rt["exit_reason"] = "target"
    rt["entry_time_ms"] = 1_700_000_000_000
    rt["exit_time_ms"] = 1_700_000_900_000
    rt["entry_price"] = 100.0
    rt["exit_price"] = 101.0
    doc, errs = build_student_learning_record_v1_from_reveal(
        reveal,
        run_id="run_x",
        context_signature_v1={"schema": "context_signature_v1", "signature_key": "k"},
        candle_timeframe_minutes=15,
        record_id="r1",
    )
    assert not errs and doc
    sub = doc["referee_outcome_subset"]
    assert sub.get("triple_barrier_label_v1") == 1
    assert sub.get("bars_held_v1") >= 1
