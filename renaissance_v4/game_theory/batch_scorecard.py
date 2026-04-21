"""
Append-only **batch scorecard** for parallel pattern-game runs: UTC start/end, duration, totals,
and **percentage scores**.

- **run_ok_pct** — share of scenarios whose worker finished without exception (``ok`` true).
- **referee_win_pct** — share of **WIN** vs (WIN+LOSS) among completed replays (paper session;
  excludes ERROR rows from denominator).
- **avg_trade_win_pct** — mean of per-scenario **trade** win rates (``summary.win_rate`` as
  winning trades ÷ total trades), across scenarios that returned a rate; **not** the same as
  session WIN or run_ok (see web UI legend).

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

from renaissance_v4.game_theory.learning_run_audit import (
    aggregate_batch_learning_run_audit_v1,
    build_memory_context_impact_audit_v1,
    compute_scorecard_learning_rollups_v1,
)
from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl

_APPEND_LOCK = threading.Lock()
SCHEMA_V1 = "pattern_game_batch_scorecard_v1"


def compute_batch_score_percentages(results: list[dict[str, Any]] | None) -> dict[str, Any]:
    """
    Aggregates for one parallel batch.

    ``referee_win_pct`` is None when no scenario returned WIN or LOSS (e.g. all failed before replay).
    ``avg_trade_win_pct`` is None when no completed scenario had ``summary.win_rate``.
    """
    if not results:
        return {
            "run_ok_pct": None,
            "referee_win_pct": None,
            "referee_wins": 0,
            "referee_losses": 0,
            "avg_trade_win_pct": None,
            "trade_win_rate_n": 0,
        }
    n = len(results)
    ok_n = sum(1 for r in results if r.get("ok"))
    run_ok_pct = round(100.0 * ok_n / n, 1) if n else None
    wins = 0
    losses = 0
    for r in results:
        if not r.get("ok"):
            continue
        rs = r.get("referee_session")
        if rs == "WIN":
            wins += 1
        elif rs == "LOSS":
            losses += 1
    judged = wins + losses
    referee_win_pct = round(100.0 * wins / judged, 1) if judged else None
    tw_vals: list[float] = []
    for r in results:
        if not r.get("ok"):
            continue
        summ = r.get("summary")
        if not isinstance(summ, dict):
            continue
        tr = summ.get("trades")
        try:
            tr_n = int(tr) if tr is not None else 0
        except (TypeError, ValueError):
            tr_n = 0
        if tr_n <= 0:
            continue
        wr = summ.get("win_rate")
        if wr is None:
            continue
        try:
            tw_vals.append(float(wr))
        except (TypeError, ValueError):
            continue
    trade_win_rate_n = len(tw_vals)
    avg_trade_win_pct = round(100.0 * (sum(tw_vals) / trade_win_rate_n), 1) if tw_vals else None
    return {
        "run_ok_pct": run_ok_pct,
        "referee_win_pct": referee_win_pct,
        "referee_wins": wins,
        "referee_losses": losses,
        "avg_trade_win_pct": avg_trade_win_pct,
        "trade_win_rate_n": trade_win_rate_n,
    }


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


def remove_batch_scorecard_line_by_job_id(
    job_id: str,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """
    Remove **all** JSONL lines whose ``job_id`` matches (append-only file may duplicate job_id).

    Returns ``{"ok": True, "removed": n, "path": ...}``. Does **not** touch Groundhog bundles,
    engine learning, or Student Proctor store (D14-6 run-history only).
    """
    jid = str(job_id).strip()
    if not jid:
        return {"ok": False, "error": "job_id required", "removed": 0}
    p = (path or default_batch_scorecard_jsonl()).expanduser().resolve()
    if not p.is_file():
        return {"ok": True, "removed": 0, "path": str(p), "note": "file missing"}
    raw = p.read_text(encoding="utf-8", errors="replace")
    if not raw.strip():
        return {"ok": True, "removed": 0, "path": str(p)}
    lines_kept: list[str] = []
    removed = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            lines_kept.append(line)
            continue
        if str(obj.get("job_id", "")) == jid:
            removed += 1
            continue
        lines_kept.append(line)
    tmp = p.with_suffix(p.suffix + ".tmp_filter")
    tmp.write_text("\n".join(lines_kept) + ("\n" if lines_kept else ""), encoding="utf-8")
    with _APPEND_LOCK:
        tmp.replace(p)
    return {"ok": True, "removed": removed, "path": str(p.resolve())}


def truncate_batch_scorecard_jsonl(*, path: Path | None = None) -> Path:
    """
    Truncate the scorecard JSONL to empty (all batch rows removed).

    **Scope:** only this file (default ``batch_scorecard.jsonl`` under memory root).
    Replay learning, Groundhog bundles, context-signature memory, experience/run logs,
    and retrospective are separate paths and are **not** modified here.
    """
    p = (path or default_batch_scorecard_jsonl()).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp_trunc")
    tmp.write_text("", encoding="utf-8")
    tmp.replace(p)
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
        "### Pattern Machine learning batch scorecard (recent parallel runs — timing and counts only)\n",
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
        ro = r.get("run_ok_pct")
        rw = r.get("referee_win_pct")
        atw = r.get("avg_trade_win_pct")
        pct_s = ""
        if ro is not None or rw is not None or atw is not None:
            parts = []
            if ro is not None:
                parts.append(f"run_ok={ro}%")
            if rw is not None:
                parts.append(f"session_WIN={rw}%")
            if atw is not None:
                parts.append(f"avg_trade_win={atw}%")
            pct_s = " · " + " · ".join(parts)
        cls = r.get("batch_run_classification_v1")
        cls_s = f" · learning_batch={cls}" if cls else ""
        rsum = r.get("replay_decision_windows_sum")
        depth_s = f" · replay_decision_windows_sum={rsum}" if rsum is not None else ""
        ol = r.get("operator_learning_status_line_v1")
        learn_s = ""
        if isinstance(ol, str) and ol.strip():
            ls = ol.strip().replace("\n", " ")
            learn_s = f"\n   - learning: {ls[:420]}{'…' if len(ls) > 420 else ''}"
        lines_out.append(
            f"{i}. **{ts}** · status={st} · job_id={job_s}\n"
            f"   - processed {r.get('total_processed')}/{r.get('total_scenarios')} scenario rows · "
            f"ok={r.get('ok_count')} failed={r.get('failed_count')}{pct_s} · workers={r.get('workers_used')} · "
            f"duration_sec={r.get('duration_sec')}{cls_s}{depth_s}{err_s}{learn_s}\n"
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
    operator_batch_audit: dict[str, Any] | None = None,
    student_seam_observability_v1: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Append one scorecard line and return ``batch_timing`` for API payloads.

    On ``error``, ``results`` may be None; ``total_processed`` is 0.
    """
    end_unix = time.time()
    ended_at_utc = utc_timestamp_iso()
    n_result_rows = len(results or [])
    timing = build_batch_timing_payload(
        started_at_utc=started_at_utc,
        ended_at_utc=ended_at_utc,
        start_unix=start_unix,
        end_unix=end_unix,
        total_scenarios=total_scenarios,
        processed_count=n_result_rows,
    )

    learning_batch: dict[str, Any] | None = None

    if error:
        pct_fields: dict[str, Any] = {
            "run_ok_pct": 0.0,
            "referee_win_pct": None,
            "referee_wins": 0,
            "referee_losses": 0,
            "avg_trade_win_pct": None,
            "trade_win_rate_n": 0,
        }
        record = {
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
            **pct_fields,
        }
        if operator_batch_audit:
            record["operator_batch_audit"] = operator_batch_audit
    else:
        res = results or []
        ok_n = sum(1 for r in res if r.get("ok"))
        pct_fields = compute_batch_score_percentages(res)
        learning_batch = aggregate_batch_learning_run_audit_v1(res)
        oba_m = dict(operator_batch_audit or {})
        if not oba_m.get("replay_data_audit"):
            for r in res:
                if r.get("ok") and r.get("replay_data_audit") is not None:
                    oba_m["replay_data_audit"] = r.get("replay_data_audit")
                    break
        scorecard_learning = compute_scorecard_learning_rollups_v1(res, operator_batch_audit=oba_m)
        mem_impact = build_memory_context_impact_audit_v1(res, operator_batch_audit=oba_m)
        batch_depth = {
            "parallel_scenarios_completed": len(res),
            "replay_bars_processed_sum": learning_batch.get("replay_bars_processed_sum"),
            "replay_decision_windows_sum": learning_batch.get("replay_decision_windows_sum"),
            "context_candidate_replays_sum": learning_batch.get("context_candidate_replays_sum"),
            "total_processed_is_scenario_rows": len(res),
            "note": (
                "total_processed counts one worker result row per scenario submitted to the pool "
                "(not inner-bar steps). replay_*_sum aggregates replay depth across successful rows; "
                "context_candidate_replays_sum counts control+candidate replays when candidate search ran."
            ),
        }
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
            "learning_batch_audit_v1": learning_batch,
            "batch_depth_v1": batch_depth,
            "batch_run_classification_v1": learning_batch.get("batch_run_classification_v1"),
            "operator_learning_status_line_v1": learning_batch.get("operator_learning_status_line_v1"),
            "replay_decision_windows_sum": learning_batch.get("replay_decision_windows_sum"),
            **pct_fields,
        }
        record.update(
            {k: v for k, v in scorecard_learning.items() if k != "operator_learning_table_summary_v1"}
        )
        record["operator_learning_table_summary_v1"] = scorecard_learning.get(
            "operator_learning_table_summary_v1"
        )
        if pct_fields.get("referee_wins") is not None or pct_fields.get("referee_losses") is not None:
            record["batch_sessions_judged"] = int(pct_fields.get("referee_wins") or 0) + int(
                pct_fields.get("referee_losses") or 0
            )
        if operator_batch_audit:
            record["operator_batch_audit"] = operator_batch_audit
        record["memory_context_impact_audit_v1"] = mem_impact
        seam_obs = student_seam_observability_v1 or {}
        for fld in (
            "student_learning_rows_appended",
            "student_retrieval_matches",
            "student_output_fingerprint",
            "shadow_student_enabled",
        ):
            if fld in seam_obs:
                record[fld] = seam_obs[fld]

    append_batch_scorecard_line(record, path=path)
    out = {**timing, **pct_fields}
    out["job_id"] = job_id
    if learning_batch is not None:
        out["learning_batch_audit_v1"] = learning_batch
        out["batch_depth_v1"] = record.get("batch_depth_v1")
        out["batch_run_classification_v1"] = learning_batch.get("batch_run_classification_v1")
        out["operator_learning_status_line_v1"] = learning_batch.get("operator_learning_status_line_v1")
        scl = {k: v for k, v in record.items() if k != "operator_learning_table_summary_v1"}
        for k, v in scl.items():
            if k in (
                "schema",
                "job_id",
                "source",
                "started_at_utc",
                "ended_at_utc",
                "duration_sec",
                "total_scenarios",
                "total_processed",
                "ok_count",
                "failed_count",
                "workers_used",
                "status",
                "session_log_batch_dir",
                "error",
                "note",
                "learning_batch_audit_v1",
                "batch_depth_v1",
                "operator_batch_audit",
            ):
                continue
            if v is not None:
                out[k] = v
        ots = record.get("operator_learning_table_summary_v1")
        if ots is not None:
            out["operator_learning_table_summary_v1"] = ots
    return out
