"""
PLAYGROUND / DEBUG TOOL ONLY
NOT FOR RUNTIME USE
NOT AN EXECUTION PATH

Sandbox-only orchestration of the DATA remediation pipeline (Visibility Layer 1).
Thin CLI: calls learning_core stages only — no business logic here.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

_RUNTIME = Path(__file__).resolve().parents[1]
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from learning_core.data_issue_detection import build_issue_suggestion, detect_infra_issues
from learning_core.remediation_execution_simulator import simulate_and_record_remediation_execution
from learning_core.remediation_pattern_registry import register_pattern_from_outcome_analysis
from learning_core.remediation_validation import get_candidate, ingest_remediation_candidate, open_validation_sandbox, run_validation
from learning_core.validation_outcome_analysis import analyze_and_persist


def _assert_not_production_sqlite(path: Path) -> None:
    """Reject production runtime DB path (same rule as sandbox open)."""
    from _paths import default_sqlite_path

    try:
        if path.resolve() == default_sqlite_path().resolve():
            print("FAIL: path must not be production runtime SQLite (BLACKBOX_SQLITE_PATH).", file=sys.stderr)
            raise SystemExit(2)
    except SystemExit:
        raise
    except Exception:
        pass


def _ensure_issue_db_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS system_events (
          id TEXT PRIMARY KEY,
          source TEXT,
          event_type TEXT,
          severity TEXT,
          payload TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY,
          title TEXT,
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()


def _seed_demo_issue_db(conn: sqlite3.Connection) -> None:
    _ensure_issue_db_schema(conn)
    for i in range(3):
        conn.execute(
            """
            INSERT INTO system_events (id, source, event_type, severity, payload, created_at)
            VALUES (?, 'playground_seed', 'runtime', 'error', ?, datetime('now'))
            """,
            (str(uuid.uuid4()), f"seed_error_{i}"),
        )
    # Do not seed `tasks` rows; a matching market snapshot row would require UTC-aware
    # timestamps to satisfy detect_infra_issues age math — empty tasks yields "no snapshot" issue.
    conn.commit()


def _issue_dict_from_candidate(cand: Any) -> dict[str, Any]:
    ev = list(cand.evidence or [])
    return {
        "issue_id": str(uuid.uuid4()),
        "category": "system",
        "severity": "medium",
        "confidence": 0.7,
        "timestamp": cand.created_at,
        "supporting_evidence": ev,
        "message": str(cand.description or "replay"),
    }


def _stage(name: str, status: str, summary: str) -> dict[str, Any]:
    return {"name": name, "status": status, "summary": summary}


def _emit_stage(label: str, status: str, summary: str, *, quiet: bool) -> None:
    if quiet:
        return
    print(f"==== STAGE: {label} ====")
    print(f"status: {status}")
    print(f"summary: {summary}")
    print("")


def _print_disclaimer(*, stream=sys.stdout) -> None:
    print("", file=stream)
    print("THIS RUN IS SANDBOX ONLY", file=stream)
    print("NOT APPROVAL", file=stream)
    print("NOT EXECUTION PERMISSION", file=stream)
    print("", file=stream)


def run_data_pipeline(
    *,
    sandbox_db: Path,
    issue_db: Path | None,
    replay_remediation_id: str | None,
    seed_demo: bool,
    step_mode: bool,
    quiet: bool = False,
) -> dict[str, Any]:
    _assert_not_production_sqlite(sandbox_db)
    if issue_db is not None:
        _assert_not_production_sqlite(issue_db)

    sandbox_conn = open_validation_sandbox(sandbox_db)
    stages: list[dict[str, Any]] = []
    execution_state: dict[str, Any] = {"execution_sensitive": False}

    issue_db_conn: sqlite3.Connection | None = None
    issue: dict[str, Any] | None = None
    remediation_id: str | None = None
    validation_run_id: str | None = None
    analysis_id: str | None = None
    pattern_id: str | None = None

    def pause() -> None:
        if step_mode and not quiet:
            input("[step] Press Enter to continue...")

    # --- DETECT ---
    if replay_remediation_id:
        cand = get_candidate(sandbox_conn, replay_remediation_id)
        if cand is None:
            st = _stage("DETECT", "fail", f"remediation_id not found: {replay_remediation_id}")
            stages.append(st)
            _emit_stage("DETECT", st["status"], st["summary"], quiet=quiet)
            pause()
            return {"stages": stages, "ok": False}
        issue = _issue_dict_from_candidate(cand)
        remediation_id = replay_remediation_id
        st = _stage("DETECT", "blocked", "replay mode — detection skipped")
        stages.append(st)
        _emit_stage("DETECT", st["status"], st["summary"], quiet=quiet)
    else:
        if seed_demo:
            idb = sandbox_db.parent / f".playground_issue_{uuid.uuid4().hex[:8]}.db"
            issue_db_conn = sqlite3.connect(str(idb))
            _seed_demo_issue_db(issue_db_conn)
        elif issue_db is not None:
            issue_db_conn = sqlite3.connect(str(issue_db))
            _ensure_issue_db_schema(issue_db_conn)
        else:
            st = _stage("DETECT", "fail", "provide --issue-db, --seed-demo, or --replay")
            stages.append(st)
            _emit_stage("DETECT", st["status"], st["summary"], quiet=quiet)
            pause()
            return {"stages": stages, "ok": False}

        assert issue_db_conn is not None
        issues = detect_infra_issues(issue_db_conn)
        if not issues:
            st = _stage("DETECT", "fail", "no issues detected — use --seed-demo or populate issue DB")
            stages.append(st)
            _emit_stage("DETECT", st["status"], st["summary"], quiet=quiet)
            issue_db_conn.close()
            pause()
            return {"stages": stages, "ok": False}
        issue = issues[0]
        st = _stage("DETECT", "pass", f"found issue {issue.get('issue_id')}")
        stages.append(st)
        _emit_stage("DETECT", st["status"], st["summary"], quiet=quiet)
    pause()

    # --- SUGGEST ---
    assert issue is not None
    suggestion = build_issue_suggestion(issue, execution_state=execution_state)
    st = _stage("SUGGEST", "pass", "suggestion artifact built")
    stages.append(st)
    _emit_stage("SUGGEST", st["status"], st["summary"], quiet=quiet)
    pause()

    # --- INGEST ---
    if replay_remediation_id:
        assert remediation_id is not None
        st = _stage("INGEST", "blocked", f"replay — using existing remediation {remediation_id}")
        stages.append(st)
        _emit_stage("INGEST", st["status"], st["summary"], quiet=quiet)
    else:
        try:
            remediation_id = ingest_remediation_candidate(
                sandbox_conn,
                source_type="deterministic",
                description=str(issue.get("message") or "playground"),
                proposed_action=str(suggestion.get("suggested_fix") or "").strip(),
                supporting_evidence=list(issue.get("supporting_evidence") or ["playground"]),
                source_metadata={"playground": True},
                related_issue_id=str(issue.get("issue_id") or "") or None,
            )
            st = _stage("INGEST", "pass", f"remediation_id={remediation_id}")
            stages.append(st)
            _emit_stage("INGEST", st["status"], st["summary"], quiet=quiet)
        except ValueError as exc:
            st = _stage("INGEST", "fail", str(exc))
            stages.append(st)
            _emit_stage("INGEST", st["status"], st["summary"], quiet=quiet)
            if issue_db_conn:
                issue_db_conn.close()
            pause()
            return {"stages": stages, "ok": False}
    assert remediation_id is not None
    pause()

    # --- VALIDATE ---
    before_state = {"error_count": 2, "metric_score": 1.0}
    after_state = {"error_count": 0, "metric_score": 1.1, "regression_detected": False, "stable_window": True}
    vr = run_validation(
        sandbox_conn,
        remediation_id=remediation_id,
        before_state=before_state,
        after_state=after_state,
    )
    validation_run_id = str(vr["run_id"])
    vst = "pass" if vr.get("result") == "pass" else "fail"
    st = _stage("VALIDATE", vst, f"run_id={validation_run_id} result={vr.get('result')}")
    stages.append(st)
    _emit_stage("VALIDATE", st["status"], st["summary"], quiet=quiet)
    pause()

    # --- ANALYZE ---
    an = analyze_and_persist(sandbox_conn, validation_run_id)
    analysis_id = str(an["analysis_id"])
    st = _stage("ANALYZE", "pass", f"analysis_id={analysis_id}")
    stages.append(st)
    _emit_stage("ANALYZE", st["status"], st["summary"], quiet=quiet)
    pause()

    # --- PATTERN ---
    try:
        pattern_id = register_pattern_from_outcome_analysis(sandbox_conn, analysis_id)
        st = _stage("PATTERN", "pass", f"pattern_id={pattern_id}")
        stages.append(st)
        _emit_stage("PATTERN", st["status"], st["summary"], quiet=quiet)
    except sqlite3.IntegrityError:
        row = sandbox_conn.execute(
            """
            SELECT pattern_id FROM remediation_patterns
            WHERE source_remediation_id = ?
            ORDER BY datetime(created_at) DESC LIMIT 1
            """,
            (remediation_id,),
        ).fetchone()
        if row:
            pattern_id = str(row[0])
            st = _stage("PATTERN", "blocked", f"register skipped (duplicate); using {pattern_id}")
            stages.append(st)
            _emit_stage("PATTERN", st["status"], st["summary"], quiet=quiet)
        else:
            st = _stage("PATTERN", "fail", "integrity error without existing pattern")
            stages.append(st)
            _emit_stage("PATTERN", st["status"], st["summary"], quiet=quiet)
            if issue_db_conn:
                issue_db_conn.close()
            pause()
            return {"stages": stages, "ok": False}
    except Exception as exc:
        st = _stage("PATTERN", "fail", str(exc))
        stages.append(st)
        _emit_stage("PATTERN", st["status"], st["summary"], quiet=quiet)
        if issue_db_conn:
            issue_db_conn.close()
        pause()
        return {"stages": stages, "ok": False}
    assert pattern_id is not None
    pause()

    # --- SIMULATE ---
    sim = simulate_and_record_remediation_execution(
        sandbox_conn,
        pattern_id=pattern_id,
        remediation_id=remediation_id,
        validation_context={"synthetic_apply_succeeds": True, "synthetic_rollback_failure": False},
    )
    sm = "pass" if sim.get("result") == "success" else "fail"
    st = _stage("SIMULATE", sm, f"execution_simulation_id={sim.get('execution_simulation_id')}")
    stages.append(st)
    _emit_stage("SIMULATE", st["status"], st["summary"], quiet=quiet)

    if issue_db_conn:
        issue_db_conn.close()

    pause()
    return {
        "stages": stages,
        "ok": True,
        "remediation_id": remediation_id,
        "pattern_id": pattern_id,
        "simulation": sim,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sandbox-only DATA pipeline playground (Layer 1).")
    parser.add_argument("--sandbox-db", type=Path, required=True, help="Sandbox SQLite path (required; not production).")
    parser.add_argument("--issue-db", type=Path, default=None, help="Non-production DB with system_events/tasks for DETECT.")
    parser.add_argument("--replay", type=str, default=None, metavar="REMEDIATION_ID", help="Skip DETECT; use existing sandbox remediation.")
    parser.add_argument("--seed-demo", action="store_true", help="Create a temporary issue DB with deterministic seed data.")
    parser.add_argument("--step", action="store_true", help="Pause after each stage.")
    parser.add_argument("--json", action="store_true", dest="json_out", help="Emit full structured result to stdout.")
    args = parser.parse_args()

    if args.replay and (args.issue_db or args.seed_demo):
        print("FAIL: --replay is mutually exclusive with --issue-db and --seed-demo.", file=sys.stderr)
        raise SystemExit(2)

    if not args.replay and not args.seed_demo and args.issue_db is None:
        print("FAIL: provide --issue-db, --seed-demo, or --replay.", file=sys.stderr)
        raise SystemExit(2)

    quiet = bool(args.json_out)
    result = run_data_pipeline(
        sandbox_db=args.sandbox_db,
        issue_db=args.issue_db,
        replay_remediation_id=args.replay,
        seed_demo=bool(args.seed_demo),
        step_mode=bool(args.step),
        quiet=quiet,
    )

    if args.json_out:
        print(json.dumps(result, default=str, indent=2))
    _print_disclaimer(stream=sys.stderr if args.json_out else sys.stdout)

    raise SystemExit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
