#!/usr/bin/env python3
"""
GT_DIRECTIVE_038 — Student Reasoning Quality Exam (evaluation-only).

Does **not** modify RM math, pattern memory, EV logic, promotion, or execution — runs the
existing entry reasoning pipeline + Student LLM + authority merge, grades observability.

Usage::

    python3 renaissance_v4/game_theory/exam/student_reasoning_exam_v1.py --exam-id d6-reasoning-quality-001

Optional::

    --db-path /path/to/db.sqlite3
    --stub-llm  (deterministic JSON via engine-aligned stub — CI / offline)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from renaissance_v4.game_theory.exam.student_reasoning_exam_fingerprint_v1 import (
    write_exam_fingerprint_summary_md_v1,
)
from renaissance_v4.game_theory.exam.student_reasoning_exam_grading_v1 import (
    build_stub_student_json_aligned_to_engine_v1,
    grade_scenario_v1,
)
from renaissance_v4.game_theory.exam.student_reasoning_exam_scenarios_v1 import (
    resolve_scenario_windows_v1,
    synthetic_retrieved_experience_v1,
)
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    STUDENT_LLM_APPROVED_MODEL_V1,
    resolved_llm_for_exam_contract_v1,
)
from renaissance_v4.game_theory.pml_runtime_layout import blackbox_repo_root
from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import (
    apply_engine_authority_to_student_output_v1,
    run_entry_reasoning_pipeline_v1,
)
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    attach_student_context_annex_v1,
    build_student_context_annex_v1_from_entry_reasoning_eval_v1,
    build_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.student_decision_authority_v1 import (
    run_student_decision_authority_for_trade_v1,
)
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    emit_student_output_via_ollama_v1,
    verify_ollama_model_tag_available_v1,
)
from renaissance_v4.utils.db import DB_PATH


SCHEMA_RESULTS_V1 = "student_reasoning_exam_results_v1"


def _repo_runtime_exam_root_v1(exam_id: str) -> Path:
    return blackbox_repo_root() / "runtime" / "exam" / exam_id.strip()


def _required_signals_present_v1(ere: dict[str, Any] | None, required: list[str]) -> bool:
    if not isinstance(ere, dict):
        return False
    for k in required:
        if k not in ere or ere.get(k) is None:
            return False
        if isinstance(ere.get(k), dict) and not ere.get(k):
            return False
    return True


def _trace_append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def run_exam_v1(
    *,
    exam_id: str,
    db_path: Path | None,
    symbol: str | None,
    timeframe: int | None,
    stub_llm: bool,
) -> dict[str, Any]:
    db_used = Path(str(db_path or DB_PATH)).expanduser().resolve()
    scenarios, err = resolve_scenario_windows_v1(
        db_path=db_used,
        symbol_override=symbol,
        timeframe_override=timeframe,
    )
    if err:
        raise RuntimeError(err)
    if len(scenarios) != 10:
        raise RuntimeError(f"expected 10 scenarios, got {len(scenarios)}")

    out_root = _repo_runtime_exam_root_v1(exam_id)
    out_root.mkdir(parents=True, exist_ok=True)
    trace_path = out_root / "exam_trace_v1.jsonl"
    if trace_path.is_file():
        trace_path.unlink()

    exam_contract_base: dict[str, Any] = {
        "student_brain_profile_v1": STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        "student_llm_v1": {
            "llm_provider": "ollama",
            "llm_model": STUDENT_LLM_APPROVED_MODEL_V1,
            "llm_role": "student_reasoning_exam_v1",
        },
    }

    llm_model_r, base_url_r, _slm_echo, llm_errs = resolved_llm_for_exam_contract_v1(exam_contract_base)
    if not stub_llm:
        probe_err = verify_ollama_model_tag_available_v1(str(base_url_r), str(llm_model_r)) if (
            llm_model_r and base_url_r
        ) else "ollama_resolution_failed"
        if llm_errs or not llm_model_r:
            raise RuntimeError("student LLM gate: " + "; ".join(llm_errs or ["missing model/url"]))
        if probe_err:
            raise RuntimeError(probe_err)

    scenario_rows: list[dict[str, Any]] = []

    for sc in scenarios:
        sid = str(sc["scenario_id"])
        tf = int(sc["candle_timeframe_minutes"])
        sym = str(sc["symbol"])
        decision_ms = int(sc["decision_open_time_ms"])
        inj = sc.get("memory_injection_v1")
        rse = synthetic_retrieved_experience_v1(
            candle_timeframe_minutes=tf,
            injection=str(inj) if inj else None,
        )

        ex_contract = {**exam_contract_base, "candle_timeframe_minutes": tf}

        pkt, perr = build_student_decision_packet_v1(
            db_path=db_used,
            symbol=sym,
            decision_open_time_ms=decision_ms,
            candle_timeframe_minutes=tf,
            notes=f"GT038 {exam_id} {sid}",
        )
        if perr or pkt is None:
            raise RuntimeError(f"{sid}: packet: {perr}")

        ere, ere_errs, _trace, pfm = run_entry_reasoning_pipeline_v1(
            student_decision_packet=pkt,
            retrieved_student_experience=rse,
            run_candle_timeframe_minutes=tf,
            job_id="",
            fingerprint=None,
            scenario_id=sid,
            trade_id=sid,
            emit_traces=False,
            unified_agent_router=False,
        )
        if ere_errs or ere is None:
            raise RuntimeError(f"{sid}: entry reasoning failed: {'; '.join(ere_errs or [])}")

        annex = build_student_context_annex_v1_from_entry_reasoning_eval_v1(ere)
        pkt2, aerr = attach_student_context_annex_v1(pkt, annex)
        if aerr or pkt2 is None:
            raise RuntimeError(f"{sid}: annex attach: {aerr}")

        llm_cap: dict[str, Any] = {}
        raw_txt = ""
        merge_errors: list[str] = []

        if stub_llm:
            stub_doc = build_stub_student_json_aligned_to_engine_v1(ere, scenario_id=sid)

            def _fake_once(**_kwargs: Any) -> tuple[str | None, str | None]:
                return json.dumps(stub_doc, ensure_ascii=False), None

            with mock.patch(
                "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
                side_effect=_fake_once,
            ):
                so, soe = emit_student_output_via_ollama_v1(
                    pkt2,
                    graded_unit_id=sid,
                    decision_at_ms=decision_ms,
                    llm_model=str(llm_model_r or STUDENT_LLM_APPROVED_MODEL_V1),
                    ollama_base_url=str(base_url_r),
                    prompt_version="student_reasoning_exam_v1",
                    require_directional_thesis_v1=True,
                    llm_io_capture_v1=llm_cap,
                )
        else:
            so, soe = emit_student_output_via_ollama_v1(
                pkt2,
                graded_unit_id=sid,
                decision_at_ms=decision_ms,
                llm_model=str(llm_model_r or STUDENT_LLM_APPROVED_MODEL_V1),
                ollama_base_url=str(base_url_r),
                prompt_version="student_reasoning_exam_v1",
                require_directional_thesis_v1=True,
                llm_io_capture_v1=llm_cap,
            )

        raw_txt = str((llm_cap or {}).get("raw_assistant_text_v1") or "")
        if soe or so is None:
            merge_errors.extend(list(soe or []))

        allowed_mids = frozenset(
            str(z.get("record_id") or "").strip()
            for z in rse
            if isinstance(z, dict) and str(z.get("record_id") or "").strip()
        )

        try:
            run_student_decision_authority_for_trade_v1(
                job_id=exam_id,
                fingerprint=None,
                scenario_id=sid,
                trade_id=sid,
                ere=ere,
                pkt=pkt2,
                unified_router_enabled=False,
                exam_run_contract_request_v1=ex_contract,
                mandate_active_v1=False,
            )
        except RuntimeError as e:
            merge_errors.append(f"authority_runtime:{e}")

        so2, auth_errs = apply_engine_authority_to_student_output_v1(
            so,
            ere,
            allowed_memory_ids=allowed_mids,
        )
        merge_errors.extend(list(auth_errs or []))

        sealed_ok = bool(so2) and not auth_errs
        fin_action = str((so2 or {}).get("student_action_v1") or "no_trade")

        grading = grade_scenario_v1(
            scenario=sc,
            ere=ere,
            final_so=so2,
            raw_llm_text=raw_txt,
            merge_errors=merge_errors,
        )

        req_sig = list(sc.get("required_signals") or [])
        signals_ok = _required_signals_present_v1(ere, req_sig)

        row_out: dict[str, Any] = {
            "scenario_id": sid,
            "symbol": sym,
            "candle_timeframe_minutes": tf,
            "decision_open_time_ms": decision_ms,
            "bars_window_note": sc.get("bars_window_note"),
            "window_resolution_v1": sc.get("window_resolution_v1"),
            "expected_state": sc.get("expected_state"),
            "expected_behavior": sc.get("expected_behavior"),
            "allowed_actions": sc.get("allowed_actions"),
            "disallowed_actions": sc.get("disallowed_actions"),
            "required_signals": req_sig,
            "required_signals_present_v1": signals_ok,
            "student_raw_output": raw_txt[:24000],
            "parsed_output_v1": so,
            "decision_synthesis_v1": ere.get("decision_synthesis_v1"),
            "pattern_memory_eval_v1": ere.get("pattern_memory_eval_v1"),
            "expected_value_risk_cost_v1": ere.get("expected_value_risk_cost_v1"),
            "final_sealed_action_v1": fin_action,
            "student_output_after_engine_authority_v1": so2,
            "merge_errors_v1": merge_errors,
            "sealed_ok_v1": sealed_ok,
            "grading_v1": grading,
        }
        scenario_rows.append(row_out)

        summary_bits = (
            f"action={grading.get('action_correct')} hallu={grading.get('hallucination')} "
            f"sealed={'YES' if sealed_ok else 'NO'}"
        )
        _trace_append(
            trace_path,
            {
                "stage": "exam_scenario_execution_v1",
                "exam_id": exam_id,
                "scenario_id": sid,
                "expected_behavior": sc.get("expected_behavior"),
                "student_action": fin_action,
                "pass_fail_summary": summary_bits,
            },
        )

    acc = _acceptance_block_v1(scenario_rows)

    results_doc: dict[str, Any] = {
        "schema": SCHEMA_RESULTS_V1,
        "exam_id": exam_id,
        "db_path_resolved_v1": str(db_used),
        "stub_llm_v1": bool(stub_llm),
        "acceptance_v1": acc,
        "scenarios_v1": scenario_rows,
    }

    json_path = out_root / "student_reasoning_exam_results_v1.json"
    json_path.write_text(json.dumps(results_doc, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_exam_fingerprint_summary_md_v1(results_doc, out_root)
    return results_doc


def _acceptance_block_v1(rows: list[dict[str, Any]]) -> dict[str, str]:
    n = len(rows)
    all_run = n == 10
    all_sealed = all(bool(r.get("sealed_ok_v1")) for r in rows)
    strict_nt = ("d6_s03_sideways_chop", "d6_s04_fake_breakout_trap", "d6_s10_memory_warning_trade")
    nt_ok = all(
        str((r.get("grading_v1") or {}).get("no_trade_correct")) == "YES"
        for r in rows
        if str(r.get("scenario_id") or "") in strict_nt
    )
    hallu_absent = all(str((r.get("grading_v1") or {}).get("hallucination")) == "NO" for r in rows)
    mem_ids = ("d6_s09_memory_supported_trade", "d6_s10_memory_warning_trade")
    mem_ok = all(
        str((r.get("grading_v1") or {}).get("memory_alignment")) != "FAIL"
        for r in rows
        if str(r.get("scenario_id") or "") in mem_ids
    )
    ev_ok = all(str((r.get("grading_v1") or {}).get("ev_alignment")) != "FAIL" for r in rows)
    risk_ok = all(
        str((r.get("grading_v1") or {}).get("risk_awareness")) != "FAIL"
        for r in rows
        if str(r.get("scenario_id") or "") == "d6_s08_high_volatility_danger"
    )

    def yn(x: bool) -> str:
        return "YES" if x else "NO"

    return {
        "all_10_scenarios_executed_v1": yn(all_run),
        "all_scenarios_sealed_v1": yn(all_sealed),
        "no_trade_correctly_used_v1": yn(nt_ok),
        "hallucination_absent_v1": yn(hallu_absent),
        "memory_influenced_decisions_correctly_v1": yn(mem_ok),
        "ev_influenced_decisions_correctly_v1": yn(ev_ok),
        "high_risk_scenarios_handled_v1": yn(risk_ok),
        "exam_results_file_created_v1": "YES",
        "trace_file_created_v1": "YES",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="GT_DIRECTIVE_038 — Student reasoning quality exam")
    ap.add_argument("--exam-id", required=True, help="e.g. d6-reasoning-quality-001")
    ap.add_argument("--db-path", default="", help="SQLite path (default: renaissance_v4 DB_PATH)")
    ap.add_argument("--symbol", default="", help="Override symbol for resolver")
    ap.add_argument("--timeframe", type=int, default=None, help="Candle timeframe minutes (5/15/60/240)")
    ap.add_argument(
        "--stub-llm",
        action="store_true",
        help="Bypass live Ollama; emit deterministic JSON aligned to engine synthesis.",
    )
    ns = ap.parse_args()
    dbp = Path(ns.db_path).expanduser().resolve() if str(ns.db_path).strip() else None
    sym = str(ns.symbol).strip() or None
    doc = run_exam_v1(
        exam_id=str(ns.exam_id).strip(),
        db_path=dbp,
        symbol=sym,
        timeframe=ns.timeframe,
        stub_llm=bool(ns.stub_llm),
    )
    root = _repo_runtime_exam_root_v1(str(ns.exam_id).strip())
    print(json.dumps({"ok": True, "wrote": str(root), "acceptance_v1": doc.get("acceptance_v1")}, indent=2))


if __name__ == "__main__":
    main()
