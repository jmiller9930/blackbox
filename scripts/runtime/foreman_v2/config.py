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
    poll_seconds: float
    mission_control_url: str
    mc_api_token: str
    developer_session_id: str
    architect_session_id: str
    dry_run: bool
    strict_session_guard: bool


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
        poll_seconds=float(os.environ.get("FOREMAN_V2_POLL_SECONDS", "3")),
        mission_control_url=os.environ.get("MISSION_CONTROL_URL", "http://localhost:4000").rstrip("/"),
        mc_api_token=os.environ.get("MC_API_TOKEN", "").strip(),
        developer_session_id=os.environ.get("FOREMAN_V2_DEVELOPER_SESSION", "").strip(),
        architect_session_id=os.environ.get("FOREMAN_V2_ARCHITECT_SESSION", "").strip(),
        dry_run=os.environ.get("FOREMAN_V2_DRY_RUN", "").strip().lower() in {"1", "true", "yes"},
        strict_session_guard=os.environ.get("FOREMAN_V2_STRICT_SESSION_GUARD", "1").strip().lower()
        in {"1", "true", "yes"},
    )

