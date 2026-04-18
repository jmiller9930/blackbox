"""
Append-only **batch scorecard** for parallel pattern-game runs: UTC start/end, duration, totals.

Persists to ``batch_scorecard.jsonl`` (under ``PATTERN_GAME_MEMORY_ROOT`` when set). Safe for
operators to tail or ship to analysis; one JSON object per line.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl

_APPEND_LOCK = threading.Lock()
SCHEMA_V1 = "pattern_game_batch_scorecard_v1"


def utc_timestamp_iso() -> str:
    """UTC wall time with second precision, ``Z`` suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_batch_scorecard_line(
    record: dict[str, Any],
    *,
    path: Path | None = None,
) -> Path:
    """Append one JSON line; return resolved path."""
    p = path or default_batch_scorecard_jsonl()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _APPEND_LOCK:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return p.resolve()


def read_batch_scorecard_recent(
    limit: int = 30,
    *,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return up to ``limit`` newest entries (newest first)."""
    p = path or default_batch_scorecard_jsonl()
    if not p.is_file():
        return []
    raw = p.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return []
    lines = raw.splitlines()
    tail = lines[-limit:] if len(lines) > limit else lines
    out: list[dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.reverse()
    return out


def format_batch_scorecard_for_prompt(
    *,
    limit: int = 15,
    max_chars: int = 12000,
    path: Path | None = None,
) -> str:
    """
    Markdown block for Anna context injection: recent parallel batch lines (timing, counts, workers).

    These are **operational** facts from ``batch_scorecard.jsonl``, not per-trade Referee outcomes.
    Empty string if no file or no rows.
    """
    rows = read_batch_scorecard_recent(limit, path=path)
    if not rows:
        return ""
    lines_out: list[str] = [
        "### Pattern game batch scorecard (recent parallel runs — timing and counts only)\n",
        "Referee trade/session metrics live in replay results JSON, not this log.\n\n",
    ]
    for i, r in enumerate(rows, 1):
        ts = r.get("ended_at_utc") or r.get("started_at_utc") or "?"
        st = r.get("status") or "?"
        job = r.get("job_id") or "?"
        job_s = job if len(str(job)) <= 16 else (str(job)[:14] + "…")
        err = r.get("error")
        err_s = ""
        if err:
            es = str(err).replace("\n", " ")
            err_s = f"\n   - error: {es[:480]}{'…' if len(es) > 480 else ''}"
        lines_out.append(
            f"{i}. **{ts}** · status={st} · job_id={job_s}\n"
            f"   - processed {r.get('total_processed')}/{r.get('total_scenarios')} scenarios · "
            f"ok={r.get('ok_count')} failed={r.get('failed_count')} · workers={r.get('workers_used')} · "
            f"duration_sec={r.get('duration_sec')}{err_s}\n"
        )
    body = "".join(lines_out)
    if len(body) > max_chars:
        body = body[: max_chars - 24] + "\n… [truncated]\n"
    return body


def build_batch_timing_payload(
    *,
    started_at_utc: str,
    ended_at_utc: str,
    start_unix: float,
    end_unix: float,
    total_scenarios: int,
    processed_count: int,
) -> dict[str, Any]:
    """Embedded in API responses for the UI and scripts."""
    duration_sec = max(0.0, round(end_unix - start_unix, 3))
    return {
        "started_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "duration_sec": duration_sec,
        "total_scenarios": total_scenarios,
        "total_processed": processed_count,
    }


def record_parallel_batch_finished(
    *,
    job_id: str,
    started_at_utc: str,
    start_unix: float,
    total_scenarios: int,
    workers_used: int,
    results: list[dict[str, Any]] | None,
    session_log_batch_dir: str | None,
    error: str | None,
    source: str = "pattern_game_web_ui",
    path: Path | None = None,
) -> dict[str, Any]:
    """
    Append one scorecard line and return ``batch_timing`` for API payloads.

    On ``error``, ``results`` may be None; ``total_processed`` is 0.
    """
    end_unix = time.time()
    ended_at_utc = utc_timestamp_iso()
    timing = build_batch_timing_payload(
        started_at_utc=started_at_utc,
        ended_at_utc=ended_at_utc,
        start_unix=start_unix,
        end_unix=end_unix,
        total_scenarios=total_scenarios,
        processed_count=len(results or []),
    )

    if error:
        record: dict[str, Any] = {
            "schema": SCHEMA_V1,
            "job_id": job_id,
            "source": source,
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at_utc,
            "duration_sec": timing["duration_sec"],
            "total_scenarios": total_scenarios,
            "total_processed": 0,
            "ok_count": 0,
            "failed_count": total_scenarios,
            "note": "Batch failed before or during parallel run; processed count is 0.",
            "workers_used": workers_used,
            "status": "error",
            "error": error[:4000],
        }
    else:
        res = results or []
        ok_n = sum(1 for r in res if r.get("ok"))
        record = {
            "schema": SCHEMA_V1,
            "job_id": job_id,
            "source": source,
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at_utc,
            "duration_sec": timing["duration_sec"],
            "total_scenarios": total_scenarios,
            "total_processed": len(res),
            "ok_count": ok_n,
            "failed_count": len(res) - ok_n,
            "workers_used": workers_used,
            "status": "done",
            "session_log_batch_dir": session_log_batch_dir,
        }

    append_batch_scorecard_line(record, path=path)
    return timing
