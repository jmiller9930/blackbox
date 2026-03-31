from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from foreman_v2.config import ForemanV2Config


@dataclass(frozen=True)
class DispatchResult:
    sent: bool
    target: str
    detail: str


def _request_json(
    url: str,
    method: str,
    token: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[bool, str, dict]:
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url=url, data=data, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if headers:
        for key, value in headers.items():
            # urllib/http headers must be latin-1 encodable. Normalize to ASCII-safe.
            safe_value = str(value).encode("ascii", errors="replace").decode("ascii")
            req.add_header(key, safe_value)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            if not raw:
                return True, f"http_{resp.status}", {}
            parsed = json.loads(raw.decode("utf-8"))
            if isinstance(parsed, dict):
                return True, f"http_{resp.status}", parsed
            return True, f"http_{resp.status}", {}
    except urllib.error.HTTPError as exc:
        return False, f"http_error_{exc.code}", {}
    except Exception as exc:  # noqa: BLE001
        return False, f"error_{exc}", {}


def _session_id_for_actor(config: ForemanV2Config, actor: str) -> str:
    # Prefer the live role registry mapping when present, since session IDs can
    # be rebound at runtime and env-loaded IDs may go stale in long-running loops.
    try:
        if config.role_registry_path.exists():
            payload = json.loads(config.role_registry_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                roles = payload.get("roles", {})
                if isinstance(roles, dict):
                    actor_data = roles.get(actor, {})
                    if isinstance(actor_data, dict):
                        sid = str(actor_data.get("session_id", "")).strip()
                        if sid:
                            return sid
    except Exception:  # noqa: BLE001
        pass
    if actor == "developer":
        return config.developer_session_id
    if actor == "architect":
        return config.architect_session_id
    return ""


def _load_lock(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_lock(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _verify_and_lock_session(config: ForemanV2Config, actor: str, sid: str) -> tuple[bool, str]:
    if not config.strict_session_guard:
        return True, "guard_disabled"
    ok, detail, data = _request_json(
        f"{config.mission_control_url}/api/openclaw/sessions/{sid}",
        "GET",
        config.mc_api_token,
    )
    if not ok:
        return False, f"session_preflight_failed:{detail}"
    session = data.get("session")
    if not isinstance(session, dict):
        return False, "session_preflight_failed:no_session_payload"
    returned_id = str(session.get("id", "")).strip()
    returned_session_id = str(session.get("sessionId", "")).strip()
    openclaw_session_id = str(session.get("openclaw_session_id", "")).strip()
    if sid not in {returned_id, returned_session_id, openclaw_session_id}:
        return False, "session_preflight_failed:id_mismatch"

    lock = _load_lock(config.session_lock_path)
    actor_locks = lock.get("actor_locks", {})
    if not isinstance(actor_locks, dict):
        actor_locks = {}
    existing = actor_locks.get(actor)
    if isinstance(existing, str) and existing and existing != sid:
        return False, f"session_lock_conflict:{actor}:{existing}->{sid}"
    actor_locks[actor] = sid
    lock["actor_locks"] = actor_locks
    lock["updated_at"] = datetime.now().astimezone().isoformat()
    if "created_at" not in lock:
        lock["created_at"] = lock["updated_at"]
    _save_lock(config.session_lock_path, lock)
    return True, "session_locked"


def close_actor_session(config: ForemanV2Config, actor: str) -> tuple[bool, str]:
    sid = _session_id_for_actor(config, actor)
    if not sid:
        return False, "missing_session_id"
    ended_at = datetime.now().astimezone().isoformat()
    ok_patch, detail_patch, _ = _request_json(
        f"{config.mission_control_url}/api/openclaw/sessions/{sid}",
        "PATCH",
        config.mc_api_token,
        {"status": "completed", "ended_at": ended_at},
    )
    ok_delete, detail_delete, _ = _request_json(
        f"{config.mission_control_url}/api/openclaw/sessions/{sid}",
        "DELETE",
        config.mc_api_token,
    )
    if ok_patch or ok_delete:
        return True, f"remote_closed patch={detail_patch} delete={detail_delete}"
    # Treat missing DB-mapped session rows as already closed from Foreman's view.
    if detail_patch == "http_error_404" and detail_delete == "http_error_404":
        return True, "remote_already_absent"
    return False, f"remote_close_failed patch={detail_patch} delete={detail_delete}"


def _should_fallback_session_failure(detail: str) -> bool:
    """True when failure is recoverable (no/stale session), not lock conflicts."""
    if "session_lock_conflict" in detail:
        return False
    if "session_preflight_failed" in detail:
        return True
    if detail == "missing_session_id":
        return True
    if detail == "missing_session_payload":
        return True
    return False


def dispatch_to_actor(
    config: ForemanV2Config,
    actor: str,
    message: str,
    dispatch_key: str | None = None,
) -> DispatchResult:
    if config.dry_run:
        return DispatchResult(True, actor, "dry_run")
    sid = _session_id_for_actor(config, actor)
    if not sid and actor not in {"developer", "architect"}:
        return DispatchResult(False, actor, "no_target_actor")
    if not sid:
        if config.dispatch_fallback_dry_run:
            return DispatchResult(True, actor, "dry_run_fallback:missing_session_id")
        return DispatchResult(False, actor, "missing_session_id")
    ok_verify, detail_verify = _verify_and_lock_session(config, actor, sid)
    if not ok_verify:
        if config.dispatch_fallback_dry_run and _should_fallback_session_failure(detail_verify):
            return DispatchResult(True, actor, f"dry_run_fallback:{detail_verify}")
        return DispatchResult(False, actor, detail_verify)
    ok, detail, _ = _request_json(
        f"{config.mission_control_url}/api/openclaw/sessions/{sid}",
        "POST",
        config.mc_api_token,
        {"content": message},
        headers={
            "X-Foreman-Actor": actor,
            "X-Foreman-Dispatch-Key": (dispatch_key or "").encode("ascii", errors="replace").decode("ascii"),
        },
    )
    return DispatchResult(ok, actor, detail)

