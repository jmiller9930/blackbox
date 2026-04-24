"""
Ask DATA **operator signals** — append-only JSONL for repeatability and future service quality.

Each answered question appends an ``interaction`` line. Operators POST ``feedback`` (rating + optional tags).
Rollups for the same **question fingerprint** are injected into the next Ask DATA bundle as
``operator_feedback_signals`` (aggregates only — **not** Referee or run truth).

Disable all file I/O: ``ASK_DATA_OPERATOR_FEEDBACK=0``.

Override path (tests): ``ASK_DATA_OPERATOR_FEEDBACK_PATH=/tmp/x.jsonl``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections import Counter, deque
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.memory_paths import default_ask_data_operator_feedback_jsonl

_WS = re.compile(r"\s+")


def ask_data_operator_feedback_enabled_v1() -> bool:
    v = os.environ.get("ASK_DATA_OPERATOR_FEEDBACK")
    if v is None or str(v).strip() == "":
        return True
    return str(v).strip().lower() not in ("0", "false", "no", "off")


def ask_data_operator_feedback_jsonl_path_v1() -> Path:
    p = (os.environ.get("ASK_DATA_OPERATOR_FEEDBACK_PATH") or "").strip()
    if p:
        return Path(p).expanduser()
    return default_ask_data_operator_feedback_jsonl()


def question_fingerprint_v1(question: str) -> str:
    q = (question or "").strip().lower()
    q = _WS.sub(" ", q)[:2000]
    return hashlib.sha256(q.encode("utf-8")).hexdigest()


def _read_tail_lines(path: Path, max_lines: int) -> list[str]:
    if max_lines < 1 or not path.is_file():
        return []
    dq: deque[str] = deque(maxlen=max_lines)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if line:
                dq.append(line)
    return list(dq)


def rollup_operator_feedback_for_fingerprint_v1(
    question_fingerprint: str,
    *,
    path: Path | None = None,
    tail_lines: int = 8000,
) -> dict[str, Any]:
    """Aggregate prior **feedback** events matching ``question_fingerprint`` (tail scan)."""
    if not ask_data_operator_feedback_enabled_v1():
        return {
            "schema": "ask_data_operator_feedback_signals_v1",
            "enabled": False,
            "question_fingerprint": question_fingerprint,
        }
    p = path or ask_data_operator_feedback_jsonl_path_v1()
    lines = _read_tail_lines(p, tail_lines)
    ratings: Counter[str] = Counter()
    tag_ctr: Counter[str] = Counter()
    n = 0
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("schema") != "ask_data_telemetry_v1":
            continue
        if row.get("event") != "feedback":
            continue
        if row.get("question_fingerprint") != question_fingerprint:
            continue
        n += 1
        r = str(row.get("rating") or "")
        if r in ("up", "down", "neutral"):
            ratings[r] += 1
        for t in row.get("tags") or []:
            if isinstance(t, str) and t.strip():
                tag_ctr[t.strip()[:64]] += 1
    top_tags = [k for k, _ in tag_ctr.most_common(6)]
    return {
        "schema": "ask_data_operator_feedback_signals_v1",
        "enabled": True,
        "question_fingerprint": question_fingerprint,
        "prior_feedback_count": n,
        "rating_counts": dict(ratings),
        "top_tags": top_tags,
        "honesty_line": (
            "Aggregated from operator feedback on **similar questions** (same text fingerprint). "
            "This is **not** Referee truth or run facts — use it only to calibrate explanations and UX."
        ),
    }


def bundle_with_operator_feedback_signals_v1(
    bundle: dict[str, Any],
    signals: dict[str, Any],
) -> dict[str, Any]:
    out = dict(bundle)
    out["operator_feedback_signals"] = signals
    return out


def _append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def append_ask_data_interaction_telemetry_v1(
    *,
    interaction_id: str,
    question_fingerprint: str,
    job_id: str | None,
    ask_data_route: str,
    answer_source: str,
    job_resolution: str,
    question_len: int,
    path: Path | None = None,
) -> None:
    if not ask_data_operator_feedback_enabled_v1():
        return
    p = path or ask_data_operator_feedback_jsonl_path_v1()
    _append_jsonl(
        p,
        {
            "schema": "ask_data_telemetry_v1",
            "event": "interaction",
            "ts_unix": time.time(),
            "interaction_id": interaction_id,
            "question_fingerprint": question_fingerprint,
            "job_id": (job_id or "").strip() or None,
            "ask_data_route": ask_data_route,
            "answer_source": answer_source,
            "job_resolution": job_resolution,
            "question_len": int(question_len),
        },
    )


def interaction_feedback_already_recorded_v1(
    interaction_id: str,
    *,
    path: Path | None = None,
    tail_lines: int = 8000,
) -> bool:
    p = path or ask_data_operator_feedback_jsonl_path_v1()
    for line in _read_tail_lines(p, tail_lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("schema") != "ask_data_telemetry_v1" or row.get("event") != "feedback":
            continue
        if row.get("interaction_id") == interaction_id:
            return True
    return False


def interaction_exists_in_telemetry_v1(
    interaction_id: str,
    *,
    path: Path | None = None,
    tail_lines: int = 8000,
) -> bool:
    p = path or ask_data_operator_feedback_jsonl_path_v1()
    for line in _read_tail_lines(p, tail_lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("schema") != "ask_data_telemetry_v1" or row.get("event") != "interaction":
            continue
        if row.get("interaction_id") == interaction_id:
            return True
    return False


def lookup_interaction_meta_v1(
    interaction_id: str,
    *,
    path: Path | None = None,
    tail_lines: int = 8000,
) -> dict[str, Any] | None:
    """Return the newest matching interaction row (for fingerprint on feedback line)."""
    p = path or ask_data_operator_feedback_jsonl_path_v1()
    for line in reversed(_read_tail_lines(p, tail_lines)):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("schema") != "ask_data_telemetry_v1" or row.get("event") != "interaction":
            continue
        if row.get("interaction_id") == interaction_id:
            return row
    return None


def append_ask_data_feedback_telemetry_v1(
    *,
    interaction_id: str,
    question_fingerprint: str,
    rating: str,
    tags: list[str],
    note: str,
    path: Path | None = None,
) -> tuple[bool, str | None]:
    """
    Append a feedback line. Returns ``(True, None)`` or ``(False, error_message)``.
    Caller should verify interaction exists and duplicate feedback absent.
    """
    if not ask_data_operator_feedback_enabled_v1():
        return False, "operator feedback is disabled (ASK_DATA_OPERATOR_FEEDBACK)"
    p = path or ask_data_operator_feedback_jsonl_path_v1()
    _append_jsonl(
        p,
        {
            "schema": "ask_data_telemetry_v1",
            "event": "feedback",
            "ts_unix": time.time(),
            "interaction_id": interaction_id,
            "question_fingerprint": question_fingerprint,
            "rating": rating,
            "tags": tags,
            "note": note,
        },
    )
    return True, None


def new_interaction_id_v1() -> str:
    return uuid.uuid4().hex


__all__ = [
    "append_ask_data_feedback_telemetry_v1",
    "append_ask_data_interaction_telemetry_v1",
    "ask_data_operator_feedback_enabled_v1",
    "ask_data_operator_feedback_jsonl_path_v1",
    "bundle_with_operator_feedback_signals_v1",
    "interaction_exists_in_telemetry_v1",
    "interaction_feedback_already_recorded_v1",
    "lookup_interaction_meta_v1",
    "new_interaction_id_v1",
    "question_fingerprint_v1",
    "rollup_operator_feedback_for_fingerprint_v1",
]
