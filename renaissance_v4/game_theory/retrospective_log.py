"""
Append-only **retrospective log** — “what we saw / what to try next” between runs.

Not Referee scores. Operators (or tooling) append JSON lines; Anna can load the tail via
``ANNA_CONTEXT_PROFILE=...,retrospective`` (see ``scripts/agent_context_bundle.py``).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.memory_paths import default_retrospective_log_jsonl

_APPEND_LOCK = threading.Lock()
SCHEMA_V1 = "pattern_game_retrospective_v1"


def utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_retrospective_line(
    record: dict[str, Any],
    *,
    path: Path | None = None,
) -> Path:
    """Append one JSON line; return resolved path."""
    p = path or default_retrospective_log_jsonl()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _APPEND_LOCK:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return p.resolve()


def append_retrospective(
    *,
    what_observed: str,
    what_to_try_next: str,
    run_ref: str | None = None,
    source: str = "operator",
    path: Path | None = None,
) -> Path:
    """Convenience wrapper with schema v1."""
    return append_retrospective_line(
        {
            "schema": SCHEMA_V1,
            "utc": utc_iso(),
            "source": source,
            "run_ref": run_ref,
            "what_observed": (what_observed or "")[:12000],
            "what_to_try_next": (what_to_try_next or "")[:12000],
        },
        path=path,
    )


def read_retrospective_recent(
    limit: int = 25,
    *,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Newest first."""
    p = path or default_retrospective_log_jsonl()
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


def format_retrospective_for_prompt(
    *,
    limit: int = 15,
    max_chars: int = 12000,
    path: Path | None = None,
) -> str:
    """Markdown block for Anna context injection."""
    rows = read_retrospective_recent(limit, path=path)
    if not rows:
        return ""
    lines_out: list[str] = [
        "### Retrospective log (recent entries — learn from prior runs; not ground truth scores)\n",
    ]
    for i, r in enumerate(rows, 1):
        ts = r.get("utc") or "?"
        obs = (r.get("what_observed") or "").strip() or "—"
        nxt = (r.get("what_to_try_next") or "").strip() or "—"
        ref = r.get("run_ref")
        ref_s = f" (run_ref: {ref})" if ref else ""
        lines_out.append(f"{i}. **{ts}**{ref_s}\n   - Observed: {obs}\n   - Try next: {nxt}\n")
    body = "\n".join(lines_out)
    if len(body) > max_chars:
        body = body[: max_chars - 20] + "\n… [truncated]\n"
    return body


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Append a retrospective line (JSONL).")
    ap.add_argument("--observed", required=True, help="What you saw / what happened")
    ap.add_argument("--next", required=True, dest="try_next", help="What to try on the next experiment")
    ap.add_argument("--run-ref", default=None, help="Optional job_id or batch folder path")
    ap.add_argument("--source", default="operator", help="Source label (default: operator)")
    args = ap.parse_args()
    p = append_retrospective(
        what_observed=args.observed,
        what_to_try_next=args.try_next,
        run_ref=args.run_ref,
        source=args.source,
    )
    print(f"Appended to {p}")


if __name__ == "__main__":
    main()
