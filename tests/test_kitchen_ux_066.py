"""Kitchen UX DV-066: archive, sort, dedupe listing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.policy_intake.candidates_registry import (
    list_intake_candidates,
    set_intake_candidate_active,
)


def _write_pass(
    sub: Path,
    *,
    sid: str,
    cid: str,
    ts: str,
    et: str = "jupiter",
    is_active: bool | None = True,
) -> None:
    (sub / "report").mkdir(parents=True, exist_ok=True)
    (sub / "canonical").mkdir(parents=True, exist_ok=True)
    rep: dict = {
        "schema": "policy_intake_report_v1",
        "submission_id": sid,
        "pass": True,
        "candidate_policy_id": cid,
        "execution_target": et,
        "original_filename": "x.ts",
        "stages": {"stage_1_intake": {"timestamp_utc": ts}},
    }
    if is_active is not None:
        rep["is_active"] = is_active
    (sub / "report" / "intake_report.json").write_text(json.dumps(rep), encoding="utf-8")
    (sub / "canonical" / "policy_spec_v1.json").write_text("{}", encoding="utf-8")


def test_list_newest_first(tmp_path: Path) -> None:
    root = tmp_path
    subs = root / "renaissance_v4" / "state" / "policy_intake_submissions"
    _write_pass(subs / "old", sid="old", cid="a", ts="2026-01-01T12:00:00+00:00")
    _write_pass(subs / "new", sid="new", cid="b", ts="2026-06-01T12:00:00+00:00")
    rows = list_intake_candidates(root, execution_target="jupiter", collapse_duplicate_policy_ids=False)
    assert [r["submission_id"] for r in rows] == ["new", "old"]


def test_hide_archived_by_default(tmp_path: Path) -> None:
    root = tmp_path
    subs = root / "renaissance_v4" / "state" / "policy_intake_submissions"
    _write_pass(subs / "a", sid="a", cid="x", ts="2026-01-02T12:00:00+00:00", is_active=True)
    _write_pass(subs / "b", sid="b", cid="y", ts="2026-01-03T12:00:00+00:00", is_active=False)
    vis = list_intake_candidates(root, execution_target="jupiter", include_archived=False)
    assert len(vis) == 1 and vis[0]["submission_id"] == "a"
    all_rows = list_intake_candidates(root, execution_target="jupiter", include_archived=True)
    assert len(all_rows) == 2


def test_collapse_duplicate_policy_id(tmp_path: Path) -> None:
    root = tmp_path
    subs = root / "renaissance_v4" / "state" / "policy_intake_submissions"
    _write_pass(subs / "first", sid="first", cid="same", ts="2026-01-01T12:00:00+00:00")
    _write_pass(subs / "second", sid="second", cid="same", ts="2026-02-01T12:00:00+00:00")
    collapsed = list_intake_candidates(root, execution_target="jupiter", collapse_duplicate_policy_ids=True)
    assert len(collapsed) == 1
    assert collapsed[0]["submission_id"] == "second"
    assert collapsed[0]["same_policy_submission_count"] == 2
    full = list_intake_candidates(root, execution_target="jupiter", collapse_duplicate_policy_ids=False)
    assert len(full) == 2


def test_set_intake_candidate_active_roundtrip(tmp_path: Path) -> None:
    root = tmp_path
    subs = root / "renaissance_v4" / "state" / "policy_intake_submissions" / "s1"
    _write_pass(subs, sid="s1", cid="c1", ts="2026-01-01T12:00:00+00:00", is_active=True)
    r = set_intake_candidate_active(root, "s1", is_active=False)
    assert r.get("ok") is True
    vis = list_intake_candidates(root, execution_target="jupiter")
    assert vis == []
    r2 = set_intake_candidate_active(root, "s1", is_active=True)
    assert r2.get("ok") is True
    vis2 = list_intake_candidates(root, execution_target="jupiter")
    assert len(vis2) == 1
