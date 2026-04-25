"""
Scorecard drill-down helpers: resolve batch by ``job_id``, list scenario artifacts, CSV builders.

Used by ``web_app.py`` only; reads ``batch_scorecard.jsonl`` and on-disk batch session folders.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.groundhog_memory import groundhog_auto_merge_enabled
from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl
from renaissance_v4.game_theory.scenario_contract import referee_session_outcome


def find_scorecard_entry_by_job_id(
    job_id: str,
    *,
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Return the **last** JSON line in the scorecard file matching ``job_id`` (newest wins)."""
    jid = str(job_id).strip()
    if not jid:
        return None
    p = path or default_batch_scorecard_jsonl()
    if not p.is_file():
        return None
    last: dict[str, Any] | None = None
    with p.open(encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(obj.get("job_id", "")) == jid:
                last = obj
    return last


def parse_batch_readme_table(batch_dir: Path) -> list[dict[str, Any]]:
    """
    Parse ``BATCH_README.md`` scenario table: scenario id, folder name, run_id.

    Falls back to empty list if missing or unparsable.
    """
    readme = Path(batch_dir) / "BATCH_README.md"
    if not readme.is_file():
        return []
    text = readme.read_text(encoding="utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    # Lines like: | `sid` | `folder` | `run_id` |
    pat = re.compile(r"^\|\s*`([^`]*)`\s*\|\s*`([^`]*)`\s*\|\s*`([^`]*)`\s*\|")
    for line in text.splitlines():
        m = pat.match(line.strip())
        if not m:
            continue
        sid = m.group(1)
        if sid.lower() in ("scenario", "----------"):
            continue
        rows.append(
            {
                "scenario_id": sid,
                "folder": m.group(2),
                "run_id": m.group(3),
            }
        )
    return rows


def _safe_child_dir(batch_dir: Path, folder_name: str) -> Path | None:
    base = batch_dir.resolve()
    if not base.is_dir():
        return None
    if ".." in folder_name or (folder_name and Path(folder_name).is_absolute()):
        return None
    child = (base / folder_name).resolve()
    try:
        child.relative_to(base)
    except ValueError:
        return None
    return child if child.is_dir() else None


def discover_scenarios_fallback(batch_dir: Path) -> list[dict[str, Any]]:
    """If BATCH_README is missing, infer scenario rows from subdirs containing ``run_record.json``."""
    out: list[dict[str, Any]] = []
    base = batch_dir.resolve()
    if not base.is_dir():
        return out
    for sub in sorted(base.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        rr = sub / "run_record.json"
        if not rr.is_file():
            continue
        try:
            raw = json.loads(rr.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rid = str(raw.get("run_id") or "")
        out.append(
            {
                "scenario_id": sub.name,
                "folder": sub.name,
                "run_id": rid,
            }
        )
    return out


def load_batch_parallel_results_v1(batch_dir: Path | str) -> dict[str, Any] | None:
    """
    Load ``batch_parallel_results_v1.json`` written alongside ``BATCH_README.md`` when parallel
    batches complete with session logging (see :mod:`renaissance_v4.game_theory.parallel_runner`).
    """
    p = Path(batch_dir).expanduser().resolve() / "batch_parallel_results_v1.json"
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict) or raw.get("schema") != "batch_parallel_results_v1":
        return None
    return raw


def load_run_record(batch_dir: Path, folder_name: str) -> dict[str, Any] | None:
    sub = _safe_child_dir(batch_dir, folder_name)
    if sub is None:
        return None
    rr = sub / "run_record.json"
    if not rr.is_file():
        return None
    try:
        return json.loads(rr.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def flatten_scenario_for_api(
    job_id: str,
    batch_dir: Path,
    row: dict[str, Any],
    *,
    run_record: dict[str, Any] | None,
) -> dict[str, Any]:
    """One scenario object for ``/api/batch-detail`` and CSV rows."""
    folder = row.get("folder") or ""
    sid = row.get("scenario_id") or ""
    sub = _safe_child_dir(batch_dir, str(folder))
    human_path = ""
    json_path = ""
    if sub:
        hp = sub / "HUMAN_READABLE.md"
        jp = sub / "run_record.json"
        if hp.is_file():
            human_path = str(hp.resolve())
        if jp.is_file():
            json_path = str(jp.resolve())

    ref = (run_record or {}).get("referee") if isinstance(run_record, dict) else None
    ref = ref if isinstance(ref, dict) else {}
    summ = run_record.get("summary") if isinstance(run_record, dict) else None
    if not isinstance(summ, dict):
        summ = {}
    ok_run = bool(run_record) and not (run_record or {}).get("error")
    rs_out = referee_session_outcome(ok_run, ref if ref else None)

    lme = (run_record or {}).get("learning_memory_evidence") if isinstance(run_record, dict) else None
    lme = lme if isinstance(lme, dict) else {}
    ol = lme.get("operator_labels") if isinstance(lme.get("operator_labels"), dict) else {}

    mem_applied = bool(lme.get("memory_applied"))
    gh_mode = str(lme.get("groundhog_mode") or "")
    lf = lme.get("learned_from") if isinstance(lme.get("learned_from"), dict) else {}

    da = (run_record or {}).get("decision_audit") if isinstance(run_record, dict) else None
    da = da if isinstance(da, dict) else {}
    mb = da.get("memory_bundle") if isinstance(da.get("memory_bundle"), dict) else {}
    keys_applied = mb.get("keys_applied")
    if isinstance(keys_applied, list):
        keys_str = ";".join(str(x) for x in keys_applied)
    else:
        keys_str = ""

    icq = (run_record or {}).get("indicator_context_quality") if isinstance(run_record, dict) else None
    icq = icq if isinstance(icq, dict) else {}
    icq_level = icq.get("level")

    return {
        "job_id": job_id,
        "scenario_id": sid,
        "folder": folder,
        "run_id": row.get("run_id") or (run_record or {}).get("run_id"),
        "manifest_path": (run_record or {}).get("manifest_path"),
        "ok": ok_run,
        "referee_session": rs_out,
        "wins": ref.get("wins"),
        "losses": ref.get("losses"),
        "trades": ref.get("trades"),
        "win_rate": ref.get("win_rate"),
        "cumulative_pnl": ref.get("cumulative_pnl"),
        "validation_checksum": ref.get("validation_checksum"),
        "human_report_path": human_path,
        "run_record_path": json_path,
        "memory_applied": mem_applied,
        "groundhog_mode": gh_mode,
        "groundhog_env_enabled": groundhog_auto_merge_enabled(),
        "memory_bundle_path": lf.get("bundle_path"),
        "memory_from_run_id": lf.get("bundle_from_run_id"),
        "memory_keys_applied": keys_str,
        "prior_run_id": (run_record or {}).get("prior_run_id"),
        "indicator_context_quality": icq_level,
        "operator_labels": ol,
        "learning_memory_evidence": lme if lme else None,
    }


def build_scenario_list_for_batch(job_id: str, session_log_batch_dir: str | None) -> tuple[Path | None, list[dict[str, Any]], str | None]:
    """
    Returns ``(batch_dir_or_none, flattened_scenarios, error_message)``.
    """
    if not session_log_batch_dir or not str(session_log_batch_dir).strip():
        return None, [], "No session_log_batch_dir on this scorecard line (session logs disabled or batch failed before logs)."
    batch_dir = Path(session_log_batch_dir).expanduser().resolve()
    if not batch_dir.is_dir():
        return batch_dir, [], f"Batch folder not found on disk: {batch_dir}"

    table = parse_batch_readme_table(batch_dir)
    if not table:
        table = discover_scenarios_fallback(batch_dir)

    flat: list[dict[str, Any]] = []
    for row in table:
        fn = row.get("folder") or ""
        rr = load_run_record(batch_dir, str(fn))
        flat.append(flatten_scenario_for_api(job_id, batch_dir, row, run_record=rr))

    return batch_dir, flat, None


_SCORECARD_CSV_FIELDS = [
    "job_id",
    "started_at_utc",
    "ended_at_utc",
    "duration_sec",
    "total_scenarios",
    "total_processed",
    "work_units_v1",
    "learning_status",
    "decision_windows_total",
    "bars_processed",
    "candidate_count",
    "selected_candidate_id",
    "winner_vs_control_delta",
    "memory_used",
    "memory_records_loaded",
    "groundhog_status",
    "recall_attempts",
    "recall_matches",
    "recall_bias_applied",
    "signal_bias_applied_count",
    "suppressed_modules_count",
    "trade_entries_total",
    "trade_exits_total",
    "batch_trades_count",
    "batch_trade_win_pct",
    "batch_trade_win_rate_n",
    "avg_trade_win_pct",
    "trade_win_rate_n",
    "expectancy_per_trade",
    "exit_efficiency",
    "win_loss_size_ratio",
    "batch_sessions_judged",
    "referee_win_pct",
    "run_ok_pct",
    "ok_count",
    "failed_count",
    "workers_used",
    "status",
    "session_log_batch_dir",
    "batch_run_classification_v1",
    "replay_decision_windows_sum",
    "operator_learning_status_line_v1",
    "learning_audit_v1",
    "student_learning_rows_appended",
    "student_retrieval_matches",
    "student_output_fingerprint",
    "shadow_student_enabled",
]


def _scorecard_csv_value(field: str, v: Any) -> str:
    if v is None:
        return ""
    if field == "memory_used":
        if isinstance(v, bool):
            return "yes" if v else "no"
        s = str(v).strip().lower()
        return "yes" if s in ("1", "true", "yes") else "no"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def scorecard_history_csv(entries: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_SCORECARD_CSV_FIELDS, extrasaction="ignore")
    w.writeheader()
    for e in entries:
        row = {k: _scorecard_csv_value(k, e.get(k)) for k in _SCORECARD_CSV_FIELDS}
        w.writerow(row)
    return buf.getvalue()


_BATCH_DETAIL_CSV_FIELDS = [
    "job_id",
    "scenario_id",
    "run_id",
    "manifest_path",
    "ok",
    "referee_session",
    "wins",
    "losses",
    "trades",
    "win_rate",
    "cumulative_pnl",
    "validation_checksum",
    "report_path",
    "memory_applied",
    "groundhog_enabled",
    "memory_bundle_path",
    "memory_from_run_id",
    "memory_keys_applied",
    "prior_run_id",
    "indicator_context_quality",
]


def read_scenario_artifact(
    job_id: str,
    scenario_id: str,
    kind: str,
) -> tuple[bytes | None, str | None, str | None]:
    """
    Read ``HUMAN_READABLE.md`` (kind ``human``) or ``run_record.json`` (kind ``json``).

    Returns ``(body_bytes, content_type, error_message)``.
    """
    if kind not in ("human", "json"):
        return None, None, "kind must be human or json"
    entry = find_scorecard_entry_by_job_id(job_id)
    if not entry:
        return None, None, "job_id not found in scorecard log"
    _bd, scenarios, err = build_scenario_list_for_batch(job_id, entry.get("session_log_batch_dir"))
    if err and not scenarios:
        return None, None, err or "no scenarios"
    for s in scenarios:
        if str(s.get("scenario_id")) != str(scenario_id):
            continue
        rel = "human_report_path" if kind == "human" else "run_record_path"
        p_raw = s.get(rel) or ""
        if not p_raw:
            return None, None, f"missing {rel} for scenario"
        p = Path(p_raw).resolve()
        batch_root = Path(entry.get("session_log_batch_dir") or "").expanduser().resolve()
        try:
            p.relative_to(batch_root)
        except ValueError:
            return None, None, "path escapes batch folder"
        if not p.is_file():
            return None, None, f"file not found: {p}"
        try:
            data = p.read_bytes()
        except OSError as e:
            return None, None, str(e)
        ct = "text/markdown; charset=utf-8" if kind == "human" else "application/json; charset=utf-8"
        return data, ct, None
    return None, None, "scenario_id not found in batch"


def batch_detail_csv_rows(job_id: str, scenarios: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_BATCH_DETAIL_CSV_FIELDS, extrasaction="ignore")
    w.writeheader()
    for s in scenarios:
        w.writerow(
            {
                "job_id": job_id,
                "scenario_id": s.get("scenario_id"),
                "run_id": s.get("run_id"),
                "manifest_path": s.get("manifest_path"),
                "ok": s.get("ok"),
                "referee_session": s.get("referee_session"),
                "wins": s.get("wins"),
                "losses": s.get("losses"),
                "trades": s.get("trades"),
                "win_rate": s.get("win_rate"),
                "cumulative_pnl": s.get("cumulative_pnl"),
                "validation_checksum": s.get("validation_checksum"),
                "report_path": s.get("human_report_path"),
                "memory_applied": s.get("memory_applied"),
                "groundhog_enabled": (s.get("groundhog_mode") == "active"),
                "memory_bundle_path": s.get("memory_bundle_path"),
                "memory_from_run_id": s.get("memory_from_run_id"),
                "memory_keys_applied": s.get("memory_keys_applied"),
                "prior_run_id": s.get("prior_run_id"),
                "indicator_context_quality": s.get("indicator_context_quality"),
            }
        )
    return buf.getvalue()
