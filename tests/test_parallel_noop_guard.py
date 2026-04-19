"""Post-run guard: no-op parallel batches must not masquerade as successful replays."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.web_app import _guard_parallel_batch_not_noop


def test_guard_raises_when_result_rows_empty() -> None:
    with pytest.raises(RuntimeError, match="parallel_batch_empty_results"):
        _guard_parallel_batch_not_noop([{"scenario_id": "a", "manifest_path": "x.json"}], [])


def test_guard_raises_when_ok_rows_have_zero_replay_depth() -> None:
    results = [
        {
            "ok": True,
            "scenario_id": "s1",
            "learning_run_audit_v1": {"decision_windows_total": 0, "bars_processed": 0},
        }
    ]
    with pytest.raises(RuntimeError, match="replay_noop_batch"):
        _guard_parallel_batch_not_noop([{"scenario_id": "s1"}], results)


def test_guard_passes_when_decision_windows_positive() -> None:
    results = [
        {
            "ok": True,
            "scenario_id": "s1",
            "learning_run_audit_v1": {"decision_windows_total": 3, "bars_processed": 0},
        }
    ]
    _guard_parallel_batch_not_noop([{"scenario_id": "s1"}], results)


def test_guard_allows_all_failed_rows() -> None:
    results = [{"ok": False, "scenario_id": "s1", "error": "ManifestError: x"}]
    _guard_parallel_batch_not_noop([{"scenario_id": "s1"}], results)
