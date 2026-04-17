"""
Path A deployment manifest — binds Kitchen submissions to deployable runtime policy ids.

Source of truth file: ``renaissance_v4/config/kitchen_policy_deployment_manifest_v1.json``.

Each entry ties ``(execution_target, deployed_runtime_policy_id)`` to exactly one
``(submission_id, content_sha256)``. Kitchen assignment must match an entry; runtime
GET observability reports the same identity for manifest-bound policies.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "kitchen_policy_deployment_manifest_v1"
MANIFEST_REL = Path("renaissance_v4/config/kitchen_policy_deployment_manifest_v1.json")


def manifest_path(repo: Path) -> Path:
    return repo.resolve() / MANIFEST_REL


def load_manifest(repo: Path) -> dict[str, Any]:
    p = manifest_path(repo)
    if not p.is_file():
        return {"schema": MANIFEST_SCHEMA, "entries": []}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {"schema": MANIFEST_SCHEMA, "entries": []}
    if not isinstance(raw, dict) or raw.get("schema") != MANIFEST_SCHEMA:
        return {"schema": MANIFEST_SCHEMA, "entries": []}
    ent = raw.get("entries")
    if not isinstance(ent, list):
        return {"schema": MANIFEST_SCHEMA, "entries": []}
    return {"schema": MANIFEST_SCHEMA, "entries": ent}


def _normalize_hex_sha256(s: str) -> str:
    t = str(s or "").strip().lower()
    if len(t) == 64 and all(c in "0123456789abcdef" for c in t):
        return t
    return ""


def validate_manifest_entries(entries: list[Any]) -> tuple[bool, str | None]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            return False, f"entries[{i}] must be an object"
        et = str(e.get("execution_target") or "").strip().lower()
        pid = str(e.get("deployed_runtime_policy_id") or "").strip()
        sid = str(e.get("submission_id") or "").strip()
        h = _normalize_hex_sha256(str(e.get("content_sha256") or ""))
        if et not in ("jupiter", "blackbox"):
            return False, f"entries[{i}].execution_target must be jupiter or blackbox"
        if not pid:
            return False, f"entries[{i}].deployed_runtime_policy_id is required"
        if not sid:
            return False, f"entries[{i}].submission_id is required"
        if not h:
            return False, f"entries[{i}].content_sha256 must be a 64-char hex sha256"
        key = (et, pid)
        if key in seen:
            return False, f"duplicate deployed_runtime_policy_id for {et}: {pid!r}"
        seen[key] = e
    return True, None


def deployment_ids_for_target(repo: Path, execution_target: str) -> list[str]:
    """Listed ``deployed_runtime_policy_id`` values for Jupiter or BlackBox (manifest order, unique)."""
    et = str(execution_target or "").strip().lower()
    if et not in ("jupiter", "blackbox"):
        return []
    m = load_manifest(repo)
    out: list[str] = []
    for e in m.get("entries") or []:
        if not isinstance(e, dict):
            continue
        if str(e.get("execution_target") or "").strip().lower() != et:
            continue
        pid = str(e.get("deployed_runtime_policy_id") or "").strip()
        if pid and pid not in out:
            out.append(pid)
    return out


def find_manifest_entry(
    repo: Path,
    execution_target: str,
    deployed_runtime_policy_id: str,
) -> dict[str, Any] | None:
    et = str(execution_target or "").strip().lower()
    pid = str(deployed_runtime_policy_id or "").strip()
    m = load_manifest(repo)
    for e in m.get("entries") or []:
        if not isinstance(e, dict):
            continue
        if str(e.get("execution_target") or "").strip().lower() != et:
            continue
        if str(e.get("deployed_runtime_policy_id") or "").strip() == pid:
            return e
    return None


def validate_kitchen_assignment_against_manifest(
    repo: Path,
    execution_target: str,
    submission_id: str,
    content_sha256: str,
    deployed_runtime_policy_id: str,
) -> tuple[bool, str | None, str | None]:
    """
    Returns (ok, error_code, detail).

    Success only if an entry exists with matching target, deployed id, submission id, and hash.
    """
    et = str(execution_target or "").strip().lower()
    sid = str(submission_id or "").strip()
    want_h = _normalize_hex_sha256(content_sha256)
    pid = str(deployed_runtime_policy_id or "").strip()
    if not want_h:
        return False, "intake_missing_content_sha256", "Intake report must include stages.stage_1_intake.content_sha256"
    if not sid:
        return False, "missing_submission_id", ""
    m = load_manifest(repo)
    for e in m.get("entries") or []:
        if not isinstance(e, dict):
            continue
        if str(e.get("execution_target") or "").strip().lower() != et:
            continue
        if str(e.get("deployed_runtime_policy_id") or "").strip() != pid:
            continue
        if str(e.get("submission_id") or "").strip() != sid:
            continue
        eh = _normalize_hex_sha256(str(e.get("content_sha256") or ""))
        if eh == want_h:
            return True, None, None
    return (
        False,
        "artifact_not_in_deployment_manifest",
        f"No manifest entry for {et!r} ties submission {sid!r} + hash to deployed id {pid!r}",
    )


def artifact_identity_for_submission(
    repo: Path, execution_target: str, submission_id: str
) -> dict[str, Any] | None:
    """
    If the deployment manifest ties this passing submission to a built artifact, return
    ``submission_id``, ``content_sha256``, and ``deployed_runtime_policy_id``.
    Otherwise None (not yet promoted / not in manifest).
    """
    from renaissance_v4.execution_targets import normalize_execution_target

    et = normalize_execution_target(execution_target)
    sid = str(submission_id or "").strip()
    if not sid:
        return None
    content_sha = canonical_runtime_artifact_sha256(repo, sid)
    if not content_sha:
        return None
    m = load_manifest(repo)
    for e in m.get("entries") or []:
        if not isinstance(e, dict):
            continue
        if str(e.get("execution_target") or "").strip().lower() != et:
            continue
        if str(e.get("submission_id") or "").strip() != sid:
            continue
        eh = _normalize_hex_sha256(str(e.get("content_sha256") or ""))
        if eh != content_sha:
            continue
        pid = str(e.get("deployed_runtime_policy_id") or "").strip()
        if not pid:
            continue
        return {
            "submission_id": sid,
            "content_sha256": content_sha,
            "deployed_runtime_policy_id": pid,
        }
    return None


def submission_content_sha256_from_intake(repo: Path, submission_id: str) -> str:
    """Return normalized hex sha256 from intake report, or empty string if missing."""
    from renaissance_v4.policy_intake.storage import read_json, submission_dir

    rep_path = submission_dir(repo, submission_id) / "report" / "intake_report.json"
    rep = read_json(rep_path)
    if not isinstance(rep, dict):
        return ""
    st = rep.get("stages")
    if isinstance(st, dict):
        s1 = st.get("stage_1_intake")
        if isinstance(s1, dict):
            return _normalize_hex_sha256(str(s1.get("content_sha256") or ""))
    return ""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_runtime_artifact_sha256(repo: Path, submission_id: str) -> str:
    """
    Path A identity hash aligned with SeanV3 ``artifact_policy_loader.mjs``:

    When ``artifacts/evaluator.mjs`` exists, return its sha256 (the engine compares the manifest
    entry to this file). Otherwise fall back to ``stage_1_intake.content_sha256`` (raw upload),
    e.g. promotion not run yet or hand-authored evaluator-only flows.
    """
    from renaissance_v4.policy_intake.storage import submission_dir

    ep = submission_dir(repo, submission_id) / "artifacts" / "evaluator.mjs"
    if ep.is_file():
        return _normalize_hex_sha256(_sha256_file(ep))
    return submission_content_sha256_from_intake(repo, submission_id)


def write_manifest(repo: Path, manifest: dict[str, Any]) -> None:
    p = manifest_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def append_manifest_entry(repo: Path, entry: dict[str, Any]) -> None:
    """Append one entry; validates uniqueness of (execution_target, deployed_runtime_policy_id)."""
    m = load_manifest(repo)
    entries = [x for x in m.get("entries") or [] if isinstance(x, dict)]
    entries.append(entry)
    ok, err = validate_manifest_entries(entries)
    if not ok:
        raise ValueError(err or "invalid manifest entry")
    write_manifest(repo, {"schema": MANIFEST_SCHEMA, "entries": entries})


def upsert_manifest_entry(repo: Path, entry: dict[str, Any]) -> None:
    """
    Replace any Jupiter/BlackBox row that matches the same ``execution_target`` and either
    ``deployed_runtime_policy_id`` or ``submission_id``, then append the new entry.
    Use when re-promoting the same submission or redeploying the same runtime id.
    """
    et = str(entry.get("execution_target") or "").strip().lower()
    pid = str(entry.get("deployed_runtime_policy_id") or "").strip()
    sid = str(entry.get("submission_id") or "").strip()
    m = load_manifest(repo)
    entries = [x for x in m.get("entries") or [] if isinstance(x, dict)]
    filtered: list[dict[str, Any]] = []
    for e in entries:
        eet = str(e.get("execution_target") or "").strip().lower()
        if eet != et:
            filtered.append(e)
            continue
        esid = str(e.get("submission_id") or "").strip()
        epid = str(e.get("deployed_runtime_policy_id") or "").strip()
        if esid == sid or epid == pid:
            continue
        filtered.append(e)
    filtered.append(entry)
    ok, err = validate_manifest_entries(filtered)
    if not ok:
        raise ValueError(err or "invalid manifest entry")
    write_manifest(repo, {"schema": MANIFEST_SCHEMA, "entries": filtered})
