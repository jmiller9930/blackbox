from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RuntimeState:
    generation: str
    directive_title: str
    directive_status: str
    bridge_state: str
    next_actor: str
    required_phrase: str
    proof_status: str
    last_transition_reason: str
    updated_at: str


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1252")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")


def load_state(path: Path) -> RuntimeState | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return RuntimeState(
        generation=str(data.get("generation", "")),
        directive_title=str(data.get("directive_title", "")),
        directive_status=str(data.get("directive_status", "")),
        bridge_state=str(data.get("bridge_state", "idle")),
        next_actor=str(data.get("next_actor", "none")),
        required_phrase=str(data.get("required_phrase", "")),
        proof_status=str(data.get("proof_status", "missing")),
        last_transition_reason=str(data.get("last_transition_reason", "")),
        updated_at=str(data.get("updated_at", "")),
    )


def save_state(path: Path, state: RuntimeState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_directive_fields(docs_working: Path) -> tuple[str, str, bool]:
    directive_path = docs_working / "current_directive.md"
    text = _read_text(directive_path)
    status_match = re.search(r"^\*\*Status:\*\* (.+)$", text, re.M)
    title_match = re.search(r"^## Title\s*\n\s*\*\*(.+)\*\*$", text, re.M)
    status = status_match.group(1).strip() if status_match else "unknown"
    title = title_match.group(1).strip() if title_match else "unknown"
    closed = status.lower().startswith("closed")
    return title, status, closed


def read_shared_log_text(docs_working: Path) -> str:
    return _read_text(docs_working / "shared_coordination_log.md")


def make_generation(title: str, status: str, bridge_state: str, next_actor: str, proof_status: str) -> str:
    return "|".join([title, status, bridge_state, next_actor, proof_status])


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()

