"""RCA fix: production seam uses live Ollama; RM preflight uses stub seal only.

``PATTERN_GAME_STUDENT_LLM_CONTRACT_REPAIR`` (default on) enables GT036/GT037 repair outside student_test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from renaissance_v4.game_theory.student_proctor.contracts_v1 import legal_example_student_output_with_thesis_v1
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import build_student_decision_packet_v1
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    emit_student_output_via_ollama_v1,
    student_llm_contract_repair_enabled_v1,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


@pytest.fixture()
def decision_packet(tmp_path: Path) -> dict[str, Any]:
    db = tmp_path / "repair_rca.sqlite3"
    _mk_synthetic_db(db)
    pkt, err = build_student_decision_packet_v1(
        db_path=db, symbol="TESTUSDT", decision_open_time_ms=5_000_000, candle_timeframe_minutes=5
    )
    assert err is None and isinstance(pkt, dict)
    return pkt


def test_student_llm_contract_repair_env_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATTERN_GAME_STUDENT_LLM_CONTRACT_REPAIR", raising=False)
    assert student_llm_contract_repair_enabled_v1() is True
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LLM_CONTRACT_REPAIR", "0")
    assert student_llm_contract_repair_enabled_v1() is False


def test_repair_off_no_second_ollama_on_parse_failure(
    monkeypatch: pytest.MonkeyPatch, decision_packet: dict[str, Any]
) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LLM_CONTRACT_REPAIR", "0")
    monkeypatch.setattr(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1.student_test_mode_isolation_active_v1",
        lambda: False,
    )
    calls = 0

    def fake_once(**_kwargs: object) -> tuple[str, str | None]:
        nonlocal calls
        calls += 1
        return "prose_only_no_json", None

    with mock.patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        fake_once,
    ):
        out, err = emit_student_output_via_ollama_v1(
            decision_packet,
            graded_unit_id="tr_rca_off",
            decision_at_ms=5_000_000,
            llm_model="stub-model",
            ollama_base_url="http://127.0.0.1:11434",
            prompt_version="test_pv",
            require_directional_thesis_v1=True,
        )
    assert out is None
    assert err
    assert calls == 1


def test_repair_on_second_ollama_can_recover_json(
    monkeypatch: pytest.MonkeyPatch, decision_packet: dict[str, Any]
) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LLM_CONTRACT_REPAIR", "1")
    monkeypatch.setattr(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1.student_test_mode_isolation_active_v1",
        lambda: False,
    )
    good = legal_example_student_output_with_thesis_v1()
    good["graded_unit_id"] = "tr_rca_on"
    good["decision_at_ms"] = 5_000_000
    calls = 0

    def fake_once(**_kwargs: object) -> tuple[str, str | None]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return "prose_only_no_json", None
        return json.dumps(good), None

    with mock.patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        fake_once,
    ):
        out, err = emit_student_output_via_ollama_v1(
            decision_packet,
            graded_unit_id="tr_rca_on",
            decision_at_ms=5_000_000,
            llm_model="stub-model",
            ollama_base_url="http://127.0.0.1:11434",
            prompt_version="test_pv",
            require_directional_thesis_v1=True,
        )
    assert err == []
    assert isinstance(out, dict)
    assert calls >= 2
