"""Candidate registry (DV-ARCH-KITCHEN-CANDIDATE-REGISTRY-061)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from renaissance_v4.policy_intake.candidates_registry import list_intake_candidates

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_pass_report(sub: Path, *, pass_ok: bool, cid: str | None, et: str = "jupiter") -> None:
    (sub / "report").mkdir(parents=True, exist_ok=True)
    (sub / "canonical").mkdir(parents=True, exist_ok=True)
    rep = {
        "schema": "policy_intake_report_v1",
        "submission_id": sub.name,
        "pass": pass_ok,
        "candidate_policy_id": cid,
        "execution_target": et,
        "original_filename": "x.ts",
        "stages": {"stage_1_intake": {"timestamp_utc": "2026-01-01T12:00:00+00:00"}},
    }
    (sub / "report" / "intake_report.json").write_text(json.dumps(rep), encoding="utf-8")
    (sub / "canonical" / "policy_spec_v1.json").write_text("{}", encoding="utf-8")


def test_list_intake_candidates_pass_with_canonical(tmp_path: Path) -> None:
    root = tmp_path
    subs = root / "renaissance_v4" / "state" / "policy_intake_submissions"
    s1 = subs / "aaa111"
    _write_pass_report(s1, pass_ok=True, cid="cand_a")
    rows = list_intake_candidates(root, execution_target="jupiter")
    assert len(rows) == 1
    assert rows[0]["candidate_policy_id"] == "cand_a"
    assert rows[0]["intake_status"] == "pass"


def test_list_intake_candidates_excludes_fail(tmp_path: Path) -> None:
    root = tmp_path
    subs = root / "renaissance_v4" / "state" / "policy_intake_submissions"
    _write_pass_report(subs / "good", pass_ok=True, cid="ok")
    _write_pass_report(subs / "bad", pass_ok=False, cid=None)
    rows = list_intake_candidates(root, execution_target="jupiter")
    assert len(rows) == 1
    assert rows[0]["submission_id"] == "good"


def test_list_intake_candidates_excludes_missing_canonical(tmp_path: Path) -> None:
    root = tmp_path
    subs = root / "renaissance_v4" / "state" / "policy_intake_submissions" / "nocan"
    (subs / "report").mkdir(parents=True)
    rep = {
        "pass": True,
        "candidate_policy_id": "x",
        "submission_id": "nocan",
        "stages": {},
    }
    (subs / "report" / "intake_report.json").write_text(json.dumps(rep), encoding="utf-8")
    rows = list_intake_candidates(root, execution_target="jupiter")
    assert rows == []


def _copy_registry(root: Path) -> None:
    dest = root / "renaissance_v4" / "config"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO_ROOT / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json",
        dest / "kitchen_policy_registry_v1.json",
    )


def test_list_intake_candidates_runtime_policy_id_dv077(tmp_path: Path) -> None:
    """DV-077 — each row exposes runtime_policy_id for green indicator vs runtime GET."""
    _copy_registry(tmp_path)
    subs = tmp_path / "renaissance_v4" / "state" / "policy_intake_submissions"
    _write_pass_report(subs / "m1", pass_ok=True, cid="kitchen_mechanical_always_long_v1")
    _write_pass_report(subs / "j1", pass_ok=True, cid="jup_mc_test_v1")
    rows = list_intake_candidates(tmp_path, execution_target="jupiter")
    assert len(rows) == 2
    by_c = {str(r["candidate_policy_id"]): r for r in rows}
    assert by_c["kitchen_mechanical_always_long_v1"]["runtime_policy_id"] == "jup_kitchen_mechanical_v1"
    assert by_c["jup_mc_test_v1"]["runtime_policy_id"] == "jup_mc_test"


def test_list_intake_candidates_filters_execution_target(tmp_path: Path) -> None:
    root = tmp_path
    subs = root / "renaissance_v4" / "state" / "policy_intake_submissions"
    _write_pass_report(subs / "j1", pass_ok=True, cid="a", et="jupiter")
    _write_pass_report(subs / "b1", pass_ok=True, cid="b", et="blackbox")
    j = list_intake_candidates(root, execution_target="jupiter")
    bb = list_intake_candidates(root, execution_target="blackbox")
    assert len(j) == 1 and j[0]["candidate_policy_id"] == "a"
    assert len(bb) == 1 and bb[0]["candidate_policy_id"] == "b"
