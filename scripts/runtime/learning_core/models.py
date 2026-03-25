"""Learning core record model (Directive 4.6.3.2 Part A)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class LearningRecord:
    id: str
    state: str  # candidate | under_test | validated | rejected
    source: str
    content: str
    created_at: datetime
    updated_at: datetime
    evidence_links: list[str]
    validation_notes: str
    version: int

    @staticmethod
    def from_row(row: dict[str, Any]) -> "LearningRecord":
        return LearningRecord(
            id=str(row["id"]),
            state=str(row["state"]),
            source=str(row["source"]),
            content=str(row["content"]),
            created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00")),
            evidence_links=list(row.get("evidence_links") or []),
            validation_notes=str(row.get("validation_notes") or ""),
            version=int(row.get("version") or 1),
        )
