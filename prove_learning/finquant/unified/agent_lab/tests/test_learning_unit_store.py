"""Tests for learning/learning_unit_store.py — durability and replay correctness."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from learning.learning_unit_store import LearningUnitStore, StoreWriteError


def _new_store(tmpdir):
    return LearningUnitStore(os.path.join(tmpdir, "units"))


def test_upsert_creates_new_unit():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _new_store(tmpdir)
        unit = store.upsert_unit(
            pattern_id="p1",
            signature_components={"trend_v1": "trend_up"},
            human_label="trend_up",
            proposed_action="ENTER_LONG",
            hypothesis="trend_continuation",
            expected_outcome="price up",
            invalidation_condition="rsi<45",
        )
        assert unit["pattern_id_v1"] == "p1"
        assert unit["status_v1"] == "candidate"


def test_upsert_existing_returns_existing():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _new_store(tmpdir)
        u1 = store.upsert_unit(
            pattern_id="p1", signature_components={}, human_label="x",
            proposed_action="NO_TRADE", hypothesis="", expected_outcome="", invalidation_condition="")
        u2 = store.upsert_unit(
            pattern_id="p1", signature_components={}, human_label="x",
            proposed_action="ENTER_LONG", hypothesis="", expected_outcome="", invalidation_condition="")
        # Should be the same unit, not overwritten
        assert u2["proposed_action_v1"] == "NO_TRADE"


def test_record_outcome_updates_unit():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _new_store(tmpdir)
        store.upsert_unit(
            pattern_id="p1", signature_components={}, human_label="x",
            proposed_action="ENTER_LONG", hypothesis="", expected_outcome="", invalidation_condition="")
        updated = store.record_outcome(
            pattern_id="p1", verdict="confirmed", evidence_record_id="lr_1")
        assert updated["hit_count_v1"] == 1
        assert updated["confidence_score_v1"] > 0.0


def test_record_outcome_unknown_pattern_raises():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _new_store(tmpdir)
        with pytest.raises(KeyError):
            store.record_outcome(
                pattern_id="missing", verdict="confirmed", evidence_record_id="lr_x")


def test_events_log_is_appended():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _new_store(tmpdir)
        store.upsert_unit(
            pattern_id="p1", signature_components={}, human_label="x",
            proposed_action="ENTER_LONG", hypothesis="", expected_outcome="", invalidation_condition="")
        store.record_outcome(
            pattern_id="p1", verdict="confirmed", evidence_record_id="lr_1")
        store.transition_status(
            pattern_id="p1", new_status="provisional", reason="enough_obs")

        events_path = store.get_paths()["events_path"]
        with open(events_path, "r") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 3
        assert lines[0]["event_type_v1"] == "create_unit"
        assert lines[1]["event_type_v1"] == "observation"
        assert lines[2]["event_type_v1"] == "status_change"


def test_replay_rebuilds_state():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _new_store(tmpdir)
        store.upsert_unit(
            pattern_id="p1", signature_components={}, human_label="x",
            proposed_action="ENTER_LONG", hypothesis="", expected_outcome="", invalidation_condition="")
        store.record_outcome(
            pattern_id="p1", verdict="confirmed", evidence_record_id="lr_1")
        store.record_outcome(
            pattern_id="p1", verdict="confirmed", evidence_record_id="lr_2")

        # Reopen store — should replay events into same state
        store2 = LearningUnitStore(os.path.join(tmpdir, "units"))
        u = store2.get_unit("p1")
        assert u is not None
        assert u["hit_count_v1"] == 2


def test_write_receipt_recorded():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _new_store(tmpdir)
        store.upsert_unit(
            pattern_id="p1", signature_components={}, human_label="x",
            proposed_action="ENTER_LONG", hypothesis="", expected_outcome="", invalidation_condition="")
        receipt_path = store.get_paths()["receipt_path"]
        assert os.path.exists(receipt_path)
        receipt = json.load(open(receipt_path))
        assert receipt["last_event_v1"] == "create_unit"
        assert receipt["pattern_id_v1"] == "p1"


def test_units_by_status_filters_correctly():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _new_store(tmpdir)
        for pid in ("p1", "p2", "p3"):
            store.upsert_unit(
                pattern_id=pid, signature_components={}, human_label=pid,
                proposed_action="NO_TRADE", hypothesis="", expected_outcome="", invalidation_condition="")
        store.transition_status(pattern_id="p1", new_status="active", reason="test")
        store.transition_status(pattern_id="p2", new_status="retired", reason="test")

        actives = store.units_by_status({"active"})
        retireds = store.units_by_status({"retired"})
        candidates = store.units_by_status({"candidate"})
        assert len(actives) == 1 and actives[0]["pattern_id_v1"] == "p1"
        assert len(retireds) == 1 and retireds[0]["pattern_id_v1"] == "p2"
        assert len(candidates) == 1 and candidates[0]["pattern_id_v1"] == "p3"


def test_summary_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _new_store(tmpdir)
        for pid in ("p1", "p2"):
            store.upsert_unit(
                pattern_id=pid, signature_components={}, human_label=pid,
                proposed_action="NO_TRADE", hypothesis="", expected_outcome="", invalidation_condition="")
        stats = store.summary_stats()
        assert stats["total_units_v1"] == 2
        assert stats["by_status_v1"]["candidate"] == 2
