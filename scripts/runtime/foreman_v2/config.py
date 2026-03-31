from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ForemanV2Config:
    repo_root: Path
    docs_working: Path
    state_path: Path
    audit_path: Path
    pid_path: Path
    session_lock_path: Path
    role_registry_path: Path
    talking_stick_path: Path
    poll_seconds: float
    mission_control_url: str
    mc_api_token: str
    developer_session_id: str
    architect_session_id: str
    dry_run: bool
    strict_session_guard: bool
    dispatch_fallback_dry_run: bool = True
    actor_progress_path: Path | None = None


def load_config() -> ForemanV2Config:
    repo_root = Path(__file__).resolve().parents[3]
    docs_working = repo_root / "docs" / "working"
    return ForemanV2Config(
        repo_root=repo_root,
        docs_working=docs_working,
        state_path=docs_working / "foreman_v2_runtime_state.json",
        audit_path=docs_working / "foreman_v2_audit.jsonl",
        pid_path=docs_working / "foreman_v2.pid",
        session_lock_path=docs_working / "foreman_v2_session_lock.json",
        role_registry_path=docs_working / "foreman_v2_role_registry.json",
        talking_stick_path=docs_working / "talking_stick.json",
        actor_progress_path=docs_working / "actor_progress.jsonl",
        poll_seconds=float(os.environ.get("FOREMAN_V2_POLL_SECONDS", "3")),
        mission_control_url=os.environ.get("MISSION_CONTROL_URL", "http://localhost:4000").rstrip("/"),
        mc_api_token=os.environ.get("MC_API_TOKEN", "").strip(),
        developer_session_id=os.environ.get("FOREMAN_V2_DEVELOPER_SESSION", "").strip(),
        architect_session_id=os.environ.get("FOREMAN_V2_ARCHITECT_SESSION", "").strip(),
        dry_run=os.environ.get("FOREMAN_V2_DRY_RUN", "").strip().lower() in {"1", "true", "yes"},
        strict_session_guard=os.environ.get("FOREMAN_V2_STRICT_SESSION_GUARD", "1").strip().lower()
        in {"1", "true", "yes"},
        dispatch_fallback_dry_run=os.environ.get("FOREMAN_V2_DISPATCH_FALLBACK_DRY_RUN", "1").strip().lower()
        not in {"0", "false", "no"},
    )


def apply_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs from a .env-style file into ``os.environ`` (later lines override)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value

