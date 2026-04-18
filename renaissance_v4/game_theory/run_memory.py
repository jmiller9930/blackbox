"""
run_memory.py

Append-only JSONL memory for replay runs: hypothesis + indicator context + Referee metrics.

This does not change deterministic scores; it guarantees each run can leave a durable record
for the next swing (operator, Anna, or a future outer loop).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "renaissance_v4_run_memory_v1"


def build_decision_audit(*, prior_run_id: str | None) -> dict[str, Any]:
    """
    Explicit, machine-generated audit: what inputs actually drove execution vs what was metadata only.

    Deterministic replay never loads prior run_memory rows to change trade logic; this block states that.
    """
    pid = (prior_run_id or "").strip() or None
    return {
        "prior_outcomes_or_parameters_loaded_into_replay_engine": False,
        "prior_run_id_provided": pid,
        "human_readable_summary": (
            "Trade decisions in this run came only from: (1) the manifest JSON on disk, "
            "(2) optional CLI ATR overrides, (3) bar data read forward in time by the Referee. "
            "No code path reads run_memory JSONL or prior HUMAN_READABLE logs to alter signals, "
            "fusion, risk tiers, or execution during the replay."
        ),
        "if_prior_run_id_is_set": (
            f"You supplied prior_run_id={pid!r} as an audit link between experiments. "
            "That ID is stored for your review and diffing; it was **not** loaded as simulation input."
        )
        if pid
        else "No prior_run_id was supplied; this run is not linked to an earlier run_id in metadata.",
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_hypothesis_bundle(
    scenario: dict[str, Any] | None,
    *,
    hypothesis_cli: str | None = None,
    indicator_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Prefer explicit CLI args; else read ``agent_explanation.hypothesis`` and
    ``agent_explanation.indicator_context`` from a scenario dict.
    """
    hyp = (hypothesis_cli or "").strip()
    ctx: dict[str, Any] = dict(indicator_context or {})
    if scenario:
        ae = scenario.get("agent_explanation")
        if isinstance(ae, dict):
            if not hyp:
                h2 = ae.get("hypothesis")
                if isinstance(h2, str) and h2.strip():
                    hyp = h2.strip()
            if not ctx and isinstance(ae.get("indicator_context"), dict):
                ctx = dict(ae["indicator_context"])
    return {"hypothesis": hyp or None, "indicator_context": ctx or None}


def build_run_memory_record(
    *,
    source: str,
    manifest_path: str,
    json_summary_row: dict[str, Any] | None,
    scenario: dict[str, Any] | None = None,
    hypothesis_cli: str | None = None,
    indicator_context: dict[str, Any] | None = None,
    prior_run_id: str | None = None,
    atr_stop_mult: float | None = None,
    atr_target_mult: float | None = None,
    parallel_error: str | None = None,
) -> dict[str, Any]:
    """One JSON object suitable for a single JSONL line."""
    mp = Path(manifest_path).expanduser().resolve()
    bundle = extract_hypothesis_bundle(
        scenario,
        hypothesis_cli=hypothesis_cli,
        indicator_context=indicator_context,
    )
    run_id = str(uuid.uuid4())
    rec: dict[str, Any] = {
        "schema": SCHEMA,
        "run_id": run_id,
        "utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "manifest_path": str(mp),
        "manifest_sha256": sha256_file(mp) if mp.is_file() else None,
        "hypothesis": bundle["hypothesis"],
        "indicator_context": bundle["indicator_context"],
        "prior_run_id": prior_run_id,
        "atr_stop_mult": atr_stop_mult,
        "atr_target_mult": atr_target_mult,
        "referee": json_summary_row,
        "decision_audit": build_decision_audit(prior_run_id=prior_run_id),
        "post_mortem": {
            "why": None,
            "next_hypothesis": None,
            "note": "Fill after review; optional Anna/human — does not affect Referee.",
        },
    }
    if parallel_error:
        rec["error"] = parallel_error
    return rec


def append_run_memory(path: Path | str, record: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_run_memory_tail(path: Path | str, n: int = 20) -> list[dict[str, Any]]:
    """Last n JSON objects from JSONL (best-effort; loads whole file if small)."""
    p = Path(path)
    if not p.is_file():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    tail = lines[-n:] if n > 0 else lines
    out: list[dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
