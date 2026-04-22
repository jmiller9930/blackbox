"""Groundhog memory bundle — executable continuity across replays."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory import groundhog_memory as gm


@pytest.fixture
def gh_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "groundhog_memory_bundle.json"
    monkeypatch.setattr(gm, "groundhog_bundle_path", lambda: p)
    return p


def test_resolve_explicit_wins(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gh_path.write_text(
        json.dumps(
            {
                "schema": "pattern_game_memory_bundle_v1",
                "apply": {"atr_stop_mult": 1.0, "atr_target_mult": 2.0},
            }
        ),
        encoding="utf-8",
    )
    out = gm.resolve_memory_bundle_for_scenario(
        {"skip_groundhog_bundle": False},
        explicit_path="/tmp/explicit.json",
    )
    assert out == "/tmp/explicit.json"


def test_skip_groundhog(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gh_path.write_text(
        json.dumps(
            {
                "schema": "pattern_game_memory_bundle_v1",
                "apply": {"atr_stop_mult": 1.0, "atr_target_mult": 2.0},
            }
        ),
        encoding="utf-8",
    )
    out = gm.resolve_memory_bundle_for_scenario(
        {"skip_groundhog_bundle": True},
        explicit_path=None,
    )
    assert out is None


def test_env_merge_when_file_exists(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gh_path.write_text(
        json.dumps(
            {
                "schema": "pattern_game_memory_bundle_v1",
                "apply": {"atr_stop_mult": 1.5, "atr_target_mult": 3.0},
            }
        ),
        encoding="utf-8",
    )
    out = gm.resolve_memory_bundle_for_scenario({}, explicit_path=None)
    assert out == str(gh_path)


def test_env_off_no_merge(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")
    gh_path.write_text(
        json.dumps(
            {
                "schema": "pattern_game_memory_bundle_v1",
                "apply": {"atr_stop_mult": 1.0, "atr_target_mult": 2.0},
            }
        ),
        encoding="utf-8",
    )
    out = gm.resolve_memory_bundle_for_scenario({}, explicit_path=None)
    assert out is None


def test_groundhog_wiring_signal_merge_off_is_yellow(
    gh_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")
    sig, detail = gm.groundhog_wiring_signal()
    assert sig == "yellow"
    assert "opt-out" in detail.lower() or "bundle=0" in detail.lower()


def test_groundhog_wiring_signal_merge_on_missing_is_yellow(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert not gh_path.is_file()
    sig, detail = gm.groundhog_wiring_signal()
    assert sig == "yellow"
    assert "bundle" in detail.lower()


def test_groundhog_wiring_signal_green_when_promoted(
    gh_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gh_path.write_text(
        json.dumps(
            {
                "schema": gm.MEMORY_BUNDLE_SCHEMA,
                "apply": {"atr_stop_mult": 1.0, "atr_target_mult": 2.0},
            }
        ),
        encoding="utf-8",
    )
    sig, detail = gm.groundhog_wiring_signal()
    assert sig == "green"
    assert "promoted" in detail.lower()


def test_groundhog_wiring_signal_yellow_when_apply_empty(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gh_path.write_text(
        json.dumps(
            {"schema": gm.MEMORY_BUNDLE_SCHEMA, "apply": {}},
        ),
        encoding="utf-8",
    )
    sig, _detail = gm.groundhog_wiring_signal()
    assert sig == "yellow"


def test_groundhog_wiring_signal_red_on_bad_json(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gh_path.write_text("{not json", encoding="utf-8")
    sig, detail = gm.groundhog_wiring_signal()
    assert sig == "red"
    assert "json" in detail.lower()


def test_write_roundtrip(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = gm.write_groundhog_bundle(
        atr_stop_mult=2.0,
        atr_target_mult=4.0,
        from_run_id="run-abc",
        note="promoted after batch",
    )
    assert p == gh_path
    raw = json.loads(gh_path.read_text(encoding="utf-8"))
    assert raw["apply"]["atr_stop_mult"] == 2.0
    assert raw["from_run_id"] == "run-abc"


def test_promote_from_parallel_scenarios_writes_bundle(
    gh_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert not gh_path.is_file()
    out = gm.promote_groundhog_bundle_from_parallel_scenarios_v1(
        [
            {"scenario_id": "a", "atr_stop_mult": 1.25, "atr_target_mult": 2.5},
            {"scenario_id": "b", "atr_stop_mult": 9.0, "atr_target_mult": 9.0},
        ],
        from_run_id="job_xyz",
    )
    assert out["ok"] is True
    assert out["action"] == "written"
    assert out["atr_stop_mult"] == 1.25
    assert out["atr_target_mult"] == 2.5
    sig, _detail = gm.groundhog_wiring_signal()
    assert sig == "green"
    raw = json.loads(gh_path.read_text(encoding="utf-8"))
    assert raw.get("from_run_id") == "job_xyz"


def test_promote_skips_first_when_skip_groundhog_bundle(
    gh_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = gm.promote_groundhog_bundle_from_parallel_scenarios_v1(
        [
            {"skip_groundhog_bundle": True, "atr_stop_mult": 9.0, "atr_target_mult": 9.0},
            {"atr_stop_mult": 3.0, "atr_target_mult": 6.0},
        ],
        from_run_id="j2",
    )
    assert out["action"] == "written"
    assert out["atr_stop_mult"] == 3.0


def test_promote_skips_when_env_opt_out(gh_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")
    out = gm.promote_groundhog_bundle_from_parallel_scenarios_v1(
        [{"atr_stop_mult": 1.0, "atr_target_mult": 2.0}],
        from_run_id="j3",
    )
    assert out["action"] == "skipped_env_opt_out"
    assert not gh_path.is_file()


def test_clear_groundhog_bundle_file_deleted_then_absent(gh_path: Path) -> None:
    gh_path.write_text("{}", encoding="utf-8")
    r1 = gm.clear_groundhog_bundle_file()
    assert r1["ok"] is True
    assert r1["action"] == "deleted"
    assert not gh_path.is_file()
    r2 = gm.clear_groundhog_bundle_file()
    assert r2["ok"] is True
    assert r2["action"] == "absent_skipped"
