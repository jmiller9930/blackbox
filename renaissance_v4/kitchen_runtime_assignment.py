"""
DV-068 / DV-074 — Multi-target Kitchen → runtime assignment with runtime as source of truth.

Flow: **Kitchen candidate** → **approved runtime slot** → **execution target** → **active runtime policy id**.

DV-074: Assignment **never** persists unless the runtime accepts the change and a read-back confirms the
active policy. Kitchen local store records intent; **runtime GET** is authoritative for \"what is running\".
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
from renaissance_v4.kitchen_policy_ledger import (
    append_ledger_entry,
    get_external_dedupe_fingerprint,
    ledger_entries_for_target,
    set_external_dedupe_fingerprint,
)
from renaissance_v4.kitchen_policy_registry import (
    approved_mechanical_by_target,
    load_registry,
    runtime_policy_approved,
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
) -> dict[str, Any] | None:
    """
    DV-070 — Runtime read-back is authoritative for live policy. If the persisted Kitchen row
    disagrees with ``active_policy`` from the runtime GET, collapse ``active_runtime_policy_id``
    to match (ledger records reconciliation; no parallel “Kitchen active” vs runtime).
    """
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
    row["active_runtime_policy_id"] = r_active
    row["operator_action"] = (
        "runtime_read_back_reconcile_dv070" if et == "jupiter" else "runtime_read_back_reconcile_dv071"
    )
    row["reconciled_at_utc"] = _utc_now()
    row["reconcile_source"] = "runtime_get"
    store.setdefault("assignments_by_target", {})[et] = row
    write_store(repo, store)
    append_ledger_entry(
        repo,
        execution_target=et,
        previous_policy_id=k_active,
        new_policy_id=r_active,
        source="reconciliation",
        detail=(
            "dv070_kitchen_collapsed_to_runtime_read_back"
            if et == "jupiter"
            else "dv071_kitchen_collapsed_to_runtime_read_back"
        ),
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


def blackbox_post_active_policy(base: str, token: str, policy_id: str) -> dict[str, Any]:
    url = base.rstrip("/") + "/api/v1/blackbox/active-policy"
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
    if k_active and r_active and k_active == r_active:
        return {"state": "match", "detail": None, "runtime_active_policy": r_active, "kitchen_active_policy_id": k_active}
    return {
        "state": "runtime_diverged",
        "detail": "Kitchen last assigned policy does not match runtime (policy may have been changed outside Kitchen).",
        "runtime_active_policy": r_active,
        "kitchen_active_policy_id": k_active,
    }


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
    """Merged payload for GET /api/v1/renaissance/kitchen-runtime-assignment."""
    repo = repo.resolve()
    et = normalize_execution_target(execution_target)
    row = get_assignment(repo, et)
    reg = load_registry(repo)
    rt = query_runtime_truth(
        repo,
        et,
        http_jupiter_base=http_jupiter_base,
        http_jupiter_token=http_jupiter_token,
        http_blackbox_base=http_blackbox_base,
        http_blackbox_token=http_blackbox_token,
    )
    maybe_record_external_runtime_change(repo, et, row, rt)
    reconcile_assignment_store_to_runtime_truth(repo, et, rt, row)
    row = get_assignment(repo, et)
    drift = drift_status(repo, et, row, rt)
    lc_sum: dict[str, Any] = {"schema": "kitchen_policy_lifecycle_summary_v1", "by_submission_id": {}}
    try:
        from renaissance_v4.kitchen_policy_lifecycle import lifecycle_summary_for_target, reconcile_with_drift

        reconcile_with_drift(repo, et, row, drift, rt)
        lc_sum = lifecycle_summary_for_target(repo, et)
    except Exception:
        pass
    ledger_tail = ledger_entries_for_target(repo, et, limit=20)
    return {
        "schema": "kitchen_runtime_assignment_read_v3",
        "execution_target": et,
        "assignment": row,
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
    Assign passing mechanical intake: **runtime must accept and read-back must match** (DV-074).
    Does not write local store unless verification succeeds.
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

    mech = mechanical_slot_safe(repo, et)
    if not mech:
        return {"ok": False, "error": "unsupported_execution_target", "execution_target": et}

    slot = mech["approved_runtime_slot_id"]
    active_pid = mech["active_runtime_policy_id"]
    adapter = mech.get("runtime_adapter", "")

    if not runtime_policy_approved(repo, et, active_pid):
        return {
            "ok": False,
            "error": "policy_not_in_registry",
            "detail": f"Runtime policy {active_pid!r} is not approved in kitchen_policy_registry_v1 for {et}.",
            "active_runtime_policy_id": active_pid,
        }

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
        try:
            from renaissance_v4.kitchen_policy_lifecycle import mark_assignment_requested

            mark_assignment_requested(repo, submission_id, et, intent_runtime_policy_id=active_pid)
        except Exception:
            pass
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
        try:
            from renaissance_v4.kitchen_policy_lifecycle import mark_assignment_requested

            mark_assignment_requested(repo, submission_id, et, intent_runtime_policy_id=active_pid)
        except Exception:
            pass
        post = blackbox_post_active_policy(base, tok, active_pid)
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
