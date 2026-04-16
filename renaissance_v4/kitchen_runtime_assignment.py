"""
DV-068 — Multi-target Kitchen → runtime assignment (governed approved-slot model).

Flow: **Kitchen candidate** → **approved runtime slot** → **execution target** → **active runtime policy id** for that target.

No arbitrary TS execution: only registered slot ids per target. Jupiter uses SeanV3 POST; BlackBox slot is reserved with a clear adapter hook.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.execution_targets import normalize_execution_target
from renaissance_v4.policy_intake.storage import read_json, submission_dir

MECHANICAL_CANDIDATE_POLICY_ID = "kitchen_mechanical_always_long_v1"

# Approved mechanical proof slots per execution target (must match shipped runtime registry when wired).
APPROVED_MECHANICAL_BY_TARGET: dict[str, dict[str, str]] = {
    "jupiter": {
        "approved_runtime_slot_id": "jup_kitchen_mechanical_v1",
        "active_runtime_policy_id": "jup_kitchen_mechanical_v1",
        "runtime_adapter": "seanv3_jupiter_active_policy",
    },
    "blackbox": {
        "approved_runtime_slot_id": "bb_kitchen_mechanical_v1",
        "active_runtime_policy_id": "bb_kitchen_mechanical_v1",
        "runtime_adapter": "reserved_blackbox_control_plane",
    },
}

STORE_SCHEMA = "kitchen_runtime_assignment_store_v1"
STATE_FILENAME = "kitchen_runtime_assignment.json"
LEGACY_JUPITER_FILENAME = "kitchen_jupiter_assignment.json"


def runtime_assignment_store_path(repo: Path) -> Path:
    return repo.resolve() / "renaissance_v4" / "state" / STATE_FILENAME


def legacy_jupiter_assignment_path(repo: Path) -> Path:
    return repo.resolve() / "renaissance_v4" / "state" / LEGACY_JUPITER_FILENAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_store() -> dict[str, Any]:
    return {
        "schema": STORE_SCHEMA,
        "assignments_by_target": {},
    }


def read_store(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    p = runtime_assignment_store_path(repo)
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("schema") == STORE_SCHEMA:
                raw.setdefault("assignments_by_target", {})
                return raw
        except (OSError, json.JSONDecodeError):
            pass
    store = _empty_store()
    _migrate_legacy_jupiter_json(repo, store)
    return store


def _migrate_legacy_jupiter_json(repo: Path, store: dict[str, Any]) -> None:
    """Import DV-067 single-file Jupiter assignment into ``assignments_by_target.jupiter``."""
    leg = legacy_jupiter_assignment_path(repo)
    if not leg.is_file():
        return
    try:
        old = json.loads(leg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(old, dict):
        return
    if store["assignments_by_target"].get("jupiter"):
        return
    slot = str(old.get("jupiter_policy_slot") or old.get("approved_runtime_slot_id") or "jup_kitchen_mechanical_v1")
    store["assignments_by_target"]["jupiter"] = {
        "schema": "kitchen_runtime_assignment_record_v1",
        "execution_target": "jupiter",
        "submission_id": str(old.get("submission_id") or ""),
        "candidate_policy_id": str(old.get("candidate_policy_id") or MECHANICAL_CANDIDATE_POLICY_ID),
        "approved_runtime_slot_id": slot,
        "active_runtime_policy_id": str(old.get("active_runtime_policy_id") or slot),
        "assigned_at_utc": str(old.get("assigned_at_utc") or _utc_now()),
        "operator_action": "migrated_from_kitchen_jupiter_assignment_v1",
        "runtime_adapter": "seanv3_jupiter_active_policy",
    }


def write_store(repo: Path, store: dict[str, Any]) -> None:
    p = runtime_assignment_store_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")


def get_assignment(repo: Path, execution_target: str | None) -> dict[str, Any] | None:
    et = normalize_execution_target(execution_target)
    st = read_store(repo)
    row = st.get("assignments_by_target", {}).get(et)
    return row if isinstance(row, dict) else None


def assign_mechanical_candidate(
    repo: Path,
    submission_id: str,
    execution_target: str | None = None,
    *,
    http_jupiter_base: str | None = None,
    http_jupiter_token: str | None = None,
) -> dict[str, Any]:
    """
    Assign passing mechanical intake to the approved slot for the given execution target.

    ``execution_target`` defaults from the intake report's ``execution_target`` (must match).
    """
    repo = repo.resolve()
    rep_path = submission_dir(repo, submission_id) / "report" / "intake_report.json"
    rep = read_json(rep_path)
    if not isinstance(rep, dict) or not rep.get("pass"):
        return {"ok": False, "error": "submission_not_passing", "submission_id": submission_id}

    cid = str(rep.get("candidate_policy_id") or "").strip()
    if cid != MECHANICAL_CANDIDATE_POLICY_ID:
        return {
            "ok": False,
            "error": "candidate_not_mechanical_proof_policy",
            "detail": f"Only candidate_policy_id {MECHANICAL_CANDIDATE_POLICY_ID!r} maps to approved mechanical slots.",
            "candidate_policy_id": cid,
        }

    rep_et = normalize_execution_target(str(rep.get("execution_target") or "jupiter"))
    et = normalize_execution_target(execution_target) if execution_target is not None else rep_et
    if et != rep_et:
        return {
            "ok": False,
            "error": "execution_target_mismatch",
            "detail": "Intake report execution_target must match the assignment request.",
            "execution_target_requested": et,
            "execution_target_intake": rep_et,
        }

    if et not in APPROVED_MECHANICAL_BY_TARGET:
        return {"ok": False, "error": "unsupported_execution_target", "execution_target": et}

    mapping = APPROVED_MECHANICAL_BY_TARGET[et]
    slot = mapping["approved_runtime_slot_id"]
    active_pid = mapping["active_runtime_policy_id"]
    adapter = mapping["runtime_adapter"]

    record: dict[str, Any] = {
        "schema": "kitchen_runtime_assignment_record_v1",
        "execution_target": et,
        "submission_id": submission_id,
        "candidate_policy_id": cid,
        "approved_runtime_slot_id": slot,
        "active_runtime_policy_id": active_pid,
        "assigned_at_utc": _utc_now(),
        "operator_action": "kitchen_dashboard_assign",
        "runtime_adapter": adapter,
    }

    http_ok: bool | None = None
    http_detail: str | None = None

    if et == "jupiter":
        base = (http_jupiter_base or os.environ.get("KITCHEN_JUPITER_CONTROL_BASE") or "").strip()
        tok = (http_jupiter_token or os.environ.get("KITCHEN_JUPITER_OPERATOR_TOKEN") or "").strip()
        if base and tok:
            url = base.rstrip("/") + "/api/v1/jupiter/active-policy"
            payload = json.dumps({"policy": active_pid}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    http_ok = resp.status == 200
                    http_detail = raw[:2000]
            except urllib.error.HTTPError as e:
                http_ok = False
                http_detail = (e.read() or b"").decode("utf-8", errors="replace")[:2000]
            except OSError as e:
                http_ok = False
                http_detail = str(e)[:2000]
        else:
            http_ok = None
            http_detail = (
                "Jupiter: set KITCHEN_JUPITER_CONTROL_BASE and KITCHEN_JUPITER_OPERATOR_TOKEN on the API host to POST to SeanV3."
            )
    elif et == "blackbox":
        http_ok = None
        http_detail = (
            "BlackBox: runtime control-plane adapter not wired (DV-068); assignment persisted for audit. "
            "Implement KITCHEN_BLACKBOX_* when the BlackBox active-policy API exists."
        )

    record["runtime_http_post_ok"] = http_ok
    record["runtime_http_detail"] = http_detail

    store = read_store(repo)
    store.setdefault("assignments_by_target", {})
    store["assignments_by_target"][et] = record
    write_store(repo, store)

    out: dict[str, Any] = {"ok": True, **record}
    return out


# --- Backward-compatible names (DV-067 callers) ---

def read_assignment(repo: Path) -> dict[str, Any] | None:
    """Return Jupiter row only (legacy read shape for old GET handler)."""
    return get_assignment(repo, "jupiter")


def assign_mechanical_candidate_to_jupiter(
    repo: Path,
    submission_id: str,
    *,
    http_base: str | None = None,
    operator_token: str | None = None,
) -> dict[str, Any]:
    return assign_mechanical_candidate(
        repo,
        submission_id,
        "jupiter",
        http_jupiter_base=http_base,
        http_jupiter_token=operator_token,
    )


def assignment_json_path(repo: Path) -> Path:
    """Deprecated: use :func:`runtime_assignment_store_path`."""
    return runtime_assignment_store_path(repo)
