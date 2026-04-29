"""GT058 / GT059 label gate — activation rules (replay)."""

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


def test_gt059_blocks_only_strong_negative_history(monkeypatch) -> None:
    monkeypatch.setenv("GT058_LABEL_GATE_ACTIVATION_V1", "1")
    monkeypatch.setenv("GT059_LABEL_MIN_SAMPLES", "5")
    monkeypatch.setenv("GT059_LABEL_BLOCK_THRESHOLD", "-0.2")
    priors = [-1, -1, -1, -1, -1]
    assert gt058_should_block_entry_from_prior_labels_v1(priors, ev_best_value_v1=0.0)


def test_gt059_ev_override_allows_when_positive(monkeypatch) -> None:
    monkeypatch.setenv("GT058_LABEL_GATE_ACTIVATION_V1", "1")
    monkeypatch.setenv("GT059_LABEL_MIN_SAMPLES", "5")
    priors = [-1, -1, -1, -1, -1]
    assert not gt058_should_block_entry_from_prior_labels_v1(priors, ev_best_value_v1=0.05)


def test_gt059_insufficient_samples_never_blocks(monkeypatch) -> None:
    monkeypatch.setenv("GT058_LABEL_GATE_ACTIVATION_V1", "1")
    monkeypatch.setenv("GT059_LABEL_MIN_SAMPLES", "5")
    assert not gt058_should_block_entry_from_prior_labels_v1([-1, -1, -1, -1], ev_best_value_v1=0.0)


def test_gt059_borderline_negative_no_block(monkeypatch) -> None:
    """Avg about -0.133 — above -0.2 threshold."""
    monkeypatch.setenv("GT058_LABEL_GATE_ACTIVATION_V1", "1")
    monkeypatch.setenv("GT059_LABEL_MIN_SAMPLES", "5")
    priors = [-1, -1, -1, 1, 1]
    assert not gt058_should_block_entry_from_prior_labels_v1(priors, ev_best_value_v1=0.0)


def test_gt058_disabled_never_blocks(monkeypatch) -> None:
    monkeypatch.delenv("GT058_LABEL_GATE_ACTIVATION_V1", raising=False)
    assert not gt058_should_block_entry_from_prior_labels_v1([-1] * 10, ev_best_value_v1=-1.0)
