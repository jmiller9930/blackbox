"""Filesystem layout for policy intake (DV-ARCH-KITCHEN-POLICY-INTAKE-048)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def intake_root(repo: Path) -> Path:
    return repo.resolve() / "renaissance_v4" / "state" / "policy_intake_submissions"


def submission_dir(repo: Path, submission_id: str) -> Path:
    sid = re.sub(r"[^a-zA-Z0-9_-]", "", submission_id)[:128]
    return intake_root(repo) / sid


def ensure_submission_layout(repo: Path, submission_id: str) -> dict[str, Path]:
    base = submission_dir(repo, submission_id)
    raw = base / "raw"
    canonical = base / "canonical"
    report = base / "report"
    raw.mkdir(parents=True, exist_ok=True)
    canonical.mkdir(parents=True, exist_ok=True)
    report.mkdir(parents=True, exist_ok=True)
    return {"base": base, "raw": raw, "canonical": canonical, "report": report}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
