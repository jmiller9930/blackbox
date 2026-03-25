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
from learning_core.remediation_pattern_registry import get_pattern, register_pattern_from_outcome_analysis
from learning_core.remediation_validation import (
    assert_non_production_sqlite_path,
    get_candidate,
    ingest_remediation_candidate,
    open_validation_sandbox,
    run_validation,
)
from learning_core.validation_outcome_analysis import analyze_and_persist


def _conf_str(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def _print_global_header(*, quiet: bool) -> None:
    if quiet:
        return
    print("=== PLAYGROUND MODE (SANDBOX ONLY) ===")
    print("")


def _emit_stage_contract(
    stage_key: str,
    status: str,
    contract: dict[str, Any],
    *,
    quiet: bool,
) -> None:
    """Human-readable stage lines; keys align with canonical directive (presentation-only)."""
    if quiet:
        return
    print(f"[STAGE: {stage_key}]")
    print(f"status: {status}")

    def _disp(v: Any) -> str:
        if v is None:
            return "N/A"
        if isinstance(v, bool):
            return "true" if v else "false"
        s = str(v).strip()
        return s if s else "N/A"

    sk = stage_key.lower()
    if sk == "detect":
        print(f"issue_id={_disp(contract.get('issue_id'))}")
        print(f"category={_disp(contract.get('category'))}")
        print(f"severity={_disp(contract.get('severity'))}")
        print(f"evidence_summary={_disp(contract.get('evidence_summary'))}")
    elif sk == "suggest":
        print("Suggestion only")
        print(f"suggested_fix={_disp(contract.get('suggested_fix'))}")
        pc = contract.get("possible_causes")
        if isinstance(pc, (list, tuple)) and len(pc) > 0:
            print(f"possible_causes={', '.join(_disp(x) for x in pc[:5])}")
    elif sk == "ingest":
        print(f"remediation_id={_disp(contract.get('remediation_id'))}")
        print(f"source_type={_disp(contract.get('source_type'))}")
    elif sk == "validate":
        print(f"result={_disp(contract.get('result'))}")
        res_l = str(contract.get("result") or "").lower()
        if res_l == "fail":
            print(f"failure_class={_disp(contract.get('failure_class'))}")
        else:
            print("failure_class=N/A")
    elif sk == "analyze":
        print(f"outcome_category={_disp(contract.get('outcome_category'))}")
        print(f"evidence_summary={_disp(contract.get('evidence_summary'))}")
    elif sk == "pattern":
        print(f"pattern_id={_disp(contract.get('pattern_id'))}")
        print(f"pattern_status={_disp(contract.get('pattern_status'))}")
    elif sk == "simulate":
        print(
            f"execution_blocked={_disp(contract.get('execution_blocked'))} | "
            f"blocked_reason={_disp(contract.get('blocked_reason'))}"
        )
        print(f"approval_required={_disp(contract.get('approval_required'))}")
    else:
        print("N/A")
    print("")


def _print_simulation_policy(sim: dict[str, Any], *, quiet: bool) -> None:
    if quiet:
        return
    pol = sim.get("policy") or {}
    war = pol.get("would_allow_real_execution", False)
    print("Simulation Policy:")
    print(f"- would_allow_real_execution: {war}")
    print("")


def _print_playground_result(
    *,
    issue: dict[str, Any] | None,
    suggestion: dict[str, Any] | None,
    vr: dict[str, Any] | None,
    pattern_id: str | None,
    pattern_status: str | None,
    sim: dict[str, Any] | None,
    validation_confidence: Any,
    quiet: bool,
) -> None:
    if quiet:
        return
    sig = "—"
    if issue:
        sig = f"{issue.get('category', '?')}: {issue.get('message', '')}"[:240]
    sugg = "—"
    if suggestion:
        sugg = str(suggestion.get("suggested_fix") or "—")[:240]
    vres = "—"
    reason = "—"
    if vr:
        vres = str(vr.get("result", "—")).upper()
        if str(vr.get("result")) == "pass":
            reason = "sandbox validation passed"
        else:
            reason = str(vr.get("failure_reason") or vr.get("failure_class") or "—")[:200]
    pm = "—"
    if pattern_id:
        pm = f"id={pattern_id}"
        if pattern_status:
            pm += f", status={pattern_status}"
    sout = "—"
    if sim:
        sout = f"result={sim.get('result')}, simulation_id={sim.get('execution_simulation_id')}"
    print("=== PLAYGROUND RESULT ===")
    print("")
    print("Detected Signals:")
    print(f"- {sig}")
    print("")
    print("Suggested Action:")
    print(f"- {sugg}")
    print("")
    print("Validation Result:")
    print(f"- {vres}")
    print(f"- Reason: {reason}")
    print("")
    print("Pattern Match:")
    print(f"- {pm}")
    print("")
    print("Simulation Outcome:")
    print(f"- {sout}")
    print("")
    print("Confidence Score:")
    print(f"- {_conf_str(validation_confidence)}")
    print("")
    print("----------------------------------------")
    print("")
    print("THIS RUN IS SANDBOX ONLY")
    print("NOT APPROVAL")
    print("NOT EXECUTION PERMISSION")
    print("")
    print("⚠️ PLAYGROUND MODE — NO EXECUTION PATH")
    print("⚠️ Simulation only — not approval")
    print("⚠️ No action has been taken")
    print("")


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


def _stage(
    name: str,
    status: str,
    summary: str,
    *,
    stage_key: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "stage_key": stage_key,
        "contract": contract,
    }


def run_data_pipeline(
    *,
    sandbox_db: Path,
    issue_db: Path | None,
    replay_remediation_id: str | None,
    seed_demo: bool,
    step_mode: bool,
    quiet: bool = False,
) -> dict[str, Any]:
    assert_non_production_sqlite_path(sandbox_db)
    if issue_db is not None:
        assert_non_production_sqlite_path(issue_db)

    _print_global_header(quiet=quiet)

    sandbox_conn = open_validation_sandbox(sandbox_db)
    stages: list[dict[str, Any]] = []
    execution_state: dict[str, Any] = {"execution_sensitive": False}

    issue_db_conn: sqlite3.Connection | None = None
    issue: dict[str, Any] | None = None
    suggestion: dict[str, Any] | None = None
    remediation_id: str | None = None
    remediation_source_type: str | None = None
    validation_run_id: str | None = None
    vr: dict[str, Any] | None = None
    analysis_id: str | None = None
    an: dict[str, Any] | None = None
    pattern_id: str | None = None
    pattern_status: str | None = None
    sim: dict[str, Any] | None = None

    def pause() -> None:
        if step_mode and not quiet:
            input("[step] Press Enter to continue...")

    # --- DETECT ---
    if replay_remediation_id:
        cand = get_candidate(sandbox_conn, replay_remediation_id)
        if cand is None:
            contract = {
                "issue_id": "N/A",
                "category": "N/A",
                "severity": "N/A",
                "evidence_summary": "N/A",
            }
            st = _stage("DETECT", "fail", f"remediation_id not found: {replay_remediation_id}", stage_key="detect", contract=contract)
            stages.append(st)
            _emit_stage_contract("detect", st["status"], contract, quiet=quiet)
            pause()
            return {"stages": stages, "ok": False}
        issue = _issue_dict_from_candidate(cand)
        remediation_id = replay_remediation_id
        remediation_source_type = getattr(cand, "source_type", None)
        evidence_list = list(issue.get("supporting_evidence") or [])
        evidence_summary = evidence_list[0] if evidence_list else "N/A"
        contract = {
            "issue_id": issue.get("issue_id"),
            "category": issue.get("category"),
            "severity": issue.get("severity"),
            "evidence_summary": evidence_summary,
        }
        st = _stage("DETECT", "blocked", "replay mode — detection skipped", stage_key="detect", contract=contract)
        stages.append(st)
        _emit_stage_contract("detect", st["status"], contract, quiet=quiet)
    else:
        if seed_demo:
            idb = sandbox_db.parent / f".playground_issue_{uuid.uuid4().hex[:8]}.db"
            issue_db_conn = sqlite3.connect(str(idb))
            _seed_demo_issue_db(issue_db_conn)
            idesc = f"seed-demo temp issue DB: {idb.name}"
        elif issue_db is not None:
            issue_db_conn = sqlite3.connect(str(issue_db))
            _ensure_issue_db_schema(issue_db_conn)
            idesc = f"--issue-db: {issue_db}"
        else:
            contract = {
                "issue_id": "N/A",
                "category": "N/A",
                "severity": "N/A",
                "evidence_summary": "N/A",
            }
            st = _stage("DETECT", "fail", "provide --issue-db, --seed-demo, or --replay", stage_key="detect", contract=contract)
            stages.append(st)
            _emit_stage_contract("detect", st["status"], contract, quiet=quiet)
            pause()
            return {"stages": stages, "ok": False}

        assert issue_db_conn is not None
        issues = detect_infra_issues(issue_db_conn)
        if not issues:
            contract = {
                "issue_id": "N/A",
                "category": "N/A",
                "severity": "N/A",
                "evidence_summary": "N/A",
            }
            st = _stage("DETECT", "fail", "no issues detected — use --seed-demo or populate issue DB", stage_key="detect", contract=contract)
            stages.append(st)
            _emit_stage_contract("detect", st["status"], contract, quiet=quiet)
            issue_db_conn.close()
            pause()
            return {"stages": stages, "ok": False}
        issue = issues[0]
        evidence_list = list(issue.get("supporting_evidence") or [])
        evidence_summary = evidence_list[0] if evidence_list else "N/A"
        contract = {
            "issue_id": issue.get("issue_id"),
            "category": issue.get("category"),
            "severity": issue.get("severity"),
            "evidence_summary": evidence_summary,
        }
        st = _stage("DETECT", "pass", f"found issue {issue.get('issue_id')}", stage_key="detect", contract=contract)
        stages.append(st)
        _emit_stage_contract("detect", st["status"], contract, quiet=quiet)
    pause()

    # --- SUGGEST ---
    assert issue is not None
    suggestion = build_issue_suggestion(issue, execution_state=execution_state)
    sfix = str(suggestion.get("suggested_fix") or "")
    causes = suggestion.get("possible_causes") or []
    contract = {
        "label": "Suggestion only",
        "suggested_fix": sfix,
        "possible_causes": causes,
    }
    st = _stage("SUGGEST", "pass", "suggestion artifact built", stage_key="suggest", contract=contract)
    stages.append(st)
    _emit_stage_contract("suggest", st["status"], contract, quiet=quiet)
    pause()

    # --- INGEST ---
    if replay_remediation_id:
        assert remediation_id is not None
        contract = {
            "remediation_id": remediation_id,
            "source_type": remediation_source_type,
        }
        st = _stage("INGEST", "blocked", f"replay — using existing remediation {remediation_id}", stage_key="ingest", contract=contract)
        stages.append(st)
        _emit_stage_contract("ingest", st["status"], contract, quiet=quiet)
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
            contract = {
                "remediation_id": remediation_id,
                "source_type": "deterministic",
            }
            st = _stage("INGEST", "pass", f"remediation_id={remediation_id}", stage_key="ingest", contract=contract)
            stages.append(st)
            _emit_stage_contract("ingest", st["status"], contract, quiet=quiet)
        except ValueError as exc:
            contract = {
                "remediation_id": "N/A",
                "source_type": "N/A",
            }
            st = _stage("INGEST", "fail", str(exc), stage_key="ingest", contract=contract)
            stages.append(st)
            _emit_stage_contract("ingest", st["status"], contract, quiet=quiet)
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
    fc_val = str(vr.get("failure_class") or "").strip() or "N/A"
    contract = {
        "result": vst,
        "failure_class": fc_val if vst == "fail" else "N/A",
    }
    st = _stage("VALIDATE", vst, f"run_id={validation_run_id} result={vr.get('result')}", stage_key="validate", contract=contract)
    stages.append(st)
    _emit_stage_contract("validate", st["status"], contract, quiet=quiet)
    pause()

    # --- ANALYZE ---
    an = analyze_and_persist(sandbox_conn, validation_run_id)
    analysis_id = str(an["analysis_id"])
    ev = an.get("evidence_summary") or {}
    evidence_parts: list[str] = []
    for k in ("what_changed", "what_improved", "what_failed"):
        v = ev.get(k)
        if v:
            evidence_parts.append(str(v))
    evidence_summary_short = ("; ".join(evidence_parts[:2]))[:180] if evidence_parts else "N/A"
    contract = {
        "outcome_category": an.get("outcome_category"),
        "evidence_summary": evidence_summary_short,
    }
    st = _stage("ANALYZE", "pass", f"analysis_id={analysis_id}", stage_key="analyze", contract=contract)
    stages.append(st)
    _emit_stage_contract("analyze", st["status"], contract, quiet=quiet)
    pause()

    # --- PATTERN ---
    try:
        pattern_id = register_pattern_from_outcome_analysis(sandbox_conn, analysis_id)
        pat = get_pattern(sandbox_conn, pattern_id)
        pattern_status = str(pat.pattern_status) if pat else None
        contract = {
            "pattern_id": pattern_id,
            "pattern_status": pattern_status,
        }
        st = _stage("PATTERN", "pass", f"pattern_id={pattern_id}", stage_key="pattern", contract=contract)
        stages.append(st)
        _emit_stage_contract("pattern", st["status"], contract, quiet=quiet)
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
            pat = get_pattern(sandbox_conn, pattern_id)
            pattern_status = str(pat.pattern_status) if pat else None
            contract = {
                "pattern_id": pattern_id,
                "pattern_status": pattern_status,
            }
            st = _stage("PATTERN", "blocked", f"register skipped (duplicate); using {pattern_id}", stage_key="pattern", contract=contract)
            stages.append(st)
            _emit_stage_contract("pattern", st["status"], contract, quiet=quiet)
        else:
            contract = {
                "pattern_id": "N/A",
                "pattern_status": "N/A",
            }
            st = _stage("PATTERN", "fail", "integrity error without existing pattern", stage_key="pattern", contract=contract)
            stages.append(st)
            _emit_stage_contract("pattern", st["status"], contract, quiet=quiet)
            if issue_db_conn:
                issue_db_conn.close()
            pause()
            return {"stages": stages, "ok": False}
    except Exception as exc:
        contract = {
            "pattern_id": "N/A",
            "pattern_status": "N/A",
        }
        st = _stage("PATTERN", "fail", str(exc), stage_key="pattern", contract=contract)
        stages.append(st)
        _emit_stage_contract("pattern", st["status"], contract, quiet=quiet)
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
    pol = sim.get("policy") or {}
    execution_blocked = not bool(pol.get("would_allow_real_execution", False))
    contract = {
        "execution_blocked": execution_blocked,
        "blocked_reason": pol.get("execution_blocked_reason"),
        "approval_required": pol.get("approval_required"),
    }
    st = _stage("SIMULATE", sm, f"execution_simulation_id={sim.get('execution_simulation_id')}", stage_key="simulate", contract=contract)
    stages.append(st)
    _emit_stage_contract("simulate", st["status"], contract, quiet=quiet)

    _print_simulation_policy(sim, quiet=quiet)

    _print_playground_result(
        issue=issue,
        suggestion=suggestion,
        vr=vr,
        pattern_id=pattern_id,
        pattern_status=pattern_status,
        sim=sim,
        validation_confidence=vr.get("confidence") if vr else None,
        quiet=quiet,
    )

    if issue_db_conn:
        issue_db_conn.close()

    pause()
    out: dict[str, Any] = {
        "stages": stages,
        "ok": True,
        "remediation_id": remediation_id,
        "pattern_id": pattern_id,
        "simulation": sim,
        "playground_mode": "sandbox_only",
        "simulation_policy": {"would_allow_real_execution": (sim.get("policy") or {}).get("would_allow_real_execution", False)},
    }
    return out


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
    try:
        result = run_data_pipeline(
            sandbox_db=args.sandbox_db,
            issue_db=args.issue_db,
            replay_remediation_id=args.replay,
            seed_demo=bool(args.seed_demo),
            step_mode=bool(args.step),
            quiet=quiet,
        )
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if args.json_out:
        print(json.dumps(result, default=str, indent=2))

    raise SystemExit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
