"""
Append-only experiment index (JSON) for audit lineage.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Status = Literal["pending", "running", "complete", "rejected", "promoted", "archived"]


@dataclass
class ExperimentRecord:
    experiment_id: str
    branch: str
    commit_hash: str
    baseline_tag: str
    description: str
    subsystem: str
    status: Status
    deterministic_summary_path: str
    monte_carlo_summary_path: str
    comparison_report_path: str
    recommendation: str
    created_at: str
    completed_at: str | None = None
    files_changed: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["extra"] = dict(self.extra)
        return d


def _default_index_path() -> Path:
    return Path(__file__).resolve().parent.parent / "state" / "experiment_index.json"


def load_index(path: Path | None = None) -> dict[str, Any]:
    p = path or _default_index_path()
    if not p.exists():
        return {"schema": "renaissance_v4_experiment_index_v1", "experiments": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save_index(data: dict[str, Any], path: Path | None = None) -> None:
    p = path or _default_index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def new_experiment_id() -> str:
    return f"exp_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"


def append_experiment(rec: ExperimentRecord, path: Path | None = None) -> None:
    data = load_index(path)
    data.setdefault("experiments", []).append(rec.to_dict())
    save_index(data, path)
