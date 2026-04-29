"""GT058 label gate — unit tests (activation rules only)."""

from unittest.mock import patch

from renaissance_v4.game_theory.gt058_label_gate_v1 import (
    gt058_should_block_entry_from_prior_labels_v1,
    gt058_signature_key_v1,
)


def test_gt058_signature_key_stable() -> None:
    a = gt058_signature_key_v1("trend_up", "long", ["trend_continuation", "mean_reversion_fade"])
    b = gt058_signature_key_v1("trend_up", "long", ["mean_reversion_fade", "trend_continuation"])
    assert a == b
    assert len(a) == 28


def test_gt058_blocks_when_prior_mean_negative(monkeypatch) -> None:
    monkeypatch.setenv("GT058_LABEL_GATE_ACTIVATION_V1", "1")
    monkeypatch.setenv("GT058_MIN_PRIOR_LABELS", "3")
    assert gt058_should_block_entry_from_prior_labels_v1([-1, -1, 1])


def test_gt058_cold_start_no_block(monkeypatch) -> None:
    monkeypatch.setenv("GT058_LABEL_GATE_ACTIVATION_V1", "1")
    monkeypatch.setenv("GT058_MIN_PRIOR_LABELS", "5")
    assert not gt058_should_block_entry_from_prior_labels_v1([-1, -1])


def test_gt058_disabled_never_blocks(monkeypatch) -> None:
    monkeypatch.delenv("GT058_LABEL_GATE_ACTIVATION_V1", raising=False)
    assert not gt058_should_block_entry_from_prior_labels_v1([-1, -1, -1])
