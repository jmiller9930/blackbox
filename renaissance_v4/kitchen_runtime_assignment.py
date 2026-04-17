"""
DV-068 / DV-074 — Multi-target Kitchen → runtime assignment.

**Nexus rule:** Kitchen assignment intent is persisted only from ``assign_mechanical_candidate`` (any
registry-mapped passing intake) after POST to the trade service and GET read-back verification (DV-074).
That path is authoritative: failure leaves the store unchanged.

**GET** ``build_kitchen_runtime_read_payload`` does **not** mutate the assignment store. Runtime GET is
for drift/ledger/lifecycle and for displaying ``live_runtime_policy`` vs the persisted assignment row.
It must not silently collapse Kitchen to whatever the target is already running (that was a defect).

Optional ``reconcile_assignment_store_to_runtime_truth`` is for tests, explicit tooling, and
``apply_runtime_policy_checkin`` (trade-surface handshake)—not for passive GET polling.
"""

from __future__ import annotations

import copy
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.execution_targets import normalize_execution_target
from renaissance_v4.kitchen_policy_ledger import (
    append_ledger_entry,
    get_external_dedupe_fingerprint,
    ledger_entries_for_target,
    set_external_dedupe_fingerprint,
)
from renaissance_v4.kitchen_policy_registry import (
    approved_mechanical_by_target,
    infer_runtime_policy_id_for_candidate,
    load_registry,
    runtime_policy_approved,
)
from renaissance_v4.policy_intake.kitchen_policy_manifest import (
    submission_content_sha256_from_intake,
    validate_kitchen_assignment_against_manifest,
)
from renaissance_v4.policy_intake.storage import read_json, submission_dir

MECHANICAL_CANDIDATE_POLICY_ID = "kitchen_mechanical_always_long_v1"

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


def reconcile_assignment_store_to_runtime_truth(
    repo: Path,
    execution_target: str,
    runtime_payload: dict[str, Any],
    kitchen_row_before: dict[str, Any] | None,
    *,
    ledger_source: str = "reconciliation",
    ledger_detail: str | None = None,
    reconcile_source_tag: str = "runtime_get",
) -> dict[str, Any] | None:
    """
    Optional store rewrite: collapse persisted Kitchen row toward runtime GET (DV-070B rebind/unlink).

    **Not** called from ``GET …/kitchen-runtime-assignment``. Callers: tests, tooling,
    ``apply_runtime_policy_checkin``.
    """
    from renaissance_v4.policy_intake.candidates_registry import find_best_submission_for_runtime_policy

    repo = repo.resolve()
    et = normalize_execution_target(execution_target)
    if et not in ("jupiter", "blackbox"):
        return None
    if not kitchen_row_before or not runtime_payload.get("ok"):
        return None
    r_active = str(runtime_payload.get("active_policy") or "").strip()
    if not r_active:
        return None
    if not runtime_policy_approved(repo, et, r_active):
        return None
    k_active = str(kitchen_row_before.get("active_runtime_policy_id") or "").strip()
    if k_active == r_active:
        return None
    store = read_store(repo)
    row = store.get("assignments_by_target", {}).get(et)
    if not isinstance(row, dict):
        return None

    rebind = find_best_submission_for_runtime_policy(repo, et, r_active)
    if rebind:
        row["submission_id"] = rebind["submission_id"]
        row["candidate_policy_id"] = rebind["candidate_policy_id"]
        row["approved_runtime_slot_id"] = _approved_slot_for_rebind(
            repo, et, rebind["candidate_policy_id"], r_active
        )
        row["active_runtime_policy_id"] = r_active
        ada = _runtime_adapter_for_rebind(repo, et, rebind["candidate_policy_id"])
        if ada:
            row["runtime_adapter"] = ada
        row["operator_action"] = (
            "runtime_read_back_reconcile_dv070_rebind" if et == "jupiter" else "runtime_read_back_reconcile_dv071_rebind"
        )
        row["reconcile_linkage"] = "candidate_rebound"
    else:
        row["submission_id"] = ""
        row["candidate_policy_id"] = ""
        row["approved_runtime_slot_id"] = ""
        row["active_runtime_policy_id"] = r_active
        row.pop("runtime_adapter", None)
        row["operator_action"] = (
            "runtime_read_back_reconcile_dv070_external_unlinked"
            if et == "jupiter"
            else "runtime_read_back_reconcile_dv071_external_unlinked"
        )
        row["reconcile_linkage"] = "external_unlinked"

    row["reconciled_at_utc"] = _utc_now()
    row["reconcile_source"] = reconcile_source_tag
    store.setdefault("assignments_by_target", {})[et] = row
    write_store(repo, store)

    if ledger_detail is None:
        if rebind:
            detail = "dv070_rebind_to_runtime_read_back" if et == "jupiter" else "dv071_rebind_to_runtime_read_back"
        else:
            detail = "dv070_external_unlinked_to_runtime_read_back" if et == "jupiter" else "dv071_external_unlinked_to_runtime_read_back"
    else:
        detail = ledger_detail

    append_ledger_entry(
        repo,
        execution_target=et,
        previous_policy_id=k_active,
        new_policy_id=r_active,
        source=ledger_source,
        detail=detail,
    )
    return row


def _http_json(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any | None, str]:
    """Return (status, parsed_json_or_none, body_snippet)."""
    h = dict(headers or {})
    m = method.upper()
    if m == "GET":
        req = urllib.request.Request(url, headers=h)
    else:
        req = urllib.request.Request(url, data=data, headers=h, method=m)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
            try:
                return status, json.loads(raw), raw[:4000]
            except json.JSONDecodeError:
                return status, None, raw[:4000]
    except urllib.error.HTTPError as e:
        body = (e.read() or b"").decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body), body[:4000]
        except json.JSONDecodeError:
            return e.code, None, body[:4000]
    except OSError as e:
        return 0, None, str(e)[:2000]


def jupiter_post_active_policy(base: str, token: str, policy_id: str) -> dict[str, Any]:
    url = base.rstrip("/") + "/api/v1/jupiter/active-policy"
    payload = json.dumps({"policy": policy_id}).encode("utf-8")
    h = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    status, js, snippet = _http_json("POST", url, data=payload, headers=h)
    ok_http = status == 200
    ok_body = isinstance(js, dict) and js.get("ok") is True
    return {
        "ok": ok_http and ok_body,
        "http_status": status,
        "json": js,
        "body_snippet": snippet,
    }


def jupiter_get_policy(base: str, token: str) -> dict[str, Any]:
    url = base.rstrip("/") + "/api/v1/jupiter/policy"
    h = {"Authorization": f"Bearer {token}"}
    status, js, snippet = _http_json("GET", url, headers=h)
    ok = status == 200 and isinstance(js, dict) and "active_policy" in js
    return {
        "ok": ok,
        "http_status": status,
        "json": js if isinstance(js, dict) else None,
        "body_snippet": snippet,
    }


def blackbox_post_active_policy(
    base: str,
    token: str,
    policy_id: str,
    *,
    submission_id: str = "",
    content_sha256: str = "",
) -> dict[str, Any]:
    url = base.rstrip("/") + "/api/v1/blackbox/active-policy"
    body: dict[str, Any] = {"policy": policy_id}
    if str(submission_id or "").strip():
        body["submission_id"] = str(submission_id).strip()
    if str(content_sha256 or "").strip():
        body["content_sha256"] = str(content_sha256).strip()
    payload = json.dumps(body).encode("utf-8")
    h = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    status, js, snippet = _http_json("POST", url, data=payload, headers=h)
    ok_http = status == 200
    ok_body = isinstance(js, dict) and js.get("ok") is True
    return {
        "ok": ok_http and ok_body,
        "http_status": status,
        "json": js,
        "body_snippet": snippet,
    }


def blackbox_get_policy(base: str, token: str) -> dict[str, Any]:
    url = base.rstrip("/") + "/api/v1/blackbox/policy"
    h = {"Authorization": f"Bearer {token}"}
    status, js, snippet = _http_json("GET", url, headers=h)
    ok = status == 200 and isinstance(js, dict) and "active_policy" in js
    return {
        "ok": ok,
        "http_status": status,
        "json": js if isinstance(js, dict) else None,
        "body_snippet": snippet,
    }


def query_jupiter_runtime_truth(
    repo: Path,
    *,
    http_jupiter_base: str | None = None,
    http_jupiter_token: str | None = None,
) -> dict[str, Any]:
    """Authoritative Jupiter runtime policy via GET /api/v1/jupiter/policy (Bearer)."""
    repo = repo.resolve()
    base = (http_jupiter_base or os.environ.get("KITCHEN_JUPITER_CONTROL_BASE") or "").strip()
    tok = (http_jupiter_token or os.environ.get("KITCHEN_JUPITER_OPERATOR_TOKEN") or "").strip()
    if not base or not tok:
        return {
            "ok": False,
            "error": "jupiter_runtime_not_configured",
            "detail": "Set KITCHEN_JUPITER_CONTROL_BASE and KITCHEN_JUPITER_OPERATOR_TOKEN on the API host.",
            "execution_target": "jupiter",
        }
    r = jupiter_get_policy(base, tok)
    if not r.get("ok"):
        return {
            "ok": False,
            "error": "jupiter_runtime_unreachable",
            "http_status": r.get("http_status"),
            "detail": r.get("body_snippet"),
            "execution_target": "jupiter",
        }
    js = r.get("json") or {}
    active = str(js.get("active_policy") or "").strip()
    allowed = js.get("allowed_policies")
    unknown = False
    try:
        unknown = bool(active) and not runtime_policy_approved(repo, "jupiter", active)
    except (OSError, ValueError, FileNotFoundError):
        unknown = True
    return {
        "ok": True,
        "execution_target": "jupiter",
        "active_policy": active,
        "submission_id": str(js.get("submission_id") or "").strip(),
        "content_sha256": str(js.get("content_sha256") or "").strip(),
        "source": js.get("source"),
        "allowed_policies": allowed if isinstance(allowed, list) else [],
        "unknown_runtime_policy": unknown,
        "raw": js,
    }


def query_blackbox_runtime_truth(
    repo: Path,
    *,
    http_blackbox_base: str | None = None,
    http_blackbox_token: str | None = None,
) -> dict[str, Any]:
    """Authoritative BlackBox policy via GET /api/v1/blackbox/policy (Bearer), DV-071."""
    repo = repo.resolve()
    base = (http_blackbox_base or os.environ.get("KITCHEN_BLACKBOX_CONTROL_BASE") or "").strip()
    tok = (http_blackbox_token or os.environ.get("KITCHEN_BLACKBOX_OPERATOR_TOKEN") or "").strip()
    if not base or not tok:
        return {
            "ok": False,
            "error": "blackbox_runtime_not_configured",
            "detail": "Set KITCHEN_BLACKBOX_CONTROL_BASE and KITCHEN_BLACKBOX_OPERATOR_TOKEN on the API host.",
            "execution_target": "blackbox",
        }
    r = blackbox_get_policy(base, tok)
    if not r.get("ok"):
        return {
            "ok": False,
            "error": "blackbox_runtime_unreachable",
            "http_status": r.get("http_status"),
            "detail": r.get("body_snippet"),
            "execution_target": "blackbox",
        }
    js = r.get("json") or {}
    active = str(js.get("active_policy") or "").strip()
    allowed = js.get("allowed_policies")
    unknown = False
    try:
        unknown = bool(active) and not runtime_policy_approved(repo, "blackbox", active)
    except (OSError, ValueError, FileNotFoundError):
        unknown = True
    return {
        "ok": True,
        "execution_target": "blackbox",
        "active_policy": active,
        "submission_id": str(js.get("submission_id") or "").strip(),
        "content_sha256": str(js.get("content_sha256") or "").strip(),
        "source": js.get("source"),
        "allowed_policies": allowed if isinstance(allowed, list) else [],
        "unknown_runtime_policy": unknown,
        "raw": js,
    }


def query_runtime_truth(
    repo: Path,
    execution_target: str | None,
    *,
    http_jupiter_base: str | None = None,
    http_jupiter_token: str | None = None,
    http_blackbox_base: str | None = None,
    http_blackbox_token: str | None = None,
) -> dict[str, Any]:
    et = normalize_execution_target(execution_target)
    if et == "jupiter":
        return query_jupiter_runtime_truth(
            repo,
            http_jupiter_base=http_jupiter_base,
            http_jupiter_token=http_jupiter_token,
        )
    if et == "blackbox":
        return query_blackbox_runtime_truth(
            repo,
            http_blackbox_base=http_blackbox_base,
            http_blackbox_token=http_blackbox_token,
        )
    return {"ok": False, "error": "unsupported_execution_target", "execution_target": et}


def mechanical_slot_safe(repo: Path, et: str) -> dict[str, Any] | None:
    try:
        reg = load_registry(repo)
    except (OSError, ValueError, FileNotFoundError):
        return None
    ms = reg.get("mechanical_slot") or {}
    if not isinstance(ms, dict):
        return None
    row = ms.get(et)
    return row if isinstance(row, dict) else None


def _approved_slot_for_rebind(repo: Path, et: str, candidate_policy_id: str, r_active: str) -> str:
    ms = mechanical_slot_safe(repo, et)
    if ms and str(ms.get("candidate_policy_id") or "").strip() == str(candidate_policy_id).strip():
        return str(ms.get("approved_runtime_slot_id") or r_active).strip()
    return str(r_active).strip()


def _runtime_adapter_for_rebind(repo: Path, et: str, candidate_policy_id: str) -> str:
    ms = mechanical_slot_safe(repo, et)
    if ms and str(ms.get("candidate_policy_id") or "").strip() == str(candidate_policy_id).strip():
        return str(ms.get("runtime_adapter") or "").strip()
    return ""


def drift_status(
    repo: Path,
    execution_target: str | None,
    kitchen_row: dict[str, Any] | None,
    runtime_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare Kitchen last assignment vs runtime truth.

    States: match | runtime_unreachable | kitchen_unassigned | runtime_diverged | unknown_runtime_policy
    """
    et = normalize_execution_target(execution_target)
    if not runtime_payload.get("ok"):
        err = str(runtime_payload.get("error") or "runtime_unreachable")
        return {
            "state": "runtime_unreachable",
            "detail": runtime_payload.get("detail") or err,
            "error_code": err,
        }
    r_active = str(runtime_payload.get("active_policy") or "").strip()
    if runtime_payload.get("unknown_runtime_policy"):
        return {
            "state": "unknown_runtime_policy",
            "detail": "Runtime reports a policy id that is not in kitchen_policy_registry_v1 — manual change or skew.",
            "runtime_active_policy": r_active,
        }
    if not kitchen_row:
        return {
            "state": "kitchen_unassigned",
            "detail": "Kitchen has no recorded assignment for this target; runtime still has an active policy.",
            "runtime_active_policy": r_active,
        }
    k_active = str(kitchen_row.get("active_runtime_policy_id") or "").strip()
    k_hash = str(kitchen_row.get("content_sha256") or "").strip()
    k_sub = str(kitchen_row.get("submission_id") or "").strip()
    r_hash = str(runtime_payload.get("content_sha256") or "").strip()
    r_sub = str(runtime_payload.get("submission_id") or "").strip()
    if k_active and r_active and k_active == r_active:
        if k_hash:
            if not r_hash or not r_sub:
                return {
                    "state": "artifact_identity_mismatch",
                    "detail": "Kitchen assignment is manifest-bound but runtime did not report submission_id/content_sha256.",
                    "runtime_active_policy": r_active,
                    "kitchen_active_policy_id": k_active,
                    "kitchen_submission_id": k_sub,
                    "runtime_submission_id": r_sub,
                }
            if k_hash != r_hash or k_sub != r_sub:
                return {
                    "state": "artifact_identity_mismatch",
                    "detail": "Runtime submission_id or content_sha256 does not match Kitchen assignment.",
                    "runtime_active_policy": r_active,
                    "kitchen_active_policy_id": k_active,
                    "kitchen_submission_id": k_sub,
                    "runtime_submission_id": r_sub,
                }
        return {"state": "match", "detail": None, "runtime_active_policy": r_active, "kitchen_active_policy_id": k_active}
    return {
        "state": "runtime_diverged",
        "detail": "Kitchen last assigned policy does not match runtime (policy may have been changed outside Kitchen).",
        "runtime_active_policy": r_active,
        "kitchen_active_policy_id": k_active,
    }


def jupiter_control_plane_warnings(
    http_jupiter_base: str | None = None,
) -> list[str]:
    """
    DV-072 — Surface misconfiguration when Kitchen would talk to the wrong HTTP server.

    BlackBox ``api`` often listens on :8080; Sean Jupiter policy API is a different process
    (typically another port, e.g. 707 on the lab host). Using localhost:8080 for
    ``KITCHEN_JUPITER_CONTROL_BASE`` points at BlackBox, not Jupiter.
    """
    base = (http_jupiter_base or os.environ.get("KITCHEN_JUPITER_CONTROL_BASE") or "").strip().rstrip("/")
    out: list[str] = []
    if not base:
        out.append(
            "KITCHEN_JUPITER_CONTROL_BASE is unset. Set it to the same Jupiter origin the operator "
            "uses in the browser (scheme + host + port), not BlackBox api :8080."
        )
        return out
    low = base.lower()
    if ("127.0.0.1" in low or "localhost" in low) and ":8080" in low:
        out.append(
            "KITCHEN_JUPITER_CONTROL_BASE points at localhost:8080 — that is BlackBox api, not Sean Jupiter. "
            "Use the operator Jupiter origin (same host:port as the Jupiter UI)."
        )
    return out


def jupiter_control_base_blocks_assignment(http_jupiter_base: str | None = None) -> list[str]:
    """Non-empty only when assign must fail before HTTP (fatal misconfiguration)."""
    base = (http_jupiter_base or os.environ.get("KITCHEN_JUPITER_CONTROL_BASE") or "").strip().rstrip("/")
    if not base:
        return []
    low = base.lower()
    if ("127.0.0.1" in low or "localhost" in low) and ":8080" in low:
        return [
            "KITCHEN_JUPITER_CONTROL_BASE points at localhost:8080 — that is BlackBox api, not Sean Jupiter. "
            "Use the operator Jupiter origin (same host:port as the Jupiter UI)."
        ]
    return []


def maybe_record_external_runtime_change(
    repo: Path,
    execution_target: str,
    kitchen_row: dict[str, Any] | None,
    rt: dict[str, Any],
) -> dict[str, Any] | None:
    """
    DV-074A — When runtime truth differs from last Kitchen assignment, append an ``external`` ledger entry
    (deduped). Unknown registry policies get a separate dedupe key.
    """
    et = normalize_execution_target(execution_target)
    if not rt.get("ok"):
        return None
    r_active = str(rt.get("active_policy") or "").strip()
    if not r_active:
        return None

    if rt.get("unknown_runtime_policy"):
        fp = f"unreg:{r_active}"
        if get_external_dedupe_fingerprint(repo, et) == fp:
            return None
        e = append_ledger_entry(
            repo,
            execution_target=et,
            previous_policy_id=str(kitchen_row.get("active_runtime_policy_id") or "") if kitchen_row else "",
            new_policy_id=r_active,
            source="external",
            detail="runtime_active_policy_not_in_shared_registry",
        )
        set_external_dedupe_fingerprint(repo, et, fp)
        return e

    if not kitchen_row:
        return None
    k_active = str(kitchen_row.get("active_runtime_policy_id") or "").strip()
    if not k_active or k_active == r_active:
        return None
    fp = f"drift:{k_active}|{r_active}"
    if get_external_dedupe_fingerprint(repo, et) == fp:
        return None
    e = append_ledger_entry(
        repo,
        execution_target=et,
        previous_policy_id=k_active,
        new_policy_id=r_active,
        source="external",
        detail="runtime_diverged_from_last_kitchen_assignment",
    )
    set_external_dedupe_fingerprint(repo, et, fp)
    return e


def build_kitchen_runtime_read_payload(
    repo: Path,
    execution_target: str | None,
    *,
    http_jupiter_base: str | None = None,
    http_jupiter_token: str | None = None,
    http_blackbox_base: str | None = None,
    http_blackbox_token: str | None = None,
) -> dict[str, Any]:
    """Merged payload for GET /api/v1/renaissance/kitchen-runtime-assignment.

    Kitchen assignment store is **not** mutated on GET. Successful assignment only follows
    ``assign_mechanical_candidate`` (POST + runtime verify). Drift compares persisted assignment vs
    runtime GET for override/diagnostic display.
    """
    repo = repo.resolve()
    et = normalize_execution_target(execution_target)
    row_live = get_assignment(repo, et)
    reg = load_registry(repo)
    rt = query_runtime_truth(
        repo,
        et,
        http_jupiter_base=http_jupiter_base,
        http_jupiter_token=http_jupiter_token,
        http_blackbox_base=http_blackbox_base,
        http_blackbox_token=http_blackbox_token,
    )
    maybe_record_external_runtime_change(repo, et, row_live, rt)
    drift = drift_status(repo, et, row_live, rt)
    lc_sum: dict[str, Any] = {"schema": "kitchen_policy_lifecycle_summary_v1", "by_submission_id": {}}
    try:
        from renaissance_v4.kitchen_policy_lifecycle import lifecycle_summary_for_target, reconcile_with_drift

        reconcile_with_drift(repo, et, row_live, drift, rt)
        lc_sum = lifecycle_summary_for_target(repo, et)
    except Exception:
        pass
    ledger_tail = ledger_entries_for_target(repo, et, limit=20)
    cp_warnings: list[str] = []
    if et == "jupiter":
        cp_warnings = jupiter_control_plane_warnings(http_jupiter_base)
    live_policy = ""
    if isinstance(rt, dict) and rt.get("ok"):
        live_policy = str(rt.get("active_policy") or "").strip()
    k_assigned = str((row_live or {}).get("active_runtime_policy_id") or "").strip()
    # Primary operator story: Kitchen nexus when a row exists; else fall back to live observation.
    authoritative_active_policy = k_assigned if k_assigned else live_policy
    return {
        "schema": "kitchen_runtime_assignment_read_v5",
        "execution_target": et,
        "authoritative_active_policy": authoritative_active_policy,
        "live_runtime_policy": live_policy,
        "assignment": row_live,
        "drift_basis": "kitchen_assignment_row_vs_runtime_get",
        "mechanical_candidate_policy_id": MECHANICAL_CANDIDATE_POLICY_ID,
        "policy_registry": {
            "schema": reg.get("schema"),
            "runtime_policies": reg.get("runtime_policies"),
        },
        "approved_slots_by_target": {
            k: v["approved_runtime_slot_id"] for k, v in approved_mechanical_by_target(repo).items()
        },
        "runtime": rt,
        "drift": drift,
        "lifecycle": lc_sum,
        "ledger_tail": ledger_tail,
        "ledger_note": "Append-only history (Kitchen assigns + external/runtime drift). Rollback must use registry + ledger.",
        "control_plane_warnings": cp_warnings,
        "sync_state": (
            "synced"
            if drift.get("state") == "match"
            else ("runtime_unreachable" if drift.get("state") == "runtime_unreachable" else "drift")
        ),
    }


def _ensure_runtime_assignment_row_exists(repo: Path, et: str) -> None:
    """Minimal store row so reconcile / check-in can attach runtime policy ids."""
    if get_assignment(repo, et):
        return
    store = read_store(repo)
    store.setdefault("assignments_by_target", {})[et] = {
        "schema": "kitchen_runtime_assignment_record_v1",
        "execution_target": et,
        "submission_id": "",
        "candidate_policy_id": "",
        "approved_runtime_slot_id": "",
        "active_runtime_policy_id": "",
        "assigned_at_utc": _utc_now(),
        "operator_action": "seed_runtime_checkin",
        "runtime_adapter": "",
    }
    write_store(repo, store)


def apply_runtime_policy_checkin(
    repo: Path,
    execution_target: str,
    reported_active_policy: str,
    *,
    change_source: str = "trade_surface_manual",
    verify_runtime: bool = True,
    http_jupiter_base: str | None = None,
    http_jupiter_token: str | None = None,
    http_blackbox_base: str | None = None,
    http_blackbox_token: str | None = None,
) -> dict[str, Any]:
    """
    Explicit trade-surface → Kitchen handshake: verify live runtime GET matches ``reported_active_policy``,
    then persist assignment via ``reconcile_assignment_store_to_runtime_truth`` (rebind/unlink).

    Does **not** run on passive browser GET; callers POST ``/api/v1/renaissance/runtime-policy-checkin``.
    """
    from renaissance_v4.kitchen_policy_lifecycle import reconcile_with_drift, lifecycle_summary_for_target

    repo = repo.resolve()
    try:
        et = normalize_execution_target(execution_target)
    except ValueError as e:
        return {"ok": False, "error": "invalid_execution_target", "detail": str(e)[:500]}

    if et not in ("jupiter", "blackbox"):
        return {"ok": False, "error": "unsupported_execution_target", "execution_target": et}

    rid = str(reported_active_policy or "").strip()
    if not rid:
        return {"ok": False, "error": "missing_active_policy"}

    if not runtime_policy_approved(repo, et, rid):
        return {
            "ok": False,
            "error": "policy_not_in_registry",
            "detail": f"Policy {rid!r} is not approved for {et} in kitchen_policy_registry_v1.",
            "execution_target": et,
        }

    _ensure_runtime_assignment_row_exists(repo, et)
    row_before = copy.deepcopy(get_assignment(repo, et))

    rt = query_runtime_truth(
        repo,
        et,
        http_jupiter_base=http_jupiter_base,
        http_jupiter_token=http_jupiter_token,
        http_blackbox_base=http_blackbox_base,
        http_blackbox_token=http_blackbox_token,
    )

    if verify_runtime:
        if not rt.get("ok"):
            return {
                "ok": False,
                "error": "runtime_unreachable",
                "detail": str(rt.get("detail") or rt.get("error") or "runtime GET failed")[:2000],
                "execution_target": et,
                "reported_active_policy": rid,
                "runtime": rt,
            }
        live = str(rt.get("active_policy") or "").strip()
        if live != rid:
            return {
                "ok": False,
                "error": "runtime_verify_mismatch",
                "detail": "Live runtime GET active_policy does not match reported_active_policy (check-in is not trusted without verify).",
                "execution_target": et,
                "reported_active_policy": rid,
                "verified_runtime_policy": live,
                "runtime": rt,
            }

    k_before = str((row_before or {}).get("active_runtime_policy_id") or "").strip()
    if k_before == rid:
        row_after = get_assignment(repo, et)
        drift_post = drift_status(repo, et, row_after, rt)
        try:
            reconcile_with_drift(repo, et, row_after, drift_post, rt)
        except Exception:
            pass
        lc = lifecycle_summary_for_target(repo, et)
        return {
            "ok": True,
            "schema": "runtime_policy_checkin_result_v1",
            "execution_target": et,
            "reported_active_policy": rid,
            "verified_runtime_policy": str(rt.get("active_policy") or "").strip() if rt.get("ok") else "",
            "before_assignment": row_before,
            "after_assignment": row_after,
            "reconcile_linkage": "no_change",
            "change_source": change_source,
            "runtime": rt,
            "lifecycle": lc,
            "detail": "Kitchen assignment already matched verified runtime; no store mutation.",
        }

    ldetail = f"runtime_policy_checkin:{change_source}"
    reconciled = reconcile_assignment_store_to_runtime_truth(
        repo,
        et,
        rt,
        row_before,
        ledger_source="runtime_checkin",
        ledger_detail=ldetail,
        reconcile_source_tag="runtime_policy_checkin",
    )
    if reconciled is None:
        return {
            "ok": False,
            "error": "reconcile_failed",
            "detail": "reconcile_assignment_store_to_runtime_truth returned no update (unexpected).",
            "execution_target": et,
            "runtime": rt,
        }

    linkage = str(reconciled.get("reconcile_linkage") or "")
    row_after = get_assignment(repo, et)
    drift_post = drift_status(repo, et, row_after, rt)
    try:
        reconcile_with_drift(repo, et, row_after, drift_post, rt)
    except Exception:
        pass
    lc = lifecycle_summary_for_target(repo, et)

    return {
        "ok": True,
        "schema": "runtime_policy_checkin_result_v1",
        "execution_target": et,
        "reported_active_policy": rid,
        "verified_runtime_policy": str(rt.get("active_policy") or "").strip() if rt.get("ok") else "",
        "before_assignment": row_before,
        "after_assignment": row_after,
        "reconcile_linkage": linkage,
        "change_source": change_source,
        "runtime": rt,
        "lifecycle": lc,
        "detail": "Kitchen assignment updated to match verified runtime (runtime check-in).",
    }


def assign_mechanical_candidate(
    repo: Path,
    submission_id: str,
    execution_target: str | None = None,
    *,
    http_jupiter_base: str | None = None,
    http_jupiter_token: str | None = None,
    http_blackbox_base: str | None = None,
    http_blackbox_token: str | None = None,
) -> dict[str, Any]:
    """
    Assign a **passing** intake candidate whose ``candidate_policy_id`` maps to an approved runtime
    policy for the target (``kitchen_policy_registry_v1.json`` via
    :func:`~renaissance_v4.kitchen_policy_registry.infer_runtime_policy_id_for_candidate`).
    Includes the governed mechanical slot and any id listed under ``runtime_policies.{jupiter|blackbox}``.

    **Runtime must accept and read-back must match** (DV-074). Does not write local store unless
    verification succeeds.
    """
    repo = repo.resolve()
    rep_path = submission_dir(repo, submission_id) / "report" / "intake_report.json"
    rep = read_json(rep_path)
    if not isinstance(rep, dict) or not rep.get("pass"):
        return {"ok": False, "error": "submission_not_passing", "submission_id": submission_id}

    cid = str(rep.get("candidate_policy_id") or "").strip()

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

    if et not in ("jupiter", "blackbox"):
        return {"ok": False, "error": "unsupported_execution_target", "execution_target": et}

    mech = mechanical_slot_safe(repo, et)

    active_pid = infer_runtime_policy_id_for_candidate(repo, et, cid)
    if not active_pid:
        return {
            "ok": False,
            "error": "candidate_not_deployable",
            "detail": (
                "candidate_policy_id is not mapped to an approved runtime policy for this target in "
                "renaissance_v4/config/kitchen_policy_registry_v1.json "
                "(add to runtime_policies or mechanical_slot), or intake id cannot be deployed."
            ),
            "candidate_policy_id": cid,
            "execution_target": et,
        }

    is_mechanical_row = bool(
        mech and str(mech.get("candidate_policy_id") or "").strip() == cid
    )
    if is_mechanical_row and mech:
        slot = str(mech.get("approved_runtime_slot_id") or "")
        adapter = str(mech.get("runtime_adapter") or "")
    else:
        slot = active_pid
        adapter = (
            "seanv3_jupiter_active_policy"
            if et == "jupiter"
            else "reserved_blackbox_control_plane"
        )

    if not runtime_policy_approved(repo, et, active_pid):
        return {
            "ok": False,
            "error": "policy_not_in_registry",
            "detail": f"Runtime policy {active_pid!r} is not approved in kitchen_policy_registry_v1 for {et}.",
            "active_runtime_policy_id": active_pid,
        }

    if et == "jupiter":
        fatal_base = jupiter_control_base_blocks_assignment(http_jupiter_base)
        if fatal_base:
            return {
                "ok": False,
                "error": "jupiter_control_base_misconfigured",
                "detail": fatal_base[0],
                "control_plane_warnings": fatal_base,
            }

    content_sha = submission_content_sha256_from_intake(repo, submission_id)
    ok_m, err_m, det_m = validate_kitchen_assignment_against_manifest(
        repo, et, submission_id, content_sha, active_pid
    )
    if not ok_m:
        return {
            "ok": False,
            "error": err_m,
            "detail": det_m,
            "submission_id": submission_id,
            "candidate_policy_id": cid,
            "active_runtime_policy_id": active_pid,
            "execution_target": et,
        }

    record: dict[str, Any] = {
        "schema": "kitchen_runtime_assignment_record_v1",
        "execution_target": et,
        "submission_id": submission_id,
        "candidate_policy_id": cid,
        "approved_runtime_slot_id": slot,
        "active_runtime_policy_id": active_pid,
        "content_sha256": content_sha,
        "assigned_at_utc": _utc_now(),
        "operator_action": "kitchen_dashboard_assign",
        "runtime_adapter": adapter,
    }

    prev_policy_for_ledger = ""
    if et == "jupiter":
        base = (http_jupiter_base or os.environ.get("KITCHEN_JUPITER_CONTROL_BASE") or "").strip()
        tok = (http_jupiter_token or os.environ.get("KITCHEN_JUPITER_OPERATOR_TOKEN") or "").strip()
        if not base or not tok:
            return {
                "ok": False,
                "error": "jupiter_runtime_not_configured",
                "detail": "Set KITCHEN_JUPITER_CONTROL_BASE and KITCHEN_JUPITER_OPERATOR_TOKEN so Kitchen can apply and verify Jupiter runtime.",
            }
        pre_get = jupiter_get_policy(base, tok)
        if not pre_get.get("ok"):
            return {
                "ok": False,
                "error": "jupiter_runtime_unreachable_before_assign",
                "http_status": pre_get.get("http_status"),
                "detail": pre_get.get("body_snippet"),
            }
        pre_js = pre_get.get("json") or {}
        if not isinstance(pre_js, dict):
            return {
                "ok": False,
                "error": "jupiter_runtime_invalid_policy_payload",
                "detail": "GET /api/v1/jupiter/policy did not return a JSON object.",
            }
        prev_policy_for_ledger = str(pre_js.get("active_policy") or "").strip()
        allowed_raw = pre_js.get("allowed_policies")
        allowed_list = [str(x).strip() for x in allowed_raw] if isinstance(allowed_raw, list) else []
        if allowed_list and active_pid not in allowed_list:
            return {
                "ok": False,
                "error": "jupiter_runtime_policy_set_mismatch",
                "detail": (
                    f"Kitchen registry assigns {active_pid!r}, but this Jupiter instance's allowed_policies "
                    "does not include it. Redeploy Sean (vscode-test/seanv3) so ALLOWED_POLICY_IDS matches "
                    "renaissance_v4/config/kitchen_policy_registry_v1.json, or align the registry."
                ),
                "active_runtime_policy_id": active_pid,
                "jupiter_allowed_policies": allowed_list,
            }
        post = jupiter_post_active_policy(base, tok, active_pid)
        if not post.get("ok"):
            return {
                "ok": False,
                "error": "jupiter_runtime_post_failed",
                "http_status": post.get("http_status"),
                "detail": post.get("body_snippet"),
                "post_json": post.get("json"),
            }
        verify = jupiter_get_policy(base, tok)
        if not verify.get("ok"):
            return {
                "ok": False,
                "error": "jupiter_runtime_readback_failed",
                "http_status": verify.get("http_status"),
                "detail": verify.get("body_snippet"),
            }
        js = verify.get("json") or {}
        live = str(js.get("active_policy") or "").strip()
        if live != active_pid:
            return {
                "ok": False,
                "error": "runtime_verify_mismatch",
                "detail": "POST succeeded but GET /api/v1/jupiter/policy does not report the assigned policy.",
                "expected_active_policy": active_pid,
                "runtime_active_policy": live,
            }
        if not runtime_policy_approved(repo, "jupiter", live):
            return {
                "ok": False,
                "error": "runtime_reports_unregistered_policy",
                "detail": "Runtime active policy is not listed in kitchen_policy_registry_v1.",
                "runtime_active_policy": live,
            }
        js_sub = str(js.get("submission_id") or "").strip()
        js_hash = str(js.get("content_sha256") or "").strip()
        if content_sha:
            if not js_hash or not js_sub:
                return {
                    "ok": False,
                    "error": "runtime_identity_missing",
                    "detail": (
                        "GET /api/v1/jupiter/policy must report submission_id and content_sha256 "
                        "for manifest-bound assignment (BLACKBOX_REPO_ROOT + deployment manifest on Sean host)."
                    ),
                    "expected_submission_id": submission_id,
                    "expected_content_sha256": content_sha,
                }
            if js_hash != content_sha or js_sub != submission_id:
                return {
                    "ok": False,
                    "error": "runtime_identity_mismatch",
                    "detail": "Runtime GET submission_id or content_sha256 does not match Kitchen assignment.",
                    "expected_submission_id": submission_id,
                    "expected_content_sha256": content_sha,
                    "runtime_submission_id": js_sub,
                    "runtime_content_sha256": js_hash,
                }
        record["runtime_http_post_ok"] = True
        record["runtime_http_detail"] = str((post.get("json") or {}))[:2000]
        record["runtime_verify"] = {"source": js.get("source"), "allowed_policies": js.get("allowed_policies")}
    elif et == "blackbox":
        base = (http_blackbox_base or os.environ.get("KITCHEN_BLACKBOX_CONTROL_BASE") or "").strip()
        tok = (http_blackbox_token or os.environ.get("KITCHEN_BLACKBOX_OPERATOR_TOKEN") or "").strip()
        if not base or not tok:
            return {
                "ok": False,
                "error": "blackbox_runtime_not_configured",
                "detail": "Set KITCHEN_BLACKBOX_CONTROL_BASE and KITCHEN_BLACKBOX_OPERATOR_TOKEN so Kitchen can apply and verify BlackBox runtime.",
            }
        pre_get = blackbox_get_policy(base, tok)
        if not pre_get.get("ok"):
            return {
                "ok": False,
                "error": "blackbox_runtime_unreachable_before_assign",
                "http_status": pre_get.get("http_status"),
                "detail": pre_get.get("body_snippet"),
            }
        pre_js = pre_get.get("json") or {}
        if not isinstance(pre_js, dict):
            return {
                "ok": False,
                "error": "blackbox_runtime_invalid_policy_payload",
                "detail": "GET /api/v1/blackbox/policy did not return a JSON object.",
            }
        prev_policy_for_ledger = str(pre_js.get("active_policy") or "").strip()
        allowed_raw = pre_js.get("allowed_policies")
        allowed_list = [str(x).strip() for x in allowed_raw] if isinstance(allowed_raw, list) else []
        if allowed_list and active_pid not in allowed_list:
            return {
                "ok": False,
                "error": "blackbox_runtime_policy_set_mismatch",
                "detail": (
                    f"Kitchen registry assigns {active_pid!r}, but this BlackBox instance's allowed_policies "
                    "does not include it. Align kitchen_policy_registry_v1.json runtime_policies.blackbox with the API host."
                ),
                "active_runtime_policy_id": active_pid,
                "blackbox_allowed_policies": allowed_list,
            }
        post = blackbox_post_active_policy(
            base, tok, active_pid, submission_id=submission_id, content_sha256=content_sha
        )
        if not post.get("ok"):
            return {
                "ok": False,
                "error": "blackbox_runtime_post_failed",
                "http_status": post.get("http_status"),
                "detail": post.get("body_snippet"),
                "post_json": post.get("json"),
            }
        verify = blackbox_get_policy(base, tok)
        if not verify.get("ok"):
            return {
                "ok": False,
                "error": "blackbox_runtime_readback_failed",
                "http_status": verify.get("http_status"),
                "detail": verify.get("body_snippet"),
            }
        js = verify.get("json") or {}
        live = str(js.get("active_policy") or "").strip()
        if live != active_pid:
            return {
                "ok": False,
                "error": "runtime_verify_mismatch",
                "detail": "POST succeeded but GET /api/v1/blackbox/policy does not report the assigned policy.",
                "expected_active_policy": active_pid,
                "runtime_active_policy": live,
            }
        if not runtime_policy_approved(repo, "blackbox", live):
            return {
                "ok": False,
                "error": "runtime_reports_unregistered_policy",
                "detail": "Runtime active policy is not listed in kitchen_policy_registry_v1.",
                "runtime_active_policy": live,
            }
        js_sub = str(js.get("submission_id") or "").strip()
        js_hash = str(js.get("content_sha256") or "").strip()
        if content_sha:
            if not js_hash or not js_sub:
                return {
                    "ok": False,
                    "error": "runtime_identity_missing",
                    "detail": (
                        "GET /api/v1/blackbox/policy must report submission_id and content_sha256 "
                        "for manifest-bound assignment."
                    ),
                    "expected_submission_id": submission_id,
                    "expected_content_sha256": content_sha,
                }
            if js_hash != content_sha or js_sub != submission_id:
                return {
                    "ok": False,
                    "error": "runtime_identity_mismatch",
                    "detail": "Runtime GET submission_id or content_sha256 does not match Kitchen assignment.",
                    "expected_submission_id": submission_id,
                    "expected_content_sha256": content_sha,
                    "runtime_submission_id": js_sub,
                    "runtime_content_sha256": js_hash,
                }
        record["runtime_http_post_ok"] = True
        record["runtime_http_detail"] = str((post.get("json") or {}))[:2000]
        record["runtime_verify"] = {"source": js.get("source"), "allowed_policies": js.get("allowed_policies")}
    else:
        return {"ok": False, "error": "unsupported_execution_target", "execution_target": et}

    store = read_store(repo)
    store.setdefault("assignments_by_target", {})
    store["assignments_by_target"][et] = record
    write_store(repo, store)

    if et in ("jupiter", "blackbox"):
        append_ledger_entry(
            repo,
            execution_target=et,
            previous_policy_id=prev_policy_for_ledger,
            new_policy_id=str(record.get("active_runtime_policy_id") or ""),
            source="kitchen",
            detail="kitchen_assign_runtime_confirmed",
        )
        try:
            from renaissance_v4.kitchen_policy_lifecycle import mark_assigned_runtime_confirmed

            mark_assigned_runtime_confirmed(
                repo,
                submission_id,
                et,
                runtime_policy_id=str(record.get("active_runtime_policy_id") or ""),
                candidate_policy_id=str(record.get("candidate_policy_id") or ""),
            )
        except Exception:
            pass

    out: dict[str, Any] = {"ok": True, **record}
    return out


# --- Legacy module-level map for imports that expect APPROVED_MECHANICAL_BY_TARGET (repo-agnostic defaults) ---

_DEFAULT_MECH: dict[str, dict[str, str]] = {
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


def _approved_fallback() -> dict[str, dict[str, str]]:
    return dict(_DEFAULT_MECH)


# Exported name: tests and api may use with repo-aware helper
APPROVED_MECHANICAL_BY_TARGET: dict[str, dict[str, str]] = _approved_fallback()


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
