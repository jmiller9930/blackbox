"""
Local web UI for **Pattern Machine learning**: **curated operator recipes** + **evaluation window**
(months) + **trade window** (candle rollup 5m / 15m / 1h / 4h), or **Custom JSON**, then Run (parallel workers).
Recipes are defined in ``operator_recipes.py`` (not a glob of every file in ``examples/``). The evaluation window
is merged into each scenario and drives **calendar tape slicing**; trade window drives **OHLCV rollup from
``market_bars_5m``** before ``run_manifest_replay`` (see ``replay_data_audit`` / ``candle_timeframe_rollup_v1``).

Batches use **``POST /api/run-parallel/start``** + polling **``GET /api/run-parallel/status/<job_id>``**
(or **``GET /api/run-status/<job_id>``**, same payload) so the UI shows **per-scenario progress** plus
**``POST /api/run-parallel/cancel/<job_id>``** to request cancel (best-effort: pending scenarios are not scheduled; workers already running may finish),
**live telemetry** (decision windows, trades, candidate phase) from worker-written JSON snapshots.
``POST /api/run-parallel`` remains as a blocking API for scripts.

Each completed batch also writes a **unique session folder** under the batch logs directory
(default: ``<repo>/runtime/batches/`` via ``PATTERN_GAME_SESSION_LOGS_ROOT``, or
``renaissance_v4/game_theory/logs/`` if unset; or ``$PATTERN_GAME_MEMORY_ROOT/logs`` when that env
is set). Folders look like ``batch_<UTC>_<id>/`` with ``BATCH_README.md`` and per-scenario
``HUMAN_READABLE.md``, unless ``PATTERN_GAME_NO_SESSION_LOG=1``. The JSON result includes
``session_log_batch_dir`` when present.

Parallel batches append one line per run to ``batch_scorecard.jsonl`` (UTC start/end, duration,
counts, **run_ok_pct**, **referee_win_pct**, **avg_trade_win_pct**) and expose ``batch_timing`` on the API; see
``GET /api/batch-scorecard``. Operators may truncate that log with
``POST /api/batch-scorecard/clear`` (does not touch engine memory or Student Proctor store). Destructive engine reset:
``POST /api/pattern-game/reset-learning`` with typed confirm phrase (see UI). Student Proctor store:
``GET /api/student-proctor/learning-store``, ``POST /api/student-proctor/learning-store/clear`` (separate confirm).

**D13 Student panel (run → run summary + trade carousel → trade deep dive):** ``GET /api/student-panel/runs``
(includes embedded ``l1_road_v1`` overlay for L1 road columns + API legend),
``GET /api/student-panel/l1-road`` (**GT_DIRECTIVE_016** — full road payload, same aggregation),
``GET /api/student-panel/run/<job_id>/decisions``, ``GET /api/student-panel/run/<job_id>/l3?trade_id=`` (**GT_DIRECTIVE_017** — L3 envelope + structured ``data_gaps[]``),
``GET /api/student-panel/run/<job_id>/learning`` (**GT_DIRECTIVE_018** — memory promotion / retrieval eligibility),
``GET /api/student-panel/run/<job_id>/learning-loop-trace`` — LangGraph-style **learning loop trace** JSON (nodes, edges, blunt health banner); **debug** fingerprint compare + breakpoints: ``GET /api/debug/learning-loop/trace/<job_id>``, ``GET /api/debug/learning-loop/trace-stream/<job_id>`` (NDJSON progress + payload), and ``GET /debug/learning-loop?job_id=…`` (legacy ``GET /learning-loop-trace`` redirects there); runtime handoffs append to ``learning_trace_events_v1.jsonl`` (see ``learning_trace_events_v1``) and merge into the debug payload when present,
``GET /api/training-exam-audit/<job_id>`` — deterministic ``training_exam_audit_v1`` for one scorecard line (learning vs harness vs missing seam; rebuilds from fields if older lines lack the block),
``GET /api/student-panel/decision?job_id=&trade_id=`` (``decision_id`` accepted as alias for migration).
``GET /api/training/export`` (**GT_DIRECTIVE_022** — promoted-only training export preview / download); ``POST /api/training/export/materialize`` (typed confirm writes ``training_dataset_v1.jsonl``).
``GET /api/training/learning-effectiveness`` (**GT_DIRECTIVE_023** — read-only effectiveness audit JSON); ``POST /api/training/learning-effectiveness/materialize`` (typed confirm writes ``learning_effectiveness_report_v1``).
``GET /api/training/learning-flow-validate`` (**GT_DIRECTIVE_025** — Run A→B step chain + verdict); ``POST /api/training/learning-flow-validate/materialize`` (typed confirm writes ``learning_flow_validation_v1.json``).
``GET /api/training/learning-loop-proof`` (**GT_DIRECTIVE_026L** — node-by-node causal learning-loop graph); ``POST /api/training/learning-loop-proof/materialize`` (typed confirm ``MATERIALIZE_LEARNING_LOOP_PROOF_V1`` writes full ``learning_loop_proof_graph_v1`` JSON).

**Post-certification ``trade_strategy`` (DEV STUB):** Same routes under **``/api/v1/trade-strategy``** (stable for external callers) and **``/api/trade-strategy``** (alias).
``GET …/contract`` returns integration metadata. Methods: list, ``<id>/export`` (download JSON), get one, POST, PATCH — placeholder payloads until persistence + execution;
see ``trade_strategy_post_cert_stub_v1.py`` and ``docs/STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md`` §17.

**Exam unit state machine (GT_DIRECTIVE_003 / §11.1):** ``POST /api/v1/exam/units``, ``GET /api/v1/exam/units/<exam_unit_id>``,
``POST /api/v1/exam/units/<exam_unit_id>/transition`` — in-process dev store; see ``exam_state_machine_v1.py`` and ``directives/GT_DIRECTIVE_003_exam_state_machine_v1.md``.

**Exam deliberation frame 0 (GT_DIRECTIVE_004 / §11.2):** ``PUT /api/v1/exam/units/<exam_unit_id>/frames/0/deliberation`` (valid body **200**, bad envelope **400**, policy/placeholder **422**, unknown unit **404**),
``GET …/frames/0/deliberation`` (**200** when set, **404** when missing). Schema: ``schemas/exam_deliberation_payload_v1.schema.json``; see ``exam_deliberation_capture_v1.py`` and ``directives/GT_DIRECTIVE_004_deliberation_capture_v1.md``.

**Exam decision frames (GT_DIRECTIVE_005 / §11.3; GT_DIRECTIVE_006 / §11.4):** ``GET /api/v1/exam/units/<exam_unit_id>/decision-frames`` (**200** committed timeline after Decision A seal, **404** unknown unit or timeline not committed),
``GET /api/v1/exam/frames/<decision_frame_id>`` (**200** single frame, **404** not found). **ENTER** timelines append downstream frames per §11.4 (``POST …/ohlc-strip`` optional before seal; else deterministic synthetic strip). Frame ids use ``{exam_unit_id}__df{n}`` (URL-safe). Timeline commits on successful ``decision_a_sealed`` transition; deliberation read-through from §11.2 store (no duplicate storage). See ``exam_decision_frame_schema_v1.py``, ``exam_downstream_frame_generator_v1.py``, and ``directives/GT_DIRECTIVE_005_decision_frame_schema_v1.md``.

**Exam grading (GT_DIRECTIVE_007 / §11.5):** ``GET /api/v1/exam/units/<exam_unit_id>/grade`` (**200** E/P/pass when unit is sealed, timeline + deliberation exist, and pack grading config is registered; **404** unknown unit; **409** incomplete; **422** bad pack reference / malformed economic inputs; **500** missing pack grading config). Dev: ``POST /api/v1/exam/packs/<exam_pack_id>/grading-config`` registers pack constants. See ``exam_grading_service_v1.py``.

**Exam decision-frame APIs (GT_DIRECTIVE_008 / §11.7 / §12):** ``GET /api/v1/exam/units/<exam_unit_id>/decision-frames`` and ``GET /api/v1/exam/frames/<decision_frame_id>`` remain available for tools and dev callers; the Pattern Machine **operator page** no longer embeds the exam-timeline carousel in the Student fold (dashboard space). Closure: ``directives/GT_DIRECTIVE_008_exam_ui_splice_v1.md``.

**System Dialogue** (post-run formatter; ``/api/barney-summary``): ``POST /api/barney-summary`` with ``{"job_id": "…"}`` — structured
run facts only. **Ask DATA** (bounded self-explainer): ``POST /api/ask-data`` with ``question`` and optional
``job_id`` / ``ui_context`` — answers only from bundled PML knowledge + run/scorecard facts
(when LLM enabled: **intent router** may select **PML lightweight**, **System Agent**, or **DeepSeek** tier; see
``ask_data_router_v1.py``, ``ollama_role_routing_v1.py``, ``GET /api/operator/ollama-role-routing``).
Successful responses may include ``interaction_id`` and ``question_fingerprint`` when
``ASK_DATA_OPERATOR_FEEDBACK`` is enabled; operators POST ratings to ``POST /api/ask-data/feedback``
(body: ``interaction_id``, ``rating`` — one of ``up``, ``down``, ``neutral``; optional ``tags``, ``note``).
Prior ratings for similar questions appear in the bundle as ``operator_feedback_signals`` (telemetry, not Referee).
Env: ``ASK_DATA_USE_LLM``, ``ASK_DATA_ROUTER``, ``ASK_DATA_ROUTE``, ``ASK_DATA_OPERATOR_FEEDBACK``,
``ASK_DATA_OPERATOR_FEEDBACK_PATH``, ``BARNEY_USE_LLM``, ``ANNA_USE_LLM``, ``PML_LIGHTWEIGHT_OLLAMA_*``,
``SYSTEM_AGENT_OLLAMA_*``, ``DEEPSEEK_ESCALATION_OLLAMA_*``, ``STUDENT_OLLAMA_BASE_URL``.

**Operator Ollama role routing (read-only snapshot):** ``GET /api/operator/ollama-role-routing`` — JSON snapshot of resolved bases/models per role (no secrets). **System Agent** tooling must use ``system_agent_ollama_v1`` + **tool layers** only; models never execute mutations directly.

Operator **retrospective** (learn / next experiment): ``GET /api/retrospective-log``,
``POST /api/retrospective-append`` — persists to ``retrospective_log.jsonl`` (see
``renaissance_v4/game_theory/retrospective_log.py``).

**Hunter planner (memory-aware batch suggestions):** ``GET /api/suggest-hunters`` returns
distinct parallel scenarios from scorecard + retrospective (see ``hunter_planner.py``); not
Referee predictions.

**Chef (catalog batch builder):** ``GET /api/catalog-batch-meta`` returns defaults (ATR grids, caps).
``POST /api/catalog-batch-generate`` with ``{"mode":"atr_sweep","manifest_path":"…"}`` builds a
validator-ready scenario array (same manifest, ATR geometry sweep) for paste or parallel run —
see ``catalog_batch_builder.py``.

**API:** ``GET /api/operator-recipes``, ``GET /api/operator-recipe-preview`` — curated playbooks.
**Advanced:** ``GET /api/scenario-presets`` lists raw ``examples/*.json`` for templates and debugging.

No manifest/ATR fields in the main controls — policy lives in the recipe / JSON. **Workers** slider defaults
to **logical CPU count** (capped by host hard max, see ``GET /api/capabilities``). ``POST /api/run`` remains for
scripted single-manifest runs (optional JSON field ``memory_bundle_path``).

  pip install -r renaissance_v4/game_theory/requirements.txt
  PYTHONPATH=. python3 -m renaissance_v4.game_theory.web_app

Default bind is loopback; use ``--host 0.0.0.0`` for LAN/SSH access (prototype).

**Hypothesis (default on):** parallel runs validate a non-empty ``agent_explanation.hypothesis`` per
scenario unless ``PATTERN_GAME_REQUIRE_HYPOTHESIS=0`` (or ``false`` / ``no`` / ``off``). Shipped
presets include a starter hypothesis string.
"""

from __future__ import annotations

import html
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, jsonify, request, send_file, stream_with_context
from pydantic import ValidationError

_GAME_THEORY = Path(__file__).resolve().parent
_RV4_ROOT = _GAME_THEORY.parent
_BLACKBOX_REPO_ROOT = _RV4_ROOT.parent
_PATTERN_BANNER_PATH = _RV4_ROOT / "assets" / "pattern.png"
# Lossy WebP (~4× smaller than PNG); regenerate when pattern.png changes:
#   cwebp -q 83 renaissance_v4/assets/pattern.png -o renaissance_v4/assets/pattern.webp
_PATTERN_BANNER_WEBP_PATH = _RV4_ROOT / "assets" / "pattern.webp"
# External banner bootstrap (CSP-safe: ``script-src 'self'`` allows same-origin .js when inline is blocked).
_PATTERN_GAME_BANNER_BOOT_JS = _GAME_THEORY / "static" / "pattern_game_banner_boot.js"

# Operator-visible web UI bundle version — bump when changing PAGE_HTML (HTML/CSS/JS) so deploys are provable.
PATTERN_GAME_WEB_UI_VERSION = "2.19.87"

from renaissance_v4.game_theory.reasoning_model_operator_surface_v1 import (
    get_reasoning_model_operator_snapshot_v1,
    write_operator_external_api_gateway_enabled_v1,
)
from renaissance_v4.game_theory.context_signature_memory import truncate_context_signature_memory_store
from renaissance_v4.game_theory.groundhog_memory import (
    clear_groundhog_bundle_file,
    groundhog_auto_merge_enabled,
    groundhog_bundle_path,
    groundhog_wiring_signal,
    promote_groundhog_bundle_from_parallel_scenarios_v1,
    read_groundhog_bundle,
    write_groundhog_bundle,
)
from renaissance_v4.game_theory.batch_scorecard import (
    read_batch_scorecard_recent,
    record_parallel_batch_finished,
    remove_batch_scorecard_line_by_job_id,
    truncate_batch_scorecard_jsonl,
    utc_timestamp_iso,
)
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    build_exam_run_line_meta_v1,
    normalize_student_reasoning_mode_v1,
    parse_exam_run_contract_request_v1,
    preview_run_config_fingerprint_sha256_40_v1,
)
from renaissance_v4.game_theory.pattern_game_operator_reset import (
    RESET_PATTERN_GAME_LEARNING_CONFIRM,
    reset_pattern_game_engine_learning_state_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_operator_v1 import (
    RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM,
    clear_student_learning_store_v1,
    student_learning_store_status_v1,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.game_theory.student_controlled_replay_v1 import (
    apply_automated_student_lanes_from_exam_contract_v1,
)
from renaissance_v4.game_theory.student_panel_d11 import build_d11_run_rows_v1
from renaissance_v4.game_theory.student_panel_d13 import (
    build_d13_selected_run_payload_v1,
    build_student_decision_record_v1,
)
from renaissance_v4.game_theory.scorecard_drill import find_scorecard_entry_by_job_id
from renaissance_v4.game_theory.student_panel_d14 import enrich_student_panel_run_rows_d14
from renaissance_v4.game_theory.training_exam_audit_v1 import build_training_exam_audit_v1
from renaissance_v4.game_theory.debug_learning_loop_trace_v1 import (
    build_debug_learning_loop_trace_v1,
    iter_debug_learning_loop_trace_ndjson_v1,
    read_debug_learning_loop_page_html_v1,
)
from renaissance_v4.game_theory.learning_loop_trace_v1 import (
    build_learning_loop_trace_v1,
    read_learning_loop_trace_page_html_v1,
)
from renaissance_v4.game_theory.student_panel_l1_road_v1 import build_l1_road_payload_v1
from renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1 import build_student_panel_l3_payload_v1
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    build_student_panel_run_learning_payload_v1,
)
from renaissance_v4.game_theory.student_proctor.training_export_v1 import (
    MATERIALIZE_TRAINING_DATASET_CONFIRM_V1,
    build_training_export_payload_v1,
    default_training_dataset_jsonl_path_v1,
    iter_training_record_lines_v1,
    materialize_training_dataset_v1,
)
from renaissance_v4.game_theory.student_proctor.learning_effectiveness_report_v1 import (
    MATERIALIZE_LEARNING_EFFECTIVENESS_CONFIRM_V1,
    build_learning_effectiveness_report_v1,
    default_learning_effectiveness_report_path_v1,
    materialize_learning_effectiveness_report_v1,
    summarize_learning_effectiveness_report_v1,
)
from renaissance_v4.game_theory.learning_flow_validator_v1 import (
    MATERIALIZE_LEARNING_FLOW_VALIDATION_V1,
    build_learning_flow_validation_v1,
    default_learning_flow_validation_report_path_v1,
    materialize_learning_flow_validation_v1,
)
from renaissance_v4.game_theory.learning_loop_proof_graph_v1 import (
    build_learning_loop_proof_graph_v1,
    default_learning_loop_proof_output_path_v1,
    materialize_learning_loop_proof_graph_v1,
)
from renaissance_v4.game_theory.exam_decision_frame_schema_v1 import (
    ExamUnitTimelineDocumentV1,
    append_local_time_to_decision_frame_dict_v1,
    build_complete_enter_timeline_v1,
    build_timeline_document_no_trade_single_frame_v1,
    commit_timeline_immutable_v1,
    find_frame_in_committed_timelines_v1,
    get_committed_timeline_v1,
    timeline_to_public_response_v1,
)
from renaissance_v4.game_theory.exam_downstream_frame_generator_v1 import (
    DownstreamTerminationPolicyV1,
    default_synthetic_ohlc_strip_v1,
    get_exam_downstream_termination_v1,
    get_exam_ohlc_strip_v1,
    set_exam_downstream_termination_v1,
    set_exam_ohlc_strip_v1,
)
from renaissance_v4.game_theory.exam_grading_service_v1 import (
    compute_exam_grade_v1,
    get_exam_pack_grading_config_v1,
    register_exam_pack_grading_config_v1,
)
from renaissance_v4.game_theory.exam_deliberation_capture_v1 import (
    assert_non_placeholder_deliberation_v1,
    deliberation_payload_to_export_dict_v1,
    get_frame0_deliberation_v1,
    parse_submit_envelope_v1,
    put_frame0_deliberation_v1,
    validate_deliberation_against_policy_v1,
)
from renaissance_v4.game_theory.exam_state_machine_v1 import (
    ExamPhase,
    apply_exam_unit_transition_v1,
    create_exam_unit_v1,
    exam_unit_to_public_dict,
    get_exam_unit_v1,
)
from renaissance_v4.game_theory.trade_strategy_post_cert_stub_v1 import (
    stub_trade_strategy_create_v1,
    stub_trade_strategy_export_document_v1,
    stub_trade_strategy_get_v1,
    stub_trade_strategy_list_v1,
    stub_trade_strategy_update_v1,
    trade_strategy_api_contract_v1,
)
from renaissance_v4.game_theory.data_health import get_data_health
from renaissance_v4.game_theory.search_space_estimate import build_search_space_estimate
from renaissance_v4.game_theory.memory_paths import (
    default_batch_scorecard_jsonl,
    default_experience_log_jsonl,
    default_retrospective_log_jsonl,
    ensure_memory_root_tree,
)
from renaissance_v4.game_theory.pml_runtime_layout import (
    apply_main_process_runtime_env_defaults,
    check_disk_before_run,
    configure_web_server_file_logging,
    describe_pml_runtime_for_startup,
    ensure_pml_runtime_dirs,
    prune_pml_runtime_batch_dirs,
    runtime_status_snapshot,
)
from renaissance_v4.game_theory.catalog_batch_builder import (
    build_atr_sweep_scenarios,
    catalog_batch_builder_meta,
)
from renaissance_v4.game_theory.learning_run_audit import (
    aggregate_batch_learning_run_audit_v1,
    build_memory_context_impact_audit_v1,
)
from renaissance_v4.game_theory.hunter_planner import build_hunter_suggestion
from renaissance_v4.game_theory.retrospective_log import append_retrospective, read_retrospective_recent
from renaissance_v4.game_theory.live_telemetry_v1 import (
    clear_job_telemetry_files,
    default_telemetry_dir,
    read_job_telemetry_v1,
)
from renaissance_v4.game_theory.candle_timeframe_runtime import (
    annotate_scenarios_with_candle_timeframe,
    resolve_ui_trade_window,
)
from renaissance_v4.game_theory.evaluation_window_runtime import (
    annotate_scenarios_with_window_and_recipe,
    resolve_ui_evaluation_window,
)
from renaissance_v4.game_theory.operator_recipes import (
    build_scenarios_for_recipe,
    default_recipe_id,
    operator_recipe_catalog,
    policy_catalog,
    recipe_meta_by_id,
)
from renaissance_v4.game_theory.parallel_runner import (
    OPERATOR_LEARNING_HARNESS_RECIPE_IDS,
    ParallelBatchCancelledError,
    clamp_parallel_workers,
    get_parallel_limits,
    run_scenarios_parallel,
    validate_reference_comparison_batch_results,
)
from renaissance_v4.game_theory.pattern_game import (
    PATTERN_GAME_STARTING_EQUITY_USD_SPEC,
    _default_manifest_path,
    json_summary,
    run_pattern_game,
)
from renaissance_v4.game_theory.policy_framework import attach_policy_framework_audits
from renaissance_v4.game_theory.ask_data_explainer import (
    ask_data_answer,
    build_ask_data_bundle_v1,
    sanitize_ui_context,
    scorecard_snapshot_for_ask,
)
from renaissance_v4.game_theory.barney_summary import (
    barney_summarize_job_facts,
    build_barney_facts_from_job_state,
)
from renaissance_v4.game_theory.operator_strategy_upload import (
    active_manifest_repo_relative,
    clear_active_operator_strategy,
    default_repo_root as operator_upload_repo_root,
    process_strategy_idea_upload,
    public_state as operator_strategy_public_state,
)
from renaissance_v4.game_theory.scenario_contract import (
    extract_policy_contract_summary,
    resolve_scenario_manifest_path,
    referee_session_outcome,
    validate_scenarios,
)
from renaissance_v4.game_theory.module_board import compute_pattern_game_module_board
from renaissance_v4.game_theory.scorecard_drill import (
    batch_detail_csv_rows,
    build_scenario_list_for_batch,
    find_scorecard_entry_by_job_id,
    read_scenario_artifact,
    scorecard_history_csv,
)

_JOBS_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_JOB_MAX_AGE_SEC = 7200


def _prune_jobs() -> None:
    now = time.time()
    with _JOBS_LOCK:
        stale = [k for k, v in _JOBS.items() if now - float(v.get("created", 0)) > _JOB_MAX_AGE_SEC]
        for k in stale:
            del _JOBS[k]


def _parallel_job_cancel_requested(job_id: str) -> bool:
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
        return bool(j and j.get("cancel_requested"))


def _merge_scorecard_with_inflight(
    file_rows: list[dict[str, Any]],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    """
    Prepend **running** parallel jobs so operators see **start time** before JSONL append.

    Completed batches appear only from ``batch_scorecard.jsonl`` (one line at end of run).
    """
    _prune_jobs()
    inflight: list[tuple[float, dict[str, Any]]] = []
    with _JOBS_LOCK:
        for jid, v in list(_JOBS.items()):
            if v.get("status") != "running":
                continue
            started = str(v.get("started_at_utc") or "").strip()
            if not started:
                started = utc_timestamp_iso()
            total = int(v.get("total") or 0)
            total = max(1, total)
            completed = int(v.get("completed") or 0)
            entry: dict[str, Any] = {
                "schema": "pattern_game_batch_scorecard_v1",
                "job_id": jid,
                "source": "pattern_game_web_ui_inflight",
                "started_at_utc": started,
                "ended_at_utc": None,
                "duration_sec": None,
                "total_scenarios": total,
                "total_processed": completed,
                "ok_count": None,
                "failed_count": None,
                "workers_used": v.get("workers_used"),
                "status": "running",
                "scorecard_inflight": True,
                "session_log_batch_dir": None,
            }
            inflight.append((float(v.get("created") or 0), entry))
    inflight.sort(key=lambda x: x[0], reverse=True)
    inflight_rows = [e for _, e in inflight]
    file_ids = {str(r.get("job_id") or "") for r in file_rows}
    inflight_rows = [e for e in inflight_rows if str(e.get("job_id") or "") not in file_ids]
    n_inflight = len(inflight_rows)
    rest = max(0, limit - n_inflight)
    merged = inflight_rows + file_rows[:rest]
    return merged, n_inflight


def _slug_preset_display_name(name: str) -> str:
    """Filesystem-safe slug from operator display name (user_*.json stem)."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:72] if s else "preset") or "preset"


def _web_ui_require_hypothesis() -> bool:
    """
    Require ``agent_explanation.hypothesis`` on each scenario for POST /api/run-parallel*.

    Default **True**. Disable with ``PATTERN_GAME_REQUIRE_HYPOTHESIS=0`` (or ``false`` / ``no`` / ``off``).
    """
    v = os.environ.get("PATTERN_GAME_REQUIRE_HYPOTHESIS", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


def _prepare_parallel_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Validate POST body for parallel run. Returns ``ok`` + fields or ``ok: False`` + ``error``."""
    recipe_id_in = (data.get("operator_recipe_id") or "").strip() or "custom"
    window_mode = (data.get("evaluation_window_mode") or "12").strip().lower()
    custom_m = data.get("evaluation_window_custom_months")

    try:
        resolved = resolve_ui_evaluation_window(window_mode, custom_m)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    tw_mode = (data.get("trade_window_mode") or "5m").strip().lower()
    try:
        tw_resolved = resolve_ui_trade_window(tw_mode)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    health = get_data_health()
    cap = health.get("max_evaluation_window_calendar_months")
    req_m = int(resolved["effective_calendar_months"])
    cap_warning: str | None = None
    if isinstance(cap, int) and cap > 0 and req_m > cap:
        span_d = health.get("replay_tape_span_days_approx") or health.get("all_bars_span_days")
        span_bit = f"~{round(float(span_d))}d of 5m bars" if isinstance(span_d, (int, float)) else "available 5m bars"
        cap_warning = (
            f"Evaluation window ({req_m} mo) exceeds replay tape length "
            f"(max ~{cap} mo from {span_bit}). "
            "Replay will proceed on the available tape and the final replay_data_audit will show the actual span."
        )

    scenarios: list[dict[str, Any]] = []
    recipe_default_months = 12
    recipe_label = "Custom JSON"

    if recipe_id_in != "custom":
        meta = recipe_meta_by_id(recipe_id_in)
        if not meta:
            return {"ok": False, "error": f"Unknown operator_recipe_id: {recipe_id_in!r}"}
        try:
            scenarios = build_scenarios_for_recipe(recipe_id_in)
        except (FileNotFoundError, ValueError) as e:
            return {"ok": False, "error": str(e)}
        recipe_default_months = int(meta["default_evaluation_window_months"])
        recipe_label = str(meta["operator_label"])
    else:
        raw = data.get("scenarios_json")
        if not raw or not isinstance(raw, str):
            return {"ok": False, "error": "Missing scenarios_json string (Custom JSON mode)"}
        try:
            scenarios = json.loads(raw)
            if isinstance(scenarios, dict) and "scenarios" in scenarios:
                scenarios = scenarios["scenarios"]
            if not isinstance(scenarios, list):
                raise ValueError("scenarios must be a JSON array")
            scenarios = [x for x in scenarios if isinstance(x, dict)]
        except (json.JSONDecodeError, ValueError) as e:
            return {"ok": False, "error": str(e)}
        if scenarios:
            ew0 = scenarios[0].get("evaluation_window")
            if isinstance(ew0, dict) and ew0.get("calendar_months") is not None:
                try:
                    recipe_default_months = int(ew0["calendar_months"])
                except (TypeError, ValueError):
                    recipe_default_months = 12

    if not scenarios:
        return {
            "ok": False,
            "error": "No runnable scenarios (empty list after parse/build). Choose a pattern with scenarios or paste Custom JSON.",
        }

    annotate_scenarios_with_window_and_recipe(
        scenarios,
        recipe_id=recipe_id_in,
        recipe_label=recipe_label,
        recipe_default_calendar_months=recipe_default_months,
        resolved=resolved,
    )
    annotate_scenarios_with_candle_timeframe(scenarios, resolved=tw_resolved)

    _root_for_upload = operator_upload_repo_root()
    use_up = data.get("use_operator_uploaded_strategy")
    apply_uploaded = True
    if use_up is False or (isinstance(use_up, str) and use_up.strip().lower() in ("0", "false", "no", "off")):
        apply_uploaded = False
    operator_upload_manifest_repo_relative: str | None = None
    if apply_uploaded:
        amp = active_manifest_repo_relative(_root_for_upload)
        if amp:
            pabs = (_root_for_upload / amp).resolve()
            if pabs.is_file():
                operator_upload_manifest_repo_relative = amp.replace("\\", "/")
                for s in scenarios:
                    s["manifest_path"] = operator_upload_manifest_repo_relative

    for s in scenarios:
        if "manifest_path" in s and s["manifest_path"]:
            s["manifest_path"] = str(resolve_scenario_manifest_path(s["manifest_path"]))

    fw_ok, fw_msgs = attach_policy_framework_audits(scenarios)
    if not fw_ok:
        return {
            "ok": False,
            "error": fw_msgs[0] if fw_msgs else "Policy framework attach failed",
            "scenario_validation": {"ok": False, "messages": fw_msgs},
        }

    ok_val, val_msgs = validate_scenarios(
        scenarios,
        require_hypothesis=_web_ui_require_hypothesis(),
    )
    if not ok_val:
        return {
            "ok": False,
            "error": val_msgs[0] if val_msgs else "Invalid scenarios",
            "scenario_validation": {"ok": False, "messages": val_msgs},
        }

    val_msgs = list(val_msgs) + list(fw_msgs)
    if cap_warning:
        val_msgs.append(cap_warning)

    max_workers = data.get("max_workers")
    if max_workers is not None:
        try:
            max_workers = int(max_workers)
        except (TypeError, ValueError):
            max_workers = None

    log_path = data.get("log_path")
    if log_path is True or log_path == "1":
        log_path = default_experience_log_jsonl()
    elif log_path:
        log_path = Path(str(log_path))
    else:
        log_path = None

    ew0 = scenarios[0].get("evaluation_window") if scenarios else {}
    # Product default: Decision Context Recall is always on for operator batches (READ+WRITE).
    # UI no longer exposes a toggle; API may still send read/off for rare tooling compatibility.
    cmem_in = str(data.get("context_signature_memory_mode") or "read_write").strip().lower()
    if cmem_in not in ("off", "read", "read_write"):
        return {
            "ok": False,
            "error": f"Invalid context_signature_memory_mode (use off, read, read_write): {data.get('context_signature_memory_mode')!r}",
        }

    operator_batch_audit: dict[str, Any] = {
        "operator_recipe_id": recipe_id_in,
        "operator_recipe_label": recipe_label,
        "evaluation_window_mode": resolved["evaluation_window_mode"],
        "evaluation_window_effective_calendar_months": int(resolved["effective_calendar_months"]),
        "evaluation_window_cap_warning": cap_warning,
        "recipe_default_calendar_months": recipe_default_months,
        "window_overrode_recipe_default": bool(
            isinstance(ew0, dict) and ew0.get("window_overrode_recipe_default")
        ),
        "manifest_path_primary": scenarios[0].get("manifest_path") if scenarios else None,
        "policy_framework_path": scenarios[0].get("policy_framework_path") if scenarios else None,
        "policy_framework_audit": scenarios[0].get("policy_framework_audit") if scenarios else None,
        "context_signature_memory_mode": cmem_in or None,
        "operator_upload_manifest_repo_relative": operator_upload_manifest_repo_relative,
        "trade_window_mode": tw_resolved["trade_window_mode"],
        "candle_timeframe_minutes": int(tw_resolved["candle_timeframe_minutes"]),
        "candle_timeframe_label": tw_resolved.get("candle_timeframe_label"),
    }

    if cmem_in in ("off", "read", "read_write"):
        for s in scenarios:
            s["context_signature_memory_mode"] = cmem_in

    ex_req, ex_err = parse_exam_run_contract_request_v1(data)
    if ex_err:
        return {"ok": False, "error": ex_err}
    op_tf = int(operator_batch_audit["candle_timeframe_minutes"])
    if ex_req and isinstance(ex_req, dict):
        if ex_req.get("candle_timeframe_minutes") is None:
            ex_req["candle_timeframe_minutes"] = op_tf
        elif int(ex_req["candle_timeframe_minutes"]) != op_tf:
            return {
                "ok": False,
                "error": (
                    f"exam_run_contract_v1.candle_timeframe_minutes ({ex_req.get('candle_timeframe_minutes')}) "
                    f"does not match operator trade window ({op_tf})"
                ),
            }
        _prof = normalize_student_reasoning_mode_v1(
            str(ex_req.get("student_brain_profile_v1") or ex_req.get("student_reasoning_mode") or "")
        )
        if _prof == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
            cmem_in = "off"
            operator_batch_audit["context_signature_memory_mode"] = "off"
            operator_batch_audit["operator_run_mode_surface_v1"] = "baseline"
            for s in scenarios:
                s["context_signature_memory_mode"] = "off"
        elif _prof == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
            operator_batch_audit["operator_run_mode_surface_v1"] = "student"
    fp_prev = preview_run_config_fingerprint_sha256_40_v1(scenarios, operator_batch_audit)
    operator_batch_audit["exam_run_contract_request_v1"] = ex_req
    operator_batch_audit["exam_run_fingerprint_preview_sha256_40_v1"] = fp_prev

    return {
        "ok": True,
        "scenarios": scenarios,
        "max_workers": max_workers,
        "log_path": log_path,
        "val_msgs": val_msgs,
        "operator_batch_audit": operator_batch_audit,
        "evaluation_window_resolved": resolved,
        "exam_run_contract_request_v1": ex_req,
        "exam_run_fingerprint_preview_v1": fp_prev,
    }


def _exam_run_line_meta_for_parallel_job_v1(
    *,
    exam_req: dict[str, Any] | None,
    fingerprint_preview: str | None,
    operator_batch_audit: dict[str, Any] | None,
    results: list[dict[str, Any]] | None,
    job_id: str,
    seam_audit: dict[str, Any] | None,
    error: str | None,
) -> dict[str, Any]:
    """GT_DIRECTIVE_015 — scorecard line fields for run mode, skip-cold audit, LLM binding."""
    oba_m = dict(operator_batch_audit or {})
    if results and not error:
        mem = build_memory_context_impact_audit_v1(
            results, operator_batch_audit=oba_m
        )
        fp = str(mem.get("run_config_fingerprint_sha256_40") or "").strip() or None
    else:
        fp = (fingerprint_preview or "").strip() or None
    return build_exam_run_line_meta_v1(
        request=exam_req,
        operator_batch_audit=operator_batch_audit,
        fingerprint_sha256_40=fp,
        job_id=job_id,
        student_seam_observability_v1=seam_audit,
        batch_status="error" if error else "done",
        seam_audit=seam_audit,
    )


def _guard_parallel_batch_not_noop(
    scenarios: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> None:
    """
    Fail closed when the pool returns nothing or successful rows report zero replay depth.

    A batch with zero decision windows and zero bars on **ok** rows is not a completed replay —
    it is surfaced as ``RuntimeError`` so the job records ``error`` and does not masquerade as done.
    """
    if not scenarios:
        raise RuntimeError(
            "internal_empty_scenarios: parallel job had an empty scenario list "
            "(this should have been rejected by _prepare_parallel_payload)."
        )
    if not results:
        raise RuntimeError(
            "parallel_batch_empty_results: worker pool returned zero result rows "
            f"(submitted {len(scenarios)} scenario(s)) — no-op batch."
        )
    ok_rows = [r for r in results if r.get("ok")]
    if not ok_rows:
        return
    agg = aggregate_batch_learning_run_audit_v1(results)
    dw = int(agg.get("replay_decision_windows_sum") or 0)
    bars = int(agg.get("replay_bars_processed_sum") or 0)
    if dw <= 0 and bars <= 0:
        raise RuntimeError(
            "replay_noop_batch: successful scenario rows report zero decision windows and zero bars processed "
            f"(submitted={len(scenarios)}, result_rows={len(results)}, ok_rows={len(ok_rows)}). "
            "Replay did not consume tape — check market_bars_5m, manifest paths, and evaluation window."
        )


def _telemetry_context_for_parallel_job(operator_batch_audit: dict[str, Any]) -> dict[str, Any]:
    """Static fields merged into per-worker telemetry files (plus live counters from replay)."""
    rid = str(operator_batch_audit.get("operator_recipe_id") or "").strip()
    pfa = operator_batch_audit.get("policy_framework_audit")
    fw_id = pfa.get("framework_id") if isinstance(pfa, dict) else None
    harness = rid in OPERATOR_LEARNING_HARNESS_RECIPE_IDS
    return {
        "operator_recipe_id": rid or None,
        "operator_recipe_label": operator_batch_audit.get("operator_recipe_label"),
        "policy_framework_id": fw_id,
        "evaluation_window_calendar_months": operator_batch_audit.get(
            "evaluation_window_effective_calendar_months"
        ),
        "candle_timeframe_minutes": operator_batch_audit.get("candle_timeframe_minutes"),
        "learning_path_mode": (
            "operator_harness_candidate_search" if harness else "baseline_replay_only"
        ),
        "candidate_search_active": harness,
        "context_signature_memory_mode": operator_batch_audit.get("context_signature_memory_mode"),
    }


def _batch_pnl_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum Referee ``cumulative_pnl`` across successful scenarios (independent replays, not one portfolio)."""
    start = float(PATTERN_GAME_STARTING_EQUITY_USD_SPEC)
    total = 0.0
    for r in results:
        if not r.get("ok"):
            continue
        p = r.get("cumulative_pnl")
        if isinstance(p, (int, float)):
            total += float(p)
    return {
        "starting_equity_usd": start,
        "batch_total_pnl_usd": total,
        "ending_equity_usd": start + total,
        "note": (
            "Paper baseline is the spec $1k starting equity per replay. "
            "A multi-scenario batch sums each scenario’s cumulative PnL (separate runs)."
        ),
    }


def _render_page_html() -> str:
    lim = get_parallel_limits()
    return (
        PAGE_HTML.replace("__LIMITS_JSON__", json.dumps(lim))
        .replace("__STARTING_EQUITY__", str(float(PATTERN_GAME_STARTING_EQUITY_USD_SPEC)))
        .replace("__PATTERN_GAME_WEB_UI_VERSION__", PATTERN_GAME_WEB_UI_VERSION)
    )


def create_app() -> Flask:
    apply_main_process_runtime_env_defaults()
    ensure_pml_runtime_dirs()
    ensure_memory_root_tree()
    app = Flask(__name__)

    @app.get("/")
    def index() -> Response:
        resp = Response(_render_page_html(), mimetype="text/html; charset=utf-8")
        resp.headers["X-Pattern-Game-UI-Version"] = PATTERN_GAME_WEB_UI_VERSION
        return resp

    @app.get("/assets/pattern-banner.png")
    def pattern_banner_png() -> Response:
        """Top-of-page banner image (``renaissance_v4/assets/pattern.png``)."""
        if not _PATTERN_BANNER_PATH.is_file():
            abort(404)
        return send_file(_PATTERN_BANNER_PATH, mimetype="image/png")

    @app.get("/assets/pattern-banner.webp")
    def pattern_banner_webp() -> Response:
        """Lightweight WebP for the same art (see ``_PATTERN_BANNER_WEBP_PATH``)."""
        if not _PATTERN_BANNER_WEBP_PATH.is_file():
            abort(404)
        return send_file(_PATTERN_BANNER_WEBP_PATH, mimetype="image/webp")

    @app.get("/assets/pattern-banner.jpg")
    def pattern_banner_jpg_legacy() -> Response:
        """Legacy URL — serves the same PNG asset."""
        if not _PATTERN_BANNER_PATH.is_file():
            abort(404)
        return send_file(_PATTERN_BANNER_PATH, mimetype="image/png")

    @app.get("/assets/pattern-game-banner-boot.js")
    def pattern_game_banner_boot_js() -> Response:
        """Banner API bootstrap loaded before the large inline script (strict CSP compatibility)."""
        if not _PATTERN_GAME_BANNER_BOOT_JS.is_file():
            abort(404)
        return send_file(_PATTERN_GAME_BANNER_BOOT_JS, mimetype="application/javascript; charset=utf-8")

    @app.get("/api/capabilities")
    def capabilities() -> Any:
        h = get_data_health()
        return jsonify(
            {
                **get_parallel_limits(),
                "pattern_game_web_ui_version": PATTERN_GAME_WEB_UI_VERSION,
                "max_evaluation_window_calendar_months": h.get("max_evaluation_window_calendar_months"),
                "replay_tape_span_days_approx": h.get("replay_tape_span_days_approx"),
                **runtime_status_snapshot(),
            }
        )

    @app.get("/api/reasoning-model/status")
    def api_reasoning_model_status() -> Any:
        """Live unified reasoning stack: router config merge, Ollama probe, optional ``job_id`` trace slice."""
        jid = (request.args.get("job_id") or "").strip() or None
        return jsonify(get_reasoning_model_operator_snapshot_v1(jid))

    @app.post("/api/reasoning-model/external-gateway")
    def api_reasoning_model_external_gateway() -> Any:
        """Operator toggle — blocks external escalation only (local reasoning unchanged). JSON: ``external_api_gateway_enabled`` bool."""
        data = request.get_json(force=True, silent=True) or {}
        if "external_api_gateway_enabled" not in data:
            return jsonify({"ok": False, "error": 'JSON must include "external_api_gateway_enabled" (boolean)'}), 400
        return jsonify(write_operator_external_api_gateway_enabled_v1(bool(data.get("external_api_gateway_enabled"))))

    @app.get("/api/groundhog-memory")
    @app.get("/api/promoted-bundle")
    def api_groundhog_memory_get() -> Any:
        """Promoted memory bundle on disk: wiring signal, path, and optional ATR apply block (legacy route: ``/api/groundhog-memory``)."""
        p = groundhog_bundle_path()
        wiring_signal, wiring_detail = groundhog_wiring_signal()
        bundle: dict[str, Any] | None = None
        if p.is_file():
            try:
                raw = read_groundhog_bundle()
                bundle = raw if isinstance(raw, dict) else None
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
                bundle = None
        return jsonify(
            {
                "ok": True,
                "path": str(p),
                "env_enabled": groundhog_auto_merge_enabled(),
                "exists": p.is_file(),
                "wiring_signal": wiring_signal,
                "wiring_detail": wiring_detail,
                "bundle": bundle,
            }
        )

    @app.post("/api/groundhog-memory")
    @app.post("/api/promoted-bundle")
    def api_groundhog_memory_post() -> Any:
        """Write promoted ATR geometry to the canonical bundle (``pattern_game_memory_bundle_v1``). Legacy path: ``/api/groundhog-memory``."""
        data = request.get_json(force=True, silent=True) or {}
        try:
            a = float(data["atr_stop_mult"])
            b = float(data["atr_target_mult"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"ok": False, "error": "Need numeric atr_stop_mult and atr_target_mult"}), 400
        rid = (data.get("from_run_id") or "").strip() or None
        note = (data.get("note") or "").strip() or None
        path = write_groundhog_bundle(
            atr_stop_mult=a,
            atr_target_mult=b,
            from_run_id=rid,
            note=note,
        )
        return jsonify({"ok": True, "path": str(path), "bundle": read_groundhog_bundle()})

    @app.post("/api/groundhog-memory/clear")
    @app.post("/api/promoted-bundle/clear")
    def api_groundhog_memory_clear() -> Any:
        """Delete only the promoted memory bundle file (ATR container start-over). Legacy path: ``/api/groundhog-memory/clear``."""
        data = request.get_json(force=True, silent=True) or {}
        if not data.get("confirm"):
            return jsonify({"ok": False, "error": 'Request JSON must include "confirm": true'}), 400
        out = clear_groundhog_bundle_file()
        st = student_learning_store_status_v1()
        body: dict[str, Any] = {
            **out,
            "student_proctor_learning_store_unchanged": True,
            "student_proctor_learning_store": {"path": st.get("path"), "line_count": st.get("line_count")},
            "note": (
                "Removed promoted memory bundle file only when it existed. "
                "Experience log, run memory, context signature memory, and batch scorecard were not modified."
            ),
        }
        return jsonify(body), (200 if out.get("ok") else 500)

    @app.post("/api/context-signature-memory/clear")
    def api_context_signature_memory_clear() -> Any:
        """Truncate only the context signature / DCR recall JSONL (granular parity with promoted-bundle clear)."""
        data = request.get_json(force=True, silent=True) or {}
        if not data.get("confirm"):
            return jsonify({"ok": False, "error": 'Request JSON must include "confirm": true'}), 400
        out = truncate_context_signature_memory_store()
        st = student_learning_store_status_v1()
        body = {
            **out,
            "student_proctor_learning_store_unchanged": True,
            "student_proctor_learning_store": {"path": st.get("path"), "line_count": st.get("line_count")},
            "note": (
                "Truncated context signature memory JSONL only. "
                "Promoted memory bundle, experience/run logs, and batch scorecard were not modified."
            ),
        }
        return jsonify(body), (200 if out.get("ok") else 500)

    @app.get("/api/data-health")
    def data_health() -> Any:
        """SQLite reachable, ``market_bars_5m`` present, replay row count, SOLUSDT ~12mo span."""
        return jsonify(get_data_health())

    @app.get("/api/module-board")
    def api_module_board() -> Any:
        """Subsystem wiring truth (DEF-001): each row green/red (or yellow for promoted bundle wiring) + modal copy."""
        return jsonify(compute_pattern_game_module_board())

    @app.get("/api/search-space-estimate")
    def search_space_estimate() -> Any:
        """Finite catalog counts, bar rows, optional batch/worker parallel rounds (see ``search_space_estimate``)."""
        bs = request.args.get("batch_size")
        w = request.args.get("workers")
        try:
            batch_size = int(bs) if bs not in (None, "") else None
        except ValueError:
            batch_size = None
        try:
            workers = int(w) if w not in (None, "") else None
        except ValueError:
            workers = None
        return jsonify(build_search_space_estimate(batch_size=batch_size, workers=workers))

    @app.get("/api/operator-recipes")
    def api_operator_recipes() -> Any:
        """Curated operator playbooks (main UI). Not a directory glob."""
        return jsonify(
            {
                "ok": True,
                "recipes": operator_recipe_catalog(),
                "policy_catalog": policy_catalog(),
                "default_recipe_id": default_recipe_id(),
            }
        )

    @app.get("/api/operator-recipe-preview")
    def api_operator_recipe_preview() -> Any:
        """Return validated scenario JSON for a curated recipe + evaluation window (fills the textarea)."""
        recipe_id = (request.args.get("recipe_id") or default_recipe_id()).strip()
        window_mode = (request.args.get("evaluation_window_mode") or "12").strip().lower()
        cs = request.args.get("evaluation_window_custom_months")
        custom_m: int | None = None
        if cs not in (None, ""):
            try:
                custom_m = int(cs)
            except ValueError:
                return jsonify({"ok": False, "error": "evaluation_window_custom_months must be an integer"}), 400
        prep = _prepare_parallel_payload(
            {
                "operator_recipe_id": recipe_id,
                "evaluation_window_mode": window_mode,
                "evaluation_window_custom_months": custom_m,
                "scenarios_json": "[]",
            }
        )
        if not prep["ok"]:
            if recipe_id == "custom":
                return jsonify(
                    {
                        "ok": False,
                        "error": "Pattern 'custom' is filled from the textarea — no server preview.",
                    }
                ), 400
            return jsonify(dict(prep)), 400
        return jsonify(
            {
                "ok": True,
                "operator_batch_audit": prep["operator_batch_audit"],
                "scenario_count": len(prep["scenarios"]),
                "scenarios_json": json.dumps(prep["scenarios"], indent=2, ensure_ascii=False) + "\n",
            }
        )

    @app.get("/api/scenario-presets")
    def scenario_presets() -> Any:
        """
        **Advanced / examples:** raw ``*.json`` files under ``game_theory/examples/``.

        The main operator dropdown uses :func:`api_operator_recipes` instead of this glob.
        """
        ex = _GAME_THEORY / "examples"
        rows: list[dict[str, Any]] = []
        for p in sorted(ex.glob("*.json")):
            fn = p.name
            if fn.startswith("user_") and fn.endswith(".json"):
                label = "Uploaded: " + fn[5:-5].replace("_", " ")
                kind = "user"
            else:
                label = fn.replace("_", " ").replace(".example.json", "").replace(".json", "")
                kind = "builtin"
            rows.append({"filename": fn, "label": label, "kind": kind})
        return jsonify(rows)

    @app.get("/api/scenario-preset")
    def scenario_preset() -> Any:
        name = (request.args.get("name") or "").strip()
        if not name or Path(name).name != name:
            abort(400)
        allowed = {p.name for p in (_GAME_THEORY / "examples").glob("*.json")}
        if name not in allowed:
            abort(404)
        p = _GAME_THEORY / "examples" / name
        return jsonify({"ok": True, "filename": name, "content": p.read_text(encoding="utf-8")})

    @app.post("/api/scenario-preset-upload")
    def scenario_preset_upload() -> Any:
        """
        Upload a scenario JSON file and save as **user_<slug>.json** under ``game_theory/examples/``.

        **Standard format:** UTF-8 JSON — either a **JSON array** of scenario objects, or
        ``{\"scenarios\": [ ... ]}``. Same contract as the textarea / ``POST /api/run-parallel``.

        Multipart form: ``file`` (required), ``preset_name`` (required display name for the slug).
        """
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "missing form field: file"}), 400
        preset_name = (request.form.get("preset_name") or "").strip()
        if not preset_name:
            return jsonify({"ok": False, "error": "missing form field: preset_name"}), 400
        up = request.files["file"]
        if not up or not up.filename:
            return jsonify({"ok": False, "error": "empty file upload"}), 400
        raw = up.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"ok": False, "error": "file must be UTF-8 encoded text"}), 400
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return jsonify({"ok": False, "error": f"invalid JSON: {e}"}), 400
        if isinstance(data, dict) and "scenarios" in data:
            scenarios = data["scenarios"]
        elif isinstance(data, list):
            scenarios = data
        else:
            return jsonify(
                {
                    "ok": False,
                    "error": 'JSON must be a list of scenarios or an object with "scenarios" array',
                }
            ), 400
        if not isinstance(scenarios, list):
            return jsonify({"ok": False, "error": "scenarios must be a JSON array"}), 400
        scenarios = [x for x in scenarios if isinstance(x, dict)]
        if not scenarios:
            return jsonify({"ok": False, "error": "no scenario objects in list"}), 400
        ok_val, val_msgs = validate_scenarios(
            scenarios,
            require_hypothesis=_web_ui_require_hypothesis(),
        )
        if not ok_val:
            return jsonify(
                {
                    "ok": False,
                    "error": val_msgs[0] if val_msgs else "scenario validation failed",
                    "messages": val_msgs,
                }
            ), 400
        slug = _slug_preset_display_name(preset_name)
        filename = f"user_{slug}.json"
        dest = _GAME_THEORY / "examples" / filename
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return jsonify({"ok": False, "error": f"cannot create examples directory: {e}"}), 500
        if dest.is_file():
            return jsonify(
                {
                    "ok": False,
                    "error": f"Preset file already exists: {filename}. Pick another name or rename/delete the existing preset.",
                }
            ), 409
        try:
            dest.write_text(
                json.dumps(scenarios, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            return jsonify({"ok": False, "error": f"cannot write preset: {e}"}), 500
        return jsonify({"ok": True, "filename": filename, "saved_as": str(dest)})

    @app.post("/api/scenario-preset-rename")
    def scenario_preset_rename() -> Any:
        """Rename **user_*.json** only. Body JSON: ``old_filename``, ``new_preset_name`` (display name)."""
        data = request.get_json(force=True, silent=True) or {}
        old_fn = (data.get("old_filename") or "").strip()
        new_name = (data.get("new_preset_name") or "").strip()
        if not old_fn or not new_name:
            return jsonify({"ok": False, "error": "old_filename and new_preset_name are required"}), 400
        if Path(old_fn).name != old_fn or not old_fn.startswith("user_") or not old_fn.endswith(".json"):
            return jsonify({"ok": False, "error": "only user-uploaded presets (user_*.json) can be renamed"}), 400
        ex = _GAME_THEORY / "examples"
        old_path = ex / old_fn
        if not old_path.is_file():
            return jsonify({"ok": False, "error": "preset not found"}), 404
        new_slug = _slug_preset_display_name(new_name)
        new_fn = f"user_{new_slug}.json"
        new_path = ex / new_fn
        if new_path.resolve() == old_path.resolve():
            return jsonify({"ok": True, "filename": old_fn, "message": "name unchanged"})
        if new_path.is_file():
            return jsonify({"ok": False, "error": f"target file already exists: {new_fn}"}), 409
        try:
            old_path.rename(new_path)
        except OSError as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        return jsonify({"ok": True, "filename": new_fn})

    @app.post("/api/run")
    def api_run() -> Any:
        data = request.get_json(force=True, silent=True) or {}
        _allow, _disk_warn, disk_block = check_disk_before_run()
        if disk_block:
            return jsonify({"ok": False, "error": disk_block}), 503
        manifest = (data.get("manifest_path") or str(_default_manifest_path())).strip()
        atr_s = data.get("atr_stop_mult")
        atr_t = data.get("atr_target_mult")
        emit = bool(data.get("emit_baseline_artifacts"))
        mb = (data.get("memory_bundle_path") or "").strip() or None
        scen_echo: dict[str, Any] = {}
        if mb:
            scen_echo["memory_bundle_path"] = mb
        if data.get("skip_groundhog_bundle") is not None:
            scen_echo["skip_groundhog_bundle"] = bool(data.get("skip_groundhog_bundle"))
        try:
            out = run_pattern_game(
                manifest,
                atr_stop_mult=float(atr_s) if atr_s not in (None, "") else None,
                atr_target_mult=float(atr_t) if atr_t not in (None, "") else None,
                memory_bundle_path=mb,
                emit_baseline_artifacts=emit,
                verbose=False,
            )
            js = json_summary(out, scenario=scen_echo or None)
            cpn = out.get("cumulative_pnl")
            pnl = float(cpn) if isinstance(cpn, (int, float)) else 0.0
            start = float(PATTERN_GAME_STARTING_EQUITY_USD_SPEC)
            pnl_summary = {
                "starting_equity_usd": start,
                "batch_total_pnl_usd": pnl,
                "ending_equity_usd": start + pnl,
                "note": "Single manifest replay: cumulative PnL vs spec $1k paper baseline.",
            }
            return jsonify(
                {
                    "ok": True,
                    "summary": js,
                    "learning_run_audit_v1": js.get("learning_run_audit_v1"),
                    "operator_learning_status_line_v1": js.get("operator_learning_status_line_v1"),
                    "policy_contract": extract_policy_contract_summary(out.get("manifest_effective")),
                    "referee_session": referee_session_outcome(True, js),
                    "pnl_summary": pnl_summary,
                    "memory_bundle_audit": out.get("memory_bundle_audit"),
                    "memory_bundle_proof": out.get("memory_bundle_proof"),
                }
            )
        except Exception as e:
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 400

    @app.post("/api/run-parallel/start")
    def api_parallel_start() -> Any:
        """Start batch in a background thread; poll with ``GET /api/run-parallel/status/<job_id>``."""
        data = request.get_json(force=True, silent=True) or {}
        prep = _prepare_parallel_payload(data)
        if not prep["ok"]:
            return jsonify(dict(prep)), 400
        _allow, disk_warn_msgs, disk_block = check_disk_before_run()
        if disk_block:
            return jsonify({"ok": False, "error": disk_block}), 503
        scenarios = prep["scenarios"]
        max_workers = prep["max_workers"]
        log_path = prep["log_path"]
        val_msgs = prep["val_msgs"]
        operator_batch_audit = prep["operator_batch_audit"]
        exam_req = prep.get("exam_run_contract_request_v1")
        fp_prev = prep.get("exam_run_fingerprint_preview_v1")

        _prune_jobs()
        job_id = uuid.uuid4().hex
        workers_used = clamp_parallel_workers(max_workers, len(scenarios))
        telem_dir = default_telemetry_dir()
        clear_job_telemetry_files(job_id, base=telem_dir)
        telemetry_ctx = _telemetry_context_for_parallel_job(operator_batch_audit)
        started_iso = utc_timestamp_iso()
        with _JOBS_LOCK:
            _JOBS[job_id] = {
                "status": "running",
                "created": time.time(),
                "started_at_utc": started_iso,
                "total": len(scenarios),
                "completed": 0,
                "workers_used": workers_used,
                "last_scenario_id": None,
                "last_ok": None,
                "last_message": None,
                "error": None,
                "result": None,
                "batch_timing": None,
                "telemetry_dir": str(telem_dir),
                "telemetry_context_echo": telemetry_ctx,
                "cancel_requested": False,
            }

        def run_job() -> None:
            from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
                emit_packet_built_v1,
                emit_referee_execution_completed_v1,
                emit_referee_execution_started_v1,
                emit_seam_disabled_placeholder_events_v1,
                fingerprint_for_parallel_job_v1,
            )

            session_batch_dir: list[str | None] = [None]
            start_unix = time.time()
            lt_fp = fingerprint_for_parallel_job_v1(
                operator_batch_audit=operator_batch_audit if isinstance(operator_batch_audit, dict) else None,
                fingerprint_preview=fp_prev if isinstance(fp_prev, str) else None,
            )

            def on_session_batch(p: Path) -> None:
                session_batch_dir[0] = str(p.resolve())
                emit_packet_built_v1(
                    job_id=job_id,
                    fingerprint=lt_fp,
                    batch_dir=session_batch_dir[0],
                    scenario_count=len(scenarios),
                )

            def cb(completed: int, total: int, row: dict[str, Any]) -> None:
                sid = row.get("scenario_id", "?")
                ok = bool(row.get("ok"))
                msg = f"{sid}: {'ok' if ok else 'failed'}"
                if not ok and row.get("error"):
                    msg += f" ({row.get('error')})"
                with _JOBS_LOCK:
                    j = _JOBS.get(job_id)
                    if j:
                        j["completed"] = completed
                        j["last_scenario_id"] = sid
                        j["last_ok"] = ok
                        j["last_message"] = msg

            results: list[dict[str, Any]] | None = None
            referee_parallel_completed_emit_v1 = False
            try:
                emit_referee_execution_started_v1(
                    job_id=job_id, fingerprint=lt_fp, scenario_total=len(scenarios)
                )
                results = run_scenarios_parallel(
                    scenarios,
                    max_workers=max_workers,
                    experience_log_path=log_path,
                    progress_callback=cb,
                    on_session_log_batch=on_session_batch,
                    telemetry_job_id=job_id,
                    telemetry_dir=telem_dir,
                    telemetry_context=telemetry_ctx,
                    cancel_check=lambda: _parallel_job_cancel_requested(job_id),
                )
                emit_referee_execution_completed_v1(job_id=job_id, fingerprint=lt_fp, results=results)
                referee_parallel_completed_emit_v1 = True
                validate_reference_comparison_batch_results(
                    results, operator_recipe_id=operator_batch_audit.get("operator_recipe_id")
                )
                _guard_parallel_batch_not_noop(scenarios, results)
                gh_promo = promote_groundhog_bundle_from_parallel_scenarios_v1(
                    scenarios, from_run_id=job_id
                )
                ok_n = sum(1 for r in results if r.get("ok"))
                op_rid = str(operator_batch_audit.get("operator_recipe_id") or "").strip() or None
                seam_audit = student_loop_seam_after_parallel_batch_v1(
                    results=results,
                    run_id=job_id,
                    strategy_id=op_rid,
                    exam_run_contract_request_v1=exam_req if isinstance(exam_req, dict) else None,
                    operator_batch_audit=operator_batch_audit
                    if isinstance(operator_batch_audit, dict)
                    else None,
                )
                if seam_audit.get("skipped"):
                    emit_seam_disabled_placeholder_events_v1(
                        job_id=job_id,
                        fingerprint=lt_fp,
                        reason=str(seam_audit.get("reason") or "skipped"),
                    )
                auto_stu = apply_automated_student_lanes_from_exam_contract_v1(
                    results=results,
                    scenarios=scenarios,
                    job_id=job_id,
                    exam_run_contract_request_v1=exam_req if isinstance(exam_req, dict) else None,
                    seam_audit=seam_audit,
                    fingerprint=lt_fp,
                )
                seam_audit["automated_student_lane_batch_audit_v1"] = auto_stu
                exam_line = _exam_run_line_meta_for_parallel_job_v1(
                    exam_req=exam_req if isinstance(exam_req, dict) else None,
                    fingerprint_preview=fp_prev if isinstance(fp_prev, str) else None,
                    operator_batch_audit=operator_batch_audit,
                    results=results,
                    job_id=job_id,
                    seam_audit=seam_audit,
                    error=None,
                )
                timing = record_parallel_batch_finished(
                    job_id=job_id,
                    started_at_utc=started_iso,
                    start_unix=start_unix,
                    total_scenarios=len(scenarios),
                    workers_used=workers_used,
                    results=results,
                    session_log_batch_dir=session_batch_dir[0],
                    error=None,
                    operator_batch_audit=operator_batch_audit,
                    student_seam_observability_v1=seam_audit,
                    exam_run_line_meta_v1=exam_line,
                )
                payload = {
                    "ok": True,
                    "job_id": job_id,
                    "ran": len(results),
                    "ok_count": ok_n,
                    "failed_count": len(results) - ok_n,
                    "results": results,
                    "pnl_summary": _batch_pnl_summary(results),
                    "limits_applied": get_parallel_limits(),
                    "workers_used": workers_used,
                    "scenario_validation": {"ok": True, "messages": val_msgs},
                    "session_log_batch_dir": session_batch_dir[0],
                    "batch_timing": timing,
                    "operator_batch_audit": operator_batch_audit,
                    "learning_batch_audit_v1": timing.get("learning_batch_audit_v1"),
                    "batch_depth_v1": timing.get("batch_depth_v1"),
                    "batch_run_classification_v1": timing.get("batch_run_classification_v1"),
                    "operator_learning_status_line_v1": timing.get("operator_learning_status_line_v1"),
                    "student_loop_directive_09_v1": seam_audit,
                    "student_learning_rows_appended": int(
                        seam_audit.get("student_learning_rows_appended") or 0
                    ),
                    "student_retrieval_matches": int(seam_audit.get("student_retrieval_matches") or 0),
                    "student_output_fingerprint": seam_audit.get("student_output_fingerprint"),
                    "shadow_student_enabled": bool(seam_audit.get("shadow_student_enabled")),
                    "groundhog_auto_promote_v1": gh_promo,
                }
                with _JOBS_LOCK:
                    j = _JOBS.get(job_id)
                    if j:
                        j["status"] = "done"
                        j["completed"] = len(results)
                        j["result"] = payload
                        j["batch_timing"] = timing
            except ParallelBatchCancelledError as e:
                emit_referee_execution_completed_v1(
                    job_id=job_id, fingerprint=lt_fp, results=list(e.partial_results or [])
                )
                referee_parallel_completed_emit_v1 = True
                partial = e.partial_results
                err_s = (
                    f"Cancelled by operator — {len(partial)}/{len(scenarios)} scenario result(s) "
                    "returned before remaining work was stopped."
                )
                exam_line_err = _exam_run_line_meta_for_parallel_job_v1(
                    exam_req=exam_req if isinstance(exam_req, dict) else None,
                    fingerprint_preview=fp_prev if isinstance(fp_prev, str) else None,
                    operator_batch_audit=operator_batch_audit,
                    results=partial if partial else None,
                    job_id=job_id,
                    seam_audit=None,
                    error=err_s,
                )
                timing = record_parallel_batch_finished(
                    job_id=job_id,
                    started_at_utc=started_iso,
                    start_unix=start_unix,
                    total_scenarios=len(scenarios),
                    workers_used=workers_used,
                    results=None,
                    session_log_batch_dir=session_batch_dir[0],
                    error=err_s,
                    operator_batch_audit=operator_batch_audit,
                    student_seam_observability_v1=None,
                    exam_run_line_meta_v1=exam_line_err,
                    parallel_cancel_partial_results=partial,
                )
                with _JOBS_LOCK:
                    j = _JOBS.get(job_id)
                    if j:
                        j["status"] = "cancelled"
                        j["completed"] = len(partial)
                        j["error"] = err_s
                        j["batch_timing"] = timing
                        j["last_message"] = err_s
            except Exception as e:
                if not referee_parallel_completed_emit_v1:
                    emit_referee_execution_completed_v1(
                        job_id=job_id, fingerprint=lt_fp, results=list(results) if results is not None else []
                    )
                err_s = f"{type(e).__name__}: {e}"
                exam_line_err = _exam_run_line_meta_for_parallel_job_v1(
                    exam_req=exam_req if isinstance(exam_req, dict) else None,
                    fingerprint_preview=fp_prev if isinstance(fp_prev, str) else None,
                    operator_batch_audit=operator_batch_audit,
                    results=None,
                    job_id=job_id,
                    seam_audit=None,
                    error=err_s,
                )
                timing = record_parallel_batch_finished(
                    job_id=job_id,
                    started_at_utc=started_iso,
                    start_unix=start_unix,
                    total_scenarios=len(scenarios),
                    workers_used=workers_used,
                    results=None,
                    session_log_batch_dir=None,
                    error=err_s,
                    operator_batch_audit=operator_batch_audit,
                    exam_run_line_meta_v1=exam_line_err,
                )
                with _JOBS_LOCK:
                    j = _JOBS.get(job_id)
                    if j:
                        j["status"] = "error"
                        j["error"] = err_s
                        j["batch_timing"] = timing
            finally:
                try:
                    prune_pml_runtime_batch_dirs()
                except Exception:
                    pass

        threading.Thread(target=run_job, daemon=True).start()
        start_body: dict[str, Any] = {
            "ok": True,
            "job_id": job_id,
            "total": len(scenarios),
            "workers_used": workers_used,
        }
        if disk_warn_msgs:
            start_body["operator_disk_warnings"] = disk_warn_msgs
        return jsonify(start_body)

    @app.get("/api/run-parallel/status/<job_id>")
    @app.get("/api/run-status/<job_id>")
    def api_parallel_status(job_id: str) -> Any:
        _prune_jobs()
        with _JOBS_LOCK:
            j = _JOBS.get(job_id)
        if not j:
            return jsonify({"ok": False, "error": "Unknown or expired job_id"}), 404
        out: dict[str, Any] = {
            "ok": True,
            "status": j["status"],
            "total": j["total"],
            "completed": j["completed"],
            "workers_used": j.get("workers_used"),
            "last_scenario_id": j.get("last_scenario_id"),
            "last_ok": j.get("last_ok"),
            "last_message": j.get("last_message"),
        }
        if j.get("started_at_utc"):
            out["started_at_utc"] = j["started_at_utc"]
        if j.get("telemetry_context_echo") is not None:
            out["telemetry_context_echo"] = j["telemetry_context_echo"]
        td = j.get("telemetry_dir")
        if td:
            try:
                out["telemetry"] = read_job_telemetry_v1(job_id, base=Path(td))
            except OSError:
                out["telemetry"] = {
                    "schema": "pattern_game_live_telemetry_v1",
                    "job_id": job_id,
                    "scenarios": [],
                    "read_at_unix": time.time(),
                }
        if j.get("error"):
            out["error"] = j["error"]
        if j.get("batch_timing") is not None:
            out["batch_timing"] = j["batch_timing"]
        if j["status"] == "done" and j.get("result"):
            out["result"] = j["result"]
        return jsonify(out)

    @app.post("/api/run-parallel/cancel/<job_id>")
    @app.post("/api/run-status/cancel/<job_id>")
    def api_parallel_cancel(job_id: str) -> Any:
        """
        Request cancellation of a **running** parallel job started from this Flask process.

        Sets ``cancel_requested`` on the in-memory job; the pool stops scheduling new scenarios and
        raises :class:`ParallelBatchCancelledError` when the runner observes the flag. Already-running
        worker processes are not SIGKILL'd — they may complete while the parent tears down pending futures.
        """
        jid = str(job_id or "").strip()
        if not jid:
            return jsonify({"ok": False, "error": "job_id required"}), 400
        _prune_jobs()
        with _JOBS_LOCK:
            j = _JOBS.get(jid)
            if not j:
                return jsonify({"ok": False, "error": "Unknown or expired job_id"}), 404
            st = str(j.get("status") or "").strip().lower()
            if st != "running":
                return jsonify(
                    {"ok": False, "error": f"Job is not running (status={j.get('status')!r})"}
                ), 400
            j["cancel_requested"] = True
        return jsonify({"ok": True, "job_id": jid, "cancel_requested": True})

    @app.post("/api/barney-summary")
    def api_barney_summary() -> Any:
        """
        System Dialogue — plain-English recap from structured facts for a **completed** parallel job.

        Body JSON: ``{"job_id": "<hex>"}`` (in-memory job on this Flask host).
        """
        data = request.get_json(force=True, silent=True) or {}
        jid = str(data.get("job_id") or "").strip()
        if not jid:
            return jsonify({"ok": False, "error": "job_id is required"}), 400
        with _JOBS_LOCK:
            j = _JOBS.get(jid)
        if not j:
            return jsonify({"ok": False, "error": "job not found or expired — run finished too long ago"}), 404
        st = str(j.get("status") or "")
        if st not in ("done", "error"):
            return jsonify({"ok": False, "error": f"job is still {st!r}; wait for completion"}), 400
        res = j.get("result") if isinstance(j.get("result"), dict) else None
        bt = j.get("batch_timing") if isinstance(j.get("batch_timing"), dict) else None
        echo = j.get("telemetry_context_echo") if isinstance(j.get("telemetry_context_echo"), dict) else None
        facts = build_barney_facts_from_job_state(
            status=st,
            error_message=j.get("error"),
            parallel_result=res,
            batch_timing=bt,
            telemetry_echo=echo,
        )
        out = barney_summarize_job_facts(facts)
        return jsonify({"ok": True, "facts": facts, **out})

    @app.post("/api/ask-data")
    def api_ask_data() -> Any:
        """
        Ask DATA — bounded self-explainer (PML + run facts). Body JSON::

            {
              "question": "...",
              "job_id": "<hex optional>",
              "ui_context": { ... optional, server-sanitized keys only }
            }

        When ``ASK_DATA_OPERATOR_FEEDBACK`` is enabled (default), JSON includes ``interaction_id``
        (use with ``POST /api/ask-data/feedback``) and ``question_fingerprint`` for deduplication.
        """
        data = request.get_json(force=True, silent=True) or {}
        question = str(data.get("question") or "").strip()
        if not question:
            return jsonify({"ok": False, "error": "question is required"}), 400
        if len(question) > 6000:
            return jsonify({"ok": False, "error": "question too long (max 6000 characters)"}), 400
        jid = str(data.get("job_id") or "").strip() or None
        ui_ctx = sanitize_ui_context(data.get("ui_context"))

        barney_facts: dict[str, Any] | None = None
        score_snap: dict[str, Any] | None = None
        job_res = "no_job"

        if jid:
            j: dict[str, Any] | None = None
            with _JOBS_LOCK:
                j = _JOBS.get(jid)
            if j:
                st = str(j.get("status") or "")
                if st in ("done", "error"):
                    res = j.get("result") if isinstance(j.get("result"), dict) else None
                    bt = j.get("batch_timing") if isinstance(j.get("batch_timing"), dict) else None
                    echo = j.get("telemetry_context_echo") if isinstance(j.get("telemetry_context_echo"), dict) else None
                    barney_facts = build_barney_facts_from_job_state(
                        status=st,
                        error_message=j.get("error"),
                        parallel_result=res,
                        batch_timing=bt,
                        telemetry_echo=echo,
                    )
                    job_res = "live_job_terminal"
                elif st == "running":
                    return jsonify(
                        {
                            "ok": False,
                            "error": "job is still running — Ask DATA run facts are available after the batch completes",
                        }
                    ), 400
                else:
                    job_res = f"job_status:{st}"
            entry = find_scorecard_entry_by_job_id(jid)
            sc = scorecard_snapshot_for_ask(entry)
            if sc:
                score_snap = sc
                if barney_facts is None:
                    job_res = "scorecard_only"
            elif not j:
                job_res = "job_unknown"

        op_state = operator_strategy_public_state(_BLACKBOX_REPO_ROOT)
        bundle = build_ask_data_bundle_v1(
            barney_facts=barney_facts,
            scorecard_snapshot=score_snap,
            ui_context=ui_ctx,
            operator_strategy_state=op_state,
            job_resolution=job_res,
        )
        out = ask_data_answer(question, bundle, job_id=jid)
        return jsonify({"ok": out.get("ok", False), "bundle_meta": {"job_resolution": job_res, "job_id": jid}, **out})

    @app.post("/api/ask-data/feedback")
    def api_ask_data_feedback() -> Any:
        """
        Record operator signal for a prior Ask DATA turn. Body JSON::

            {
              "interaction_id": "<hex from ask-data response>",
              "rating": "up" | "down" | "neutral",
              "tags": ["optional", "short_slugs"],
              "note": "optional short text"
            }
        """
        from renaissance_v4.game_theory.ask_data_operator_feedback_v1 import (
            append_ask_data_feedback_telemetry_v1,
            ask_data_operator_feedback_enabled_v1,
            interaction_exists_in_telemetry_v1,
            interaction_feedback_already_recorded_v1,
            lookup_interaction_meta_v1,
        )

        if not ask_data_operator_feedback_enabled_v1():
            return jsonify({"ok": False, "error": "ASK_DATA_OPERATOR_FEEDBACK is disabled"}), 503
        data = request.get_json(force=True, silent=True) or {}
        iid = str(data.get("interaction_id") or "").strip()
        if not iid or len(iid) > 64:
            return jsonify({"ok": False, "error": "interaction_id is required"}), 400
        rating = str(data.get("rating") or "").strip().lower()
        if rating not in ("up", "down", "neutral"):
            return jsonify({"ok": False, "error": "rating must be up, down, or neutral"}), 400
        raw_tags = data.get("tags")
        tags: list[str] = []
        if isinstance(raw_tags, list):
            for t in raw_tags[:8]:
                if isinstance(t, str) and t.strip():
                    tags.append(t.strip()[:40])
        note = str(data.get("note") or "").strip()[:500]

        if not interaction_exists_in_telemetry_v1(iid):
            return jsonify({"ok": False, "error": "unknown interaction_id (too old or invalid)"}), 404
        if interaction_feedback_already_recorded_v1(iid):
            return jsonify({"ok": False, "error": "feedback already recorded for this interaction"}), 409
        meta = lookup_interaction_meta_v1(iid)
        fp = str((meta or {}).get("question_fingerprint") or "")
        if not fp:
            return jsonify({"ok": False, "error": "interaction record missing fingerprint"}), 500
        ok, err = append_ask_data_feedback_telemetry_v1(
            interaction_id=iid,
            question_fingerprint=fp,
            rating=rating,
            tags=tags,
            note=note,
        )
        if not ok:
            return jsonify({"ok": False, "error": err or "append failed"}), 500
        return jsonify({"ok": True, "error": None})

    @app.get("/api/operator/ollama-role-routing")
    def api_operator_ollama_role_routing() -> Any:
        """Resolved Ollama bases/models per operator role (lab defaults overridable via env)."""
        from renaissance_v4.game_theory.ollama_role_routing_v1 import ollama_role_routing_snapshot_v1

        return jsonify(ollama_role_routing_snapshot_v1())

    @app.post("/api/run-parallel")
    def api_parallel() -> Any:
        """Blocking batch run (same work as ``/start`` + poll until done). Prefer ``/start`` for the UI."""
        data = request.get_json(force=True, silent=True) or {}
        prep = _prepare_parallel_payload(data)
        if not prep["ok"]:
            return jsonify(dict(prep)), 400
        _allow, disk_warn_msgs, disk_block = check_disk_before_run()
        if disk_block:
            return jsonify({"ok": False, "error": disk_block}), 503
        scenarios = prep["scenarios"]
        max_workers = prep["max_workers"]
        log_path = prep["log_path"]
        val_msgs = prep["val_msgs"]
        operator_batch_audit = prep["operator_batch_audit"]
        exam_req_block = prep.get("exam_run_contract_request_v1")
        fp_prev_block = prep.get("exam_run_fingerprint_preview_v1")

        job_id = uuid.uuid4().hex
        started_iso = utc_timestamp_iso()
        start_unix = time.time()
        workers_used = clamp_parallel_workers(max_workers, len(scenarios))
        telem_dir = default_telemetry_dir()
        clear_job_telemetry_files(job_id, base=telem_dir)
        telemetry_ctx = _telemetry_context_for_parallel_job(operator_batch_audit)
        try:
            from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
                emit_packet_built_v1,
                emit_referee_execution_completed_v1,
                emit_referee_execution_started_v1,
                emit_seam_disabled_placeholder_events_v1,
                fingerprint_for_parallel_job_v1,
            )

            lt_fp_block = fingerprint_for_parallel_job_v1(
                operator_batch_audit=operator_batch_audit if isinstance(operator_batch_audit, dict) else None,
                fingerprint_preview=fp_prev_block if isinstance(fp_prev_block, str) else None,
            )
            session_batch_dir: list[str | None] = [None]

            def on_session_batch(p: Path) -> None:
                session_batch_dir[0] = str(p.resolve())
                emit_packet_built_v1(
                    job_id=job_id,
                    fingerprint=lt_fp_block,
                    batch_dir=session_batch_dir[0],
                    scenario_count=len(scenarios),
                )

            emit_referee_execution_started_v1(
                job_id=job_id, fingerprint=lt_fp_block, scenario_total=len(scenarios)
            )
            results: list[dict[str, Any]] | None = None
            referee_parallel_completed_emit_block_v1 = False
            try:
                results = run_scenarios_parallel(
                    scenarios,
                    max_workers=max_workers,
                    experience_log_path=log_path,
                    on_session_log_batch=on_session_batch,
                    telemetry_job_id=job_id,
                    telemetry_dir=telem_dir,
                    telemetry_context=telemetry_ctx,
                )
                emit_referee_execution_completed_v1(
                    job_id=job_id, fingerprint=lt_fp_block, results=results
                )
                referee_parallel_completed_emit_block_v1 = True
            except ParallelBatchCancelledError as e:
                emit_referee_execution_completed_v1(
                    job_id=job_id, fingerprint=lt_fp_block, results=list(e.partial_results or [])
                )
                referee_parallel_completed_emit_block_v1 = True
                raise
            except Exception:
                if not referee_parallel_completed_emit_block_v1:
                    emit_referee_execution_completed_v1(
                        job_id=job_id,
                        fingerprint=lt_fp_block,
                        results=list(results) if results is not None else [],
                    )
                raise
            validate_reference_comparison_batch_results(
                results, operator_recipe_id=operator_batch_audit.get("operator_recipe_id")
            )
            _guard_parallel_batch_not_noop(scenarios, results)
            gh_promo_block = promote_groundhog_bundle_from_parallel_scenarios_v1(
                scenarios, from_run_id=job_id
            )
            ok_n = sum(1 for r in results if r.get("ok"))
            op_rid_block = str(operator_batch_audit.get("operator_recipe_id") or "").strip() or None
            seam_blocking = student_loop_seam_after_parallel_batch_v1(
                results=results,
                run_id=job_id,
                strategy_id=op_rid_block,
                exam_run_contract_request_v1=exam_req_block if isinstance(exam_req_block, dict) else None,
                operator_batch_audit=operator_batch_audit
                if isinstance(operator_batch_audit, dict)
                else None,
            )
            if seam_blocking.get("skipped"):
                emit_seam_disabled_placeholder_events_v1(
                    job_id=job_id,
                    fingerprint=lt_fp_block,
                    reason=str(seam_blocking.get("reason") or "skipped"),
                )
            auto_stu_block = apply_automated_student_lanes_from_exam_contract_v1(
                results=results,
                scenarios=scenarios,
                job_id=job_id,
                exam_run_contract_request_v1=exam_req_block if isinstance(exam_req_block, dict) else None,
                seam_audit=seam_blocking,
                fingerprint=lt_fp_block,
            )
            seam_blocking["automated_student_lane_batch_audit_v1"] = auto_stu_block
            exam_line_block = _exam_run_line_meta_for_parallel_job_v1(
                exam_req=exam_req_block if isinstance(exam_req_block, dict) else None,
                fingerprint_preview=fp_prev_block if isinstance(fp_prev_block, str) else None,
                operator_batch_audit=operator_batch_audit,
                results=results,
                job_id=job_id,
                seam_audit=seam_blocking,
                error=None,
            )
            timing = record_parallel_batch_finished(
                job_id=job_id,
                started_at_utc=started_iso,
                start_unix=start_unix,
                total_scenarios=len(scenarios),
                workers_used=workers_used,
                results=results,
                session_log_batch_dir=session_batch_dir[0],
                error=None,
                operator_batch_audit=operator_batch_audit,
                student_seam_observability_v1=seam_blocking,
                exam_run_line_meta_v1=exam_line_block,
            )
            ok_body: dict[str, Any] = {
                "ok": True,
                "job_id": job_id,
                "ran": len(results),
                "ok_count": ok_n,
                "failed_count": len(results) - ok_n,
                "results": results,
                "pnl_summary": _batch_pnl_summary(results),
                "limits_applied": get_parallel_limits(),
                "workers_used": workers_used,
                "scenario_validation": {"ok": True, "messages": val_msgs},
                "session_log_batch_dir": session_batch_dir[0],
                "batch_timing": timing,
                "operator_batch_audit": operator_batch_audit,
                "learning_batch_audit_v1": timing.get("learning_batch_audit_v1"),
                "batch_depth_v1": timing.get("batch_depth_v1"),
                "batch_run_classification_v1": timing.get("batch_run_classification_v1"),
                "operator_learning_status_line_v1": timing.get("operator_learning_status_line_v1"),
                "student_loop_directive_09_v1": seam_blocking,
                "student_learning_rows_appended": int(
                    seam_blocking.get("student_learning_rows_appended") or 0
                ),
                "student_retrieval_matches": int(seam_blocking.get("student_retrieval_matches") or 0),
                "student_output_fingerprint": seam_blocking.get("student_output_fingerprint"),
                "shadow_student_enabled": bool(seam_blocking.get("shadow_student_enabled")),
                "groundhog_auto_promote_v1": gh_promo_block,
            }
            if disk_warn_msgs:
                ok_body["operator_disk_warnings"] = disk_warn_msgs
            return jsonify(ok_body)
        except Exception as e:
            err_s = f"{type(e).__name__}: {e}"
            exam_line_block_err = _exam_run_line_meta_for_parallel_job_v1(
                exam_req=exam_req_block if isinstance(exam_req_block, dict) else None,
                fingerprint_preview=fp_prev_block if isinstance(fp_prev_block, str) else None,
                operator_batch_audit=operator_batch_audit,
                results=None,
                job_id=job_id,
                seam_audit=None,
                error=err_s,
            )
            timing = record_parallel_batch_finished(
                job_id=job_id,
                started_at_utc=started_iso,
                start_unix=start_unix,
                total_scenarios=len(scenarios),
                workers_used=workers_used,
                results=None,
                session_log_batch_dir=None,
                error=err_s,
                operator_batch_audit=operator_batch_audit,
                exam_run_line_meta_v1=exam_line_block_err,
            )
            return jsonify({"ok": False, "error": err_s, "job_id": job_id, "batch_timing": timing}), 400
        finally:
            try:
                prune_pml_runtime_batch_dirs()
            except Exception:
                pass

    @app.get("/api/batch-scorecard")
    def api_batch_scorecard() -> Any:
        """Recent batch timing lines from ``batch_scorecard.jsonl`` (newest first), plus in-flight runs."""
        try:
            limit = int(request.args.get("limit") or 25)
        except (TypeError, ValueError):
            limit = 25
        limit = max(1, min(200, limit))
        p = default_batch_scorecard_jsonl()
        rows = read_batch_scorecard_recent(limit, path=p)
        merged, inflight_n = _merge_scorecard_with_inflight(rows, limit=limit)
        return jsonify(
            {
                "ok": True,
                "path": str(p.resolve()),
                "limit": limit,
                "entries": merged,
                "inflight_batches": inflight_n,
            }
        )

    @app.get("/api/batch-scorecard.csv")
    def api_batch_scorecard_csv() -> Any:
        """CSV export of recent batch scorecard rows (same columns as GT_DIRECTIVE_001)."""
        try:
            limit = int(request.args.get("limit") or 25)
        except (TypeError, ValueError):
            limit = 25
        limit = max(1, min(200, limit))
        p = default_batch_scorecard_jsonl()
        rows = read_batch_scorecard_recent(limit, path=p)
        merged, _inflight_n = _merge_scorecard_with_inflight(rows, limit=limit)
        body = scorecard_history_csv(merged)
        return Response(
            body,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="pattern_game_batch_scorecard_history.csv"'
            },
        )

    @app.post("/api/batch-scorecard/clear")
    def api_batch_scorecard_clear() -> Any:
        """
        Truncate ``batch_scorecard.jsonl`` only (batch audit / UI / hunter rotation input).

        Does **not** modify experience log, run memory, promoted memory bundle, context signature memory,
        the Student Proctor learning store JSONL, retrospective, or session batch folders on disk.
        """
        data = request.get_json(force=True, silent=True) or {}
        if not data.get("confirm"):
            return jsonify({"ok": False, "error": 'Request JSON must include "confirm": true'}), 400
        p = truncate_batch_scorecard_jsonl()
        st = student_learning_store_status_v1()
        return jsonify(
            {
                "ok": True,
                "path": str(p),
                "note": (
                    "Truncated batch scorecard file only. Engine learning files "
                    "(bundles, recall memory JSONL, experience/run logs) and the Student Proctor "
                    "learning store were not modified."
                ),
                "student_proctor_learning_store_unchanged": True,
                "student_proctor_learning_store": {
                    "path": st.get("path"),
                    "line_count": st.get("line_count"),
                },
            }
        )

    @app.delete("/api/batch-scorecard/run/<job_id>")
    def api_batch_scorecard_delete_run(job_id: str) -> Any:
        """
        D14-6 — remove scorecard line(s) for one ``job_id`` only. Does **not** modify promoted memory bundles
        or engine learning (use ``POST /api/pattern-game/reset-learning`` separately).
        """
        data = request.get_json(force=True, silent=True) or {}
        if not data.get("confirm"):
            return jsonify({"ok": False, "error": 'Request JSON must include "confirm": true'}), 400
        out = remove_batch_scorecard_line_by_job_id(job_id.strip())
        st = student_learning_store_status_v1()
        out2 = dict(out)
        out2["groundhog_unchanged"] = True
        out2["student_proctor_learning_store_unchanged"] = True
        out2["student_proctor_learning_store"] = {
            "path": st.get("path"),
            "line_count": st.get("line_count"),
        }
        return jsonify(out2), (200 if out.get("ok") else 400)

    @app.post("/api/pattern-game/reset-learning")
    def api_pattern_game_reset_learning() -> Any:
        """
        Destructive: truncate experience + run memory JSONL, context-signature memory, delete promoted memory bundle.

        Does **not** truncate ``batch_scorecard.jsonl``, ``retrospective_log.jsonl``, or the Student Proctor
        learning store (use ``POST /api/student-proctor/learning-store/clear``).
        """
        data = request.get_json(force=True, silent=True) or {}
        c = data.get("confirm")
        if not isinstance(c, str):
            return jsonify(
                {
                    "ok": False,
                    "error": f'confirm must be the exact string {RESET_PATTERN_GAME_LEARNING_CONFIRM!r}',
                }
            ), 400
        out = reset_pattern_game_engine_learning_state_v1(confirm=c.strip())
        if not out.get("ok") and not out.get("cleared"):
            return jsonify(out), 400
        st = student_learning_store_status_v1()
        out2 = dict(out)
        out2["student_proctor_learning_store_unchanged"] = True
        out2["student_proctor_learning_store"] = {"path": st.get("path"), "line_count": st.get("line_count")}
        return jsonify(out2), (200 if out.get("ok") else 500)

    @app.get("/api/student-panel/runs")
    def api_student_panel_runs_d11() -> Any:
        """D11 — run rows from scorecard file + in-memory **running** jobs (same merge as batch-scorecard)."""
        try:
            limit = int(request.args.get("limit") or 50)
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(200, limit))
        p = default_batch_scorecard_jsonl()
        file_rows = read_batch_scorecard_recent(limit, path=p)
        merged, inflight_n = _merge_scorecard_with_inflight(file_rows, limit=limit)
        rows = enrich_student_panel_run_rows_d14(build_d11_run_rows_v1(merged))
        road = build_l1_road_payload_v1()
        l1_road_overlay_v1 = {
            "schema": "student_panel_l1_road_runs_overlay_v1",
            "legend": road.get("legend"),
            "road_by_job_id_v1": road.get("road_by_job_id_v1") or {},
            "groups": road.get("groups") or [],
            "data_gaps": road.get("data_gaps") or [],
            "note": road.get("note"),
        }
        return jsonify(
            {
                "ok": True,
                "schema": "student_panel_d14_runs_v1",
                "runs": rows,
                "inflight_batches": inflight_n,
                "l1_road_v1": l1_road_overlay_v1,
                "l1_columns_v1": {
                    "harness_baseline_trade_win_percent": (
                        "Sys BL % — batch trade win % of the oldest completed run in the same "
                        "run_config fingerprint chain (anchor for this recipe/window)."
                    ),
                    "run_trade_win_percent": (
                        "Run TW % — this scorecard line's Referee batch rollup trade win %."
                    ),
                    "beats_system_baseline_trade_win": (
                        ">BL — YES if this row is not the anchor and Run TW % > Sys BL %; "
                        "NO if Run TW < Sys BL; = if tie; — on anchor row or missing inputs."
                    ),
                    "exam_e_score_v1": (
                        "GT_DIRECTIVE_020 — E: exam economic grade scalar from exam-pack grading "
                        "(``compute_exam_grade_v1``); null if not graded on this line."
                    ),
                    "exam_p_score_v1": (
                        "GT_DIRECTIVE_020 — P: exam process score 0..1 from the same grading call; null if absent."
                    ),
                    "exam_pass_v1": (
                        "GT_DIRECTIVE_020 — PASS/FAIL from exam-pack grading ``pass``; null if not graded."
                    ),
                    "l1_e_value_source_v1": (
                        "Source of the L1 economic scalar: exam_pack_grading_v1 vs expectancy_per_trade_proxy_v1."
                    ),
                    "l1_p_value_source_v1": (
                        "Source of the L1 process scalar: exam_pack_grading_v1 vs proxy vs data_gap."
                    ),
                },
            }
        )

    @app.get("/api/student-panel/l1-road")
    def api_student_panel_l1_road_v1() -> Any:
        """GT_DIRECTIVE_016 — L1 road: fingerprint × brain profile × llm_model aggregates; A/B vs baseline anchor."""
        return jsonify(build_l1_road_payload_v1())

    @app.get("/docs/student-panel-dictionary")
    def docs_student_panel_dictionary_v1() -> Any:
        """Operator glossary: L1/L2/L3, brain profiles, L1 road, scorecard columns — same content as repo markdown."""
        p = _GAME_THEORY / "docs" / "STUDENT_PANEL_DICTIONARY_v1.md"
        if not p.is_file():
            abort(404)
        raw = p.read_text(encoding="utf-8")
        body = html.escape(raw)
        page = (
            "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>Student panel dictionary</title>\n"
            "<style>\n"
            "body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; "
            "background: #0f1419; color: #e6edf3; }\n"
            "header.dict-nav { position: sticky; top: 0; z-index: 20; display: flex; flex-wrap: wrap; "
            "align-items: center; gap: 10px 14px; padding: 10px 14px; background: #161b22; "
            "border-bottom: 1px solid #30363d; }\n"
            "header.dict-nav .dict-nav-title { font-size: 0.95rem; font-weight: 650; margin: 0; flex: 1 1 12rem; }\n"
            "header.dict-nav .dict-nav-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }\n"
            "header.dict-nav a, header.dict-nav button.dict-nav-btn { display: inline-block; font-size: 0.84rem; "
            "padding: 6px 12px; border-radius: 6px; text-decoration: none; cursor: pointer; border: 1px solid #30363d; "
            "background: #21262d; color: #e6edf3; }\n"
            "header.dict-nav a.dict-nav-primary, header.dict-nav button.dict-nav-primary { "
            "background: #238636; border-color: #2ea043; color: #fff; font-weight: 600; }\n"
            "header.dict-nav a:hover, header.dict-nav button.dict-nav-btn:hover { filter: brightness(1.08); }\n"
            "main { max-width: 52rem; margin: 0 auto; padding: 1.25rem 1rem 2.5rem; }\n"
            "h1 { font-size: 1.2rem; margin: 0 0 0.5rem; font-weight: 650; }\n"
            "p.hint { font-size: 0.84rem; color: #8b949e; margin: 0 0 1rem; line-height: 1.45; }\n"
            "pre.glossary { white-space: pre-wrap; word-break: break-word; font-size: 0.8rem; "
            "line-height: 1.48; background: #161b22; padding: 1rem 1.1rem; border-radius: 8px; "
            "border: 1px solid #30363d; margin: 0; }\n"
            "a.back { color: #58a6ff; font-size: 0.9rem; }\n"
            "</style></head><body>\n"
            "<header class=\"dict-nav\" role=\"navigation\" aria-label=\"Dictionary navigation\">\n"
            "<p class=\"dict-nav-title\">Student panel dictionary</p>\n"
            "<div class=\"dict-nav-actions\">\n"
            "<a class=\"dict-nav-primary\" href=\"/#pgStudentTriangleDock\">Return to Pattern Machine</a>\n"
            "<a href=\"/\">Application home</a>\n"
            "<button type=\"button\" class=\"dict-nav-btn dict-nav-primary\" id=\"dictFocusOpener\" "
            "hidden>Focus main window</button>\n"
            "</div></header>\n"
            "<main>\n"
            "<h1>Student panel dictionary (v1)</h1>\n"
            "<p class=\"hint\">Canonical source in repo: "
            "<code>renaissance_v4/game_theory/docs/STUDENT_PANEL_DICTIONARY_v1.md</code>. "
            "Open the main app with <strong>Return to Pattern Machine</strong> (opens the "
            "<strong>Student → learning → outcome</strong> fold). If you used a pop-out from the UI, "
            "<strong>Focus main window</strong> brings the Pattern Machine tab to the front when the browser allows it.</p>\n"
            f"<pre class=\"glossary\">{body}</pre>\n"
            '<p style="margin-top:1.25rem"><a class="back" href="/#pgStudentTriangleDock">← Student fold (Pattern Machine)</a> · '
            '<a class="back" href="/">← Application home</a></p>\n'
            "</main>\n"
            "<script>\n"
            "(function () {\n"
            "  var b = document.getElementById('dictFocusOpener');\n"
            "  if (!b) return;\n"
            "  try {\n"
            "    if (window.opener && !window.opener.closed) b.hidden = false;\n"
            "  } catch (e) { /* cross-origin opener */ }\n"
            "  b.addEventListener('click', function () {\n"
            "    try {\n"
            "      if (window.opener && !window.opener.closed) window.opener.focus();\n"
            "    } catch (e2) {}\n"
            "  });\n"
            "})();\n"
            "</script>\n"
            "</body></html>"
        )
        return Response(page, mimetype="text/html; charset=utf-8")

    @app.get("/api/student-panel/run/<job_id>/decisions")
    def api_student_panel_decisions_d11(job_id: str) -> Any:
        """D13 — selected run: mandatory run summary band + one carousel slice per ``trade_id``."""
        return jsonify(build_d13_selected_run_payload_v1(job_id.strip()))

    @app.get("/api/student-panel/run/<job_id>/l3")
    def api_student_panel_l3_gt017(job_id: str) -> Any:
        """GT_DIRECTIVE_017 — L3 payload: decision record, replay/scorecard subsets, L1 linkage, structured ``data_gaps[]``."""
        tid = (request.args.get("trade_id") or request.args.get("decision_id") or "").strip()
        payload = build_student_panel_l3_payload_v1(job_id.strip(), tid)
        return jsonify(payload), 200

    @app.get("/api/student-panel/run/<job_id>/learning")
    def api_student_panel_run_learning_gt018(job_id: str) -> Any:
        """GT_DIRECTIVE_018 — run-level learning governance, store presence, retrieval eligibility."""
        return jsonify(build_student_panel_run_learning_payload_v1(job_id.strip())), 200

    @app.get("/api/student-panel/run/<job_id>/learning-loop-trace")
    def api_student_panel_learning_loop_trace_v1(job_id: str) -> Any:
        """Learning Loop Trace — graph-shaped JSON for operator engine-health (Student path)."""
        return jsonify(build_learning_loop_trace_v1(job_id.strip())), 200

    @app.get("/api/debug/learning-loop/trace/<job_id>")
    def api_debug_learning_loop_trace_v1(job_id: str) -> Any:
        """Debug learning loop trace — graph + breakpoints + fingerprint profile compare.

        Optional: ``run_a_job_id`` (026C learning producer job) and ``control_job_id`` (baseline run for
        same scenario) populate ``learning_effect_closure_026c_v1`` (GT 026C addendum).
        """
        from flask import request

        ra = (request.args.get("run_a_job_id") or "").strip() or None
        ct = (request.args.get("control_job_id") or "").strip() or None
        return jsonify(
            build_debug_learning_loop_trace_v1(
                job_id.strip(),
                run_a_job_id=ra,
                control_job_id=ct,
            )
        ), 200

    @app.get("/api/debug/learning-loop/trace-stream/<job_id>")
    def api_debug_learning_loop_trace_stream_v1(job_id: str) -> Any:
        """NDJSON stream: stage timings then final ``complete`` payload (same as non-stream API)."""

        def gen() -> Any:
            from flask import request

            ra = (request.args.get("run_a_job_id") or "").strip() or None
            ct = (request.args.get("control_job_id") or "").strip() or None
            for chunk in iter_debug_learning_loop_trace_ndjson_v1(
                job_id.strip(),
                run_a_job_id=ra,
                control_job_id=ct,
            ):
                yield chunk

        return Response(
            stream_with_context(gen()),
            mimetype="application/x-ndjson; charset=utf-8",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/debug/learning-loop")
    def page_debug_learning_loop_trace_v1() -> Any:
        """Operator debug page: LangGraph-style trace + A/B/C profile compare (loads debug trace API)."""
        return Response(read_debug_learning_loop_page_html_v1(), mimetype="text/html; charset=utf-8")

    @app.get("/debug/learning-loop-proof")
    def page_debug_learning_loop_proof_alias_v1() -> Any:
        """Alias URL for operators — same page as ``/debug/learning-loop`` (026L proof + trace). Preserves query string."""
        from flask import redirect

        target = "/debug/learning-loop"
        if request.query_string:
            target += "?" + request.query_string.decode()
        return redirect(target)

    @app.get("/learning-loop-trace")
    def page_learning_loop_trace_legacy_redirect_v1() -> Any:
        """Legacy URL — redirect to ``/debug/learning-loop`` preserving ``job_id`` / ``trade_id``."""
        from flask import redirect

        jid = (request.args.get("job_id") or "").strip()
        tid = (request.args.get("trade_id") or "").strip()
        q = "/debug/learning-loop"
        if jid:
            q += "?job_id=" + jid
            if tid:
                q += "&trade_id=" + tid
        elif tid:
            q += "?trade_id=" + tid
        return redirect(q)

    @app.get("/api/training-exam-audit/<job_id>")
    def api_training_exam_audit_v1(job_id: str) -> Any:
        """One scorecard line → ``training_exam_audit_v1`` (verdict + checks + troubleshooting)."""
        jid = job_id.strip()
        if not jid:
            return jsonify({"ok": False, "error": "job_id required"}), 400
        entry = find_scorecard_entry_by_job_id(jid)
        if not entry:
            return jsonify({"ok": False, "error": "Unknown job_id"}), 404
        aud = entry.get("training_exam_audit_v1")
        if not isinstance(aud, dict):
            aud = build_training_exam_audit_v1(entry)
        return jsonify({"ok": True, "schema": "training_exam_audit_api_v1", "job_id": jid, "training_exam_audit_v1": aud})

    @app.get("/api/student-panel/decision")
    def api_student_panel_decision_detail_d11() -> Any:
        """D13 — ``student_decision_record_v1`` for one trade (``trade_id``; ``decision_id`` alias)."""
        jid = (request.args.get("job_id") or "").strip()
        tid = (request.args.get("trade_id") or request.args.get("decision_id") or "").strip()
        if not jid or not tid:
            return jsonify(
                {"ok": False, "error": "job_id and trade_id (or decision_id) query parameters required"}
            ), 400
        rec = build_student_decision_record_v1(jid, tid)
        if not rec:
            return jsonify({"ok": False, "error": "trade not found"}), 404
        if isinstance(rec, dict) and rec.get("ok") is False:
            return jsonify({"ok": False, "record": rec}), 200
        return jsonify({"ok": True, "record": rec})

    @app.get("/api/trade-strategy/contract")
    @app.get("/api/v1/trade-strategy/contract")
    def api_trade_strategy_contract_stub_v1() -> Any:
        """DEV STUB — machine-readable API surface for external systems (integration discovery)."""
        return jsonify(trade_strategy_api_contract_v1())

    @app.get("/api/trade-strategy")
    @app.get("/api/v1/trade-strategy")
    def api_trade_strategy_list_stub_v1() -> Any:
        """DEV STUB — list post-certification trade_strategy placeholders (see §17 exam architecture doc)."""
        return jsonify(stub_trade_strategy_list_v1())

    @app.get("/api/trade-strategy/<strategy_id>/export")
    @app.get("/api/v1/trade-strategy/<strategy_id>/export")
    def api_trade_strategy_export_stub_v1(strategy_id: str) -> Any:
        """DEV STUB — download portable ``trade_strategy`` JSON (attachment)."""
        doc = stub_trade_strategy_export_document_v1(strategy_id)
        slug = str(doc.get("export_filename_slug") or "strategy")
        fname = f"trade_strategy_{slug}_export.json"
        payload = json.dumps(doc, ensure_ascii=False, indent=2)
        return Response(
            payload + "\n",
            mimetype="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{fname}"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/api/trade-strategy/<strategy_id>")
    @app.get("/api/v1/trade-strategy/<strategy_id>")
    def api_trade_strategy_get_stub_v1(strategy_id: str) -> Any:
        """DEV STUB — fetch one trade_strategy document shell (not persisted)."""
        return jsonify(stub_trade_strategy_get_v1(strategy_id))

    @app.post("/api/trade-strategy")
    @app.post("/api/v1/trade-strategy")
    def api_trade_strategy_create_stub_v1() -> Any:
        """DEV STUB — accept upload body; echo keys only (no store)."""
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(stub_trade_strategy_create_v1(data if isinstance(data, dict) else {}))

    @app.patch("/api/trade-strategy/<strategy_id>")
    @app.patch("/api/v1/trade-strategy/<strategy_id>")
    def api_trade_strategy_patch_stub_v1(strategy_id: str) -> Any:
        """DEV STUB — accept update body; echo keys only (no merge)."""
        data = request.get_json(force=True, silent=True) or {}
        return jsonify(stub_trade_strategy_update_v1(strategy_id, data if isinstance(data, dict) else {}))

    @app.post("/api/v1/exam/units")
    def api_exam_units_create_v1() -> Any:
        """GT_DIRECTIVE_003 — create exam unit (in-memory dev store; §11.1)."""
        data = request.get_json(force=True, silent=True) or {}
        pack = data.get("exam_pack_id")
        ver = data.get("exam_pack_version")
        eid = data.get("exam_unit_id")
        try:
            u = create_exam_unit_v1(
                exam_pack_id=str(pack) if pack is not None else None,
                exam_pack_version=str(ver) if ver is not None else None,
                exam_unit_id=str(eid).strip() if isinstance(eid, str) and eid.strip() else None,
            )
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 400
        return jsonify({"ok": True, **exam_unit_to_public_dict(u)}), 201

    @app.get("/api/v1/exam/units/<exam_unit_id>")
    def api_exam_units_get_v1(exam_unit_id: str) -> Any:
        """GT_DIRECTIVE_003 — fetch exam unit state."""
        u = get_exam_unit_v1(exam_unit_id)
        if u is None:
            return jsonify({"ok": False, "error": "exam_unit_not_found"}), 404
        return jsonify({"ok": True, **exam_unit_to_public_dict(u)})

    @app.post("/api/v1/exam/units/<exam_unit_id>/transition")
    def api_exam_units_transition_v1(exam_unit_id: str) -> Any:
        """GT_DIRECTIVE_003 — apply one lifecycle event (409 on illegal transition or unknown event)."""
        data = request.get_json(force=True, silent=True) or {}
        ev = data.get("event")
        if not isinstance(ev, str) or not ev.strip():
            return jsonify({"ok": False, "error": "event_required_string"}), 400
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        out = apply_exam_unit_transition_v1(exam_unit_id.strip(), ev.strip(), payload)
        if out.get("error") == "exam_unit_not_found":
            return jsonify(out), 404
        if not out.get("ok"):
            return jsonify(out), 409
        u2 = get_exam_unit_v1(exam_unit_id.strip())
        if u2 is None:
            return jsonify(out), 500
        if u2.phase == ExamPhase.DECISION_A_SEALED and u2.enter is not None:
            try:
                delib = get_frame0_deliberation_v1(exam_unit_id.strip())
                ts_stub = "2026-04-21T15:00:00Z"
                uid_seal = u2.exam_unit_id
                if u2.enter is True:
                    strip = get_exam_ohlc_strip_v1(uid_seal) or default_synthetic_ohlc_strip_v1()
                    pol = get_exam_downstream_termination_v1(uid_seal)
                    f0_ts = str(strip[0].get("bar_close") or ts_stub).strip() or ts_stub
                    doc = build_complete_enter_timeline_v1(
                        exam_unit_id=uid_seal,
                        exam_pack_id=u2.exam_pack_id,
                        exam_pack_version=u2.exam_pack_version,
                        deliberation_export=delib,
                        frame0_bar_close_iso=f0_ts,
                        strip=strip,
                        policy=pol,
                    )
                else:
                    doc = build_timeline_document_no_trade_single_frame_v1(
                        exam_unit_id=uid_seal,
                        exam_pack_id=u2.exam_pack_id,
                        exam_pack_version=u2.exam_pack_version,
                        deliberation_export=delib,
                        bar_close_timestamp_iso=ts_stub,
                    )
                commit_timeline_immutable_v1(doc)
            except ValueError:
                pass
        return jsonify({"ok": True, **exam_unit_to_public_dict(u2)})

    @app.post("/api/v1/exam/units/<exam_unit_id>/ohlc-strip")
    def api_exam_ohlc_strip_post_v1(exam_unit_id: str) -> Any:
        """GT_DIRECTIVE_006 — dev: attach OHLC replay strip + optional downstream termination before Decision A seal."""
        uid = exam_unit_id.strip()
        if get_exam_unit_v1(uid) is None:
            return jsonify({"ok": False, "error": "exam_unit_not_found"}), 404
        raw = request.get_json(force=True, silent=True)
        if not isinstance(raw, dict):
            return jsonify({"ok": False, "error": "json_object_required"}), 400
        bars = raw.get("bars")
        if not isinstance(bars, list):
            return jsonify({"ok": False, "error": "bars_required_array"}), 400
        pol_raw = raw.get("downstream_termination")
        try:
            set_exam_ohlc_strip_v1(uid, bars)
            if pol_raw is not None:
                if not isinstance(pol_raw, dict):
                    return jsonify({"ok": False, "error": "downstream_termination_must_be_object"}), 400
                set_exam_downstream_termination_v1(uid, DownstreamTerminationPolicyV1.model_validate(pol_raw))
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 400
        return jsonify({"ok": True, "exam_unit_id": uid, "bars_count": len(bars)}), 200

    @app.put("/api/v1/exam/units/<exam_unit_id>/frames/0/deliberation")
    def api_exam_frame0_deliberation_put_v1(exam_unit_id: str) -> Any:
        """GT_DIRECTIVE_004 — attach validated H1–H4 deliberation to decision frame index 0 (dev store)."""
        uid = exam_unit_id.strip()
        if get_exam_unit_v1(uid) is None:
            return jsonify({"ok": False, "error": "exam_unit_not_found"}), 404
        raw = request.get_json(force=True, silent=True)
        if not isinstance(raw, dict):
            return jsonify({"ok": False, "error": "json_object_required"}), 400
        try:
            env = parse_submit_envelope_v1(raw)
        except ValidationError as err:
            return jsonify({"ok": False, "error": "envelope_validation_failed", "detail": err.errors()}), 400
        delib = env.deliberation
        if delib.exam_unit_id.strip() != uid:
            return jsonify({"ok": False, "error": "deliberation.exam_unit_id_mismatch"}), 422
        try:
            validate_deliberation_against_policy_v1(delib, env.pack_deliberation_policy)
            assert_non_placeholder_deliberation_v1(delib)
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 422
        export_d = deliberation_payload_to_export_dict_v1(delib)
        put_frame0_deliberation_v1(uid, export_d)
        return jsonify(
            {
                "ok": True,
                "exam_unit_id": uid,
                "decision_frame_index": 0,
                "deliberation": export_d,
            }
        ), 200

    @app.get("/api/v1/exam/units/<exam_unit_id>/frames/0/deliberation")
    def api_exam_frame0_deliberation_get_v1(exam_unit_id: str) -> Any:
        """GT_DIRECTIVE_004 — fetch deliberation attached to frame 0."""
        uid = exam_unit_id.strip()
        if get_exam_unit_v1(uid) is None:
            return jsonify({"ok": False, "error": "exam_unit_not_found"}), 404
        d = get_frame0_deliberation_v1(uid)
        if d is None:
            return jsonify({"ok": False, "error": "frame0_deliberation_not_found"}), 404
        return jsonify(
            {
                "ok": True,
                "exam_unit_id": uid,
                "decision_frame_index": 0,
                "deliberation": d,
            }
        ), 200

    @app.get("/api/v1/exam/units/<exam_unit_id>/decision-frames")
    def api_exam_unit_decision_frames_get_v1(exam_unit_id: str) -> Any:
        """GT_DIRECTIVE_005 — committed parent + ordered ``decision_frames`` (§11.3). Optional ``?tz=IANA`` or ``X-Time-Zone`` for local display strings (UTC ``timestamp`` unchanged)."""
        uid = exam_unit_id.strip()
        if get_exam_unit_v1(uid) is None:
            return jsonify({"ok": False, "error": "exam_unit_not_found"}), 404
        raw = get_committed_timeline_v1(uid)
        if raw is None:
            return jsonify({"ok": False, "error": "timeline_not_committed"}), 404
        doc = ExamUnitTimelineDocumentV1.model_validate(raw)
        tz = (request.args.get("tz") or request.headers.get("X-Time-Zone") or "").strip()
        return jsonify(timeline_to_public_response_v1(doc, local_tz=tz or None)), 200

    @app.get("/api/v1/exam/frames/<decision_frame_id>")
    def api_exam_decision_frame_get_v1(decision_frame_id: str) -> Any:
        """GT_DIRECTIVE_005 — fetch one ``decision_frame`` by stable id (§11.3). Optional ``?tz=`` / ``X-Time-Zone`` for ``timestamp_local_display``."""
        fr = find_frame_in_committed_timelines_v1(decision_frame_id.strip())
        if fr is None:
            return jsonify({"ok": False, "error": "decision_frame_not_found"}), 404
        tz = (request.args.get("tz") or request.headers.get("X-Time-Zone") or "").strip()
        body = dict(fr)
        if tz:
            body = append_local_time_to_decision_frame_dict_v1(body, tz)
            body["local_time_tz"] = tz
        return jsonify({"ok": True, **body}), 200

    @app.post("/api/v1/exam/packs/<exam_pack_id>/grading-config")
    def api_exam_pack_grading_config_post_v1(exam_pack_id: str) -> Any:
        """GT_DIRECTIVE_007 — dev: register ``ExamPackGradingConfigV1`` JSON keyed by pack id + version."""
        pid = exam_pack_id.strip()
        raw = request.get_json(force=True, silent=True)
        if not isinstance(raw, dict):
            return jsonify({"ok": False, "error": "json_object_required"}), 400
        ver = raw.get("exam_pack_version")
        grading = raw.get("grading")
        if not isinstance(ver, str) or not ver.strip():
            return jsonify({"ok": False, "error": "exam_pack_version_required_string"}), 400
        if not isinstance(grading, dict):
            return jsonify({"ok": False, "error": "grading_object_required"}), 400
        try:
            register_exam_pack_grading_config_v1(pid, ver.strip(), grading)
        except ValueError as err:
            return jsonify({"ok": False, "error": str(err)}), 400
        return jsonify({"ok": True, "exam_pack_id": pid, "exam_pack_version": ver.strip()}), 200

    @app.get("/api/v1/exam/units/<exam_unit_id>/grade")
    def api_exam_unit_grade_get_v1(exam_unit_id: str) -> Any:
        """GT_DIRECTIVE_007 — E, P, pass from pack config + committed timeline + deliberation."""
        uid = exam_unit_id.strip()
        u = get_exam_unit_v1(uid)
        if u is None:
            return jsonify({"ok": False, "error": "exam_unit_not_found"}), 404
        if u.phase == ExamPhase.INVALID:
            return jsonify({"ok": False, "error": "exam_unit_invalid"}), 422
        raw_t = get_committed_timeline_v1(uid)
        delib = get_frame0_deliberation_v1(uid)
        if raw_t is None or delib is None:
            return jsonify({"ok": False, "error": "exam_unit_incomplete_for_grading"}), 409
        if u.exam_pack_id is None or not str(u.exam_pack_id).strip():
            return jsonify({"ok": False, "error": "missing_exam_pack_id"}), 422
        if u.exam_pack_version is None or not str(u.exam_pack_version).strip():
            return jsonify({"ok": False, "error": "missing_exam_pack_version"}), 422
        cfg = get_exam_pack_grading_config_v1(u.exam_pack_id, u.exam_pack_version)
        if cfg is None:
            return jsonify({"ok": False, "error": "exam_pack_grading_config_missing"}), 500
        try:
            out = compute_exam_grade_v1(
                exam_unit_id=uid,
                exam_phase=u.phase,
                enter=u.enter,
                exam_pack_id=u.exam_pack_id,
                exam_pack_version=u.exam_pack_version,
                timeline_committed=raw_t,
                deliberation_export=delib,
                pack_config=cfg,
            )
            return jsonify(out), 200
        except ValueError as err:
            msg = str(err)
            if msg.startswith("missing_") or "incomplete" in msg or "requires_enter" in msg:
                return jsonify({"ok": False, "error": msg}), 422
            if msg.startswith("missing_economic") or msg.startswith("economic_") or "context" in msg:
                return jsonify({"ok": False, "error": msg}), 422
            return jsonify({"ok": False, "error": msg}), 422

    @app.get("/api/student-proctor/learning-store")
    def api_student_proctor_learning_store_get() -> Any:
        """Read-only Student Learning Store metadata (Directive 08 — distinct from scorecard / engine memory)."""
        return jsonify(student_learning_store_status_v1())

    @app.post("/api/student-proctor/learning-store/clear")
    def api_student_proctor_learning_store_clear() -> Any:
        """
        Truncate the Student Proctor learning JSONL only (explicit typed confirm).

        Does **not** modify ``batch_scorecard.jsonl`` or engine learning files.
        """
        data = request.get_json(force=True, silent=True) or {}
        c = data.get("confirm")
        if not isinstance(c, str):
            return jsonify(
                {
                    "ok": False,
                    "error": (
                        "confirm must be the exact string "
                        f"{RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM!r}"
                    ),
                }
            ), 400
        out = clear_student_learning_store_v1(confirm=c.strip())
        return jsonify(out), (200 if out.get("ok") else 400)

    @app.get("/api/training/export")
    def api_training_export_v1() -> Any:
        """
        GT_DIRECTIVE_022 — Promoted learning rows only; deterministic preview / NDJSON download.

        Query: ``preview`` (default 5, max 500). ``download=1`` returns ``training_dataset_v1.jsonl`` body.
        """
        st = student_learning_store_status_v1()
        store_path = Path(str(st["path"]))
        try:
            preview_n = int(str(request.args.get("preview") or "5").strip() or "5")
        except ValueError:
            preview_n = 5
        dl_raw = str(request.args.get("download") or "").strip().lower()
        if dl_raw in ("1", "true", "yes", "download"):
            lines = iter_training_record_lines_v1(store_path=store_path, scorecard_path=None)
            body = "\n".join(lines) + ("\n" if lines else "")
            return Response(
                body,
                mimetype="application/x-ndjson; charset=utf-8",
                headers={
                    "Content-Disposition": 'attachment; filename="training_dataset_v1.jsonl"',
                    "X-Training-Export-Line-Count": str(len(lines)),
                },
            )
        payload = build_training_export_payload_v1(
            store_path=store_path, scorecard_path=None, preview_limit=preview_n
        )
        payload["learning_store_path"] = str(store_path.resolve())
        return jsonify(payload), 200

    @app.post("/api/training/export/materialize")
    def api_training_export_materialize_v1() -> Any:
        """Write default ``training_dataset_v1.jsonl`` (typed confirm; GT_DIRECTIVE_022)."""
        data = request.get_json(force=True, silent=True) or {}
        st = student_learning_store_status_v1()
        store_path = Path(str(st["path"]))
        out = materialize_training_dataset_v1(
            store_path=store_path,
            scorecard_path=None,
            output_path=default_training_dataset_jsonl_path_v1(),
            confirm=str(data.get("confirm") or ""),
        )
        return jsonify(out), (200 if out.get("ok") else 400)

    @app.get("/api/training/learning-effectiveness")
    def api_training_learning_effectiveness_v1() -> Any:
        """
        GT_DIRECTIVE_023 — Read-only learning effectiveness report (scorecard + learning store).

        Query ``summary=1`` returns the same metrics without per-run ``runs_ordered_v1`` arrays.
        """
        st = student_learning_store_status_v1()
        store_path = Path(str(st["path"]))
        rep = build_learning_effectiveness_report_v1(store_path=store_path, scorecard_path=None)
        summ = str(request.args.get("summary") or "").strip().lower()
        if summ in ("1", "true", "yes"):
            return jsonify({"ok": True, **summarize_learning_effectiveness_report_v1(rep)}), 200
        return jsonify({"ok": True, **rep}), 200

    @app.post("/api/training/learning-effectiveness/materialize")
    def api_training_learning_effectiveness_materialize_v1() -> Any:
        """Persist ``learning_effectiveness_report_v1.json`` (typed confirm; GT_DIRECTIVE_023)."""
        data = request.get_json(force=True, silent=True) or {}
        st = student_learning_store_status_v1()
        store_path = Path(str(st["path"]))
        out = materialize_learning_effectiveness_report_v1(
            scorecard_path=None,
            store_path=store_path,
            output_path=default_learning_effectiveness_report_path_v1(),
            confirm=str(data.get("confirm") or ""),
        )
        return jsonify(out), (200 if out.get("ok") else 400)

    @app.get("/api/training/learning-flow-validate")
    def api_training_learning_flow_validate_v1() -> Any:
        """GT_DIRECTIVE_025 — Deterministic A→B learning chain proof (read-only JSON, no model-weight claims)."""
        run_a = (request.args.get("run_a") or "").strip()
        run_b = (request.args.get("run_b") or "").strip()
        if not run_a or not run_b:
            return jsonify({"ok": False, "error": "run_a and run_b query parameters required"}), 400
        st = student_learning_store_status_v1()
        store_path = Path(str(st["path"]))
        out = build_learning_flow_validation_v1(
            run_a, run_b, scorecard_path=None, store_path=store_path
        )
        return jsonify({"ok": True, **out}), 200

    @app.post("/api/training/learning-flow-validate/materialize")
    def api_training_learning_flow_validate_materialize_v1() -> Any:
        """Write ``learning_flow_validation_v1.json`` for one A/B pair (typed confirm; GT_DIRECTIVE_025)."""
        data = request.get_json(force=True, silent=True) or {}
        run_a = str(data.get("run_a") or "").strip()
        run_b = str(data.get("run_b") or "").strip()
        if not run_a or not run_b:
            return jsonify({"ok": False, "error": "run_a and run_b required in JSON body"}), 400
        st = student_learning_store_status_v1()
        store_path = Path(str(st["path"]))
        out = materialize_learning_flow_validation_v1(
            run_a=run_a,
            run_b=run_b,
            scorecard_path=None,
            store_path=store_path,
            output_path=default_learning_flow_validation_report_path_v1(),
            confirm=str(data.get("confirm") or ""),
        )
        return jsonify(out), (200 if out.get("ok") else 400)

    @app.get("/api/training/learning-loop-proof")
    def api_training_learning_loop_proof_v1() -> Any:
        """GT_DIRECTIVE_026L — Causal learning-loop proof graph (read-only, artifact-backed)."""
        run_a = (request.args.get("run_a") or "").strip()
        run_b = (request.args.get("run_b") or "").strip()
        if not run_a or not run_b:
            return jsonify({"ok": False, "error": "run_a and run_b query parameters required"}), 400
        st = student_learning_store_status_v1()
        store_path = Path(str(st["path"]))
        graph = build_learning_loop_proof_graph_v1(
            run_a,
            run_b,
            scorecard_path=None,
            store_path=store_path,
        )
        return jsonify(
            {
                "ok": True,
                "learning_loop_proof_graph_v1": graph,
                "final_verdict_v1": graph.get("final_verdict_v1"),
                "breakpoints_v1": graph.get("breakpoints_v1"),
                "operator_summary_v1": graph.get("operator_summary_v1"),
            }
        ), 200

    @app.post("/api/training/learning-loop-proof/materialize")
    def api_training_learning_loop_proof_materialize_v1() -> Any:
        """Write ``learning_loop_proof_<run_a>__<run_b>.json`` (typed confirm; GT_DIRECTIVE_026L)."""
        data = request.get_json(force=True, silent=True) or {}
        run_a = str(data.get("run_a") or "").strip()
        run_b = str(data.get("run_b") or "").strip()
        if not run_a or not run_b:
            return jsonify({"ok": False, "error": "run_a and run_b required in JSON body"}), 400
        st = student_learning_store_status_v1()
        store_path = Path(str(st["path"]))
        out = materialize_learning_loop_proof_graph_v1(
            run_a=run_a,
            run_b=run_b,
            scorecard_path=None,
            store_path=store_path,
            output_path=default_learning_loop_proof_output_path_v1(run_a, run_b),
            confirm=str(data.get("confirm") or ""),
            baseline_job_id=str(data.get("baseline_job_id") or "").strip() or None,
        )
        return jsonify(out), (200 if out.get("ok") else 400)

    @app.get("/api/batch-detail")
    def api_batch_detail() -> Any:
        """Drill-down: scorecard line + scenario list from session batch folder."""
        job_id = (request.args.get("job_id") or "").strip()
        if not job_id:
            return jsonify({"ok": False, "error": "job_id query parameter required"}), 400
        entry = find_scorecard_entry_by_job_id(job_id)
        if not entry:
            return jsonify({"ok": False, "error": f"job_id not found in scorecard log: {job_id!r}"}), 404
        _bd, scenarios, s_err = build_scenario_list_for_batch(job_id, entry.get("session_log_batch_dir"))
        return jsonify(
            {
                "ok": True,
                "scorecard": entry,
                "batch_dir": str(_bd.resolve()) if _bd and _bd.is_dir() else None,
                "scenarios": scenarios,
                "scenario_list_error": s_err,
            }
        )

    @app.get("/api/batch-detail.csv")
    def api_batch_detail_csv() -> Any:
        job_id = (request.args.get("job_id") or "").strip()
        if not job_id:
            return jsonify({"ok": False, "error": "job_id query parameter required"}), 400
        entry = find_scorecard_entry_by_job_id(job_id)
        if not entry:
            return jsonify({"ok": False, "error": f"job_id not found: {job_id!r}"}), 404
        _bd, scenarios, _err = build_scenario_list_for_batch(job_id, entry.get("session_log_batch_dir"))
        body = batch_detail_csv_rows(job_id, scenarios)
        safe = job_id.replace("/", "_")[:48]
        return Response(
            body,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="pattern_game_batch_{safe}_scenarios.csv"'
            },
        )

    @app.get("/api/batch-scenario-file")
    def api_batch_scenario_file() -> Any:
        """Artifact-backed HUMAN_READABLE.md or run_record.json for one scenario in a batch."""
        job_id = (request.args.get("job_id") or "").strip()
        scenario_id = (request.args.get("scenario_id") or "").strip()
        kind = (request.args.get("kind") or "human").strip().lower()
        if kind not in ("human", "json"):
            return jsonify({"ok": False, "error": "kind must be human or json"}), 400
        if not job_id or not scenario_id:
            return jsonify({"ok": False, "error": "job_id and scenario_id required"}), 400
        data, ct, err = read_scenario_artifact(job_id, scenario_id, "human" if kind == "human" else "json")
        if err or data is None:
            return jsonify({"ok": False, "error": err or "not found"}), 404
        return Response(data, mimetype=ct or "application/octet-stream")

    @app.get("/api/retrospective-log")
    def api_retrospective_log() -> Any:
        """Recent ``retrospective_log.jsonl`` lines (newest first)."""
        try:
            limit = int(request.args.get("limit") or 25)
        except (TypeError, ValueError):
            limit = 25
        limit = max(1, min(200, limit))
        p = default_retrospective_log_jsonl()
        rows = read_retrospective_recent(limit, path=p)
        return jsonify({"ok": True, "path": str(p.resolve()), "limit": limit, "entries": rows})

    @app.post("/api/retrospective-append")
    def api_retrospective_append() -> Any:
        """Append one retrospective line (what you saw / try next). Local prototype — no auth."""
        data = request.get_json(force=True, silent=True) or {}
        obs = (data.get("what_observed") or data.get("observed") or "").strip()
        nxt = (data.get("what_to_try_next") or data.get("try_next") or "").strip()
        if not obs or not nxt:
            return jsonify({"ok": False, "error": "what_observed and what_to_try_next are required strings"}), 400
        rr = (data.get("run_ref") or data.get("job_id") or "").strip() or None
        src = (data.get("source") or "web_ui").strip() or "web_ui"
        p = append_retrospective(what_observed=obs, what_to_try_next=nxt, run_ref=rr, source=src)
        return jsonify({"ok": True, "path": str(p)})

    @app.get("/api/suggest-hunters")
    def api_suggest_hunters() -> Any:
        """Return memory-aware parallel scenario JSON (scorecard + retrospective); deterministic ladder."""
        out = build_hunter_suggestion()
        if not out.get("ok"):
            return jsonify(out), 400
        return jsonify(out)

    _REPO_ROOT = Path(__file__).resolve().parent.parent.parent

    @app.get("/strategy-idea-format")
    def strategy_idea_format_doc() -> Any:
        """Plain-language spec for operator strategy idea uploads (UTF-8 text)."""
        p = _GAME_THEORY / "STRATEGY_IDEA_FORMAT.md"
        if not p.is_file():
            abort(404)
        return Response(
            p.read_text(encoding="utf-8"),
            mimetype="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'inline; filename="STRATEGY_IDEA_FORMAT.md"'},
        )

    @app.get("/api/operator-strategy-upload/state")
    def api_operator_strategy_upload_state() -> Any:
        return jsonify({"ok": True, **operator_strategy_public_state(_REPO_ROOT)})

    @app.post("/api/operator-strategy-upload")
    def api_operator_strategy_upload() -> Any:
        """Multipart: ``file`` (UTF-8 text, strategy_idea_v1). Parses, converts, validates, saves."""
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "missing form field: file"}), 400
        up = request.files["file"]
        if not up or not up.filename:
            return jsonify({"ok": False, "error": "empty file upload"}), 400
        raw = up.read()
        res = process_strategy_idea_upload(raw, up.filename or "strategy.txt", repo_root=_REPO_ROOT)
        body = {"ok": res.ok, **res.to_api_dict()}
        return jsonify(body), (200 if res.ok else 400)

    @app.post("/api/operator-strategy-upload/clear")
    def api_operator_strategy_upload_clear() -> Any:
        """Remove active uploaded strategy pointer (does not delete saved manifest/source files)."""
        clear_active_operator_strategy(_REPO_ROOT)
        return jsonify({"ok": True, **operator_strategy_public_state(_REPO_ROOT)})

    @app.get("/api/catalog-batch-meta")
    def api_catalog_batch_meta() -> Any:
        """Defaults for Chef ATR sweep (Anna / UI)."""
        return jsonify({"ok": True, **catalog_batch_builder_meta()})

    @app.post("/api/catalog-batch-generate")
    def api_catalog_batch_generate() -> Any:
        """
        Build parallel-ready scenarios: one manifest, many (stop, target) pairs (capped).

        Body JSON: ``mode`` (only ``atr_sweep``), ``manifest_path`` (optional, repo-relative),
        ``max_scenarios`` (1–200, default 24), optional ``pairs`` or ``stop_values``/``target_values``.
        """
        data = request.get_json(force=True, silent=True) or {}
        mode = (data.get("mode") or "atr_sweep").strip().lower()
        if mode != "atr_sweep":
            return jsonify({"ok": False, "error": f"unsupported mode {mode!r} (only atr_sweep)"}), 400

        mp = (data.get("manifest_path") or "").strip() or "renaissance_v4/configs/manifests/baseline_v1_recipe.json"
        cand = Path(mp)
        if not cand.is_absolute():
            cand = (_REPO_ROOT / mp).resolve()
        else:
            cand = cand.resolve()
        if not cand.is_file():
            return jsonify({"ok": False, "error": f"manifest not found: {mp}"}), 404

        try:
            max_n = int(data.get("max_scenarios") or 24)
        except (TypeError, ValueError):
            max_n = 24
        max_n = max(1, min(200, max_n))

        pairs_raw = data.get("pairs")
        pairs: list[tuple[float, float]] | None = None
        if pairs_raw is not None:
            if not isinstance(pairs_raw, list):
                return jsonify({"ok": False, "error": "pairs must be an array of [stop, target] pairs"}), 400
            pairs = []
            for row in pairs_raw:
                if not isinstance(row, (list, tuple)) or len(row) != 2:
                    return jsonify({"ok": False, "error": "each pairs entry must be [atr_stop_mult, atr_target_mult]"}), 400
                try:
                    pairs.append((float(row[0]), float(row[1])))
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "pairs must be numeric [stop, target]"}), 400

        sv_raw = data.get("stop_values")
        tv_raw = data.get("target_values")
        if sv_raw is not None and not isinstance(sv_raw, list):
            return jsonify({"ok": False, "error": "stop_values must be an array of numbers or omitted"}), 400
        if tv_raw is not None and not isinstance(tv_raw, list):
            return jsonify({"ok": False, "error": "target_values must be an array of numbers or omitted"}), 400
        sv = [float(x) for x in sv_raw] if sv_raw else None
        tv = [float(x) for x in tv_raw] if tv_raw else None

        try:
            scenarios = build_atr_sweep_scenarios(
                cand,
                pairs=pairs if pairs else None,
                stop_values=sv,
                target_values=tv,
                max_scenarios=max_n,
            )
        except FileNotFoundError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        ok, msgs = validate_scenarios(scenarios, require_hypothesis=_web_ui_require_hypothesis())
        if not ok:
            return jsonify({"ok": False, "error": "; ".join(msgs)}), 400
        return jsonify({"ok": True, "count": len(scenarios), "scenarios": scenarios, "warnings": msgs})

    return app


PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Pattern Machine learning · UI __PATTERN_GAME_WEB_UI_VERSION__</title>
  <link rel="preload" href="/assets/pattern-banner.webp" as="image" type="image/webp"/>
  <style>
    :root {
      --pg-bg: #f2efe8;
      --pg-bg-accent: #e7e1d3;
      --pg-surface: rgba(255, 252, 246, 0.92);
      --pg-surface-strong: #fffdf8;
      --pg-ink: #1d232c;
      --pg-muted: #66707b;
      --pg-line: rgba(54, 64, 74, 0.14);
      --pg-shadow: 0 20px 50px rgba(35, 44, 56, 0.08);
      --pg-radius-xl: 26px;
      --pg-radius-lg: 18px;
      --pg-header-accent: #d7b56d;
      --pg-teal: #2f7f79;
      --pg-teal-soft: rgba(47, 127, 121, 0.14);
      --pg-amber: #b7772c;
      --pg-amber-soft: rgba(183, 119, 44, 0.14);
      --pg-rose: #9c544c;
      --pg-rose-soft: rgba(156, 84, 76, 0.14);
      --pg-steel: #50647a;
      --pg-steel-soft: rgba(80, 100, 122, 0.12);
      --pg-mono: ui-monospace, "SFMono-Regular", Menlo, monospace;
      --pg-sans: system-ui, -apple-system, "Segoe UI", "Avenir Next", "Helvetica Neue", sans-serif;
      --pg-accent: #1d6fa5;
      font-family: var(--pg-sans);
    }
    * { box-sizing: border-box; }
    body.pg-theme {
      margin: 0;
      color: var(--pg-ink);
      background:
        radial-gradient(circle at top left, rgba(255,255,255,0.85), transparent 35%),
        linear-gradient(180deg, var(--pg-bg) 0%, var(--pg-bg-accent) 100%);
      min-height: 100vh;
      line-height: 1.45;
    }
    .pg-shell {
      max-width: min(1920px, calc(100vw - 16px));
      margin: 0 auto;
      padding: 24px 24px 40px;
    }
    .pg-header {
      display: flex;
      flex-direction: column;
      padding: 0;
      background: linear-gradient(135deg, #14202a 0%, #243341 100%);
      color: #f7f1e6;
      border-radius: var(--pg-radius-xl);
      box-shadow: var(--pg-shadow);
      margin-bottom: 22px;
      overflow: hidden;
      position: relative;
      isolation: isolate;
    }
    .pg-header > picture {
      display: contents;
    }
    /* Full-bleed banner: image fills the entire header; copy and cards sit above via scrim. */
    .pg-header-banner {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      margin: 0;
      display: block;
      object-fit: cover;
      object-position: center 35%;
      z-index: 0;
      pointer-events: none;
    }
    .pg-header::before {
      content: "";
      position: absolute;
      inset: 0;
      z-index: 1;
      pointer-events: none;
      background: linear-gradient(
        180deg,
        rgba(8, 12, 18, 0.35) 0%,
        rgba(8, 12, 18, 0.55) 38%,
        rgba(8, 12, 18, 0.78) 100%
      );
    }
    .pg-header-content {
      padding: 22px 26px 22px;
      position: relative;
      z-index: 2;
      display: flex;
      flex-direction: column;
      align-items: stretch;
      width: 100%;
      box-sizing: border-box;
    }
    .pg-header::after {
      content: "";
      position: absolute;
      inset: auto -80px -80px auto;
      width: 220px;
      height: 220px;
      border-radius: 50%;
      z-index: 1;
      background: radial-gradient(circle, rgba(215,181,109,0.22), transparent 65%);
      pointer-events: none;
    }
    .pg-header-drawers {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 16px;
      position: relative;
    }
    @media (max-width: 960px) {
      .pg-header-drawers { grid-template-columns: 1fr; }
    }
    .pg-header-evidence,
    .pg-header-modules {
      position: relative;
      margin-top: 0;
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 16px;
      background: rgba(0,0,0,0.2);
    }
    .pg-header-evidence > summary,
    .pg-header-modules > summary {
      list-style: none;
      cursor: pointer;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px 14px;
      padding: 12px 14px;
      font-size: 0.95rem;
      font-weight: 700;
      color: #f7f1e6;
    }
    .pg-header-evidence > summary::-webkit-details-marker,
    .pg-header-modules > summary::-webkit-details-marker { display: none; }
    .pg-header-evidence > summary::before,
    .pg-header-modules > summary::before {
      content: "▸";
      display: inline-block;
      font-size: 0.85rem;
      opacity: 0.85;
      transition: transform 0.15s ease;
    }
    .pg-header-evidence[open] > summary::before,
    .pg-header-modules[open] > summary::before { transform: rotate(90deg); }
    .pg-header-evidence-hint {
      flex: 1 1 100%;
      margin: 0;
      padding-left: 1.35rem;
      font-size: 0.8rem;
      font-weight: 500;
      color: rgba(247, 241, 230, 0.65);
    }
    .pg-header-drawer-inner {
      padding: 0 14px 14px;
      border-top: 1px solid rgba(255,255,255,0.08);
    }
    .pg-header-modules .pg-pill-row { margin-top: 4px; }
    .pg-header-modules .pg-pill {
      background: rgba(255,255,255,0.08);
      border-color: rgba(255,255,255,0.15);
      color: rgba(247, 241, 230, 0.88);
    }
    .pg-header-modules .pg-status-item {
      background: rgba(255,255,255,0.06);
      border-color: rgba(255,255,255,0.1);
    }
    .pg-header-modules .pg-status-name { color: #f0f4f8; }
    .pg-header-modules .pg-status-meta { color: rgba(247, 241, 230, 0.72); }
    .pg-header-evidence .pg-tab-strip { margin-top: 10px; }
    .pg-header-evidence .pg-tab {
      background: rgba(255,255,255,0.08);
      border-color: rgba(255,255,255,0.18);
      color: rgba(247, 241, 230, 0.9);
    }
    .pg-header-evidence .pg-tab.active {
      background: rgba(255,255,255,0.92);
      border-color: rgba(255,255,255,0.92);
      color: #183343;
    }
    .pg-header-evidence .pg-pre-json {
      background: rgba(15, 22, 28, 0.55);
      border-color: rgba(255,255,255,0.12);
      color: #e8ecf0;
    }
    .pg-header-evidence .policy-outcome-panel .hint { color: rgba(247, 241, 230, 0.7); }
    .pg-header-evidence .policy-table th { background: rgba(255,255,255,0.1); color: rgba(247, 241, 230, 0.85); }
    .pg-header-evidence .policy-table td { color: #f0f4f8; border-color: rgba(255,255,255,0.12); }
    .pg-header-evidence #sessionLogNote { color: rgba(247, 241, 230, 0.75) !important; }
    /* D10.3 — structural panel outline (mandatory hierarchy) */
    details.pg-panel-fold {
      background: var(--pg-surface);
      border: 1px solid #1e3a5f;
      border-radius: var(--pg-radius-xl);
      box-shadow: var(--pg-shadow);
      min-width: 0;
      backdrop-filter: blur(12px);
    }
    details.pg-panel-fold > summary {
      list-style: none;
      cursor: pointer;
      padding: 14px 16px;
      display: flex;
      flex-wrap: nowrap;
      align-items: flex-start;
      gap: 10px;
      width: 100%;
      box-sizing: border-box;
    }
    details.pg-panel-fold > summary .pg-panel-header { flex: 1; min-width: 0; }
    details.pg-panel-fold > summary::-webkit-details-marker { display: none; }
    details.pg-panel-fold > summary::before {
      content: "▸";
      flex-shrink: 0;
      margin-top: 4px;
      font-size: 0.85rem;
      color: var(--pg-muted);
      transition: transform 0.15s ease;
    }
    details.pg-panel-fold[open] > summary::before { transform: rotate(90deg); }
    details.pg-panel-fold .pg-panel-fold-body { padding: 0 16px 16px; }
    details.pg-panel-fold .pg-panel-header { margin-bottom: 12px; }
    .pg-title-wrap { position: relative; z-index: 1; width: 100%; max-width: 100%; }
    .pg-header-title-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px 16px;
      margin: 0 0 6px;
    }
    .pg-header-title-row .pg-title { margin: 0; flex: 1 1 auto; min-width: 0; }
    .pg-howto-btn {
      flex: 0 0 auto;
      padding: 8px 14px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.22);
      background: rgba(255, 255, 255, 0.1);
      color: #f7f1e6;
      font-size: 0.82rem;
      font-weight: 700;
      cursor: pointer;
      letter-spacing: 0.02em;
    }
    .pg-howto-btn:hover { background: rgba(255, 255, 255, 0.16); border-color: rgba(255, 255, 255, 0.35); }
    .pg-howto-btn:focus-visible { outline: 2px solid rgba(168, 212, 245, 0.8); outline-offset: 2px; }
    .pg-lead-short {
      margin: 0;
      color: rgba(247, 241, 230, 0.78);
      font-size: 0.92rem;
      line-height: 1.4;
      max-width: min(720px, 100%);
    }
    .pg-lead-short strong { color: #fff; font-weight: 600; }
    .pg-howto-dialog.pg-module-dialog { max-width: min(560px, 94vw); }
    .pg-howto-body { font-size: 0.88rem; line-height: 1.5; color: #3a4450; }
    .pg-howto-body p { margin: 0 0 12px; }
    .pg-howto-body p:last-child { margin-bottom: 0; }
    .pg-howto-body code { font-size: 0.85em; }
    .pg-title {
      font-size: clamp(1.5rem, 2.5vw, 2rem);
      line-height: 1.08;
      letter-spacing: -0.03em;
      font-weight: 800;
    }
    .pg-title em { font-style: normal; color: var(--pg-header-accent); font-weight: 700; }
    .ui-version {
      display: inline-block;
      margin-left: 8px;
      padding: 3px 10px;
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      border-radius: 999px;
      background: rgba(255,255,255,0.1);
      color: #a8d4f5;
      border: 1px solid rgba(168,212,245,0.35);
      font-variant-numeric: tabular-nums;
      vertical-align: middle;
    }
    /* Full width under header scrim so banner row aligns with main grid below (no right-side dead strip). */
    .pg-banner-strip {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
    }
    .pg-banner-stat {
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 14px;
      padding: 10px 12px;
      background: rgba(255,255,255,0.06);
      backdrop-filter: blur(10px);
      min-height: 64px;
    }
    .pg-banner-stat .pg-k {
      font-size: 0.82rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: rgba(247, 241, 230, 0.7);
      font-weight: 800;
      margin-bottom: 8px;
    }
    .pg-banner-stat .pg-v {
      font-size: 1.35rem;
      font-weight: 800;
      line-height: 1.15;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .pg-banner-stat .pg-s {
      font-size: 0.98rem;
      color: rgba(247, 241, 230, 0.85);
      line-height: 1.35;
    }
    .pg-banner-stat .pg-s.pg-s-tall { min-height: 2.8em; }
    .pg-banner-stat .status-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      flex-shrink: 0;
      background: #6b7a88;
    }
    .pg-banner-stat .status-dot.ok { background: #2fa46a; box-shadow: 0 0 8px rgba(47,164,106,0.45); }
    .pg-banner-stat .status-dot.warn { background: #b7772c; box-shadow: 0 0 8px rgba(183,119,44,0.35); }
    .pg-banner-stat .status-dot.bad { background: #d15959; box-shadow: 0 0 8px rgba(209,89,89,0.35); }
    #reasoningModelBannerTile { cursor: help; min-width: 16rem; max-width: 20rem; }
    #reasoningModelBannerTile.rm-sig-green .pg-rm-head { color: #2fa46a; }
    #reasoningModelBannerTile.rm-sig-amber .pg-rm-head { color: #b7772c; }
    #reasoningModelBannerTile.rm-sig-red .pg-rm-head { color: #d15959; }
    #reasoningModelBannerTile.rm-sig-blue .pg-rm-head { color: #4a7bb4; }
    .pg-banner-stat--reasoningmodel .pg-rm-head {
      font-size: 1.2rem; font-weight: 800; line-height: 1.2; margin-top: 2px; letter-spacing: 0.02em;
    }
    .pg-banner-stat--reasoningmodel .pg-rm-core {
      font-size: 0.9rem; font-weight: 600; line-height: 1.45; margin-top: 6px; color: rgba(247, 241, 230, 0.94);
    }
    .pg-banner-stat--reasoningmodel .pg-rm-cost {
      font-size: 0.8rem; line-height: 1.4; margin-top: 6px; color: rgba(247, 241, 230, 0.88);
    }
    .pg-rm-billing { display: inline-block; margin-top: 6px; font-size: 0.8rem; font-weight: 700; color: #6eb5f9; text-decoration: underline; }
    .pg-rm-billing:hover { color: #9dcbf9; }
    .pg-rm-gw { font-size: 0.8rem; display: flex; align-items: flex-start; gap: 6px; margin-top: 8px; cursor: pointer; line-height: 1.3; }
    .pg-rm-gw input { margin: 0; margin-top: 2px; flex-shrink: 0; }
    /* D10.1 — compact Paper P&L in banner strip (with other status cards; not in sidebar Controls) */
    .pg-banner-stat.pg-banner-stat--pnl {
      cursor: default;
    }
    .pg-banner-stat.pg-banner-stat--pnl .banner-pnl-amt {
      font-variant-numeric: tabular-nums;
      font-size: 1.55rem;
      letter-spacing: -0.02em;
    }
    .pg-banner-stat.pg-banner-stat--pnl .pg-s#bannerPnlS {
      font-size: 1.05rem;
      font-weight: 700;
    }
    .pg-banner-pnl-baseline-row {
      margin-top: 8px;
      font-size: 0.92rem;
      font-weight: 700;
      color: rgba(247, 241, 230, 0.88);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }
    .pg-banner-pnl-baseline-row label { display: flex; align-items: center; gap: 8px; flex: 1 1 auto; min-width: 0; }
    #paperBaselineSlider {
      flex: 1 1 120px;
      min-width: 100px;
      max-width: 220px;
      accent-color: #5ab88a;
    }
    #paperBaselineLabel { font-variant-numeric: tabular-nums; white-space: nowrap; }
    .pg-banner-stat.pg-banner-stat--pnl .banner-pnl-amt.up { color: #7fd9a8; }
    .pg-banner-stat.pg-banner-stat--pnl .banner-pnl-amt.down { color: #f0a8a8; }
    .pg-banner-stat.pg-banner-stat--pnl .banner-pnl-amt.neutral { color: rgba(247, 241, 230, 0.85); }
    .pg-banner-pnl-micro {
      margin-top: 6px;
      height: 4px;
      border-radius: 2px;
      background: rgba(255, 255, 255, 0.12);
      position: relative;
      overflow: hidden;
    }
    .pg-banner-pnl-micro .pg-banner-pnl-micro-fill {
      position: absolute;
      left: 0;
      top: 0;
      height: 100%;
      border-radius: 2px;
      opacity: 0.85;
      pointer-events: none;
      transition: width 0.2s ease, left 0.2s ease;
    }
    .pg-banner-pnl-micro .pg-banner-pnl-micro-fill.up { background: #2fa46a; }
    .pg-banner-pnl-micro .pg-banner-pnl-micro-fill.down { background: #d15959; }
    .pg-row {
      display: grid;
      gap: 18px;
      margin-bottom: 18px;
    }
    .pg-row-main {
      /* Wireframe: narrow Controls sidebar | main = Terminal (top) + Scorecard (bottom). */
      grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
      align-items: stretch;
      gap: 20px;
      min-height: calc(100vh - 200px);
      width: 100%;
    }
    .pg-main-col {
      min-width: 0;
      width: 100%;
      display: flex;
      flex-direction: column;
      flex: 1 1 auto;
    }
    .pg-operator-col {
      min-width: 0;
      display: flex;
      flex-direction: column;
      min-height: 0;
      border-right: 1px solid var(--pg-line);
      padding-right: 4px;
    }
    details.pg-panel-controls.pg-panel-fold {
      flex: 1 1 auto;
      min-height: 0;
      display: flex;
      flex-direction: column;
    }
    details.pg-panel-controls.pg-panel-fold > summary {
      flex-shrink: 0;
    }
    details.pg-panel-controls.pg-panel-fold > .pg-panel-fold-body.pg-panel-controls-body {
      flex: 1 1 auto;
      min-height: 0;
      display: flex;
      flex-direction: column;
      overflow-y: auto;
      padding-top: 4px;
    }
    .pg-runtime-stack {
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
      width: 100%;
      flex: 1 1 auto;
      min-height: 0;
    }
    .pg-student-triangle-dock { flex: 0 0 auto; }
    /* D10.2 — focus-driven triptych (terminal-dark overview tiles + full-width expand) */
    .pg-focus-dock {
      --pg-focus-dock-h: min(320px, 36vh);
      position: relative;
      z-index: 3;
      border: 1px solid rgba(100, 140, 180, 0.35);
      border-radius: var(--pg-radius-lg);
      background: #0a0e12;
      overflow: hidden;
      flex: 0 0 auto;
      min-height: 0;
      display: flex;
      flex-direction: column;
      width: 100%;
      min-width: 0;
      align-self: stretch;
      box-sizing: border-box;
    }
    /* Overview: shrink-wrap to tile row height — avoid a fixed band height + grid row stretch (was leaving a huge empty void). */
    .pg-focus-dock[data-pg-focus-mode="overview"] {
      height: auto;
      max-height: none;
      align-items: stretch;
    }
    /* Expanded: fixed band height so absolute panes and terminal scroll resolve. */
    .pg-focus-dock[data-pg-focus-mode]:not([data-pg-focus-mode="overview"]) {
      height: var(--pg-focus-dock-h);
      max-height: var(--pg-focus-dock-h);
      flex: 0 0 var(--pg-focus-dock-h);
    }
    .pg-focus-overview {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      padding: 10px;
      flex: 0 0 auto;
      align-content: start;
      justify-items: stretch;
      min-height: 0;
      min-width: 0;
      width: 100%;
      box-sizing: border-box;
      background: #0a0e12;
    }
    .pg-focus-overview > .pg-focus-quick-h { min-width: 0; }
    .pg-focus-overview > .pg-focus-tile { min-width: 0; }
    .pg-focus-quick-h {
      grid-column: 1 / -1;
      margin: 0 0 2px;
      padding: 0 2px;
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #6b7a88;
    }
    .pg-focus-tile {
      position: relative;
      z-index: 2;
      appearance: none;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 10px;
      background: linear-gradient(180deg, #151b22 0%, #0f1419 100%);
      padding: 10px 10px 8px;
      text-align: left;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-width: 0;
      min-height: 0;
      transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
      font: inherit;
      color: #e6edf3;
    }
    .pg-focus-tile:hover {
      border-color: rgba(45, 138, 106, 0.55);
      box-shadow: 0 0 0 1px rgba(45, 138, 106, 0.25);
      background: linear-gradient(180deg, #1a222c 0%, #121820 100%);
    }
    .pg-focus-tile:focus-visible { outline: 2px solid #3dd68c; outline-offset: 2px; }
    .pg-focus-tile-k {
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #8b98a5;
      margin: 0;
    }
    .pg-focus-tile-body {
      font-size: 0.88rem;
      line-height: 1.4;
      color: #e6edf3;
      overflow: hidden;
      overflow-wrap: anywhere;
      word-break: break-word;
      white-space: normal;
      flex: 1 1 auto;
      min-height: 0;
    }
    .pg-focus-overview .pg-focus-tile-body { flex: 0 1 auto; }
    .pg-focus-tile-hint { font-size: 0.72rem; color: #7d8a98; margin: 0; line-height: 1.35; }
    /* [hidden] must win over .pg-focus-expanded display — otherwise expanded stays on-screen and blocks tile clicks. */
    .pg-focus-overview[hidden],
    .pg-focus-expanded[hidden] {
      display: none !important;
    }
    .pg-focus-expanded:not([hidden]) {
      display: flex;
      flex-direction: column;
      flex: 1 1 auto;
      min-height: 0;
      min-width: 0;
      width: 100%;
    }
    .pg-focus-expanded-head {
      display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.1);
      background: #121820;
      flex: 0 0 auto;
    }
    .pg-focus-expanded-tabs { display: flex; align-items: center; gap: 6px; flex: 1 1 auto; min-width: 0; }
    .pg-focus-expanded-tab {
      appearance: none;
      border: 1px solid rgba(255,255,255,0.14);
      background: rgba(0,0,0,0.15);
      color: rgba(230, 237, 243, 0.9);
      padding: 6px 10px;
      border-radius: 999px;
      cursor: pointer;
      font: inherit;
      font-size: 0.78rem;
      font-weight: 700;
      line-height: 1;
      white-space: nowrap;
    }
    .pg-focus-expanded-tab:hover { background: rgba(255,255,255,0.08); }
    .pg-focus-expanded-tab.is-active {
      background: rgba(45, 164, 120, 0.18);
      border-color: rgba(45, 164, 120, 0.55);
      color: #e6edf3;
    }
    /* Subtitle only — avoids repeating the same word as the quick-view tile label ("Terminal" twice). */
    .pg-focus-expanded-title { font-size: 0.72rem; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; color: #9aa7b4; }
    .pg-focus-back-btn {
      font-size: 0.75rem;
      padding: 6px 10px;
      border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.18);
      background: #1c2530;
      color: #e6edf3;
      cursor: pointer;
      font-weight: 600;
    }
    .pg-focus-back-btn:hover { background: #243040; }
    .pg-focus-expanded-body { flex: 1 1 auto; min-height: 0; overflow: hidden; position: relative; }
    .pg-focus-pane { position: absolute; inset: 0; overflow: auto; padding: 10px 12px 12px; -webkit-overflow-scrolling: touch; }
    .pg-focus-pane-inner--dark { background: #0f1419; color: #e6edf3; border-radius: 8px; padding: 10px; }
    body[data-pg-focus-expanded="1"] .pg-focus-dock { box-shadow: 0 0 0 2px rgba(45, 164, 120, 0.35); }
    .pg-focus-pane--results {
      background: linear-gradient(180deg, #1a2330 0%, #152028 100%);
      color: #f0f4f8;
    }
    .pg-focus-pane--results .pg-tab-strip { margin-top: 4px; }
    .pg-focus-pane--results .pg-tab {
      padding: 8px 10px; font-size: 11px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.12);
      background: rgba(0,0,0,0.2); color: rgba(247,241,230,0.9); cursor: pointer;
    }
    .pg-focus-pane--results .pg-tab.active { background: rgba(255,255,255,0.12); border-color: rgba(255,255,255,0.25); color: #fff; }
    .pg-focus-pane--results .policy-table th { background: rgba(255,255,255,0.1); color: rgba(247,241,230,0.95); }
    .pg-focus-pane--results .policy-table td { color: #f0f4f8; border-color: rgba(255,255,255,0.12); }
    .pg-focus-pane--results .pg-pre-json { background: rgba(0,0,0,0.25); color: #e8ecf0; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 10px; }
    .pg-focus-pane--results .hint { color: rgba(247,241,230,0.7); }
    /* Modules pane — same dark shell as terminal; list rows readable on charcoal */
    .pg-focus-pane--modules {
      background: linear-gradient(180deg, #121820 0%, #0d1218 100%);
      color: #e6edf3;
    }
    .pg-focus-pane--modules .pg-pill-row { margin-bottom: 8px; }
    .pg-focus-pane--modules .pg-pill {
      background: rgba(255, 255, 255, 0.08);
      border-color: rgba(255, 255, 255, 0.14);
      color: #c5d0db;
    }
    .pg-focus-pane--modules .pg-status-item {
      background: rgba(255, 255, 255, 0.05);
      border-color: rgba(255, 255, 255, 0.12);
    }
    .pg-focus-pane--modules .pg-status-name { color: #f0f4f8; }
    .pg-focus-pane--modules .pg-status-meta { color: rgba(230, 237, 243, 0.78); }
    .pg-focus-pane--modules .pg-module-board-msg { color: rgba(230, 237, 243, 0.82); margin: 0; font-size: 0.82rem; }
    /* Quick View → Modules: compact chips (dot + label); full detail in modal — matches Quick view sub-panel density */
    .pg-focus-pane--modules #moduleBoardList.pg-status-list {
      display: flex;
      flex-wrap: wrap;
      align-content: flex-start;
      align-items: flex-start;
      gap: 8px 10px;
    }
    .pg-focus-pane--modules #moduleBoardList .pg-status-item {
      display: inline-flex;
      flex-direction: row;
      align-items: center;
      gap: 8px;
      width: auto;
      max-width: min(100%, 22rem);
      margin: 0;
      padding: 5px 10px 5px 8px;
      border-radius: 999px;
      grid-template-columns: unset;
    }
    .pg-focus-pane--modules #moduleBoardList .pg-status-item .status-dot { margin-top: 0; }
    .pg-focus-pane--modules #moduleBoardList .pg-status-meta { display: none; }
    .pg-focus-pane--modules #moduleBoardList .pg-status-item > div { min-width: 0; flex: 1 1 auto; }
    .pg-focus-pane--modules #moduleBoardList .pg-status-name {
      font-size: 0.82rem;
      font-weight: 700;
      margin: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .pg-student-triangle-body {
      font-size: 0.88rem;
      line-height: 1.48;
      color: var(--pg-ink);
    }
    .pg-student-triangle-body .pg-student-tri-dl {
      margin: 0;
      display: grid;
      grid-template-columns: minmax(0, 12rem) 1fr;
      gap: 6px 14px;
    }
    .pg-student-triangle-body .pg-student-tri-dl dt {
      margin: 0;
      color: var(--pg-muted);
      font-weight: 700;
      font-size: 0.78rem;
    }
    .pg-student-triangle-body .pg-student-tri-dl dd { margin: 0; }
    .pg-student-triangle-body .pg-student-tri-note {
      margin: 10px 0 0;
      font-size: 0.78rem;
      color: var(--pg-muted);
      line-height: 1.42;
    }
    /* D11 — contractual: one level visible; chrome pinned; body scrolls */
    .pg-student-d11 {
      flex: 1;
      min-height: 10rem;
      display: flex;
      flex-direction: column;
      min-height: 0;
      overflow: hidden;
    }
    .pg-student-d11-layout {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }
    /* Pinned chrome: match light Pattern Machine surface — not a dark “fat strip” on cream UI */
    .pg-student-d11-chrome {
      flex-shrink: 0;
      position: sticky;
      top: 0;
      z-index: 3;
      background: linear-gradient(180deg, var(--pg-surface-strong) 0%, var(--pg-surface) 100%);
      border-bottom: 1px solid var(--pg-line);
      padding: 6px 4px 8px;
      margin: 0 0 0;
    }
    .pg-student-d11-bc {
      font-size: 0.75rem;
      color: var(--pg-muted);
      margin: 0 0 6px;
      line-height: 1.4;
    }
    .pg-student-d11-bc strong { color: var(--pg-ink); font-weight: 600; }
    .pg-student-d11-nav {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px 12px;
      margin: 0;
    }
    .pg-student-d11-carets {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      margin-right: 4px;
    }
    .pg-student-d11-caret {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 26px;
      height: 26px;
      padding: 0;
      border-radius: 999px;
      border: 1px solid var(--pg-line);
      background: var(--pg-teal-soft);
      color: var(--pg-ink);
      font-size: 1rem;
      line-height: 1;
      cursor: pointer;
    }
    .pg-student-d11-caret:hover:not(:disabled) {
      border-color: rgba(47, 127, 121, 0.45);
      background: rgba(47, 127, 121, 0.18);
    }
    .pg-student-d11-caret:disabled {
      opacity: 0.32;
      cursor: not-allowed;
    }
    .pg-student-d11-nav button {
      font-size: 0.78rem;
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid var(--pg-line);
      background: rgba(255, 255, 255, 0.75);
      color: var(--pg-ink);
      cursor: pointer;
    }
    .pg-student-d11-nav button:hover { border-color: rgba(47, 127, 121, 0.45); }
    a.pg-student-d11-trace {
      font-size: 0.78rem;
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid rgba(47, 127, 121, 0.55);
      background: rgba(47, 127, 121, 0.14);
      color: var(--pg-ink);
      text-decoration: none;
      font-weight: 650;
      white-space: nowrap;
    }
    a.pg-student-d11-trace:hover { border-color: rgba(47, 127, 121, 0.75); }
    .pg-student-d11-trace--disabled {
      font-size: 0.78rem;
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px dashed var(--pg-line);
      color: var(--pg-muted);
      opacity: 0.75;
      white-space: nowrap;
    }
    .pg-student-d11-scroll {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      overflow-x: hidden;
      scrollbar-gutter: stable;
      padding-right: 2px;
    }
    .pg-student-d11-legend {
      font-size: 0.72rem;
      color: var(--pg-muted);
      margin: 0 0 8px;
      line-height: 1.35;
    }
    .pg-student-d11-table-wrap { overflow: auto; max-width: 100%; position: relative; }
    /* Keep remove control visible — wide L1 tables scroll horizontally. */
    .pg-student-d11-table thead th.pg-student-d11-sticky-actions,
    .pg-student-d11-table tbody td.pg-student-d11-sticky-actions {
      position: sticky;
      right: 0;
      z-index: 2;
      background: var(--pg-surface-strong);
      box-shadow: -8px 0 12px rgba(35, 44, 56, 0.07);
    }
    .pg-student-d11-table thead th.pg-student-d11-sticky-actions { z-index: 3; }
    .pg-student-d11-table tbody tr:nth-child(even) td.pg-student-d11-sticky-actions {
      background: rgba(120, 175, 235, 0.12);
    }
    .pg-student-d11-table tbody tr[data-run-inflight] td.pg-student-d11-sticky-actions {
      background: rgba(70, 78, 95, 0.55);
    }
    .pg-student-d11-table tbody tr[data-run-row]:nth-child(odd):hover td.pg-student-d11-sticky-actions {
      background: rgba(30, 214, 170, 0.12);
    }
    .pg-student-d11-table tbody tr[data-run-row]:nth-child(even):hover td.pg-student-d11-sticky-actions {
      background: rgba(30, 214, 170, 0.16);
    }
    .pg-student-d11-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.74rem;
    }
    .pg-student-d11-table th,
    .pg-student-d11-table td {
      text-align: left;
      padding: 6px 8px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      vertical-align: top;
      white-space: nowrap;
    }
    .pg-student-d11-table th { color: var(--pg-muted); font-weight: 700; font-size: 0.70rem; }
    .pg-student-d11-table tbody tr:nth-child(even) td {
      background: rgba(120, 175, 235, 0.075);
    }
    .pg-student-d11-table tbody tr[data-run-inflight] td {
      background: rgba(70, 78, 95, 0.42);
    }
    .pg-student-d11-table tbody tr[data-run-row]:nth-child(odd):hover td {
      background: rgba(30, 214, 170, 0.08);
    }
    .pg-student-d11-table tbody tr[data-run-row]:nth-child(even):hover td {
      background: rgba(30, 214, 170, 0.1);
    }
    .pg-student-d11-table tr[data-run-row] { cursor: pointer; }
    tr[data-l1-band="A"] td { box-shadow: inset 0 0 0 2px rgba(46, 160, 67, 0.38); }
    tr[data-l1-band="B"] td { box-shadow: inset 0 0 0 2px rgba(218, 85, 85, 0.32); }
    tr[data-l1-band="baseline_ruler"] td { box-shadow: inset 0 0 0 2px rgba(139, 148, 158, 0.35); }
    .pg-student-l1-groups-preview { margin-top: 8px; }
    .pg-student-l1-groups-preview .pg-student-d11-table { font-size: 0.72rem; }
    .pg-student-d11-row-del {
      min-width: 28px;
      padding: 2px 6px;
      font-size: 1rem;
      line-height: 1;
      border-radius: 6px;
      border: 1px solid rgba(163, 43, 43, 0.45);
      background: rgba(163, 43, 43, 0.12);
      color: var(--pg-ink);
      cursor: pointer;
    }
    .pg-student-d11-row-del:hover:not(:disabled) { border-color: #a32b2b; background: rgba(163, 43, 43, 0.22); }
    .pg-student-d11-row-del:disabled { opacity: 0.35; cursor: not-allowed; }
    /* D13 — single horizontal run summary band; zebra cells for scanability */
    .pg-student-d13-run-summary {
      display: flex;
      flex-wrap: nowrap;
      align-items: stretch;
      gap: 6px 8px;
      overflow-x: auto;
      margin: 0 0 12px;
      padding: 8px 4px 10px;
      border-bottom: 1px solid rgba(127, 140, 153, 0.28);
      font-size: 0.68rem;
      line-height: 1.35;
      scrollbar-gutter: stable;
    }
    .pg-student-d13-run-summary .pg-student-d13-rs-cell {
      flex: 0 0 auto;
      white-space: nowrap;
      padding: 8px 12px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
    }
    .pg-student-d13-run-summary .pg-student-d13-rs-cell:nth-child(odd) {
      background: rgba(255, 255, 255, 0.95);
      box-shadow: inset 0 0 0 1px rgba(127, 140, 153, 0.12);
    }
    .pg-student-d13-run-summary .pg-student-d13-rs-cell:nth-child(even) {
      background: rgba(186, 214, 242, 0.5);
      box-shadow: inset 0 0 0 1px rgba(100, 140, 180, 0.15);
    }
    .pg-student-d13-run-summary .pg-student-d13-rs-k {
      color: var(--pg-muted);
      font-weight: 700;
      margin-right: 4px;
    }
    .pg-student-d11-carousel-wrap {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 0 0 8px;
    }
    .pg-student-d11-carousel-row {
      display: flex;
      flex-direction: row;
      align-items: stretch;
      gap: 8px;
      min-height: 220px;
    }
    .pg-student-d11-carousel-btn {
      flex: 0 0 auto;
      align-self: center;
      width: 32px;
      min-height: 48px;
      padding: 2px 4px;
      border-radius: 6px;
      border: 1px solid rgba(255,255,255,0.14);
      background: rgba(0,0,0,0.18);
      color: var(--pg-ink);
      font-size: 1rem;
      cursor: pointer;
      line-height: 1;
    }
    .pg-student-d11-carousel-btn:hover:not(:disabled) { border-color: rgba(30, 214, 170, 0.45); }
    .pg-student-d11-carousel-btn:disabled {
      opacity: 0.35;
      cursor: not-allowed;
    }
    .pg-student-d11-carousel-viewport {
      flex: 1;
      min-width: 0;
      overflow-x: auto;
      overflow-y: hidden;
      scroll-snap-type: x mandatory;
      scroll-behavior: smooth;
      padding: 8px 0 12px;
      scrollbar-gutter: stable;
    }
    .pg-student-d11-strip {
      display: flex;
      gap: 16px;
      padding: 0 12px;
      min-height: 200px;
      align-items: stretch;
    }
    .pg-student-d11-strip--carousel {
      scroll-snap-type: x mandatory;
    }
    .pg-student-d11-carousel-meta {
      font-size: 0.70rem;
      color: var(--pg-muted);
      text-align: center;
      margin: 0 0 4px;
      line-height: 1.35;
    }
    .pg-student-d11-slice {
      /* ~3× prior mini-tile width: one readable card per viewport band */
      flex: 0 0 clamp(240px, 46vw, 400px);
      width: clamp(240px, 46vw, 400px);
      max-width: 400px;
      min-width: 240px;
      scroll-snap-align: start;
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 10px;
      padding: 12px 14px;
      background: rgba(0,0,0,0.10);
      font-size: 0.8rem;
      line-height: 1.45;
      cursor: pointer;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
      gap: 0;
    }
    .pg-student-d11-slice-id {
      font-size: 0.68rem;
      font-weight: 600;
      word-break: break-all;
      line-height: 1.3;
      margin-bottom: 8px;
      color: var(--pg-ink);
    }
    .pg-student-d11-slice-ts {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.02em;
      opacity: 0.88;
      margin-bottom: 10px;
    }
    .pg-student-d11-slice-outcome {
      font-size: 0.88rem;
      font-weight: 600;
      margin-bottom: 6px;
    }
    .pg-student-d11-slice-align {
      font-size: 0.74rem;
      margin-bottom: 8px;
      color: var(--pg-ink);
    }
    .pg-student-d11-slice-conf,
    .pg-student-d11-slice-gh,
    .pg-student-d11-slice-delta {
      font-size: 0.76rem;
      margin-top: 6px;
      color: var(--pg-ink);
    }
    .pg-student-d11-slice-gh {
      color: var(--pg-muted);
    }
    .pg-student-d11-slice-delta {
      margin-top: auto;
      padding-top: 8px;
      border-top: 1px solid rgba(127, 140, 153, 0.22);
      font-size: 0.70rem;
      color: var(--pg-muted);
    }
    .pg-student-d11-slice--focused {
      border-color: rgba(30, 214, 170, 0.45);
      box-shadow: 0 0 0 1px rgba(30, 214, 170, 0.12);
    }
    .pg-student-d11-slice:hover { border-color: rgba(30, 214, 170, 0.35); }
    .pg-student-d11-slice--WIN { border-left: 5px solid #2ea043; }
    .pg-student-d11-slice--LOSS { border-left: 5px solid #da5555; }
    .pg-student-d11-slice--NO_TRADE { border-left: 5px solid #7a8794; }
    .pg-student-d11-deep ul {
      margin: 0;
      padding-left: 1.1rem;
      font-size: 0.80rem;
      line-height: 1.4;
    }
    .pg-student-d11-deep li { margin: 0 0 4px; }
    .pg-student-d11-deep .pg-student-d11-k { color: var(--pg-muted); font-weight: 700; font-size: 0.72rem; }
    /* SR-4 / AC-3: long Student panel body scrolls inside the fold; default band ≈60% viewport, drag lower-right to resize. */
    details.pg-student-triangle-dock {
      scroll-margin-top: 12px;
      position: relative;
      z-index: 0;
    }
    details.pg-student-triangle-dock > .pg-panel-fold-body.pg-student-triangle-fold-body {
      height: 60vh;
      min-height: 14rem;
      max-height: 88vh;
      resize: vertical;
      overflow: hidden;
      overflow-x: hidden;
      box-sizing: border-box;
      scrollbar-gutter: stable;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    details.pg-student-triangle-dock .pg-student-triangle-body {
      max-height: none;
      flex: 1;
      min-height: 0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      padding-right: 4px;
    }
    .pg-secondary-surface-label {
      display: inline-block;
      margin-left: 6px;
      padding: 2px 8px;
      font-size: 0.65rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      border-radius: 999px;
      background: rgba(80, 100, 122, 0.14);
      color: var(--pg-steel);
      border: 1px solid rgba(80, 100, 122, 0.22);
      vertical-align: middle;
    }
    .pg-telemetry-dock {
      position: relative;
      top: auto;
      z-index: auto;
      flex: 0 0 auto;
      max-height: min(44vh, 540px);
      min-height: 10rem;
      display: flex;
      flex-direction: column;
    }
    /* §H: Terminal = activity left + compact summary right; capped height, internal scroll */
    .pg-terminal-split {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(160px, 220px);
      gap: 10px;
      align-items: stretch;
      max-height: min(40vh, 500px);
      min-height: 0;
    }
    @media (max-width: 1100px) {
      .pg-terminal-split {
        grid-template-columns: 1fr;
        max-height: min(50vh, 620px);
      }
      .pg-terminal-compact-summary {
        max-height: 8rem;
      }
    }
    .pg-terminal-split-left {
      display: flex;
      flex-direction: column;
      min-height: 0;
      min-width: 0;
      overflow: hidden;
    }
    .pg-terminal-compact-summary {
      font-size: 0.72rem;
      line-height: 1.4;
      color: #c5d0db;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      padding: 8px 10px;
      overflow-y: auto;
      max-height: 100%;
    }
    .pg-terminal-compact-summary .pg-tcs-title {
      margin: 0 0 6px;
      font-size: 0.68rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: #8b98a5;
    }
    .pg-terminal-compact-summary dl {
      margin: 0;
      display: grid;
      grid-template-columns: minmax(0, 5.2rem) 1fr;
      gap: 3px 6px;
    }
    .pg-terminal-compact-summary dt { color: #8b98a5; font-weight: 700; }
    .pg-terminal-compact-summary dd { margin: 0; word-break: break-word; }
    .pg-evidence-scorecard-pane {
      margin-top: 8px;
      max-height: min(58vh, 560px);
      overflow: auto;
      padding-right: 2px;
    }
    .pg-learning-events-strip {
      border: 1px solid #1e3a5f;
      border-radius: var(--pg-radius-lg);
      background: var(--pg-surface-strong);
      padding: 10px 14px 12px;
      margin-top: 10px;
    }
    .pg-learning-events-strip[hidden] { display: none !important; }
    .pg-learning-events-h {
      margin: 0 0 8px;
      font-size: 0.82rem;
      font-weight: 800;
      color: var(--pg-teal);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .pg-learning-events-ul {
      margin: 0;
      padding-left: 1.1rem;
      font-size: 0.82rem;
      line-height: 1.45;
      color: var(--pg-ink);
    }
    .pg-learning-events-note {
      margin: 8px 0 0;
      font-size: 0.72rem;
      color: var(--pg-muted);
      line-height: 1.35;
    }
    details.pg-panel-fold.pg-panel-score.pg-scorecard-dock {
      flex: 1 1 auto;
      min-height: 0;
      display: flex;
      flex-direction: column;
    }
    details.pg-panel-fold.pg-panel-score.pg-scorecard-dock > summary {
      flex-shrink: 0;
    }
    details.pg-panel-fold.pg-panel-score.pg-scorecard-dock > .pg-panel-fold-body {
      flex: 1 1 auto;
      min-height: 0;
      overflow-y: auto;
      overflow-x: hidden;
      display: flex;
      flex-direction: column;
    }
    details.pg-panel-fold.pg-panel-score.pg-scorecard-dock .scorecard-panel-inner {
      flex: 1 1 auto;
      min-height: 0;
    }
    .pg-scorecard-split {
      display: flex;
      flex-direction: column;
      gap: 10px;
      min-height: min(70vh, 720px);
    }
    .pg-scorecard-upper {
      flex: 1 1 50%;
      min-height: 0;
      overflow: auto;
      display: flex;
      flex-direction: column;
    }
    .pg-scorecard-upper .pg-table-scroll {
      max-height: min(36vh, 420px);
    }
    .pg-scorecard-lower {
      flex: 1 1 50%;
      min-height: 200px;
      max-height: min(42vh, 560px);
      overflow: hidden;
      display: flex;
      flex-direction: column;
      gap: 0;
      border-top: 2px solid var(--pg-line);
      padding-top: 0;
      background: var(--pg-surface-strong);
      border-radius: 0 0 12px 12px;
    }
    .pg-barney-subsection {
      flex: 1 1 48%;
      min-height: 72px;
      overflow: auto;
      padding: 10px 12px 8px;
      border-bottom: 1px solid var(--pg-line);
    }
    .pg-askdata-subsection {
      flex: 1 1 52%;
      min-height: 120px;
      overflow: auto;
      padding: 10px 12px 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .pg-askdata-input {
      width: 100%;
      min-height: 3.25rem;
      max-height: 6rem;
      resize: vertical;
      font-size: 0.86rem;
      line-height: 1.35;
      padding: 8px 10px;
      border-radius: 8px;
      border: 1px solid var(--pg-line);
      font-family: inherit;
      box-sizing: border-box;
    }
    .pg-askdata-invite {
      margin: 0 0 6px;
      font-size: 0.78rem;
      line-height: 1.4;
      color: var(--pg-muted);
    }
    details.pg-askdata-starters-fold {
      margin: 0 0 10px;
      border: 1px dashed rgba(54, 64, 74, 0.32);
      border-radius: 8px;
      padding: 0 8px 4px;
      background: rgba(0, 0, 0, 0.02);
    }
    details.pg-askdata-starters-fold > summary.pg-askdata-starters-fold-summary {
      cursor: pointer;
      font-size: 0.78rem;
      font-weight: 700;
      color: var(--pg-muted);
      padding: 6px 0 4px;
      user-select: none;
      list-style-position: outside;
    }
    details.pg-askdata-starters-fold .pg-askdata-starters-inner {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px 8px;
      padding: 6px 0 4px;
      border-top: 1px dashed rgba(54, 64, 74, 0.22);
    }
    button.pg-askdata-chip {
      font: inherit;
      font-size: 0.76rem;
      padding: 5px 11px;
      border-radius: 999px;
      border: 1px solid rgba(30, 58, 95, 0.38);
      background: rgba(30, 58, 95, 0.07);
      color: var(--pg-ink);
      cursor: pointer;
      line-height: 1.25;
      text-align: left;
    }
    button.pg-askdata-chip:hover {
      border-color: var(--pg-accent);
      color: var(--pg-accent);
      background: rgba(30, 58, 95, 0.12);
    }
    .pg-askdata-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .pg-askdata-status {
      font-size: 0.78rem;
      color: var(--pg-muted);
      margin: 0;
      min-height: 1.1em;
    }
    .pg-askdata-response {
      flex: 1 1 auto;
      min-height: 4rem;
      max-height: min(22vh, 240px);
      overflow: auto;
    }
    .pg-barney-title {
      font-weight: 800;
      margin: 0 0 4px;
      font-size: 0.92rem;
      color: var(--pg-accent);
    }
    .pg-barney-body {
      font-size: 0.88rem;
      line-height: 1.45;
      white-space: pre-wrap;
      color: var(--pg-ink);
      margin: 0;
    }
    @media (max-width: 1680px) {
      .pg-row-main {
        grid-template-columns: minmax(200px, 260px) minmax(0, 1fr);
        overflow-x: auto;
        padding-bottom: 6px;
        -webkit-overflow-scrolling: touch;
      }
    }
    .pg-panel {
      background: var(--pg-surface);
      border: 1px solid #1e3a5f;
      border-radius: var(--pg-radius-xl);
      box-shadow: var(--pg-shadow);
      padding: 18px 20px 20px;
      min-width: 0;
      backdrop-filter: blur(12px);
    }
    .pg-panel-controls { min-height: 0; }
    .pg-panel-controls-body {
      max-height: none;
      overflow-x: hidden;
      padding-right: 6px;
      scrollbar-gutter: stable;
    }
    .pg-controls-core {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    /* D10.3 — minimal control strip (aligned rows) */
    .pg-controls-minimal {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 4px;
    }
    .pg-controls-min-grid {
      display: grid;
      grid-template-columns: minmax(7.5rem, 38%) 1fr;
      gap: 8px 12px;
      align-items: center;
    }
    .pg-controls-min-grid label {
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--pg-muted);
      margin: 0;
      justify-self: start;
      text-align: left;
    }
    .pg-controls-min-grid select,
    .pg-controls-min-grid input[type="number"] {
      justify-self: stretch;
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
    }
    .pg-controls-min-grid .pg-controls-span-2 {
      grid-column: 1 / -1;
    }
    .pg-controls-run-row {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .pg-controls-run-row .pg-op-btn--run { width: 100%; }
    .pg-controls-run-row #parallelCancelBtn {
      width: 100%;
      max-width: 340px;
      align-self: stretch;
      box-sizing: border-box;
    }
    details.pg-controls-advanced {
      margin-top: 10px;
      border: 1px dashed rgba(30, 58, 95, 0.35);
      border-radius: 12px;
      padding: 0 10px 8px;
      background: rgba(30, 58, 95, 0.04);
    }
    details.pg-controls-advanced > summary {
      cursor: pointer;
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--pg-accent);
      padding: 10px 4px;
      list-style: none;
    }
    details.pg-controls-advanced > summary::-webkit-details-marker { display: none; }
    .pg-askdata-thread {
      flex: 1 1 auto;
      min-height: 140px;
      max-height: min(42vh, 420px);
      overflow-y: auto;
      padding: 8px 10px;
      border-radius: 10px;
      background: rgba(0, 0, 0, 0.06);
      border: 1px solid var(--pg-line);
      font-size: 0.84rem;
      line-height: 1.45;
    }
    .pg-ask-msg {
      margin: 0 0 10px;
      padding: 8px 10px;
      border-radius: 8px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .pg-ask-msg-user {
      background: rgba(45, 138, 106, 0.12);
      border: 1px solid rgba(45, 138, 106, 0.35);
      margin-left: 12px;
    }
    .pg-ask-msg-assistant {
      background: rgba(30, 58, 95, 0.08);
      border: 1px solid rgba(30, 58, 95, 0.25);
      margin-right: 12px;
    }
    .pg-ask-msg-role {
      font-size: 0.65rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--pg-muted);
      margin-bottom: 4px;
    }
    .pg-ask-feedback {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px 8px;
      margin: -4px 12px 10px 0;
      padding: 6px 8px;
      border-radius: 8px;
      border: 1px dashed rgba(30, 58, 95, 0.35);
      background: rgba(30, 58, 95, 0.04);
      font-size: 0.78rem;
    }
    .pg-ask-feedback-label {
      color: var(--pg-muted);
      font-weight: 700;
      margin-right: 4px;
    }
    .pg-ask-feedback-btn {
      font: inherit;
      font-size: 0.76rem;
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid var(--pg-line);
      background: var(--pg-surface);
      cursor: pointer;
      color: var(--pg-ink);
    }
    .pg-ask-feedback-btn:hover:not(:disabled) {
      border-color: var(--pg-accent);
      color: var(--pg-accent);
    }
    .pg-ask-feedback-btn:disabled {
      opacity: 0.55;
      cursor: default;
    }
    details.pg-panel-fold.pg-barney-dock > summary .pg-panel-sub,
    details.pg-panel-fold.pg-askdata-dock > summary .pg-panel-sub,
    details.pg-panel-fold.pg-barney-ask-unified > summary .pg-panel-sub {
      font-size: 12px;
      margin-top: 4px;
    }
    /* Ask (questions) left, Ask DATA thread + batch recap right; right column is wider.
       No CSS resize handles here — fixed grid + flex + resize:vertical fights the layout and the grip misleads operators. */
    .pg-barney-ask-unified .pg-barney-ask-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
      gap: 0;
      align-items: stretch;
      min-height: min(36vh, 360px);
      height: min(48vh, 520px);
      max-height: min(56vh, 600px);
      border: 1px solid rgba(54, 64, 74, 0.35);
      border-radius: 12px;
      overflow: hidden;
      background: rgba(255, 255, 255, 0.02);
    }
    .pg-barney-ask-unified .pg-barney-ask-col--ask {
      border-right: 1px solid rgba(54, 64, 74, 0.45);
      box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.04);
    }
    @media (max-width: 900px) {
      .pg-barney-ask-unified .pg-barney-ask-grid {
        grid-template-columns: 1fr;
        border-radius: 12px;
      }
      .pg-barney-ask-unified .pg-barney-ask-col--ask {
        border-right: none;
        border-bottom: 1px solid rgba(54, 64, 74, 0.45);
        box-shadow: inset 0 -1px 0 rgba(255, 255, 255, 0.04);
      }
    }
    .pg-barney-ask-col--barney {
      display: flex;
      flex-direction: column;
      min-height: 0;
      min-width: 0;
      padding: 10px 12px 12px;
    }
    .pg-barney-ask-col--barney .pg-barney-body {
      flex: 1 1 auto;
      min-height: min(52vh, 560px);
      max-height: min(70vh, 720px);
    }
    .pg-barney-ask-unified .pg-barney-ask-col--barney .pg-barney-body {
      flex: 1 1 0;
      min-height: 72px;
      max-height: none;
      overflow: auto;
      box-sizing: border-box;
    }
    .pg-barney-ask-col--ask {
      display: flex;
      flex-direction: column;
      min-height: 0;
      min-width: 0;
      padding: 10px 12px 12px;
    }
    .pg-barney-ask-unified .pg-askdata-input {
      flex: 1 1 auto;
      min-height: 3.5rem;
      max-height: none;
      resize: vertical;
      width: 100%;
      box-sizing: border-box;
    }
    .pg-barney-ask-col--barney .pg-askdata-thread {
      flex: 1 1 auto;
      min-height: min(18vh, 200px);
      max-height: min(26vh, 280px);
      overflow: auto;
    }
    .pg-barney-ask-unified .pg-askdata-reply-shell {
      display: flex;
      flex-direction: column;
      flex: 1 1 48%;
      min-height: 140px;
      min-width: 0;
      overflow: hidden;
      box-sizing: border-box;
    }
    .pg-barney-ask-unified .pg-askdata-reply-shell.pg-askdata-reply-shell--sized {
      flex: 0 0 auto;
    }
    .pg-barney-ask-unified .pg-askdata-reply-shell .pg-askdata-thread {
      flex: 1 1 auto;
      min-height: 72px;
      max-height: none;
      overflow: auto;
      box-sizing: border-box;
    }
    .pg-askdata-reply-drag {
      flex: 0 0 10px;
      height: 10px;
      margin: 2px -4px 0;
      cursor: row-resize;
      border-radius: 4px;
      background: rgba(54, 64, 74, 0.18);
      border: 1px solid rgba(54, 64, 74, 0.35);
      box-sizing: border-box;
    }
    .pg-askdata-reply-drag:hover {
      background: rgba(30, 58, 95, 0.16);
      border-color: var(--pg-accent);
    }
    .pg-barney-ask-unified .pg-askdata-recap-block {
      flex: 1 1 auto;
      min-height: 100px;
      min-width: 0;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .pg-barney-ask-unified .pg-askdata-recap-block .pg-barney-body {
      flex: 1 1 auto;
      min-height: 48px;
    }
    .pg-barney-ask-unified .pg-barney-recap-hint {
      margin: 0 0 6px;
      font-size: 0.72rem;
      line-height: 1.35;
      color: var(--pg-muted);
      font-weight: 500;
    }
    .pg-custom-route-hint {
      margin: 0;
      padding: 8px 10px;
      font-size: 0.82rem;
      line-height: 1.4;
      background: rgba(45, 138, 106, 0.14);
      border: 1px solid rgba(45, 138, 106, 0.4);
      border-radius: 8px;
      color: var(--pg-ink, #1a2e28);
    }
    .strategy-upload-checklist li.su-ok { color: #156b45; }
    .strategy-upload-checklist li.su-fail { color: #8b2c2c; }
    .strategy-upload-checklist li.su-warn { color: #5a4a12; }
    details.pg-pattern-info-fold {
      margin-top: 4px;
      border: 1px solid var(--pg-line);
      border-radius: 14px;
      background: var(--pg-surface-strong);
      padding: 0 12px 4px;
    }
    details.pg-pattern-info-fold > summary {
      cursor: pointer;
      font-size: 0.82rem;
      font-weight: 800;
      color: var(--pg-accent);
      padding: 10px 0;
      list-style: none;
    }
    details.pg-pattern-info-fold > summary::-webkit-details-marker { display: none; }
    details.pg-pattern-info-fold .pg-pattern-info-body {
      padding: 0 0 12px;
      border-top: 1px dashed rgba(54, 64, 74, 0.18);
      margin-top: 4px;
      padding-top: 12px;
    }
    .pg-panel-score .pg-table-scroll,
    .pg-header-evidence .pg-table-scroll {
      max-height: min(48vh, 480px);
      overflow: auto;
      border-radius: 12px;
      border: 1px solid var(--pg-line);
    }
    .pg-header-evidence .pg-tab-strip { gap: 6px; flex-wrap: wrap; }
    .pg-header-evidence .pg-tab { padding: 8px 10px; font-size: 11px; }
    .pg-panel-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 14px;
    }
    .pg-panel-h {
      margin: 0;
      font-size: 1.15rem;
      letter-spacing: -0.02em;
      font-weight: 800;
      color: var(--pg-ink);
    }
    .pg-panel-sub {
      margin: 6px 0 0;
      color: var(--pg-muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .pg-chip {
      flex-shrink: 0;
      border-radius: 999px;
      padding: 7px 10px;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 800;
      border: 1px solid transparent;
    }
    .pg-chip-teal { background: var(--pg-teal-soft); color: var(--pg-teal); border-color: rgba(47, 127, 121, 0.18); }
    .pg-chip-amber { background: var(--pg-amber-soft); color: var(--pg-amber); border-color: rgba(183, 119, 44, 0.18); }
    .pg-chip-rose { background: var(--pg-rose-soft); color: var(--pg-rose); border-color: rgba(156, 84, 76, 0.18); }
    .pg-chip-steel { background: var(--pg-steel-soft); color: var(--pg-steel); border-color: rgba(80, 100, 122, 0.16); }
    .def001-science {
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid rgba(47, 127, 121, 0.25);
      background: linear-gradient(180deg, rgba(47,127,121,0.08) 0%, rgba(47,127,121,0.03) 100%);
      font-size: 0.82rem;
      line-height: 1.5;
      color: #3a4f4c;
    }
    .def001-science .def001-tag {
      display: inline-block;
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: var(--pg-teal);
      margin-bottom: 6px;
    }
    .def001-science code { font-size: 0.85em; }
    details.help-details.pg-help {
      margin-top: 12px;
      border-radius: 12px;
      border: 1px solid var(--pg-line);
      background: var(--pg-surface-strong);
      padding: 0 12px;
    }
    details.help-details.pg-help summary {
      cursor: pointer;
      font-size: 0.82rem;
      color: var(--pg-accent);
      font-weight: 600;
      padding: 10px 0;
      list-style: none;
    }
    details.help-details summary::-webkit-details-marker { display: none; }
    .help-details-body { font-size: 0.8rem; color: var(--pg-muted); padding: 0 0 12px; }
    .help-details-body p { margin: 0 0 8px; }
    .pg-block {
      margin-top: 14px;
      padding: 14px;
      border-radius: var(--pg-radius-lg);
      border: 1px dashed rgba(54, 64, 74, 0.2);
      background: var(--pg-surface-strong);
    }
    .pg-block-title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--pg-muted);
      font-weight: 800;
      margin-bottom: 10px;
    }
    .pg-run-config {
      margin-top: 12px;
      padding: 12px 12px 10px;
      border-radius: var(--pg-radius-lg);
      border: 1px solid rgba(45, 138, 106, 0.35);
      background: rgba(45, 138, 106, 0.06);
    }
    .pg-run-config-dl {
      display: grid;
      grid-template-columns: minmax(0, 7rem) 1fr;
      gap: 4px 12px;
      font-size: 0.85rem;
      margin: 0;
    }
    .pg-run-config-dl dt {
      margin: 0;
      color: var(--pg-muted);
      font-weight: 600;
    }
    .pg-run-config-dl dd { margin: 0; color: var(--pg-ink); }
    .pg-goal-readonly {
      margin-top: 12px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid #c5cdd6;
      background: #fafbfc;
    }
    .pg-goal-line { margin: 0 0 6px; font-size: 0.84rem; line-height: 1.45; color: var(--pg-ink); }
    .pg-policy-line { margin: 8px 0 0; font-size: 0.88rem; color: var(--pg-ink); }
    textarea#scenarios:disabled {
      opacity: 0.55;
      cursor: not-allowed;
      background: #eceff2;
    }
    .pg-mini-grid { display: grid; gap: 10px; }
    .pg-mini-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    @media (max-width: 900px) {
      .pg-mini-3 { grid-template-columns: 1fr; }
    }
    details.inline-details {
      margin: 6px 0 10px;
      font-size: 0.78rem;
      color: var(--pg-muted);
      border-left: 2px solid #c5cdd6;
      padding-left: 10px;
    }
    details.inline-details summary { cursor: pointer; color: #4a5560; font-weight: 500; }
    .tool-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin-bottom: 10px; }
    .tool-row .btn-secondary {
      margin-top: 0;
      background: #e8edf2;
      color: #2c3844;
      font-weight: 600;
      font-size: 0.85rem;
      padding: 8px 12px;
      border: 1px solid var(--pg-line);
    }
    .tool-row .btn-chef {
      margin-top: 0;
      background: #2d8a6a;
      color: #fff;
      font-weight: 600;
      font-size: 0.85rem;
      padding: 8px 12px;
    }
    label { display: block; margin: 10px 0 4px; font-size: 0.85rem; color: var(--pg-muted); }
    input[type=text], input[type=number], textarea, select {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid #c5cdd6;
      border-radius: 8px;
      background: #fffefb;
      color: var(--pg-ink);
      font-size: 0.88rem;
    }
    textarea {
      min-height: 160px;
      max-height: min(48vh, 480px);
      font-family: var(--pg-mono);
      font-size: 0.8rem;
      resize: vertical;
    }
    button {
      margin-top: 12px;
      padding: 10px 18px;
      border: 0;
      border-radius: 10px;
      background: var(--pg-accent);
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    /* Operator primary actions — instant press/hover, async busy, clear disabled (DEF-001 UX). */
    button.pg-op-btn {
      transition: background-color 0.09s ease, color 0.09s ease, transform 0.09s ease, box-shadow 0.09s ease,
        filter 0.09s ease, opacity 0.12s ease, border-color 0.09s ease;
      user-select: none;
    }
    button.pg-op-btn:hover:not(:disabled):not(.is-running) {
      filter: brightness(1.05);
      box-shadow: 0 1px 0 rgba(255, 255, 255, 0.2) inset, 0 2px 12px rgba(23, 92, 211, 0.12);
    }
    button.pg-op-btn:active:not(:disabled):not(.is-running) {
      transform: scale(0.98);
      box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.16);
      filter: brightness(0.94);
    }
    button.pg-op-btn:disabled:not(.is-running) {
      opacity: 0.48;
      cursor: not-allowed;
      transform: none;
      filter: none;
      box-shadow: none;
    }
    button.pg-op-btn.is-running:disabled {
      opacity: 0.9;
      cursor: wait;
      pointer-events: none;
      transform: none;
      filter: none;
    }
    button.pg-op-btn .pg-op-btn__inner {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }
    button.pg-op-btn .pg-op-btn__spinner {
      width: 14px;
      height: 14px;
      border: 2px solid rgba(0, 0, 0, 0.12);
      border-top-color: rgba(0, 0, 0, 0.5);
      border-radius: 50%;
      flex-shrink: 0;
      animation: pg-spin 0.7s linear infinite;
    }
    #runBtn.pg-op-btn .pg-op-btn__spinner,
    .btn-chef.pg-op-btn .pg-op-btn__spinner {
      border-color: rgba(255, 255, 255, 0.35);
      border-top-color: #fff;
    }
    #runBtn.pg-op-btn.is-running:disabled {
      background: #2d5a8c;
      color: #fff;
    }
    .btn-scorecard-clear.pg-op-btn.is-running:disabled {
      background: #e4edf8;
      color: #2d4a6f;
    }
    .btn-learning-reset-danger.pg-op-btn.is-running:disabled {
      background: #edd4d4;
      color: #8a2a2a;
    }
    .tool-row .btn-secondary.pg-op-btn.is-running:disabled {
      background: #d8e0e8;
      color: #24303d;
    }
    .tool-row .btn-chef.pg-op-btn.is-running:disabled {
      background: #246b52;
      color: #fff;
    }
    .btn-chef.pg-op-btn.is-running:disabled {
      background: #246b52;
      color: #fff;
    }
    .btn-upload.pg-op-btn.is-running:disabled {
      background: #eef3fa;
      color: #3a5a8a;
    }
    .btn-rename-preset.pg-op-btn.is-running:disabled {
      background: #eef2f6;
      color: #3a5068;
    }
    #runBtn { width: 100%; max-width: 340px; padding: 12px 20px; font-size: 1rem; border-radius: 12px; }
    .caps { font-size: 0.8rem; color: var(--pg-muted); margin: 8px 0 0; }
    .run-actions {
      margin-top: 8px;
      padding: 10px 0 8px;
      border-top: 1px solid rgba(54, 64, 74, 0.12);
    }
    .pg-sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .status-stack { margin-top: 12px; }
    #workerCpuHint { font-size: 0.72rem; color: var(--pg-muted); margin: 6px 0 0; line-height: 1.4; }
    #workerEffectiveLine {
      margin: 10px 0 0;
      padding: 10px 12px;
      border-radius: 10px;
      background: #f4f1ea;
      border: 1px solid var(--pg-line);
      font-size: 0.82rem;
      line-height: 1.45;
      color: #3a4450;
    }
    #workerEffectiveLine strong { color: var(--pg-ink); }
    .scorecard-legend {
      font-size: 0.76rem;
      color: var(--pg-muted);
      margin: 0 0 10px 0;
      line-height: 1.5;
      padding: 10px 12px;
      border-radius: 10px;
      background: #f4f1ea;
      border: 1px solid var(--pg-line);
    }
    .scorecard-legend strong { color: #3a4450; }
    .last-run {
      font-size: 0.85rem;
      color: var(--pg-ink);
      margin: 0 0 10px 0;
      line-height: 1.45;
    }
    .scorecard-learning-summary {
      font-size: 0.78rem;
      line-height: 1.5;
      color: var(--pg-ink);
      background: #f6f9fc;
      border: 1px solid var(--pg-line);
      border-radius: 10px;
      padding: 10px 12px;
      margin: 0 0 10px 0;
    }
    .scorecard-learning-summary .sls-line { margin: 0; }
    .scorecard-learning-summary .sls-title { font-weight: 700; color: #2d6a4f; margin-bottom: 4px; }
    .scorecard-learning-summary.exec-only .sls-title { color: #6c757d; }
    .memory-context-impact-panel {
      margin-top: 10px;
      padding: 10px 12px;
      border: 1px solid #c5d4e0;
      border-radius: 8px;
      background: #f8fbfd;
    }
    .memory-context-impact-panel .sls-title { font-weight: 700; color: #1b4965; margin-bottom: 6px; }
    .memory-context-impact-panel .mci-grid { display: grid; grid-template-columns: 12rem 1fr; gap: 4px 12px; font-size: 0.82rem; }
    .memory-context-impact-panel .mci-k { color: #5c6b7a; }
    .memory-context-impact-panel .mci-yes { color: #1b7f4b; font-weight: 700; }
    .memory-context-impact-panel .mci-no { color: #6c757d; font-weight: 700; }
    .memory-context-impact-panel .mci-barney { margin-top: 8px; font-size: 0.78rem; color: #4a5568; line-height: 1.4; }
    .scorecard-table-wrap-wide { overflow-x: auto; max-width: 100%; }
    .scorecard-table.scorecard-table-learning th,
    .scorecard-table.scorecard-table-learning td {
      font-size: 0.62rem;
      padding: 4px 4px;
      white-space: nowrap;
    }
    .chip-learn-yes { color: #1f6a45; font-weight: 700; }
    .chip-learn-no { color: #6c757d; font-weight: 600; }
    .drill-pre {
      max-height: 280px;
      overflow: auto;
      font-size: 0.72rem;
      background: #fff;
      border: 1px solid #d5dce3;
      border-radius: 8px;
      padding: 8px;
    }
    .path-hint { font-size: 0.72rem; color: var(--pg-muted); margin: 8px 0 0 0; word-break: break-all; }
    .scorecard-table { width: 100%; border-collapse: collapse; font-size: 0.72rem; }
    .scorecard-table th, .scorecard-table td {
      border: 1px solid #d5dce3;
      padding: 5px 6px;
      text-align: left;
    }
    .scorecard-table th { background: #eef1f4; color: #5a6570; white-space: nowrap; }
    .st-ok { color: #1f8a54; font-weight: 600; }
    .st-err { color: #c65a16; font-weight: 600; }
    .st-running { color: #175cd3; font-weight: 700; }
    .run-feedback-toast {
      margin-top: 10px;
      padding: 10px 14px;
      border-radius: 10px;
      border: 1px solid #2a8fd9;
      background: #e8f4fc;
      font-size: 0.88rem;
      color: #183343;
      font-weight: 600;
      line-height: 1.45;
    }
    .run-feedback-toast[hidden] { display: none !important; }
    .scorecard-click-hint {
      margin: 6px 0 0;
      font-size: 0.78rem;
      color: #175cd3;
      line-height: 1.4;
    }
    .scorecard-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      align-items: center;
      margin: 0 0 10px 0;
    }
    .scorecard-toolbar a {
      font-size: 0.78rem;
      padding: 8px 12px;
      border-radius: 8px;
      border: 1px solid var(--pg-line);
      background: #fff;
      color: var(--pg-accent);
      text-decoration: none;
      font-weight: 600;
    }
    .scorecard-toolbar a:hover { background: #f4f8ff; }
    .scorecard-toolbar-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin: 8px 0 4px;
    }
    .btn-scorecard-clear {
      font-size: 0.78rem;
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid var(--pg-line);
      background: #fff;
      color: #2d4a6f;
      cursor: pointer;
      font-weight: 600;
    }
    .btn-scorecard-clear:hover { background: #f0f6ff; }
    .btn-learning-reset-danger {
      font-size: 0.78rem;
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid #c43b3b;
      background: #fff5f5;
      color: #a32b2b;
      cursor: pointer;
      font-weight: 600;
    }
    .btn-learning-reset-danger:hover { background: #ffe8e8; }
    tr.scorecard-row { cursor: pointer; }
    tr.scorecard-row:hover { background: #f0f4f8; }
    tr.scorecard-row.selected { background: #e8f0fe; }
    tr.scorecard-row.scorecard-row-inflight { background: #f5f9ff; }
    tr.scorecard-row.scorecard-row-inflight:hover { background: #eaf2fc; }
    .batch-drill-panel {
      margin-top: 12px;
      padding: 12px;
      border-radius: 12px;
      border: 1px solid var(--pg-line);
      background: #faf8f5;
      font-size: 0.78rem;
      display: none;
    }
    .batch-drill-panel.visible { display: block; }
    .batch-drill-panel h3 { margin: 0 0 8px 0; font-size: 0.95rem; color: var(--pg-ink); }
    .batch-drill-meta { margin: 0 0 10px 0; line-height: 1.5; word-break: break-all; }
    .drill-scenario-table { width: 100%; border-collapse: collapse; font-size: 0.72rem; margin-top: 8px; }
    .drill-scenario-table th, .drill-scenario-table td {
      border: 1px solid #d5dce3;
      padding: 5px 6px;
      text-align: left;
      vertical-align: top;
    }
    .drill-scenario-table th { background: #eef1f4; color: #5a6570; }
    .mem-pill {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 0.68rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .mem-yes { background: #e3f4ea; color: #1f6a44; }
    .mem-no { background: #f0e8e8; color: #8a3a3a; }
    .gh-on { background: #e8f0fe; color: #175cd3; }
    .gh-off { background: #f4f1ea; color: #6a6570; }
    .pg-module-dialog {
      border: none;
      border-radius: 16px;
      padding: 0;
      max-width: min(540px, 94vw);
      background: #fffefb;
      color: #24303d;
      box-shadow: 0 16px 48px rgba(0, 0, 0, 0.35);
    }
    .pg-module-dialog::backdrop { background: rgba(10, 22, 30, 0.55); }
    .pg-module-dialog-inner { padding: 20px 44px 18px 22px; position: relative; }
    .pg-module-dialog-h2 { margin: 0 0 8px; font-size: 1.15rem; color: #183343; }
    .pg-module-role { margin: 0 0 12px; font-size: 0.78rem; color: #5a6570; font-weight: 600; }
    .pg-module-body { margin: 0; white-space: pre-wrap; font-family: var(--pg-mono); font-size: 0.78rem; line-height: 1.5; color: #3a4450; max-height: min(52vh, 420px); overflow: auto; }
    .pg-module-dialog-close { position: absolute; top: 8px; right: 10px; border: 0; background: transparent; font-size: 1.5rem; line-height: 1; cursor: pointer; color: #6a7580; padding: 4px 8px; border-radius: 8px; }
    .pg-module-dialog-close:hover { background: #f0f4f8; color: #183343; }
    .pg-forensic-dialog,
    dialog.pg-forensic-dialog {
      max-width: min(640px, 96vw);
      border: 1px solid var(--pg-line);
      border-radius: var(--pg-radius-xl);
      padding: 0;
      box-shadow: var(--pg-shadow);
    }
    .pg-forensic-dialog::backdrop { background: rgba(10, 22, 30, 0.55); }
    .pg-scorecard-legend-fold {
      margin-bottom: 8px;
      border: 1px dashed var(--pg-line);
      border-radius: 8px;
      padding: 4px 8px;
      background: rgba(0, 0, 0, 0.03);
    }
    .pg-scorecard-legend-summary { cursor: pointer; font-size: 0.78rem; font-weight: 700; color: var(--pg-muted); }
    .pg-scorecard-secondary-details { margin-top: 10px; border-top: 1px solid var(--pg-line); padding-top: 6px; }
    .pg-scorecard-secondary-details > summary { cursor: pointer; font-weight: 700; font-size: 0.82rem; color: var(--pg-accent); }
    #moduleBoardList .pg-status-item { cursor: pointer; }
    #moduleBoardList .pg-status-item:hover { filter: brightness(1.03); }
    #moduleBoardList .pg-status-item:focus { outline: 2px solid #2a8fd9; outline-offset: 2px; }
    .pg-upload-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin-top: 10px;
    }
    .btn-upload {
      padding: 10px 16px;
      border-radius: 10px;
      border: 1px solid var(--pg-line);
      background: #fff;
      color: #175cd3;
      font-weight: 600;
      font-size: 0.85rem;
      cursor: pointer;
    }
    .btn-upload:hover { background: #f4f8ff; }
    .btn-upload:disabled { opacity: 0.55; cursor: not-allowed; }
    .pg-upload-hint { font-size: 0.72rem; color: var(--pg-muted); margin: 0; flex: 1 1 200px; }
    .pg-spinner {
      width: 22px;
      height: 22px;
      border: 3px solid #d5dce3;
      border-top-color: #175cd3;
      border-radius: 50%;
      animation: pg-spin 0.7s linear infinite;
      display: none;
      vertical-align: middle;
    }
    .pg-spinner.visible { display: inline-block; }
    @keyframes pg-spin { to { transform: rotate(360deg); } }
    .pg-upload-dialog {
      border: none;
      border-radius: 16px;
      padding: 0;
      max-width: min(480px, 94vw);
      background: #fffefb;
      color: #24303d;
      box-shadow: 0 16px 48px rgba(0, 0, 0, 0.35);
    }
    .pg-upload-dialog::backdrop { background: rgba(10, 22, 30, 0.55); }
    .pg-upload-dialog-inner { padding: 20px 22px 18px; position: relative; }
    .pg-upload-dialog h2 { margin: 0 0 12px; font-size: 1.05rem; color: #183343; }
    .pg-upload-dialog label { display: block; font-size: 0.8rem; font-weight: 600; margin-bottom: 6px; color: #485360; }
    .pg-upload-dialog input[type="text"] {
      width: 100%;
      box-sizing: border-box;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--pg-line);
      font-size: 0.9rem;
      margin-bottom: 8px;
    }
    .pg-upload-steps { font-size: 0.78rem; color: #5a6570; margin: 0 0 14px; line-height: 1.5; }
    .pg-upload-result {
      margin-top: 12px;
      padding: 10px 12px;
      border-radius: 10px;
      font-size: 0.82rem;
      line-height: 1.45;
      display: none;
    }
    .pg-upload-result.visible { display: block; }
    .pg-upload-result.ok { background: #e8f6ee; border: 1px solid #9dceb7; color: #1a5c38; }
    .pg-upload-result.err { background: #fdecec; border: 1px solid #e0a0a0; color: #8a2222; }
    .pg-upload-actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 14px; }
    .btn-rename-preset {
      font-size: 0.78rem;
      padding: 8px 12px;
      border-radius: 8px;
      border: 1px dashed var(--pg-line);
      background: transparent;
      color: #175cd3;
      cursor: pointer;
      font-weight: 600;
    }
    .btn-rename-preset:disabled { opacity: 0.45; cursor: not-allowed; }
    .policy-outcome-panel .hint { font-size: 0.78rem; color: var(--pg-muted); margin: 0 0 10px 0; line-height: 1.4; }
    .pg-evidence-panel .policy-outcome-panel {
      margin: 0;
      padding: 0;
      border: 0;
      background: transparent;
      box-shadow: none;
      max-height: none;
      overflow: visible;
    }
    .policy-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.76rem;
    }
    .policy-table th, .policy-table td {
      border: 1px solid #d5dce3;
      padding: 6px 7px;
      text-align: left;
      vertical-align: top;
    }
    .policy-table th { background: #eef1f4; color: #5a6570; font-weight: 600; white-space: nowrap; }
    .policy-table td { color: var(--pg-ink); }
    .tag-win { color: #1f8a54; font-weight: 700; }
    .tag-loss { color: #c43b3b; font-weight: 700; }
    .tag-err { color: #c65a16; font-weight: 700; }
    .signals-cell { font-family: var(--pg-mono); font-size: 0.72rem; max-width: 320px; word-break: break-word; }
    input[type=checkbox] { width: auto; }
    input[type=range] { width: 100%; accent-color: var(--pg-accent); }
    .batch-concurrency-banner {
      display: none;
      margin: 10px 0 8px;
      padding: 10px 12px;
      border-radius: 10px;
      background: #f4f1ea;
      border: 1px solid var(--pg-line);
      font-size: 0.85rem;
      line-height: 1.45;
      color: var(--pg-ink);
    }
    .batch-concurrency-banner.visible { display: block; }
    .batch-concurrency-banner strong { color: var(--pg-accent); font-weight: 600; }
    .batch-concurrency-banner .warn { color: #b7772c; }
    .progress-wrap { display: none; margin: 12px 0 8px; }
    .progress-wrap.active { display: block; }
    .progress-track {
      height: 10px;
      border-radius: 5px;
      background: #d5dce3;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      width: 0%;
      border-radius: 5px;
      background: linear-gradient(90deg, #175cd3, #2a8fd9);
      transition: width 0.35s ease;
    }
    #progressSub { margin-top: 6px; font-size: 0.8rem; color: var(--pg-muted); }
    .live-telemetry-wrap {
      margin: 0;
      padding: 12px 14px;
      border-radius: var(--pg-radius-lg);
      border: 1px solid var(--pg-line);
      background: #0f1419;
      color: #e6edf3;
      box-shadow: var(--pg-shadow);
      flex: 1 1 auto;
      min-height: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    body.pg-run-active .live-telemetry-wrap {
      border-color: rgba(42, 143, 217, 0.55);
      box-shadow: 0 0 0 2px rgba(42, 143, 217, 0.28), var(--pg-shadow);
    }
    /* Only show “While running” during an active batch — avoids duplicate/confusing Terminal chrome when idle */
    body:not(.pg-run-active) .telemetry-run-only { display: none !important; }
    body.pg-run-active .pg-runtime-stack .pg-panel-score {
      opacity: 0.94;
    }
    .live-telemetry-title {
      margin: 0 0 8px;
      font-size: 0.72rem;
      font-weight: 700;
      color: #8b98a5;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .memory-status-card {
      font-size: 0.78rem;
      line-height: 1.45;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 10px;
      padding: 10px 12px;
      flex: 0 0 auto;
    }
    .memory-status-narrative {
      margin: 0 0 8px;
      font-size: 0.8rem;
      font-style: italic;
      color: #c5d0db;
      line-height: 1.4;
    }
    .memory-status-card dl {
      margin: 0;
      display: grid;
      grid-template-columns: minmax(0, 11rem) 1fr;
      gap: 4px 10px;
    }
    .memory-status-card dt { color: #8b98a5; font-weight: 700; }
    .memory-status-card dd { margin: 0; color: #e6edf3; font-weight: 600; }
    .telemetry-rolling-log {
      flex: 0 0 auto;
      max-height: 7.5rem;
      overflow-y: auto;
      font-family: var(--pg-mono);
      font-size: 0.7rem;
      line-height: 1.4;
      color: #9aa7b4;
      border-top: 1px solid rgba(255, 255, 255, 0.1);
      padding-top: 6px;
    }
    .telemetry-rolling-log .telemetry-tick {
      margin: 0 0 4px;
      padding-bottom: 3px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      white-space: pre-wrap;
      word-break: break-word;
    }
    .live-telemetry-panel {
      margin: 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.74rem;
      line-height: 1.45;
      white-space: pre-wrap;
      flex: 1 1 auto;
      min-height: 6rem;
      max-height: 12rem;
      overflow: auto;
    }
    .pg-runtime-stack .pg-panel-score {
      flex: 1 1 auto;
      min-height: 0;
    }
    .pg-pattern-mode-explanation {
      margin-top: 14px;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid rgba(47, 127, 121, 0.28);
      background: linear-gradient(180deg, rgba(47, 127, 121, 0.08) 0%, rgba(255, 252, 246, 0.95) 100%);
      font-size: 0.82rem;
      line-height: 1.5;
      color: #2a3540;
    }
    .pg-pattern-mode-explanation .pg-pattern-mode-h {
      margin: 0 0 10px;
      font-size: 0.88rem;
      font-weight: 800;
      color: #1d4d48;
      letter-spacing: -0.01em;
    }
    .pg-pattern-mode-dl {
      margin: 0;
      display: grid;
      gap: 10px 0;
    }
    .pg-pattern-mode-dl dt {
      margin: 0;
      font-size: 0.68rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--pg-teal);
    }
    .pg-pattern-mode-dl dd {
      margin: 2px 0 0;
      padding: 0;
      font-size: 0.82rem;
      color: #2f3842;
      white-space: pre-line;
    }
    #statusLine { min-height: 1.3em; color: var(--pg-ink); font-size: 0.9rem; margin-top: 8px; }
    .err { color: #c43b3b; }
    .pg-pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
    .pg-pill {
      padding: 8px 10px;
      border-radius: 999px;
      border: 1px solid var(--pg-line);
      background: #fff;
      font-size: 12px;
      font-weight: 700;
      color: #485360;
    }
    .pg-status-list { display: grid; gap: 10px; }
    .pg-status-item {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 10px 12px;
      align-items: start;
      padding: 11px 12px;
      border-radius: 14px;
      border: 1px solid var(--pg-line);
      background: linear-gradient(180deg, #fffdf9 0%, #f7f2e8 100%);
    }
    .pg-status-item .status-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      margin-top: 4px;
      flex-shrink: 0;
    }
    .pg-status-item .status-dot.ok { background: #2fa46a; box-shadow: 0 0 0 3px rgba(47, 164, 106, 0.14); }
    .pg-status-item .status-dot.warn { background: #b7772c; box-shadow: 0 0 0 3px rgba(183, 119, 44, 0.14); }
    .pg-status-item .status-dot.bad { background: #d15959; box-shadow: 0 0 0 3px rgba(209, 89, 89, 0.14); }
    .pg-status-name { font-size: 13px; font-weight: 800; color: #24303d; margin-bottom: 3px; }
    .pg-status-meta { font-size: 12px; line-height: 1.45; color: var(--pg-muted); }
    .pg-tab-strip { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .pg-tab {
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--pg-line);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.02em;
      background: #fffefb;
      color: #4d5967;
      margin-top: 0;
      cursor: pointer;
    }
    .pg-tab.active {
      background: #183343;
      border-color: #183343;
      color: #f7f1e6;
    }
    .pg-evidence-panel { min-height: 120px; }
    .pg-pre-json {
      background: #f8f6f0;
      border: 1px solid var(--pg-line);
      border-radius: 12px;
      padding: 10px;
      overflow: auto;
      font-size: 0.7rem;
      font-family: var(--pg-mono);
      max-height: min(40vh, 360px);
      margin: 0;
    }
    #searchSpaceStrip strong { color: #f7f1e6; }
    #searchSpaceStrip code { font-size: 0.85em; color: rgba(247, 241, 230, 0.95); }
    @media (max-width: 1220px) {
      .pg-banner-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      /* Narrow: controls, then telemetry, then scorecard (single column). */
      .pg-row-main { grid-template-columns: 1fr; overflow-x: visible; min-height: 0; }
      .pg-operator-col { border-right: none; padding-right: 0; }
    }
    @media (max-width: 640px) {
      .pg-banner-strip { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      .pg-shell { padding: 14px; }
      .pg-banner-strip { grid-template-columns: 1fr; }
    }

  </style>
</head>
<body class="pg-theme">
  <div class="pg-shell">
    <header class="pg-header">
      <picture>
        <source srcset="/assets/pattern-banner.webp" type="image/webp"/>
        <img class="pg-header-banner" src="/assets/pattern-banner.png" width="1536" height="421" alt="" decoding="async" fetchpriority="high"/>
      </picture>
      <div class="pg-header-content">
      <div class="pg-title-wrap">
        <div class="pg-header-title-row">
          <h1 class="pg-title">Pattern Machine learning
            <span class="ui-version" title="Bump PATTERN_GAME_WEB_UI_VERSION in web_app.py">v__PATTERN_GAME_WEB_UI_VERSION__</span></h1>
          <button type="button" class="pg-howto-btn" id="pgHowToOpenBtn" aria-haspopup="dialog" aria-controls="pgHowToDialog">How to use</button>
        </div>
        <p class="pg-lead-short">Choose pattern, evaluation window, trade window (candle rollup), then <strong>Run exam</strong>. Status cards above update live.</p>
      </div>
      <div class="pg-banner-strip">
        <div class="pg-banner-stat">
          <div class="pg-k">Financial data</div>
          <div class="pg-v"><span class="status-dot" id="healthDot"></span> <span id="bannerFinancialV">—</span></div>
          <div class="pg-s" id="healthText">Checking database…</div>
        </div>
        <div class="pg-banner-stat pg-banner-stat--pnl" id="bannerPnlCard" title="Referee batch ΔP&amp;L vs paper baseline. Slider adjusts display scale only (server uses spec baseline for Referee math).">
          <div class="pg-k">P&amp;L</div>
          <div class="pg-v" id="bannerPnlV"><span class="banner-pnl-amt neutral" id="bannerPnlAmt">—</span></div>
          <div class="pg-s" id="bannerPnlS">vs $1k</div>
          <div class="pg-banner-pnl-micro" aria-hidden="true" title="Baseline → ending (scale follows slider)">
            <div class="pg-banner-pnl-micro-fill up" id="bannerPnlMicroFill" style="left:50%;width:0%;"></div>
          </div>
          <div class="pg-banner-pnl-baseline-row" title="Display-only paper baseline for the banner strip. Does not change server Referee config.">
            <label for="paperBaselineSlider">Paper baseline</label>
            <input type="range" id="paperBaselineSlider" min="500" max="10000" step="100" value="1000" />
            <span id="paperBaselineLabel">$1,000</span>
          </div>
        </div>
        <div class="pg-banner-stat pg-banner-stat--reasoningmodel" id="reasoningModelBannerTile" title="">
          <div class="pg-k">Reasoning Model</div>
          <div class="pg-rm-head" id="reasoningModelHeadV">—</div>
          <div class="pg-rm-core" id="reasoningModelCoreS">—</div>
          <div class="pg-rm-cost" id="reasoningModelCostS">—</div>
          <a class="pg-rm-billing" id="rmAddFundsLink" href="https://platform.openai.com/settings/organization/billing" target="_blank" rel="noopener noreferrer" title="Open OpenAI billing in a new tab (no key in URL)">Add funds</a>
          <label class="pg-rm-gw" title="When enabled, the router may escalate to OpenAI if configuration and your key allow it. It does not force a call on every run.">
            <input type="checkbox" id="rmExtGatewayChk" checked />
            <span>Allow External AI (OpenAI)</span>
          </label>
        </div>
        <div class="pg-banner-stat">
          <div class="pg-k">Search space</div>
          <div class="pg-s pg-s-tall" id="searchSpaceStrip" aria-live="polite"><strong>Search space</strong> — loading…</div>
        </div>
        <div class="pg-banner-stat" title="Current batch / status line">
          <div class="pg-k">Run</div>
          <div class="pg-v" id="bannerRunV">Idle</div>
          <div class="pg-s" id="bannerRunS">— run an exam —</div>
        </div>
      </div>
      </div>
    </header>

    <dialog id="pgHowToDialog" class="pg-module-dialog pg-howto-dialog" aria-labelledby="pgHowToTitle">
      <div class="pg-module-dialog-inner">
        <button type="button" class="pg-module-dialog-close" id="pgHowToClose" aria-label="Close">×</button>
        <h2 id="pgHowToTitle" class="pg-module-dialog-h2">How to use this UI</h2>
        <div class="pg-howto-body">
          <p>Pick <strong>Pattern</strong> and <strong>Evaluation window</strong> under <strong>Controls</strong>, then <strong>Run exam</strong>. While an exam runs, open <strong>Quick view → Terminal</strong> (expanded) for live telemetry. When it finishes, <strong>Student → learning → outcome</strong> is the primary inspection surface.</p>
          <p><strong>Scorecard</strong> and raw evidence stay under <strong>Quick view → Results</strong> until you need history or JSON.</p>
          <p><strong>Custom</strong> scenarios: set Pattern to <strong>Custom</strong> and paste JSON under <strong>Controls → Advanced → Custom scenario</strong> (Pattern Info).</p>
          <p>Expand panel summaries as needed. Operator contract and known gaps: DEF-001 in <code>docs/architect/pattern_game_operator_deficiencies_work_record.md</code>.</p>
        </div>
      </div>
    </dialog>

    <dialog id="moduleDetailDialog" class="pg-module-dialog" aria-labelledby="moduleModalTitle">
      <div class="pg-module-dialog-inner">
        <button type="button" class="pg-module-dialog-close" id="moduleModalClose" aria-label="Close">×</button>
        <h2 id="moduleModalTitle" class="pg-module-dialog-h2"></h2>
        <p id="moduleModalRole" class="pg-module-role"></p>
        <pre id="moduleModalBody" class="pg-module-body"></pre>
      </div>
    </dialog>

    <dialog id="uploadPresetDialog" class="pg-upload-dialog" aria-labelledby="uploadPresetDialogTitle">
      <div class="pg-upload-dialog-inner">
        <h2 id="uploadPresetDialogTitle">Upload scenario preset</h2>
        <p class="pg-upload-steps">1. Pick a <strong>.json</strong> file · 2. Name your preset · 3. Validate &amp; save (pass/fail shown here)</p>
        <p id="uploadChosenFileLabel" style="font-size:0.8rem;color:#5a6570;margin:0 0 10px"></p>
        <label for="uploadPresetNameInput">Preset name</label>
        <input type="text" id="uploadPresetNameInput" placeholder="e.g. SOL 12m grid" autocomplete="off" />
        <div class="pg-upload-result" id="uploadPresetResult" role="status" aria-live="polite"></div>
        <div class="pg-upload-actions">
          <span class="pg-spinner" id="uploadDialogSpinner" aria-hidden="true"></span>
          <button type="button" class="btn-chef pg-op-btn" id="uploadPresetSubmitBtn" data-label-idle="Validate &amp; save">Validate &amp; save</button>
          <button type="button" class="btn-secondary" id="uploadPresetDoneBtn" style="display:none">Back to controls</button>
          <button type="button" class="btn-secondary" id="uploadPresetCancelBtn">Cancel</button>
        </div>
      </div>
    </dialog>

    <dialog id="renamePresetDialog" class="pg-upload-dialog" aria-labelledby="renamePresetDialogTitle">
      <div class="pg-upload-dialog-inner">
        <h2 id="renamePresetDialogTitle">Rename uploaded preset</h2>
        <p style="font-size:0.78rem;color:#5a6570;margin:0 0 10px">Only <code>user_*.json</code> uploads can be renamed (new slug from the name below).</p>
        <label for="renamePresetInput">New preset name</label>
        <input type="text" id="renamePresetInput" autocomplete="off" />
        <div class="pg-upload-result" id="renamePresetResult" role="status"></div>
        <div class="pg-upload-actions">
          <span class="pg-spinner" id="renameDialogSpinner"></span>
          <button type="button" class="btn-chef pg-op-btn" id="renamePresetSubmitBtn" data-label-idle="Rename">Rename</button>
          <button type="button" class="btn-secondary" id="renamePresetCancelBtn">Cancel</button>
        </div>
      </div>
    </dialog>

    <section class="pg-row pg-row-main">
      <div class="pg-operator-col">
      <details class="pg-panel-fold pg-panel-controls" open>
        <summary>
          <div class="pg-panel-header" style="margin:0;flex:1">
            <div>
              <h2 class="pg-panel-h">Controls</h2>
              <p class="pg-panel-sub">Pattern · windows · Run</p>
            </div>
          </div>
        </summary>
        <div class="pg-panel-fold-body pg-panel-controls-body">
        <div class="pg-controls-minimal">
          <div class="pg-controls-min-grid">
            <label for="operatorRecipePick">Pattern</label>
            <select id="operatorRecipePick" aria-describedby="presetHelp patternModeExplanation">
              <option value="pattern_learning">Pattern Machine Learning (PML)</option>
              <option value="reference_comparison">Reference Comparison Run</option>
              <option value="custom">Custom (scenario JSON)</option>
            </select>
            <label for="evaluationWindowPick">Evaluation window</label>
            <select id="evaluationWindowPick" aria-describedby="presetHelp">
              <option value="12">12 months</option>
              <option value="18">18 months</option>
              <option value="24">24 months</option>
              <option value="custom">Custom…</option>
            </select>
            <label for="tradeWindowPick">Trade window</label>
            <select id="tradeWindowPick" aria-describedby="presetHelp" title="Candle rollup: each replay bar is this wide (from 5m base data)">
              <option value="5m" selected>5m</option>
              <option value="15m">15m</option>
              <option value="1h">1 hour</option>
              <option value="4h">4 hours</option>
            </select>
            <div id="customMonthsWrap" class="pg-controls-span-2" style="display:none">
              <div class="pg-controls-min-grid" style="grid-template-columns:minmax(7.5rem,38%) 1fr">
                <label for="evaluationWindowCustomMonths">Months</label>
                <input type="number" id="evaluationWindowCustomMonths" min="1" max="600" value="36"/>
              </div>
            </div>
            <div class="pg-controls-span-2" style="margin-top:8px;padding-top:10px;border-top:1px solid var(--pg-line)">
              <div class="pg-controls-min-grid" style="grid-template-columns:minmax(9.5rem,36%) 1fr;align-items:start">
                <label for="examStudentReasoningModePick">Run mode</label>
                <select id="examStudentReasoningModePick" aria-describedby="examContractHelp">
                  <option value="baseline_no_memory_no_llm">Baseline</option>
                  <option value="memory_context_llm_student" selected>Student</option>
                </select>
                <div id="examLlmModelWrap" class="pg-controls-span-2" style="margin-top:8px;display:none">
                  <div class="pg-controls-min-grid" style="grid-template-columns:minmax(10rem,38%) 1fr;align-items:center">
                    <label for="examLlmModelPick">Ollama model (metadata)</label>
                    <select id="examLlmModelPick" aria-label="Ollama model for Student path">
                      <option value="qwen2.5:7b">qwen2.5:7b</option>
                      <option value="deepseek-r1:14b">deepseek-r1:14b</option>
                    </select>
                  </div>
                  <p class="caps" style="margin:6px 0 0;font-size:0.72rem;color:#5a6570">The live Student stack resolves the approved model on the server (<code>exam_run_contract_v1</code>); this pick is stored as contract metadata for audits.</p>
                </div>
                <div class="pg-controls-span-2" style="margin-top:8px">
                  <label style="display:flex;align-items:flex-start;gap:8px;font-size:0.82rem;line-height:1.38;cursor:pointer;margin:0">
                    <input type="checkbox" id="examSkipColdBaselineIfAnchor" style="margin-top:3px;flex-shrink:0"/>
                    <span>Record skip-cold-baseline when a prior scorecard row matches this run’s fingerprint (<strong>metadata only</strong> — Referee still runs the full parallel replay).</span>
                  </label>
                </div>
                <label for="examPromptVersion" style="margin-top:8px">Prompt version</label>
                <input type="text" id="examPromptVersion" maxlength="256" autocomplete="off" placeholder="pattern_game_web_ui_v__PATTERN_GAME_WEB_UI_VERSION__" style="width:100%;max-width:100%"/>
              </div>
              <p id="examContractHelp" class="caps" style="margin:8px 0 0;font-size:0.72rem;line-height:1.42;color:#5a6570"><strong>Baseline</strong> = control run: deterministic Referee replay only (no Student seam, no cross-run memory, no context-signature memory, no LLM, no unified-agent router on this run). <strong>Student</strong> = full unified agent path: memory, entry and lifecycle reasoning, 026C promoted-learning retrieval, 026AI router evaluation, governed local model, and external APIs only where internal escalation rules allow. <strong>Workflow:</strong> run Baseline, then run Student, then compare; repeat Student as needed — only <em>promoted</em> prior 026C records can influence a later Student run. Advanced → internal legacy profile override for tests only.</p>
            </div>
          </div>
          <div class="pg-controls-run-row">
            <button type="button" id="runBtn" class="pg-op-btn pg-op-btn--run" data-label-idle="Run exam">Run exam</button>
            <button type="button" id="parallelCancelBtn" class="btn-secondary" style="display:none" title="Stop scheduling new scenarios; workers already running may still finish">Cancel batch</button>
          </div>
        </div>

        <details class="pg-controls-advanced" open>
          <summary>Advanced · policy · workers · progress · JSON</summary>
          <div class="pg-controls-core">
          <p id="customScenarioRouteHint" class="pg-custom-route-hint" hidden>
            <strong>Custom:</strong> JSON under <strong>Pattern Info → Advanced → Custom scenario</strong>.
          </p>
          <div id="policyMultiWrap" style="display:none;margin-top:10px">
            <label for="policyPick">Policy / manifest</label>
            <select id="policyPick" aria-label="Policy manifest"></select>
          </div>
          <p class="pg-policy-line" id="policyReadonly" style="display:none" role="status">Policy: —</p>

          <div class="pg-block pg-strategy-upload" style="margin-top:10px;border-top:1px solid var(--pg-line);padding-top:12px">
            <div class="pg-block-title">Upload Strategy</div>
            <p class="caps" style="margin:0 0 8px;font-size:0.8rem;line-height:1.35">
              Upload a <strong>strategy idea</strong> for testing (not the Pattern menu). Required format: <code>strategy_idea_v1</code> UTF-8 text.
              <a href="/strategy-idea-format" target="_blank" rel="noopener">Format specification</a>
              · Files saved under <code>runtime/operator_strategy_uploads/</code> (sources + generated manifests; never overwrites shipped baseline JSON).
            </p>
            <input type="file" id="strategyIdeaFileInput" accept=".txt,text/plain" style="display:none" aria-hidden="true" />
            <div class="pg-upload-row" style="margin-bottom:8px">
              <button type="button" class="btn-chef pg-op-btn" id="strategyUploadPickBtn" data-label-idle="Choose strategy file…">Choose strategy file…</button>
              <button type="button" class="btn-secondary pg-op-btn" id="strategyUploadClearBtn">Clear loaded strategy</button>
            </div>
            <div id="strategyUploadStageLine" class="caps" style="font-size:0.78rem;color:#3d4a52;margin:0 0 6px" aria-live="polite"></div>
            <ul id="strategyUploadChecklist" class="strategy-upload-checklist" style="margin:0;padding-left:1.15rem;font-size:0.82rem;line-height:1.45"></ul>
            <label style="margin-top:10px;font-size:0.85rem;display:block">
              <input type="checkbox" id="useOperatorUploadedStrategy" checked/>
              Use uploaded strategy for the next run (applies manifest to every scenario row when a load is active)
            </label>
          </div>

          <div class="pg-block" style="margin-top:0">
            <div class="pg-block-title">Workers &amp; logging</div>
            <label for="workersRange">Workers <span id="workersVal" style="font-weight:700">1</span></label>
            <input type="range" id="workersRange" min="1" max="64" value="1" step="1" />
            <p id="workerCpuHint" style="margin:4px 0 0;font-size:0.8rem"></p>
            <div id="workerEffectiveLine" aria-live="polite" style="font-size:0.8rem"></div>
            <label style="margin-top:8px;font-size:0.85rem;display:block"><input type="checkbox" id="doLog" checked/> Append to experience JSONL</label>
            <div id="examStudentExecutionModeWrap" class="pg-controls-span-2" style="margin-top:12px;padding-top:10px;border-top:1px solid var(--pg-line)">
              <div class="pg-block-title" style="margin:0 0 6px">Student execution (Advanced)</div>
              <div class="pg-controls-min-grid" style="grid-template-columns:minmax(11.5rem,40%) 1fr;align-items:start">
                <label for="examStudentExecutionModePick">Student execution mode (GT-024)</label>
                <select id="examStudentExecutionModePick" aria-describedby="examContractHelpAdvanced">
                  <option value="baseline_gated" selected>Baseline-gated (024C)</option>
                  <option value="student_full_control">Full control (024D)</option>
                </select>
              </div>
              <p id="examContractHelpAdvanced" class="caps" style="margin:6px 0 0;font-size:0.72rem;color:#5a6570">Applies to <strong>Student</strong> and internal stub profile runs — not to Baseline control.</p>
            </div>
            <details class="inline-details" style="margin-top:10px">
              <summary>Internal — legacy brain profile (debug)</summary>
              <p class="caps" style="margin:6px 0 8px">Leave blank for operator runs. Overrides the Run mode control for API/tests only (e.g. <code>memory_context_student</code> stub path).</p>
              <label for="pgExamLegacyBrainProfileOverride">Override profile</label>
              <select id="pgExamLegacyBrainProfileOverride" style="margin-top:4px;max-width:100%">
                <option value="" selected>— use Run mode (Baseline / Student) —</option>
                <option value="memory_context_student">memory_context_student (stub, no Ollama)</option>
                <option value="baseline_no_memory_no_llm">baseline_no_memory_no_llm (force Baseline contract)</option>
                <option value="memory_context_llm_student">memory_context_llm_student (force Student contract)</option>
              </select>
            </details>
          </div>

          <div class="run-actions">
            <div class="status-stack">
              <div id="statusLine" aria-live="polite"></div>
              <div id="batchConcurrencyBanner" class="batch-concurrency-banner" aria-live="polite"></div>
              <div id="progressWrap" class="progress-wrap" role="progressbar" aria-label="Batch replay progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
                <div class="progress-track" id="progressTrack"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
                <p class="caps" id="progressSub"></p>
              </div>
              <div id="runFeedbackToast" class="run-feedback-toast" role="status" aria-live="polite" hidden></div>
            </div>
          </div>

        <details class="pg-pattern-info-fold" id="patternInfoFold">
          <summary>Pattern Info (optional)</summary>
          <div class="pg-pattern-info-body">
            <div class="def001-science" role="region" aria-label="DEF-001">
              <span class="def001-tag">DEF-001 · SCIENCE / EVALUATION ONLY</span>
              <p style="margin:0">Same inputs + same code → reproducible Referee stats. <strong>No</strong> automatic policy training in the replay loop. “Memory” in logs is evidence or promoted bundle — not silent learning. Full contract: <code>docs/architect/pattern_game_operator_deficiencies_work_record.md</code> (DEF-001).</p>
            </div>
            <details class="help-details pg-help">
              <summary>Setup, PYTHONPATH, promoted bundle</summary>
              <div class="help-details-body">
                <p>Run from repo root with <code>PYTHONPATH</code> including the repo. Example files load from <code>game_theory/examples/</code> (Advanced only).</p>
                <p>The <strong>Reasoning Model</strong> banner shows live stack health (local Ollama, 026AI router, external gateway, operator API preference). The optional <strong>promoted-parameter bundle</strong> (JSON in <code>game_theory/state/</code>) may still merge into replay when the file is present and auto-merge is on; to opt out, set the bundle auto-merge environment flag to <code>0</code> (default is on). <code>POST /api/promoted-bundle</code> writes ATR geometry; <code>POST /api/promoted-bundle/clear</code> with <code>{"confirm": true}</code> removes that file only. <code>POST /api/context-signature-memory/clear</code> truncates context-signature recall JSONL. Older absolute paths for the same bundle handlers remain wired for API compatibility.</p>
                <p><strong>Modules row</strong> — use <strong>GET /api/module-board</strong> for subsystem wiring; the header <strong>Reasoning Model</strong> tile reflects <code>GET /api/reasoning-model/status</code>.</p>
              </div>
            </details>
            <p class="caps" id="presetHelp">The server builds scenarios for curated patterns — no JSON required. <strong>Evaluation window</strong> is calendar months of tape from the end of the series. <strong>Trade window</strong> is candle rollup (5m / 15m / 1h / 4h): replay rolls up <code>market_bars_5m</code> into wider OHLCV bars before the Referee loop. Presets longer than your tape span are disabled automatically (see Data health).</p>
            <div id="patternModeExplanation" class="pg-pattern-mode-explanation" role="region" aria-label="What the selected pattern does">
              <div id="patternModeExplanationBody">Loading…</div>
            </div>
            <div class="pg-run-config" id="runConfigPanel" role="region" aria-label="Run configuration">
              <div class="pg-block-title" style="margin-top:0">Run configuration</div>
              <dl class="pg-run-config-dl" id="runConfigDl">
                <dt>Pattern</dt><dd id="runConfigPattern">—</dd>
                <dt>Policy</dt><dd id="runConfigPolicy">—</dd>
                <dt>Evaluation window</dt><dd id="runConfigWindow">—</dd>
                <dt>Trade window</dt><dd id="runConfigTradeWindow">—</dd>
                <dt>Goal</dt><dd id="runConfigGoalSummary">—</dd>
              </dl>
            </div>
            <div class="pg-goal-readonly" id="goalReadonlyPanel" aria-live="polite">
              <div class="pg-block-title" style="margin-top:0;margin-bottom:8px">Goal (read-only)</div>
              <p id="goalReadonlyTitle" class="pg-goal-line"></p>
              <p id="goalReadonlyMetrics" class="pg-goal-line"></p>
              <p id="goalReadonlyConstraints" class="pg-goal-line caps"></p>
              <p id="goalReadonlyNote" class="pg-goal-line caps" style="margin-bottom:0"></p>
            </div>
            <details class="help-details pg-help" style="margin-top:12px" id="advancedOperatorPanel">
              <summary>Advanced — examples, uploads &amp; custom JSON</summary>
              <div class="help-details-body">
                <div class="pg-mini-grid pg-mini-3" style="margin-top:8px">
                  <div><label for="examplesFilePick">Load example file</label><select id="examplesFilePick"><option value="">— pick file —</option></select></div>
                  <div><label>&nbsp;</label><button type="button" class="btn-secondary pg-op-btn" style="width:100%;margin-top:0" id="suggestHuntersBtn" title="Scorecard + retrospective" data-label-idle="Suggest hunters">Suggest hunters</button></div>
                  <div><label>&nbsp;</label><button type="button" class="btn-chef pg-op-btn" style="width:100%;margin-top:0" id="chefAtrSweepBtn" data-label-idle="ATR sweep">ATR sweep</button></div>
                </div>
                <span class="caps" id="hunterSuggestHint"></span>
                <div class="tool-row" style="margin-top:8px">
                  <div style="flex:1;min-width:200px">
                    <label for="chefManifestPath" style="margin:0;font-size:0.8rem">Chef manifest</label>
                    <input type="text" id="chefManifestPath" style="margin-top:4px" value="renaissance_v4/configs/manifests/baseline_v1_recipe.json" spellcheck="false"/>
                  </div>
                  <span class="caps" id="chefHint" style="align-self:flex-end"></span>
                </div>
                <input type="file" id="presetFileInput" accept=".json,application/json" style="display:none" aria-hidden="true" />
                <div class="pg-upload-row">
                  <button type="button" class="btn-upload pg-op-btn" id="presetUploadBtn" data-label-idle="Upload scenario JSON…">Upload scenario JSON…</button>
                  <button type="button" class="btn-rename-preset pg-op-btn" id="presetRenameBtn" disabled title="Only for uploaded presets (user_*.json)" data-label-idle="Rename preset…">Rename preset…</button>
                </div>
                <p class="pg-upload-hint">Uploads validate against the scenario contract and appear in the example list. For a normal run, use <strong>Pattern</strong> above — not this file list.</p>
                <details class="inline-details" style="margin-top:12px;border-left-color:#2d8a6a" id="advancedJsonDetails">
                  <summary>Custom scenario (JSON)</summary>
                  <p class="caps" id="structuredJsonHint" style="margin:6px 0 8px">This field is <strong>disabled</strong> for curated patterns — the server injects manifest, window, and goal.</p>
                  <details class="inline-details"><summary>Validation (hypothesis)</summary>
                    <p style="margin:0">Non-empty <code>agent_explanation.hypothesis</code> per scenario unless <code>PATTERN_GAME_REQUIRE_HYPOTHESIS=0</code>.</p>
                  </details>
                  <textarea id="scenarios" spellcheck="false" placeholder="Used only when Pattern = Custom. Array of scenario objects or {&quot;scenarios&quot;:[…]}."></textarea>
                </details>
              </div>
            </details>
          </div>
        </details>
        </div>
        </details>
        </div>
      </details>
      </div>

      <div class="pg-main-col">
      <div class="pg-runtime-stack">
      <div class="pg-focus-dock" id="pgFocusDock" data-pg-focus-mode="overview" aria-label="Quick view — Terminal, Results, Modules (click a tile to expand full width)">
        <div class="pg-focus-overview" id="pgFocusOverview">
          <p class="pg-focus-quick-h">Quick view</p>
          <button type="button" class="pg-focus-tile" id="pgFocusTileTerminal" data-pg-focus-tile="terminal" title="Expand Terminal">
            <p class="pg-focus-tile-k">Terminal</p>
            <div class="pg-focus-tile-body" id="focusTileTerminalBody"><strong id="focusTileTerminalStatus">Idle</strong><br/><span id="focusTileTerminalLine">No batch running.</span></div>
            <p class="pg-focus-tile-hint">Engine + DCR · click to expand</p>
          </button>
          <button type="button" class="pg-focus-tile" id="pgFocusTileResults" data-pg-focus-tile="results" title="Expand Results">
            <p class="pg-focus-tile-k">Results</p>
            <div class="pg-focus-tile-body" id="focusTileResultsBody">
              <span id="focusTileResultsPnl" title="P&amp;L: cumulative profit and loss (paper) for the last completed batch">P&amp;L —</span><br/>
              <span id="focusTileResultsTw" title="Trade win rate: winning trades divided by trades with a result">Trade win —</span> · <span id="focusTileResultsTr" title="Trades: count of trades in the batch rollup">Trades —</span>
            </div>
            <p class="pg-focus-tile-hint">Referee outcomes · JSON · session</p>
          </button>
          <button type="button" class="pg-focus-tile" id="pgFocusTileModules" data-pg-focus-tile="modules" title="Expand Modules">
            <p class="pg-focus-tile-k">Modules</p>
            <div class="pg-focus-tile-body" id="focusTileModulesBody"><strong id="focusTileModulesSt">—</strong><br/><span id="focusTileModulesLine">Loading…</span></div>
            <p class="pg-focus-tile-hint">Wiring health · click to expand</p>
          </button>
        </div>
        <div class="pg-focus-expanded" id="pgFocusExpanded" hidden>
          <div class="pg-focus-expanded-head">
            <button type="button" class="pg-focus-back-btn" id="pgFocusBackBtn" aria-label="Back to Quick view tiles" title="Return to the three tiles (Terminal · Results · Modules)">Quick view</button>
            <div class="pg-focus-expanded-tabs" role="tablist" aria-label="Switch panel or click the active tab again to return to Quick view">
              <button type="button" class="pg-focus-expanded-tab" id="pgFocusTabTerminal" data-pg-focus-tab="terminal" role="tab" aria-controls="pgFocusPaneTerminal" title="Terminal (tap again when highlighted to return to Quick view)">Terminal</button>
              <button type="button" class="pg-focus-expanded-tab" id="pgFocusTabResults" data-pg-focus-tab="results" role="tab" aria-controls="pgFocusPaneResults" title="Results (tap again when highlighted to return to Quick view)">Results</button>
              <button type="button" class="pg-focus-expanded-tab" id="pgFocusTabModules" data-pg-focus-tab="modules" role="tab" aria-controls="pgFocusPaneModules" title="Modules (tap again when highlighted to return to Quick view)">Modules</button>
            </div>
            <span class="pg-focus-expanded-title" id="pgFocusExpandedTitle">Expanded view</span>
          </div>
          <div class="pg-focus-expanded-body">
            <div id="pgFocusPaneTerminal" class="pg-focus-pane">
              <div class="pg-focus-pane-inner--dark">
              <div class="pg-telemetry-dock" style="position:static;max-height:none;top:0">
      <div id="liveTelemetryWrap" class="live-telemetry-wrap">
        <p class="live-telemetry-title">Live output <span class="pg-secondary-surface-label telemetry-run-only">While running</span>
          <span class="pg-sr-only">Live engine replay telemetry and Decision Context Recall (DCR) counters — not the Student learning store.</span>
          <span aria-hidden="true" style="display:block;margin-top:6px;font-size:0.78rem;font-weight:600;color:#9aa7b4;text-transform:none;letter-spacing:0">Engine replay + DCR</span></p>
        <div class="pg-terminal-split">
        <div class="pg-terminal-split-left">
        <div id="memoryStatusCard" class="memory-status-card" aria-live="polite">
          <p id="memoryStatusNarrative" class="memory-status-narrative"></p>
          <dl>
            <dt title="DCR read/write mode for context signature memory">Memory mode</dt><dd id="memStMode">—</dd>
            <dt title="New or updated memory rows written this batch">Memory saved this run</dt><dd id="memStSaved">—</dd>
            <dt title="Whether the engine loaded a memory bundle for replay">Memory loaded</dt><dd id="memStLoaded">—</dd>
            <dt title="Count of learning records pulled into the run">Records loaded</dt><dd id="memStRec">—</dd>
            <dt title="Signature matches from Decision Context Recall">Recall matches</dt><dd id="memStMatch">—</dd>
            <dt title="Times recall or signal bias altered candidate ranking">Bias applied</dt><dd id="memStBias">—</dd>
          </dl>
        </div>
        <div id="telemetryRollingLog" class="telemetry-rolling-log" aria-live="polite"></div>
        <pre id="liveTelemetryPanel" class="live-telemetry-panel">Idle — no exam running. Live counters stream here when you click Run exam.</pre>
        </div>
        <aside class="pg-terminal-compact-summary" id="terminalCompactSummary" aria-live="polite">
          <div class="pg-tcs-title">Run summary</div>
          <dl>
            <dt title="Parallel batch lifecycle: idle, running, or finished">Status</dt><dd id="tcsStatus">Idle</dd>
            <dt title="Current or last parallel job identifier">Batch</dt><dd id="tcsBatch">—</dd>
            <dt title="Evaluation calendar window (months) for this batch">Window</dt><dd id="tcsWindow">—</dd>
            <dt title="DW: decision windows processed in the latest hot telemetry sample">DW (hot)</dt><dd id="tcsDw">—</dd>
            <dt title="Wall-clock time since this batch started">Elapsed</dt><dd id="tcsElapsed">—</dd>
            <dt title="P&amp;L: profit and loss — most recent scenario cumulative paper result">Last P&amp;L</dt><dd id="tcsLastPnl">—</dd>
            <dt title="TW%: trade win percent — winning trades divided by trades with a result, last completed scenario">Last TW%</dt><dd id="tcsLastTw">—</dd>
          </dl>
        </aside>
        </div>
      </div>
              </div>
              </div>
            </div>
            <div id="pgFocusPaneResults" class="pg-focus-pane pg-focus-pane--results" hidden>
              <div class="pg-header-drawer-inner" style="background:transparent;padding:0">
                <div class="pg-tab-strip" role="tablist">
                  <button type="button" class="pg-tab active" data-tab="outcomes" role="tab">Referee outcomes</button>
                  <button type="button" class="pg-tab" data-tab="json" role="tab">Raw JSON</button>
                  <button type="button" class="pg-tab" data-tab="session" role="tab">Session log</button>
                  <button type="button" class="pg-tab" data-tab="scorecard" role="tab">Scorecard</button>
                </div>
                <div id="pgEvidenceOutcomes" class="pg-evidence-panel">
                  <div class="policy-outcome-panel" id="policyOutcomePanel" hidden>
                    <p class="hint">Trade win % per scenario; session from cumulative P&amp;L.</p>
                    <div class="pg-table-scroll">
                      <table class="policy-table" id="policyOutcomeTable">
                        <thead>
                          <tr>
                            <th title="Scenario preset identifier for this row">Scenario</th>
                            <th title="Referee session outcome: WIN, LOSS, or other judged state">Session</th>
                            <th title="Cumulative profit and loss (paper money) for this scenario in the batch">Cum. P&amp;L</th>
                            <th title="Share of winning trades among trades taken in this scenario">Trade win %</th>
                            <th title="Count of trades executed in this scenario">Trades</th>
                            <th title="Signal engine modules that contributed to this scenario">Signal modules</th>
                            <th title="How candidate signals were fused into one decision">Fusion</th>
                            <th title="Internal strategy or ruleset identifier">Strategy id</th>
                          </tr>
                        </thead>
                        <tbody id="policyOutcomeTbody"></tbody>
                      </table>
                    </div>
                  </div>
                </div>
                <p class="caps" id="sessionLogNote" style="display:none;margin:10px 0 8px"></p>
                <pre id="out" class="pg-pre-json" style="display:none">(no run yet)</pre>
                <div id="pgEvidenceScorecard" class="pg-evidence-scorecard-pane" style="display:none" data-pg-evidence-tab="scorecard">
                  <div class="scorecard-panel-inner pg-scorecard-split" id="scorecardPanel">
                    <div class="pg-scorecard-upper" id="scorecardUpper">
                      <details class="pg-scorecard-legend-fold">
                        <summary class="pg-scorecard-legend-summary">What these columns mean (legend)</summary>
                        <p class="scorecard-legend"><strong>Run OK %</strong> — workers finished. <strong>Session WIN %</strong> — referee WIN vs LOSS among judged sessions only; <strong>n sess</strong> is that denominator (never infer from a bare percentage). <strong>Trade win %</strong> — batch mean when trades exist (with trade count). <strong>Learning (replay lane)</strong> — <code>execution_only</code> vs <code>learning_active</code> from replay counters (candidate search, memory records loaded, recall matches, signal bias); not Student Proctor learning. <strong>Memory / Context Impact</strong> — YES/NO from <code>learning_run_audit_v1</code> only (bundle merged or recall bias/signal-bias counters &gt; 0); not inferred from &ldquo;memory loaded&rdquo; or learning lane. <strong>Work</strong> — decision windows, bars, and candidate-stack replays. Scan <em>down</em> for newest batches.           <strong>In-flight</strong> — a batch that is <strong>running</strong> now appears at the <strong>top</strong> with <strong>Start</strong> time and live progress counts; the JSONL line is written when the batch finishes. <strong>Scorecard file</strong> (<code>batch_scorecard.jsonl</code>) is batch audit for this table and hunter suggestions; replay does <em>not</em> read it to apply memory or recall. <strong>Clear Card</strong> truncates that log only. <strong>Clear Groundhog container</strong> deletes only the promoted bundle file; <strong>Clear context signature memory</strong> truncates only the DCR/signature recall JSONL. <strong>Reset Learning State</strong> clears those plus experience and run memory (typed confirmation).</p>
                      </details>
                      <p class="last-run" id="lastBatchRunLine">Last completed exam: —</p>
                      <div id="scorecardLearningSummary" class="scorecard-learning-summary exec-only" aria-live="polite" hidden>
                        <p class="sls-title">Latest batch — harness learning lane &amp; contextual memory <span style="font-weight:600;color:var(--pg-muted)">(engine / DCR; not the Student Proctor store)</span></p>
                        <div id="scorecardLearningSummaryBody" class="sls-body"></div>
                      </div>
                      <div id="memoryContextImpactPanel" class="memory-context-impact-panel" aria-live="polite" hidden>
                        <p class="sls-title">Memory / Context Impact</p>
                        <div id="memoryContextImpactBody" class="mci-grid"></div>
                        <p class="mci-barney" id="memoryContextBarneyLine"></p>
                      </div>
                      <div class="scorecard-toolbar">
                        <a id="scorecardCsvLink" href="/api/batch-scorecard.csv?limit=50">Download scorecard history (CSV)</a>
                        <div class="scorecard-toolbar-actions">
                          <button type="button" class="btn-scorecard-clear pg-op-btn" id="clearScorecardBtn" data-label-idle="Clear Card — Run New Experiment" title="Truncates batch_scorecard.jsonl (table history) only. Does not clear engine memory, bundles, or the Student Proctor learning store.">Clear Card — Run New Experiment</button>
                          <button type="button" class="btn-secondary pg-op-btn" id="clearPromotedBundleBtn" data-label-idle="Clear promoted parameter bundle…" title="Deletes the promoted bundle JSON in game_theory/state/ if present. Does not clear scorecard rows, experience log, run memory, or context signature memory.">Clear promoted parameter bundle…</button>
                          <button type="button" class="btn-secondary pg-op-btn" id="clearContextSignatureMemoryBtn" data-label-idle="Clear context signature memory…" title="Truncates game_theory/state/context_signature_memory.jsonl. Does not delete the promoted bundle file or scorecard history.">Clear context signature memory…</button>
                          <button type="button" class="btn-learning-reset-danger pg-op-btn" id="resetLearningStateBtn" data-label-idle="Reset Learning State" title="Destructive: engine experience logs, signature/DCR recall store, promoted bundle file. Does not clear the scorecard file, retrospective log, or Student Proctor learning store.">Reset Learning State</button>
                        </div>
                        <span style="font-size:0.72rem;color:var(--pg-muted)">Click a row to open batch detail, scenarios, and per-scenario report links (GT_DIRECTIVE_001).</span>
                      </div>
                      <div class="pg-student-proctor-truth" style="margin:10px 0;padding:8px 10px;background:rgba(0,0,0,0.09);border-radius:6px;font-size:0.78rem;line-height:1.35">
                        <strong>Student Proctor learning store</strong> — separate file from the scorecard log and from &ldquo;Reset Learning State&rdquo; (engine memory / bundles / recall JSONL).
                        <span id="studentProctorStoreLine" aria-live="polite">Loading…</span>
                        <div style="margin-top:6px">
                          <button type="button" class="btn-secondary pg-op-btn" id="clearStudentProctorStoreBtn" data-label-idle="Clear Student Proctor store…" title="Truncates the Student Proctor append-only JSONL only. Does not clear scorecard history or engine learning files.">Clear Student Proctor store…</button>
                        </div>
                      </div>
                      <div class="pg-table-scroll scorecard-table-wrap-wide">
                        <table class="scorecard-table scorecard-table-learning" id="scorecardHistoryTable">
                          <thead>
                            <tr>
                              <th title="Job: unique parallel batch id (job_id)">Job</th>
                              <th title="UTC time the batch started">Start</th>
                              <th title="UTC time the batch finished">End</th>
                              <th title="Dur: wall-clock duration of the batch in seconds">Dur</th>
                              <th title="Work units: decision windows, price bars processed, and candidate-stack replays (engine load)">Work</th>
                              <th title="Learning lane: execution_only vs learning_active from replay counters">Learn</th>
                              <th title="DW: total decision windows evaluated in this batch">DW</th>
                              <th title="Bars: OHLC bars processed across scenarios">Bars</th>
                              <th title="Cand: pattern candidates evaluated">Cand</th>
                              <th title="Sel: selected candidate id after search">Sel</th>
                              <th title="WΔ: winner vs control delta (search quality signal)">WΔ</th>
                              <th title="Mem: whether memory bundle was used this batch">Mem</th>
                              <th title="MRec: memory records loaded from store">MRec</th>
                              <th title="PM: Promoted memory / bundle lane (ATR)">PM</th>
                              <th title="RAtt: Decision Context Recall lookup attempts">RAtt</th>
                              <th title="RMt: recall signature matches">RMt</th>
                              <th title="RBias: times recall bias was applied to candidates">RBias</th>
                              <th title="SBc: signal-bias applications count">SBc</th>
                              <th title="Sup: modules suppressed by policy">Sup</th>
                              <th title="TIn: trade entries opened">TIn</th>
                              <th title="TOut: trade exits closed">TOut</th>
                              <th title="TW%: batch trade win percent — wins divided by trades with a result">TW%</th>
                              <th title="#Tr: number of trades in the batch rollup">#Tr</th>
                              <th title="E/tr: economic expectancy per trade (batch); exam-pack exam E when denormalized on the line">E/tr</th>
                              <th title="Xeff: exit efficiency score">Xeff</th>
                              <th title="WLR: average win size divided by average loss size">WLR</th>
                              <th title="SWin%: session win percent — referee WIN vs LOSS among judged sessions only">SWin%</th>
                              <th title="#Sess: number of scenarios judged WIN or LOSS">#Sess</th>
                              <th title="RunOK%: percent of workers that finished without exception">RunOK%</th>
                              <th title="OK: count of scenarios completed OK">OK</th>
                              <th title="Fail: count of scenarios that failed">Fail</th>
                              <th title="Wkr: parallel workers used">Wkr</th>
                              <th title="St: batch status (running, done, error)">St</th>
                            </tr>
                          </thead>
                          <tbody id="scorecardHistoryTbody"></tbody>
                        </table>
                      </div>
                      <div id="batchDrillPanel" class="batch-drill-panel" aria-live="polite"></div>
                      <p id="scorecardClickHint" class="scorecard-click-hint" role="status" aria-live="polite" style="display:none"></p>
                      <p class="path-hint" id="scorecardPathHint"></p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div id="pgFocusPaneModules" class="pg-focus-pane pg-focus-pane--modules" hidden>
              <div class="pg-pill-row"><span class="pg-pill">Green = passed</span><span class="pg-pill">Amber = idle / waiting</span><span class="pg-pill">Red = fault</span></div>
              <div class="pg-status-list" id="moduleBoardList"><p class="caps pg-module-board-msg">Loading…</p></div>
            </div>
          </div>
        </div>
      </div>

      <details class="pg-panel-fold pg-student-triangle-dock" id="pgStudentTriangleDock">
        <summary>
          <div class="pg-panel-header" style="margin:0;flex:1">
            <div>
              <h2 class="pg-panel-h">Student → learning → outcome</h2>
              <p class="pg-panel-sub"><strong>Operator panel (D14):</strong> Level 1 = exam list only. Level 2 = one selected exam — run summary band + trade carousel only. Level 3 = one trade deep dive only. Resize the fold from the bottom edge; state is remembered. <a href="/docs/student-panel-dictionary" onclick="return pgOpenStudentPanelDictionaryPopout();" title="Opens glossary in a resizable pop-out window (same name reuses one window)">Student panel dictionary</a> — terms for columns, profiles, L1 road, and APIs.</p>
            </div>
            <span class="pg-chip pg-chip-teal">Primary</span>
          </div>
        </summary>
        <div id="studentTriangleFoldBody" class="pg-panel-fold-body pg-student-triangle-fold-body" title="Drag the bottom-right corner or bottom edge to resize. Size and open/closed state are saved in this browser (localStorage).">
          <div id="studentTriangleBody" class="pg-student-triangle-body" aria-live="polite">
            <div id="pgStudentPanelD11" class="pg-student-d11"></div>
          </div>
        </div>
      </details>

      <details class="pg-panel-fold pg-dev-student-seam-dock" id="pgDevStudentBatchPlumbing" style="margin-top:12px">
        <summary>
          <div class="pg-panel-header" style="margin:0;flex:1">
            <div>
              <h2 class="pg-panel-h" style="font-size:1rem">Developer — batch seam &amp; plumbing</h2>
              <p class="pg-panel-sub">Not part of the three-level Student operator panel. Expand for Directive 09 handoff detail, store path, and learning-at-a-glance (debug).</p>
            </div>
            <span class="pg-chip" style="opacity:0.75">Debug</span>
          </div>
        </summary>
        <div class="pg-panel-fold-body" style="padding:12px 14px">
          <p class="pg-student-d11-legend" style="margin-top:0">Latest batch — seam (Directive 09) · not operator Student panel content</p>
          <div id="pgDevStudentSeamInner" class="caps" style="margin:0 0 12px">No exam yet — click Run exam in Controls.</div>
      <section class="pg-learning-events-strip" id="pgLearningEventsStrip" aria-label="Learning events at a glance (developer)" hidden>
        <h3 class="pg-learning-events-h">Latest run — learning at a glance</h3>
        <ul class="pg-learning-events-ul" id="pgLearningEventsUl"></ul>
        <p class="pg-learning-events-note">Developer overview — not Level 1–3 Student panel.</p>
        <div style="margin-top:8px">
          <button type="button" class="btn-secondary pg-op-btn" id="pgForensicOpenBtn" hidden>Open forensic drill (placeholder)</button>
        </div>
      </section>
        </div>
      </details>

      <details class="pg-panel-fold pg-barney-ask-unified" id="pgBarneyAskUnified" open>
        <summary>
          <div class="pg-panel-header" style="margin:0;flex:1">
            <div>
              <h2 class="pg-panel-h">Ask DATA + System Dialogue</h2>
              <p class="pg-panel-sub">Ask DATA Q&amp;A on the left — Ask DATA thread and last-run batch recap on the right</p>
            </div>
            <span class="pg-chip pg-chip-teal">Unified</span>
          </div>
        </summary>
        <div class="pg-panel-fold-body" style="min-height:0">
          <div class="pg-barney-ask-grid">
            <div class="pg-barney-ask-col pg-barney-ask-col--ask" aria-label="Ask questions">
              <p class="pg-barney-title" style="margin:0 0 6px">Ask DATA</p>
              <p class="pg-askdata-invite">
                <strong>Ask me anything in natural language</strong> — controls, runs, memory, the Student path, or how this UI fits together.
                Optional <strong>example questions</strong> live in the fold below (closed by default). Tap a chip to send. You can also <strong>paste JSON, manifest text, or errors</strong> in the box — Ask DATA will say what it still needs.
                For <strong>downloadable reports</strong> (CSV / exports), Ask DATA points at the real <strong>HTTP routes</strong> and query strings; use those links in the browser or the existing download controls — chat does not attach binary files.
                Ask DATA only uses this app’s glossary, run/scorecard facts, and operator context — not the open web.
              </p>
              <details class="pg-askdata-starters-fold">
                <summary class="pg-askdata-starters-fold-summary">Example questions (optional)</summary>
                <div class="pg-askdata-starters-inner" role="group" aria-label="Suggested Ask DATA questions">
                  <button type="button" class="pg-askdata-chip" data-ask="What am I allowed to do in this Pattern Machine operator UI, and what is out of scope or forbidden?">What am I allowed to do?</button>
                  <button type="button" class="pg-askdata-chip" data-ask="What is required to submit a built-in pattern or recipe run (not Custom), and can you walk me through it with leading questions?">What is required to submit a pattern / recipe run?</button>
                  <button type="button" class="pg-askdata-chip" data-ask="What is required to submit a batch using an operator-uploaded strategy manifest, and can you walk me through it with leading questions?">What is required to submit an uploaded strategy?</button>
                  <button type="button" class="pg-askdata-chip" data-ask="What is required to submit a run using Custom JSON or policy framework metadata, and can you walk me through it with leading questions?">What is required for Custom JSON / framework?</button>
                  <button type="button" class="pg-askdata-chip" data-ask="What is PML?">What is PML?</button>
                  <button type="button" class="pg-askdata-chip" data-ask="Where do scenarios come from?">Where do scenarios come from?</button>
                  <button type="button" class="pg-askdata-chip" data-ask="What is the difference between pattern, policy framework, and manifest?">What is the difference between pattern, policy, and manifest?</button>
                </div>
              </details>
              <textarea id="askDataInput" class="pg-askdata-input" rows="3" maxlength="6000"
                placeholder="Ask anything in plain language… (Ctrl/Cmd+Enter to send)"
                autocomplete="off" aria-label="Ask DATA — natural language question"></textarea>
              <div class="pg-askdata-actions">
                <button type="button" class="btn-chef pg-op-btn" id="askDataSendBtn" data-label-idle="Send">Send</button>
                <button type="button" class="btn-secondary pg-op-btn" id="askDataClearBtn" data-label-idle="Clear thread">Clear thread</button>
              </div>
              <p class="pg-askdata-status" id="askDataStatus" aria-live="polite" style="margin:0;font-size:0.78rem"></p>
            </div>
            <div class="pg-barney-ask-col pg-barney-ask-col--barney" aria-label="Ask DATA replies and batch recap">
              <div id="pgAskDataReplyShell" class="pg-askdata-reply-shell">
                <p class="pg-barney-title" style="margin:0 0 6px">Ask DATA — replies</p>
                <div id="askDataThread" class="pg-askdata-thread" aria-live="polite" role="log"></div>
                <div
                  id="pgAskDataReplyDrag"
                  class="pg-askdata-reply-drag"
                  role="separator"
                  aria-orientation="horizontal"
                  aria-label="Drag to resize Ask DATA replies. Height is saved in this browser."
                  title="Drag to resize replies · height saved in this browser (localStorage)"
                ></div>
              </div>
              <div class="pg-askdata-recap-block">
                <p class="pg-barney-title" style="margin:10px 0 4px">Last run — batch recap (Barney)</p>
                <p class="pg-barney-recap-hint">
                  Plain-English summary of the <strong>most recent finished</strong> parallel job (<code>/api/barney-summary</code>).
                  Stays “—” until a batch completes here or after refresh, or if the formatter is off.
                </p>
                <pre id="barneySummaryBody" class="pg-barney-body" style="margin:0;overflow:auto">—</pre>
              </div>
            </div>
          </div>
        </div>
      </details>

      <dialog id="pgForensicDrillDialog" class="pg-forensic-dialog">
        <div class="pg-forensic-dialog-inner">
          <button type="button" class="pg-module-dialog-close" id="pgForensicDrillClose" aria-label="Close">×</button>
          <h2 class="pg-module-dialog-h2">Forensic drill</h2>
          <p class="caps" style="margin:0 0 10px;font-size:0.82rem;line-height:1.45;color:var(--pg-muted)">§H target: baseline vs with-memory on the <strong>same</strong> decision row; Referee-over-Student card; synchronized timestamps. Wire API + payload in a follow-on.</p>
          <pre class="pg-module-body" style="max-height:40vh;overflow:auto;font-size:0.78rem">Placeholder — no server route yet.</pre>
        </div>
      </dialog>
      </div>
      </div>
    </section>
  </div>

  
  <!-- External file: strict CSP often allows same-origin scripts while blocking inline ``<script>`` body. -->
  <script src="/assets/pattern-game-banner-boot.js?v=__PATTERN_GAME_WEB_UI_VERSION__"></script>
  <script>
    const LIMITS = __LIMITS_JSON__;
    const STARTING_EQUITY = __STARTING_EQUITY__;
    const RUN_TIMEOUT_MS = 7200000;
    const PATTERN_GAME_UI_VERSION_STR = '__PATTERN_GAME_WEB_UI_VERSION__';
    /** Persisted while a parallel batch is in flight so refresh restores running state until completion. */
    const PG_PARALLEL_INFLIGHT_JOB_LS = 'patternGame.parallelInflightJobId';

    function pgSetInflightJobId(jid) {
      try {
        if (jid) localStorage.setItem(PG_PARALLEL_INFLIGHT_JOB_LS, String(jid));
        else localStorage.removeItem(PG_PARALLEL_INFLIGHT_JOB_LS);
      } catch (e) { /* ignore quota / private mode */ }
    }
    function pgGetInflightJobId() {
      try {
        return String(localStorage.getItem(PG_PARALLEL_INFLIGHT_JOB_LS) || '').trim();
      } catch (e) {
        return '';
      }
    }
    /** Fallback when Run mode fields are missing (e.g. early init). */
    const CONTEXT_SIGNATURE_MEMORY_MODE_PRODUCT = 'read_write';

    function resolveExamBrainProfileV1ForStart() {
      const leg = document.getElementById('pgExamLegacyBrainProfileOverride');
      if (leg && String(leg.value || '').trim()) {
        return String(leg.value).trim();
      }
      const profEl = document.getElementById('examStudentReasoningModePick');
      if (profEl && profEl.value) return String(profEl.value).trim();
      return 'memory_context_llm_student';
    }

    function contextSignatureMemoryModeForExamRunV1() {
      return resolveExamBrainProfileV1ForStart() === 'baseline_no_memory_no_llm' ? 'off' : 'read_write';
    }

    const rangeEl = document.getElementById('workersRange');
    const workersVal = document.getElementById('workersVal');
    const statusLine = document.getElementById('statusLine');
    const progressWrap = document.getElementById('progressWrap');
    const workerCpuHint = document.getElementById('workerCpuHint');

    const hardMax = LIMITS.hard_cap_workers;
    const recommended = LIMITS.recommended_max_workers;
    const defaultWorkers = Math.max(1, Math.min(recommended, hardMax));

    if (rangeEl && workersVal) {
      rangeEl.min = '1';
      rangeEl.max = String(hardMax);
      rangeEl.value = String(defaultWorkers);
      workersVal.textContent = rangeEl.value;
      rangeEl.addEventListener('input', () => {
        workersVal.textContent = rangeEl.value;
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
      });
    }
    if (workerCpuHint) {
      workerCpuHint.textContent =
        'Host: ' + LIMITS.cpu_logical_count + ' logical CPUs · default slider ' + recommended +
        ' · max ' + hardMax + '. ' + LIMITS.note;
    }

    function parseScenarioCountFromTextarea() {
      const ta = document.getElementById('scenarios');
      if (!ta || !ta.value.trim()) return 0;
      try {
        const parsed = JSON.parse(ta.value.trim());
        const arr = Array.isArray(parsed) ? parsed : (parsed && Array.isArray(parsed.scenarios) ? parsed.scenarios : null);
        return (arr && arr.length) ? arr.length : 0;
      } catch (e) { return 0; }
    }
    /** Curated patterns: scenario count from server preview (textarea may be empty/disabled). */
    let STRUCTURED_SCENARIO_COUNT = 1;
    function getEffectiveScenarioCount() {
      const rp = document.getElementById('operatorRecipePick');
      const rid = rp && rp.value;
      if (rid && rid !== 'custom') {
        return STRUCTURED_SCENARIO_COUNT > 0 ? STRUCTURED_SCENARIO_COUNT : 1;
      }
      return parseScenarioCountFromTextarea();
    }
    function refreshWorkerEffectiveLine() {
      const el = document.getElementById('workerEffectiveLine');
      if (!el) return;
      const n = getEffectiveScenarioCount();
      const w = rangeEl ? (parseInt(rangeEl.value, 10) || 1) : 1;
      if (n < 1) {
        el.innerHTML = '<strong>Effective parallelism</strong> — For <em>Custom</em>, paste valid JSON in Advanced. The run uses <strong>min(scenario count, slider)</strong>.';
        return;
      }
      const eff = Math.min(n, w);
      let extra = '';
      if (n === 1) {
        extra = '<div style="margin-top:8px;color:#c9a227;font-size:0.9em">Single scenario: only one process runs; raising the slider does not speed it up.</div>';
      }
      el.innerHTML =
        '<strong>' + eff + '</strong> parallel process(es) for this batch ' +
        '(<strong>' + n + '</strong> scenario(s) × slider <strong>' + w + '</strong>, capped at the smaller). ' + extra;
    }

    function escapeHtml(s) {
      if (s == null) return '';
      const d = document.createElement('div');
      d.textContent = String(s);
      return d.innerHTML;
    }

    /** Student panel glossary — named pop-out so one dictionary window is reused. */
    function pgOpenStudentPanelDictionaryPopout() {
      try {
        var path = '/docs/student-panel-dictionary';
        var u =
          window.location && window.location.origin ? window.location.origin + path : path;
        var feat = 'width=940,height=880,scrollbars=yes,resizable=yes';
        var w = window.open(u, 'pgStudentPanelDictionary', feat);
        if (w) w.focus();
      } catch (_e) {}
      return false;
    }

    /** Async operator actions: disabled + spinner + label until cleared (instant feedback before network returns). */
    function setOpButtonBusy(btn, busy, busyLabel, useSpinner) {
      if (!btn) return;
      if (busy) {
        if (!btn.getAttribute('data-label-idle')) {
          var idle0 = (btn.textContent || '').trim();
          if (idle0) btn.setAttribute('data-label-idle', idle0);
        }
        btn.disabled = true;
        btn.classList.add('is-running');
        btn.setAttribute('aria-busy', 'true');
        var label = busyLabel || 'Working…';
        if (useSpinner) {
          btn.innerHTML =
            '<span class="pg-op-btn__inner"><span class="pg-op-btn__spinner" aria-hidden="true"></span><span class="pg-op-btn__label">' +
            escapeHtml(label) +
            '</span></span>';
        } else {
          btn.textContent = label;
        }
      } else {
        btn.classList.remove('is-running');
        btn.removeAttribute('aria-busy');
        var idl = btn.getAttribute('data-label-idle');
        btn.textContent = idl != null ? idl : '';
        btn.disabled = false;
      }
    }

    function recipeLabelFromDom() {
      const rp = document.getElementById('operatorRecipePick');
      if (!rp || !rp.options) return '—';
      const o = rp.options[rp.selectedIndex];
      return (o && o.text) ? String(o.text).trim() : String(rp.value || '—');
    }
    function evaluationWindowLabelFromDom() {
      const w = document.getElementById('evaluationWindowPick');
      if (!w) return '—';
      if (w.value === 'custom') {
        const c = document.getElementById('evaluationWindowCustomMonths');
        const n = c ? parseInt(c.value, 10) : NaN;
        return (n > 0) ? (String(n) + ' months (custom)') : 'custom';
      }
      return String(w.value) + ' months';
    }
    function tradeWindowLabel() {
      const tw = document.getElementById('tradeWindowPick');
      if (!tw || !tw.options) return '—';
      const o = tw.options[tw.selectedIndex];
      return (o && o.text) ? String(o.text).trim() : String(tw.value || '—');
    }
    function fmtTelemetryHMS(sec) {
      const s = Math.max(0, Math.floor(Number(sec) || 0));
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const rs = s % 60;
      if (h > 0) {
        return h + ':' + String(m).padStart(2, '0') + ':' + String(rs).padStart(2, '0');
      }
      return String(m).padStart(2, '0') + ':' + String(rs).padStart(2, '0');
    }

    let _lastTelemetryDetailText = '';
    let _lastTelemetryStreamKey = '';

    function _memoryModeLabelFromEcho(modeRaw) {
      const m = String(modeRaw || '').trim().toLowerCase();
      if (m === 'off') return 'OFF';
      if (m === 'read') return 'READ';
      if (m === 'read_write') return 'READ+WRITE';
      return '—';
    }

    function _yn(v) {
      if (v === true || v === 1 || v === '1' || v === 'yes' || v === 'Y' || v === 'YES') return 'YES';
      if (v === false || v === 0 || v === '0' || v === 'no' || v === 'N' || v === 'NO') return 'NO';
      return '—';
    }

    function updateMemoryStatusCardFromPanel(panel, echo, hot, running) {
      const narr = document.getElementById('memoryStatusNarrative');
      const mMode = document.getElementById('memStMode');
      const mSaved = document.getElementById('memStSaved');
      const mLoaded = document.getElementById('memStLoaded');
      const mRec = document.getElementById('memStRec');
      const mMatch = document.getElementById('memStMatch');
      const mBias = document.getElementById('memStBias');
      if (mMode) {
        mMode.textContent = echo && echo.context_signature_memory_mode != null
          ? _memoryModeLabelFromEcho(echo.context_signature_memory_mode)
          : _memoryModeLabelFromEcho(CONTEXT_SIGNATURE_MEMORY_MODE_PRODUCT);
      }
      if (panel && typeof panel === 'object') {
        if (narr) narr.textContent = String(panel.narrative || '').trim() || (running ? 'Run in progress — memory counters update live from the busiest worker.' : '');
        if (mSaved) mSaved.textContent = _yn(panel.memory_saved_this_run);
        if (mLoaded) mLoaded.textContent = _yn(panel.memory_loaded);
        if (mRec) mRec.textContent = fmtIntCommas(panel.memory_records_loaded_count);
        if (mMatch) mMatch.textContent = fmtIntCommas(panel.recall_matches != null ? panel.recall_matches : panel.recall_match_windows_total);
        if (mBias) mBias.textContent = fmtIntCommas(panel.bias_applied != null ? panel.bias_applied : panel.recall_bias_applied_total);
        return;
      }
      const hotObj = hot && typeof hot === 'object' ? hot : null;
      const hasHotNums = !!hotObj && (
        hotObj.recall_match_windows_so_far != null ||
        hotObj.recall_bias_applied_so_far != null ||
        hotObj.recall_match_records_so_far != null
      );
      if (running && hasHotNums) {
        const rm = hotObj.recall_match_windows_so_far != null ? Number(hotObj.recall_match_windows_so_far) : 0;
        const rb = hotObj.recall_bias_applied_so_far != null ? Number(hotObj.recall_bias_applied_so_far) : 0;
        const rrec = hotObj.recall_match_records_so_far != null ? Number(hotObj.recall_match_records_so_far) : 0;
        if (narr) {
          narr.textContent =
            rm > 0 || rb > 0
              ? 'Prior contextual memory is influencing this replay where signatures match (live counters).'
              : 'Replay is running — memory recall counts appear when the replay starts matching stored signatures.';
        }
        if (mSaved) mSaved.textContent = '—';
        if (mLoaded) mLoaded.textContent = rm > 0 || rb > 0 ? 'YES' : 'NO';
        if (mRec) mRec.textContent = fmtIntCommas(rrec);
        if (mMatch) mMatch.textContent = fmtIntCommas(rm);
        if (mBias) mBias.textContent = fmtIntCommas(rb);
      } else if (running) {
        if (narr) narr.textContent = 'Batch starting — memory stats will fill in as workers report progress.';
        if (mSaved) mSaved.textContent = '—';
        if (mLoaded) mLoaded.textContent = '—';
        if (mRec) mRec.textContent = '0';
        if (mMatch) mMatch.textContent = '0';
        if (mBias) mBias.textContent = '0';
      } else if (!running) {
        if (narr) narr.textContent = 'Idle — start a batch to see contextual memory status for that run.';
        if (mSaved) mSaved.textContent = '—';
        if (mLoaded) mLoaded.textContent = '—';
        if (mRec) mRec.textContent = '—';
        if (mMatch) mMatch.textContent = '—';
        if (mBias) mBias.textContent = '—';
      }
    }

    function aggregateContextMemoryPanelFromResults(results) {
      if (!Array.isArray(results) || !results.length) return null;
      let merged = null;
      for (const row of results) {
        if (!row || !row.ok) continue;
        const p = row.context_memory_operator_panel_v1;
        if (!p || typeof p !== 'object') continue;
        if (!merged) {
          merged = { ...p };
          continue;
        }
        merged.memory_saved_this_run = !!(merged.memory_saved_this_run || p.memory_saved_this_run);
        merged.memory_loaded = !!(merged.memory_loaded || p.memory_loaded);
        merged.memory_records_loaded_count = Math.max(
          Number(merged.memory_records_loaded_count) || 0,
          Number(p.memory_records_loaded_count) || 0
        );
        merged.recall_matches =
          (Number(merged.recall_matches) || 0) + (Number(p.recall_matches) || 0);
        merged.bias_applied =
          (Number(merged.bias_applied) || 0) + (Number(p.bias_applied) || 0);
        if (!merged.narrative && p.narrative) merged.narrative = p.narrative;
      }
      if (merged && !merged.narrative) {
        merged.narrative =
          (merged.memory_saved_this_run ? 'At least one scenario saved a winning pattern to contextual memory. ' : '') +
          (merged.memory_loaded ? 'Prior memory was read and applied where conditions matched.' : '');
      }
      return merged;
    }

    function updateMemoryStatusFromBatchResultPayload(payload) {
      const echo = (payload && payload.operator_batch_audit) || {};
      const results = payload && payload.results;
      const panel = aggregateContextMemoryPanelFromResults(results);
      updateMemoryStatusCardFromPanel(panel, echo, null, false);
    }

    /** GET JSON for Student panel APIs — timeout + non-JSON / HTTP errors (avoids stuck “Loading…”). */
    async function pgStudentPanelJsonGet(url) {
      const ctrl = new AbortController();
      const tid = window.setTimeout(function () {
        ctrl.abort();
      }, 45000);
      try {
        const r = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
        window.clearTimeout(tid);
        const raw = await r.text();
        var j;
        try {
          j = JSON.parse(raw);
        } catch (parseErr) {
          return {
            ok: false,
            error:
              'Expected JSON from server; got HTTP ' +
              r.status +
              ' — ' +
              String(raw || '').slice(0, 180),
          };
        }
        if (!r.ok) {
          return {
            ok: false,
            error: (j && j.error) || 'HTTP ' + r.status,
          };
        }
        return j;
      } catch (e) {
        window.clearTimeout(tid);
        if (e && e.name === 'AbortError') {
          return { ok: false, error: 'Request timed out after 45s — check Network tab and Flask on :8765.' };
        }
        return { ok: false, error: String(e) };
      }
    }

    /** D11 — contractual: one level replaces the panel; pinned chrome; scroll body only. */
    const studentPanelD11 = {
      level: 1,
      selectedRunId: null,
      selectedDecisionId: null,
      sliceCount: 0,
      lastVisitedRunId: null,
      firstSliceDecisionId: null,
    };

    /** Seam / handoff lives in developer-only panel (#pgDevStudentSeamInner), not in L1–L3 body. */
    function studentPanelD11HandoffEl() {
      return null;
    }
    function studentPanelD11RootEl() {
      return document.getElementById('pgStudentPanelD11');
    }
    function studentPanelD11SetHandoffVisible(_show) {
      /* D14.GC.1 — operator Student panel has no handoff strip; seam is in #pgDevStudentSeamInner only. */
    }

    function fmtD11MaybeNum(v, d) {
      if (v == null || v === '') return '—';
      const n = Number(v);
      if (Number.isNaN(n)) return escapeHtml(String(v));
      return escapeHtml(n.toFixed(d != null ? d : 2));
    }

    function studentPanelD11ShortRunId(rid) {
      const s = rid != null ? String(rid) : '';
      return s.length > 18 ? s.slice(0, 16) + '…' : s;
    }

    function studentPanelD11Layout(chromeHtml, scrollHtml) {
      return (
        '<div class="pg-student-d11-layout">' +
        '<div class="pg-student-d11-chrome" id="pgStudentD11Chrome">' +
        chromeHtml +
        '</div>' +
        '<div class="pg-student-d11-scroll" id="pgStudentD11Scroll">' +
        scrollHtml +
        '</div>' +
        '</div>'
      );
    }

    function renderStudentPanelD11Chrome(level, bcParts, showNav, traceRunId) {
      var traceRid =
        traceRunId != null && String(traceRunId).trim() ? String(traceRunId).trim() : '';
      let bc = '<nav class="pg-student-d11-bc" aria-label="D11 location">';
      if (Array.isArray(bcParts) && bcParts.length) {
        for (var i = 0; i < bcParts.length; i++) {
          if (i) bc += ' <span style="opacity:0.55">›</span> ';
          bc += bcParts[i];
        }
      }
      bc += '</nav>';
      let nav =
        '<div class="pg-student-d11-nav" id="pgStudentD11Nav">' +
        '<span class="pg-student-d11-carets" role="group" aria-label="Step between views">' +
        '<button type="button" class="pg-student-d11-caret" id="pgStudentD11StepPrev" title="Back one view" aria-label="Back one view">‹</button>' +
        '<button type="button" class="pg-student-d11-caret" id="pgStudentD11StepNext" title="Forward one view" aria-label="Forward one view">›</button>' +
        '</span>';
      if (showNav && (level === 2 || level === 3)) {
        nav += '<button type="button" id="pgStudentD11BackRuns">← Exam list</button>';
      }
      if (showNav && level === 3) {
        nav +=
          '<button type="button" id="pgStudentD11BackStrip">← Trade carousel</button>';
      }
      if (traceRid) {
        var traceUrl = '/debug/learning-loop?job_id=' + encodeURIComponent(traceRid);
        if (level === 3 && studentPanelD11 && studentPanelD11.selectedDecisionId) {
          traceUrl +=
            '&trade_id=' + encodeURIComponent(String(studentPanelD11.selectedDecisionId));
        }
        var proof026LUrl =
          '/debug/learning-loop?run_b=' +
          encodeURIComponent(traceRid) +
          '&job_id=' +
          encodeURIComponent(traceRid);
        nav +=
          '<a class="pg-student-d11-trace" href="' +
          traceUrl +
          '" target="_blank" rel="noopener noreferrer">View Learning Trace</a>' +
          '<a class="pg-student-d11-trace" href="' +
          proof026LUrl +
          '" target="_blank" rel="noopener noreferrer" title="Compare Run A (lesson) vs this run as Run B">A→B learning proof (026L)</a>';
      } else {
        nav +=
          '<span class="pg-student-d11-trace pg-student-d11-trace--disabled" title="Select an exam row on Level 1 (or open Level 2 / 3 for a run) to enable the trace link">View Learning Trace</span>' +
          '<span class="pg-student-d11-trace pg-student-d11-trace--disabled" title="Select a run first">A→B learning proof (026L)</span>';
      }
      nav += '</div>';
      return bc + nav;
    }

    function wireStudentPanelD11Nav() {
      const b1 = document.getElementById('pgStudentD11BackRuns');
      const b2 = document.getElementById('pgStudentD11BackStrip');
      if (b1) b1.onclick = function () { void studentPanelD11GotoLevel1(); };
      if (b2)
        b2.onclick = function () {
          if (studentPanelD11.selectedRunId) void studentPanelD11GotoLevel2(studentPanelD11.selectedRunId);
        };
    }

    function studentPanelD11SliceIdFromSlice(s, idx) {
      const x = s || {};
      if (x.trade_id != null) return String(x.trade_id);
      return x.decision_id != null ? String(x.decision_id) : 'd' + idx;
    }

    function renderD13RunSummaryBand(rs) {
      if (!rs || typeof rs !== 'object') return '';
      var RS_TIP = {
        run_id: 'Run id: unique job identifier for this exam batch.',
        pattern: 'Pattern: operator recipe / policy label.',
        evaluation_window: 'Evaluation window: calendar months of data in this batch.',
        total_trade_opportunities: 'Trade opportunities: scenarios where a trade could occur.',
        win_count: 'Win count: trades closed favorable.',
        loss_count: 'Loss count: trades closed unfavorable.',
        'win_rate_%': 'Win rate percent: wins divided by wins plus losses.',
        dir_align:
          'Dir align: Student thesis direction vs Referee replay direction — fraction shown when evaluable.',
        avg_win_pnl: 'Avg win PnL: mean profit on winning trades (paper).',
        avg_loss_pnl: 'Avg loss PnL: mean loss on losing trades (paper; usually negative).',
        'expectancy/tr':
          'Expectancy per trade: edge per trade from batch math; exam-pack E when denormalized on scorecard.',
        'behavior_Δ': 'Behavior changed: YES/NO if harness or Student handoff signals changed vs prior.',
        'outcome_Δ': 'Outcome improved: YES/NO if L1 economic scalar improved vs prior same-fingerprint run.',
        PM: 'PM: Promoted memory / bundle lane for this run.',
        ctx: 'Ctx: context bundle used flag from run summary.',
        mem: 'Mem: memory bundle used flag from run summary.',
        'E (exam)':
          'E (exam): economic grade scalar from exam-pack grading only (compute_exam_grade_v1); not batch expectancy.',
        'P (exam)': 'P (exam): process score 0–1 from the same exam grading call.',
        PASS: 'PASS: exam-pack pass when graded true; FAIL when graded false; — when not graded.',
        'E src':
          'E src: label for which scalar feeds L1 for this run — exam_pack_grading_v1 vs expectancy_per_trade_proxy_v1.',
        'P src':
          'P src: label for process scalar source — exam_pack_grading_v1 vs student_l1_process_score_proxy_v1 vs data_gap.',
      };
      function cell(k, v) {
        var disp = v == null || v === '' ? '—' : String(v);
        var tip = RS_TIP[k] || 'Field: ' + k;
        return (
          '<span class="pg-student-d13-rs-cell" title="' +
          escapeHtml(tip) +
          '"><span class="pg-student-d13-rs-k">' +
          escapeHtml(k) +
          '</span>' +
          escapeHtml(disp) +
          '</span>'
        );
      }
      var parts = [
        cell('run_id', rs.run_id),
        cell('pattern', rs.pattern),
        cell('evaluation_window', rs.evaluation_window),
        cell('total_trade_opportunities', rs.total_trade_opportunities),
        cell('win_count', rs.win_count),
        cell('loss_count', rs.loss_count),
        cell('win_rate_%', rs.win_rate_percent),
        cell(
          'dir_align',
          (function () {
            var ev = rs.student_referee_direction_align_evaluable_trades;
            if (ev == null || !Number(ev) || Number(ev) <= 0) return '—';
            var m = rs.student_referee_direction_align_matches;
            var pct = rs.student_referee_direction_align_rate_percent;
            return String(m) + '/' + String(ev) + ' (' + String(pct) + '%)';
          })()
        ),
        cell('avg_win_pnl', rs.avg_win_pnl),
        cell('avg_loss_pnl', rs.avg_loss_pnl),
        cell('expectancy/tr', rs.expectancy_per_trade),
        cell('behavior_Δ', rs.behavior_changed_flag),
        cell('outcome_Δ', rs.outcome_improved_flag),
        cell('PM', rs.groundhog_state),
        cell('ctx', rs.context_used_flag),
        cell('mem', rs.memory_used_flag),
        cell('E (exam)', rs.exam_e_score_v1 != null ? fmtD11MaybeNum(rs.exam_e_score_v1, 4) : '—'),
        cell('P (exam)', rs.exam_p_score_v1 != null ? fmtD11MaybeNum(rs.exam_p_score_v1, 4) : '—'),
        cell(
          'PASS',
          rs.exam_pass_v1 === true ? 'PASS' : rs.exam_pass_v1 === false ? 'FAIL' : '—'
        ),
        cell('E src', rs.l1_e_value_source_v1 != null ? String(rs.l1_e_value_source_v1) : '—'),
        cell('P src', rs.l1_p_value_source_v1 != null ? String(rs.l1_p_value_source_v1) : '—'),
      ];
      return '<div class="pg-student-d13-run-summary" role="region" aria-label="Run summary">' + parts.join('') + '</div>';
    }

    function studentPanelD11WireStep() {
      const prev = document.getElementById('pgStudentD11StepPrev');
      const next = document.getElementById('pgStudentD11StepNext');
      if (!prev || !next) return;
      const lv = studentPanelD11.level;
      if (lv === 1) {
        prev.disabled = true;
        next.disabled = !studentPanelD11.lastVisitedRunId;
        prev.onclick = function () {};
        next.onclick = function () {
          if (studentPanelD11.lastVisitedRunId)
            void studentPanelD11GotoLevel2(studentPanelD11.lastVisitedRunId);
        };
        return;
      }
      if (lv === 2) {
        prev.disabled = false;
        const canNext = !!(
          studentPanelD11.firstSliceDecisionId &&
          studentPanelD11.selectedRunId &&
          studentPanelD11.sliceCount > 0
        );
        next.disabled = !canNext;
        prev.onclick = function () { void studentPanelD11GotoLevel1(); };
        next.onclick = function () {
          if (canNext)
            void studentPanelD11GotoLevel3(
              studentPanelD11.selectedRunId,
              studentPanelD11.firstSliceDecisionId
            );
        };
        return;
      }
      if (lv === 3) {
        prev.disabled = false;
        next.disabled = true;
        prev.onclick = function () {
          if (studentPanelD11.selectedRunId)
            void studentPanelD11GotoLevel2(studentPanelD11.selectedRunId);
        };
        next.onclick = function () {};
      }
    }

    function studentPanelD11WireChrome() {
      wireStudentPanelD11Nav();
      studentPanelD11WireStep();
    }

    function studentPanelD11CarouselUpdateMeta() {
      const vp = document.getElementById('pgStudentD11CarouselViewport');
      const meta = document.getElementById('pgStudentD11CarMeta');
      const prev = document.getElementById('pgStudentD11CarPrev');
      const next = document.getElementById('pgStudentD11CarNext');
      if (!vp || !meta) return;
      const track = vp.querySelector('.pg-student-d11-strip');
      if (!track) return;
      const slices = track.querySelectorAll('.pg-student-d11-slice[data-didx]');
      const n = slices.length;
      if (!n) {
        meta.textContent = '';
        return;
      }
      const w = slices[0].offsetWidth + 12;
      const idx = Math.min(n - 1, Math.max(0, Math.round(vp.scrollLeft / Math.max(1, w))));
      meta.textContent =
        'Trade ' +
        (idx + 1) +
        ' of ' +
        n +
        ' · trade-grain (trade_id) · scroll or use ◀ ▶';
      slices.forEach(function (el, i) {
        el.classList.toggle('pg-student-d11-slice--focused', i === idx);
      });
      if (prev) prev.disabled = idx <= 0;
      if (next) next.disabled = idx >= n - 1;
    }

    function wireStudentPanelD11Carousel() {
      const vp = document.getElementById('pgStudentD11CarouselViewport');
      const prev = document.getElementById('pgStudentD11CarPrev');
      const next = document.getElementById('pgStudentD11CarNext');
      if (!vp || !prev || !next) return;
      const step = function (dir) {
        const track = vp.querySelector('.pg-student-d11-strip');
        if (!track) return;
        const slices = track.querySelectorAll('.pg-student-d11-slice[data-didx]');
        if (!slices.length) return;
        const w = slices[0].offsetWidth + 12;
        const cur = Math.min(
          slices.length - 1,
          Math.max(0, Math.round(vp.scrollLeft / Math.max(1, w)))
        );
        const nxt = Math.min(slices.length - 1, Math.max(0, cur + dir));
        slices[nxt].scrollIntoView({ behavior: 'smooth', inline: 'start', block: 'nearest' });
        window.setTimeout(studentPanelD11CarouselUpdateMeta, 380);
      };
      prev.onclick = function () { step(-1); };
      next.onclick = function () { step(1); };
      vp.addEventListener('scroll', function () {
        window.requestAnimationFrame(studentPanelD11CarouselUpdateMeta);
      });
      window.setTimeout(function () {
        const first = vp.querySelector('.pg-student-d11-slice');
        if (first) first.scrollIntoView({ inline: 'start', block: 'nearest' });
        studentPanelD11CarouselUpdateMeta();
      }, 80);
    }

    async function studentPanelD11GotoLevel1() {
      studentPanelD11.level = 1;
      studentPanelD11.selectedRunId = null;
      studentPanelD11.selectedDecisionId = null;
      studentPanelD11.sliceCount = 0;
      studentPanelD11.firstSliceDecisionId = null;
      studentPanelD11SetHandoffVisible(true);
      await refreshStudentPanelD11();
    }

    async function studentPanelD11GotoLevel2(runId) {
      studentPanelD11.level = 2;
      studentPanelD11.selectedRunId = runId;
      studentPanelD11.lastVisitedRunId = runId;
      studentPanelD11.selectedDecisionId = null;
      studentPanelD11.firstSliceDecisionId = null;
      studentPanelD11SetHandoffVisible(false);
      const root = studentPanelD11RootEl();
      if (!root) return;
      const loading = studentPanelD11Layout(
        renderStudentPanelD11Chrome(2, ['<strong>Exam list</strong>', 'Loading…'], true, runId),
        '<p class="caps" style="margin:0">Loading run summary and trades…</p>'
      );
      root.innerHTML = loading;
      studentPanelD11WireChrome();
      let j = null;
      try {
        j = await pgStudentPanelJsonGet(
          '/api/student-panel/run/' + encodeURIComponent(runId) + '/decisions'
        );
      } catch (e) {
        root.innerHTML = studentPanelD11Layout(
          renderStudentPanelD11Chrome(2, ['<strong>Exam list</strong>', '<strong>Run</strong> ' + escapeHtml(studentPanelD11ShortRunId(runId))], true, runId),
          '<p class="caps" style="margin:0;color:#a32b2b">Failed to load run: ' + escapeHtml(String(e)) + '</p>'
        );
        studentPanelD11WireChrome();
        return;
      }
      if (!j || !j.ok) {
        root.innerHTML = studentPanelD11Layout(
          renderStudentPanelD11Chrome(2, ['<strong>Exam list</strong>', '<strong>Run</strong> ' + escapeHtml(studentPanelD11ShortRunId(runId))], true, runId),
          '<p class="caps" style="margin:0;color:#a32b2b">' +
            escapeHtml((j && j.error) || 'run payload unavailable') +
            '</p>'
        );
        studentPanelD11WireChrome();
        return;
      }
      const slices = Array.isArray(j.slices) ? j.slices : [];
      studentPanelD11.sliceCount = slices.length;
      studentPanelD11.firstSliceDecisionId =
        slices.length > 0 ? studentPanelD11SliceIdFromSlice(slices[0], 0) : null;
      const ordNote =
        j.note != null
          ? escapeHtml(String(j.note))
          : 'Trade grain: one carousel card per trade_id (graded_unit_id). scenario_id is batch grouping only.';
      const rs = j.run_summary && typeof j.run_summary === 'object' ? j.run_summary : null;
      let scroll = '';
      if (rs) scroll += renderD13RunSummaryBand(rs);
      if (
        rs &&
        (rs.exam_e_score_v1 != null ||
          rs.exam_p_score_v1 != null ||
          rs.exam_pass_v1 != null)
      ) {
        const ee2 = rs.exam_e_score_v1 != null ? fmtD11MaybeNum(rs.exam_e_score_v1, 4) : '—';
        const pe2 = rs.exam_p_score_v1 != null ? fmtD11MaybeNum(rs.exam_p_score_v1, 4) : '—';
        const pass2 = rs.exam_pass_v1 === true ? 'PASS' : rs.exam_pass_v1 === false ? 'FAIL' : '—';
        scroll +=
          '<p class="caps" style="margin:6px 0 0;font-size:0.78rem" title="Run-level exam grades from scorecard (same values as L1)">' +
          '<strong><span title="E/P: exam economic and process scores from one exam-pack grading call">E/P</span> (run)</strong> — ' +
          '<span title="E: exam economic grade">E</span>=' +
          ee2 +
          ' · <span title="P: exam process score 0–1">P</span>=' +
          pe2 +
          ' · <span title="PASS: exam-pack pass bit">PASS</span>=' +
          escapeHtml(pass2) +
          '</p>';
      }
      scroll +=
        '<p class="pg-student-d11-legend" style="margin-top:0"><strong>Trade carousel</strong> — one card per trade opportunity. ' +
        ordNote +
        '</p>';
      if (j.scenario_list_error) {
        scroll +=
          '<p class="caps" style="margin:0 0 8px;font-size:0.75rem;color:#a32b2b">' +
          escapeHtml(String(j.scenario_list_error)) +
          '</p>';
      }
      if (Array.isArray(j.data_gaps) && j.data_gaps.length) {
        scroll +=
          '<p class="caps" style="margin:0 0 8px;font-size:0.72rem;color:#a32b2b">data_gaps: ' +
          escapeHtml(j.data_gaps.join(', ')) +
          '</p>';
      }
      if (!slices.length) {
        studentPanelD11.firstSliceDecisionId = null;
        scroll +=
          '<p class="caps" style="margin:0">No trade carousel slices for this run — <code>replay_outcomes_json</code> was empty (replay closed zero trades on this bar window), or <code>batch_parallel_results_v1.json</code> is missing for this job. If the UI was stuck on “Loading…”, hard-refresh after deploy and check the browser <strong>Network</strong> tab for <code>GET /api/student-panel/run/&lt;job_id&gt;/decisions</code>.</p>';
        root.innerHTML = studentPanelD11Layout(
          renderStudentPanelD11Chrome(
            2,
            ['<strong>Exam list</strong>', '<strong>Run</strong> ' + escapeHtml(studentPanelD11ShortRunId(runId))],
            true,
            runId
          ),
          scroll
        );
        studentPanelD11WireChrome();
        return;
      }
      scroll += '<div class="pg-student-d11-carousel-wrap">';
      scroll += '<p class="pg-student-d11-carousel-meta" id="pgStudentD11CarMeta"></p>';
      scroll += '<div class="pg-student-d11-carousel-row">';
      scroll +=
        '<button type="button" class="pg-student-d11-carousel-btn" id="pgStudentD11CarPrev" aria-label="Previous slice">◀</button>';
      scroll += '<div class="pg-student-d11-carousel-viewport" id="pgStudentD11CarouselViewport">';
      scroll += '<div class="pg-student-d11-strip pg-student-d11-strip--carousel">';
      for (let i = 0; i < slices.length; i++) {
        const s = slices[i] || {};
        const did =
          s.trade_id != null
            ? String(s.trade_id)
            : s.decision_id != null
              ? String(s.decision_id)
              : 'd' + i;
        const res = String(s.result || '—');
        const cls = 'pg-student-d11-slice pg-student-d11-slice--' + res.replace(/[^A-Z_]/g, '_');
        const confRaw = s.student_confidence_01 != null ? s.student_confidence_01 : s.confidence;
        var confDisp;
        if (confRaw !== undefined && confRaw !== null && confRaw !== '') {
          var confNum = Number(confRaw);
          confDisp = Number.isFinite(confNum)
            ? escapeHtml(confNum.toFixed(4))
            : escapeHtml(String(confRaw));
        } else {
          confDisp = '<span style="opacity:0.85">data_gap</span>';
        }
        var aln = s.student_referee_direction_align;
        var alignShort = aln === true ? 'YES' : aln === false ? 'NO' : '—';
        scroll +=
          '<div class="' +
          cls +
          '" role="button" tabindex="0" data-didx="' +
          i +
          '" data-did="' +
          escapeHtml(did) +
          '" data-run="' +
          escapeHtml(runId) +
          '" title="Open Level 3 trade deep dive (L3): decision record, replay subset, and structured data gaps">' +
          '<div class="pg-student-d11-slice-id">' +
          escapeHtml(did) +
          '</div>' +
          '<div class="pg-student-d11-slice-ts caps">' +
          escapeHtml(String(s.timestamp || '—')) +
          '</div>' +
          '<div class="pg-student-d11-slice-outcome">' +
          escapeHtml(res) +
          ' · ' +
          escapeHtml(String(s.direction || '—')) +
          '</div>' +
          '<div class="pg-student-d11-slice-align" title="Store student_output.direction vs replay outcome_json.direction; — = not comparable">' +
          'Student↔Referee dir ' +
          escapeHtml(alignShort) +
          '</div>' +
          '<div class="pg-student-d11-slice-conf" title="conf: Student confidence (0–1) from sealed output; data_gap when missing">' +
          'conf ' +
          confDisp +
          '</div>' +
          '<div class="pg-student-d11-slice-gh" title="PM: promoted memory usage for this trade slice">' +
          'GH ' +
          escapeHtml(String(s.groundhog_usage || '—')) +
          '</div>' +
          '<div class="pg-student-d11-slice-delta">vs baseline: not wired (per-trade export pending)</div>' +
          '</div>';
      }
      scroll += '</div></div>';
      scroll +=
        '<button type="button" class="pg-student-d11-carousel-btn" id="pgStudentD11CarNext" aria-label="Next slice">▶</button>';
      scroll += '</div></div>';
      const chrome = renderStudentPanelD11Chrome(
        2,
        ['<strong>Exam list</strong>', '<strong>Run</strong> ' + escapeHtml(studentPanelD11ShortRunId(runId))],
        true,
        runId
      );
      root.innerHTML = studentPanelD11Layout(chrome, scroll);
      studentPanelD11WireChrome();
      wireStudentPanelD11Carousel();
      const nodes = root.querySelectorAll('.pg-student-d11-slice[data-did]');
      nodes.forEach(function (node) {
        function go() {
          const rid = node.getAttribute('data-run');
          const did = node.getAttribute('data-did');
          if (rid && did) void studentPanelD11GotoLevel3(rid, did);
        }
        node.addEventListener('click', go);
        node.addEventListener('keydown', function (ev) {
          if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            go();
          }
        });
      });
    }

    function renderL3DataGapMatrixHtml(dgMatrix) {
      var arr = Array.isArray(dgMatrix) ? dgMatrix : [];
      if (!arr.length) {
        return (
          '<li><span class="pg-student-d11-k" title="L3: level-3 trade deep dive — structured missing-data matrix">data_gaps[]</span> <em>(empty — GT_DIRECTIVE_017 matrix)</em></li>'
        );
      }
      var parts = [
        '<li style="list-style:none;margin:0 0 6px 0"><span class="pg-student-d11-k" title="L3: level-3 trade deep dive — structured missing-data matrix">data_gaps[]</span> ' +
          '(<span title="GT_DIRECTIVE_017: each row names the producer subsystem, severity, and pipeline stage">GT_DIRECTIVE_017</span> — ' +
          '<span title="Producer: subsystem that should have written this field">producer</span> / ' +
          '<span title="Severity: critical = blocks truth; warning = investigate; info = context">severity</span> / ' +
          '<span title="Expected stage: where in the pipeline this field should have been produced">stage</span>)</li>',
      ];
      for (var gi = 0; gi < arr.length; gi++) {
        var g = arr[gi] || {};
        var sev = String(g.severity || '—');
        var sevColor = sev === 'critical' ? '#f85149' : sev === 'warning' ? '#d29922' : '#8b949e';
        var sevTip =
          sev === 'critical'
            ? 'Critical: missing or inconsistent data blocks operator truth for this slice.'
            : sev === 'warning'
              ? 'Warning: investigate before trusting this part of the record.'
              : 'Info: context or optional field gap.';
        var prodTip = 'Producer: subsystem responsible for this field (' + String(g.producer || '—') + ').';
        parts.push(
          '<li style="list-style:none;margin:4px 0;padding:0"><div style="margin:0;padding:6px 8px;background:#161b22;border-radius:6px;border:1px solid #30363d;font-size:0.72rem;line-height:1.35">' +
            '<div><strong style="color:' +
            sevColor +
            '" title="' +
            escapeHtml(sevTip) +
            '">' +
            escapeHtml(sev) +
            '</strong> · <span style="color:#58a6ff" title="' +
            escapeHtml(prodTip) +
            '">' +
            escapeHtml(String(g.producer || '—')) +
            '</span> · <code title="Field name in the API or scorecard this gap refers to">' +
            escapeHtml(String(g.field_name || '—')) +
            '</code></div>' +
            '<div style="margin-top:3px;opacity:0.92"><span title="Stable machine reason code for this gap">reason</span> <code>' +
            escapeHtml(String(g.reason || '—')) +
            '</code> · <span title="Pipeline stage where the field should exist">expected_stage</span> ' +
            escapeHtml(String(g.expected_stage || '—')) +
            '</div></div></li>'
        );
      }
      return parts.join('');
    }

    async function studentPanelD11GotoLevel3(runId, tradeId) {
      studentPanelD11.level = 3;
      studentPanelD11.selectedRunId = runId;
      studentPanelD11.selectedDecisionId = tradeId;
      studentPanelD11SetHandoffVisible(false);
      const root = studentPanelD11RootEl();
      if (!root) return;
      const tidDisp = tradeId.length > 22 ? tradeId.slice(0, 20) + '…' : tradeId;
      root.innerHTML = studentPanelD11Layout(
        renderStudentPanelD11Chrome(
          3,
          [
            '<strong>Exam list</strong>',
            '<strong>Run</strong> ' + escapeHtml(studentPanelD11ShortRunId(runId)),
            '<strong>Trade</strong> ' + escapeHtml(tidDisp),
          ],
          true,
          runId
        ),
        '<p class="caps" style="margin:0">Loading L3 (<code>student_panel_l3_response_v1</code>)…</p>'
      );
      studentPanelD11WireChrome();
      let l3 = null;
      try {
        const u =
          '/api/student-panel/run/' +
          encodeURIComponent(runId) +
          '/l3?trade_id=' +
          encodeURIComponent(tradeId);
        l3 = await pgStudentPanelJsonGet(u);
      } catch (e) {
        root.innerHTML = studentPanelD11Layout(
          renderStudentPanelD11Chrome(
            3,
            [
              '<strong>Exam list</strong>',
              '<strong>Run</strong> ' + escapeHtml(studentPanelD11ShortRunId(runId)),
              '<strong>Trade</strong> ' + escapeHtml(tidDisp),
            ],
            true,
            runId
          ),
          '<p class="caps" style="margin:0;color:#a32b2b">Load failed: ' + escapeHtml(String(e)) + '</p>'
        );
        studentPanelD11WireChrome();
        return;
      }
      if (!l3 || l3.decision_record_v1 == null) {
        root.innerHTML = studentPanelD11Layout(
          renderStudentPanelD11Chrome(
            3,
            [
              '<strong>Exam list</strong>',
              '<strong>Run</strong> ' + escapeHtml(studentPanelD11ShortRunId(runId)),
              '<strong>Trade</strong> ' + escapeHtml(tidDisp),
            ],
            true,
            runId
          ),
          '<p class="caps" style="margin:0;color:#a32b2b">' +
            escapeHtml((l3 && l3.error) || 'record unavailable') +
            '</p>'
        );
        studentPanelD11WireChrome();
        return;
      }
      const rec = l3.decision_record_v1;
      const sd = rec.student_decision || {};
      const ctx = rec.context || {};
      const gh = rec.groundhog || {};
      const bc = rec.baseline_comparison || {};
      const rt = rec.referee_truth || {};
      const sr = rec.structured_reasoning_v1 || {};
      const lines = [];
      lines.push('<div class="pg-student-d11-deep">');
      lines.push(
        '<p class="pg-student-d11-legend" style="margin-top:0"><strong>Trade deep dive</strong> — ' +
          'schema <code>' +
          escapeHtml(String(rec.schema || 'student_decision_record_v1')) +
          '</code>. Student fields from Student store when present; Referee from OutcomeRecord; missing fields stay <span style="opacity:0.85">data_gap</span>.</p>'
      );
      lines.push('<ul>');
      const flat = rec.schema === 'student_decision_record_v1' && rec.student_direction !== undefined;
      const sDir = flat ? rec.student_direction : sd.student_direction;
      const sConf = flat ? rec.student_confidence_01 : sd.student_confidence_01;
      const sAct = flat ? rec.student_action : sd.student_action;
      const tsU = flat ? rec.timestamp_utc : rec.timestamp;
      lines.push(
        '<li><span class="pg-student-d11-k">trade_id / run_id / scenario_id</span> ' +
          escapeHtml(String(rec.trade_id || '—')) +
          ' · ' +
          escapeHtml(String(rec.run_id || '—')) +
          ' · ' +
          escapeHtml(String(rec.scenario_id || '—')) +
          '</li>'
      );
      lines.push(
        '<li><span class="pg-student-d11-k">timestamp_utc · symbol · timeframe</span> ' +
          escapeHtml(String(tsU != null ? tsU : '—')) +
          ' · ' +
          escapeHtml(String(rec.symbol != null ? rec.symbol : '—')) +
          ' · ' +
          escapeHtml(String(rec.timeframe != null ? rec.timeframe : '—')) +
          '</li>'
      );
      lines.push(
        '<li><span class="pg-student-d11-k">student_action · direction · confidence_01</span> ' +
          escapeHtml(String(sAct != null ? sAct : '—')) +
          ' · ' +
          escapeHtml(String(sDir != null ? sDir : '—')) +
          ' · ' +
          escapeHtml(String(sConf != null ? sConf : '—')) +
          '</li>'
      );
      lines.push(
        '<li><span class="pg-student-d11-k" title="OHLC: open/high/low/close. EMA/RSI/ATR: indicators. vol: volume. regimes: trend and volatility labels.">OHLC · ema_fast/slow · rsi_14 · atr_14 · vol · regimes</span> ' +
          (flat
            ? 'O ' +
              fmtD11MaybeNum(rec.price_open, 4) +
              ' H ' +
              fmtD11MaybeNum(rec.price_high, 4) +
              ' L ' +
              fmtD11MaybeNum(rec.price_low, 4) +
              ' C ' +
              fmtD11MaybeNum(rec.price_close, 4) +
              ' · ema ' +
              escapeHtml(String(rec.ema_fast != null ? rec.ema_fast : '—')) +
              '/' +
              escapeHtml(String(rec.ema_slow != null ? rec.ema_slow : '—')) +
              ' · rsi ' +
              escapeHtml(String(rec.rsi_14 != null ? rec.rsi_14 : '—')) +
              ' · atr ' +
              escapeHtml(String(rec.atr_14 != null ? rec.atr_14 : '—')) +
              ' · vol ' +
              escapeHtml(String(rec.volume != null ? rec.volume : '—')) +
              ' · trend ' +
              escapeHtml(String(rec.trend_state != null ? rec.trend_state : '—')) +
              ' · ' +
              escapeHtml(String(rec.volatility_regime != null ? rec.volatility_regime : '—')) +
              ' · ' +
              escapeHtml(String(rec.structure_state != null ? rec.structure_state : '—'))
            : 'OHLC ' +
              escapeHtml(String(ctx.ohlc != null ? ctx.ohlc : '—')) +
              ' · EMA ' +
              escapeHtml(String(ctx.ema != null ? ctx.ema : '—')) +
              ' · RSI ' +
              escapeHtml(String(ctx.rsi != null ? ctx.rsi : '—')) +
              ' · ATR ' +
              escapeHtml(String(ctx.atr != null ? ctx.atr : '—')) +
              ' · vol ' +
              escapeHtml(String(ctx.volume != null ? ctx.volume : '—')) +
              ' · trend ' +
              escapeHtml(String(ctx.trend_state != null ? ctx.trend_state : '—')) +
              ' · volReg ' +
              escapeHtml(String(ctx.volatility_regime != null ? ctx.volatility_regime : '—')) +
              ' · struct ' +
              escapeHtml(String(ctx.structure_state != null ? ctx.structure_state : '—'))) +
          '</li>'
      );
      lines.push(
        '<li><span class="pg-student-d11-k">promoted memory</span> used ' +
          escapeHtml(String((flat ? rec.groundhog_used_flag : gh.used) != null ? String(flat ? rec.groundhog_used_flag : gh.used) : '—')) +
          ' · ctx ' +
          escapeHtml(String((flat ? rec.context_used_flag : gh.context_used_flag) != null ? String(flat ? rec.context_used_flag : gh.context_used_flag) : '—')) +
          ' · mem ' +
          escapeHtml(String((flat ? rec.memory_used_flag : gh.memory_used_flag) != null ? String(flat ? rec.memory_used_flag : gh.memory_used_flag) : '—')) +
          ' · retrieval_count ' +
          escapeHtml(String((flat ? rec.retrieval_count : gh.retrieval_count) != null ? String(flat ? rec.retrieval_count : gh.retrieval_count) : '—')) +
          ' · sig_key ' +
          escapeHtml(String(flat ? (rec.retrieval_signature_key != null ? rec.retrieval_signature_key : '—') : '—')) +
          ' · ' +
          escapeHtml(String((flat ? rec.influence_summary : gh.influence_summary) != null ? String(flat ? rec.influence_summary : gh.influence_summary) : '—')) +
          '</li>'
      );
      lines.push(
        '<li><span class="pg-student-d11-k">baseline</span> action ' +
          escapeHtml(String(flat ? (rec.baseline_action != null ? rec.baseline_action : '—') : '—')) +
          ' · dir ' +
          escapeHtml(String((flat ? rec.baseline_direction : bc.baseline_direction) != null ? String(flat ? rec.baseline_direction : bc.baseline_direction) : '—')) +
          ' · conf ' +
          escapeHtml(String((flat ? rec.baseline_confidence_01 : bc.baseline_confidence) != null ? String(flat ? rec.baseline_confidence_01 : bc.baseline_confidence) : '—')) +
          ' · decision_changed ' +
          escapeHtml(String((flat ? rec.decision_changed_flag : bc.decision_changed_flag) != null ? String(flat ? rec.decision_changed_flag : bc.decision_changed_flag) : '—')) +
          '</li>'
      );
      lines.push(
        '<li><span class="pg-student-d11-k">pattern / rules</span> sel ' +
          escapeHtml(String(flat ? (rec.pattern_selected != null ? rec.pattern_selected : '—') : '—')) +
          ' · eval ' +
          escapeHtml(String(flat ? (rec.patterns_evaluated != null ? rec.patterns_evaluated : '—') : '—')) +
          ' · summary ' +
          escapeHtml(String(flat ? (rec.pattern_pass_fail_summary != null ? rec.pattern_pass_fail_summary : '—') : '—')) +
          '</li>'
      );
      lines.push(
        '<li><span class="pg-student-d11-k">structured_reasoning_v1</span> ' +
          escapeHtml(JSON.stringify(sr && typeof sr === 'object' ? sr : {})) +
          '</li>'
      );
      lines.push(
        '<li><span class="pg-student-d11-k">referee truth</span> actual_trade ' +
          escapeHtml(String(flat ? (rec.referee_actual_trade != null ? rec.referee_actual_trade : '—') : '—')) +
          ' · direction ' +
          escapeHtml(String((flat ? rec.referee_direction : rt.referee_direction) != null ? String(flat ? rec.referee_direction : rt.referee_direction) : '—')) +
          ' · outcome ' +
          escapeHtml(String((flat ? rec.referee_outcome : rt.outcome) != null ? String(flat ? rec.referee_outcome : rt.outcome) : '—')) +
          ' · pnl ' +
          fmtD11MaybeNum(flat ? rec.referee_pnl : rt.pnl, 4) +
          ' · is_win/is_loss ' +
          escapeHtml(String(flat ? rec.is_win : '')) +
          '/' +
          escapeHtml(String(flat ? rec.is_loss : '')) +
          '</li>'
      );
      const scl = l3.scorecard_line_v1;
      if (scl && typeof scl === 'object') {
        const hasEp =
          scl.exam_e_score_v1 != null ||
          scl.exam_p_score_v1 != null ||
          scl.exam_pass_v1 != null ||
          (scl.l1_e_value_source_v1 != null && String(scl.l1_e_value_source_v1).trim()) ||
          (scl.l1_p_value_source_v1 != null && String(scl.l1_p_value_source_v1).trim());
        if (hasEp) {
          const ee = scl.exam_e_score_v1 != null ? fmtD11MaybeNum(scl.exam_e_score_v1, 4) : '—';
          const pe = scl.exam_p_score_v1 != null ? fmtD11MaybeNum(scl.exam_p_score_v1, 4) : '—';
          const pv =
            scl.exam_pass_v1 === true ? 'PASS' : scl.exam_pass_v1 === false ? 'FAIL' : '—';
          lines.push(
            '<li><span class="pg-student-d11-k" title="Scorecard line subset for this job (L3 payload)">Exam E/P (scorecard)</span> ' +
              '<span title="E: exam economic grade from exam-pack grading (not batch expectancy)">E</span>=' +
              ee +
              ' · <span title="P: exam process score 0–1 from grading">P</span>=' +
              pe +
              ' · <span title="PASS/FAIL from exam-pack grading pass bit">PASS</span>=' +
              escapeHtml(pv) +
              ' · <span title="Which value feeds L1 for E on this line">E src</span>=' +
              escapeHtml(String(scl.l1_e_value_source_v1 != null ? scl.l1_e_value_source_v1 : '—')) +
              ' · <span title="Which value feeds L1 for P on this line">P src</span>=' +
              escapeHtml(String(scl.l1_p_value_source_v1 != null ? scl.l1_p_value_source_v1 : '—')) +
              '</li>'
          );
        }
      }
      lines.push(renderL3DataGapMatrixHtml(l3.data_gaps));
      if (rec.error) {
        lines.push('<li><span class="pg-student-d11-k">error</span> ' + escapeHtml(String(rec.error)) + '</li>');
      }
      lines.push('</ul></div>');
      const inner = lines.join('');
      root.innerHTML = studentPanelD11Layout(
        renderStudentPanelD11Chrome(
          3,
          [
            '<strong>Exam list</strong>',
            '<strong>Run</strong> ' + escapeHtml(studentPanelD11ShortRunId(runId)),
            '<strong>Trade</strong> ' + escapeHtml(tidDisp),
          ],
          true,
          runId
        ),
        inner
      );
      studentPanelD11WireChrome();
    }

    function l1RoadRowMeta(rid, ov) {
      const m = (ov && ov.road_by_job_id_v1) || {};
      return m[rid] || null;
    }

    /** Full API legend line for a road band code (hover on Road cells / headers). */
    function l1RoadBandLegendTitle(legend, bandRaw) {
      if (!legend || bandRaw == null || bandRaw === '') return '';
      const b = String(bandRaw).trim().toLowerCase().replace(/\s+/g, '_');
      if (b === 'a') return typeof legend.band_a === 'string' ? legend.band_a : '';
      if (b === 'b') return typeof legend.band_b === 'string' ? legend.band_b : '';
      if (b === 'baseline_ruler') return typeof legend.band_baseline_ruler === 'string' ? legend.band_baseline_ruler : '';
      if (b === 'data_gap') return 'Road merge reported data_gap for this job (see Road gaps column).';
      return '';
    }

    /** API brain_profiles blurb for hover on profile symbology. */
    function l1BrainProfileLegendTitle(legend, profileId) {
      if (!legend || profileId == null) return '';
      const bp = legend.brain_profiles;
      if (!bp || typeof bp !== 'object') return '';
      const s = bp[String(profileId).trim()];
      return typeof s === 'string' ? s : '';
    }

    function renderL1RoadGroupsPreviewFromApi(ov) {
      const groups = (ov && ov.groups) || [];
      if (!Array.isArray(groups) || !groups.length) return '';
      const legend = (ov && ov.legend) || {};
      let h =
        '<div class="pg-student-l1-groups-preview"><p class="caps" style="margin:10px 0 4px;font-size:0.75rem">' +
        '<strong title="E/P: same exam-pack scalars used for Road band A/B (GT_DIRECTIVE_020)">L1 road — by fingerprint</strong> ' +
        '(compare baseline vs memory vs LLM within the same config hash — hover column headers and cells for definitions from <code>l1_road_v1.legend</code>)</p>';
      h += '<table class="pg-student-d11-table"><thead><tr>';
      const tipFp =
        typeof legend.fingerprint === 'string' && legend.fingerprint
          ? legend.fingerprint
          : 'Fingerprint: 40-char same recipe/window hash';
      const tipE =
        typeof legend.avg_e_expectancy_per_trade === 'string' && legend.avg_e_expectancy_per_trade
          ? legend.avg_e_expectancy_per_trade
          : 'E: group mean economic scalar per line (exam E when present, else batch proxy — same as band logic)';
      const tipP =
        typeof legend.avg_p_process_score === 'string' && legend.avg_p_process_score
          ? legend.avg_p_process_score
          : 'P: group mean process per line (exam P when present, else proxy)';
      const tipExamE =
        typeof legend.group_avg_exam_e_score_v1 === 'string' && legend.group_avg_exam_e_score_v1
          ? legend.group_avg_exam_e_score_v1
          : 'Mean of exam_e_score_v1 on graded lines only';
      const tipExamP =
        typeof legend.group_avg_exam_p_score_v1 === 'string' && legend.group_avg_exam_p_score_v1
          ? legend.group_avg_exam_p_score_v1
          : 'Mean of exam_p_score_v1 on graded lines only';
      const tipLlm =
        typeof legend.llm_model === 'string' && legend.llm_model
          ? legend.llm_model
          : 'LLM: model tag when profile is memory_context_llm_student';
      h +=
        '<th title="' + escapeHtml(tipFp) + '">fp</th>' +
        '<th title="Brain profile — hover each cell for the API legend blurb">profile</th>' +
        '<th title="' + escapeHtml(tipLlm) + '">LLM</th>' +
        '<th title="Number of runs in this bucket">n</th>' +
        '<th title="' + escapeHtml(tipE) + '">avg E</th>' +
        '<th title="' + escapeHtml(tipP) + '">avg P</th>' +
        '<th title="' + escapeHtml(tipExamE) + '">avg exam E</th>' +
        '<th title="' + escapeHtml(tipExamP) + '">avg exam P</th>' +
        '<th title="Road band — hover cell for full Band A / B / baseline_ruler text from API">band</th>' +
        '</tr></thead><tbody>';
      for (let gi = 0; gi < groups.length; gi++) {
        const g = groups[gi] || {};
        const gk = g.group_key || {};
        const fp = String(gk.fingerprint_sha256_40 || '');
        const fpDisp = fp.length > 10 ? fp.slice(0, 8) + '…' : fp;
        const prof = String(gk.student_brain_profile_v1 || '');
        const profTip = l1BrainProfileLegendTitle(legend, prof) || 'student_brain_profile_v1';
        const bandVal = g.band != null ? String(g.band) : '';
        const bandTip = l1RoadBandLegendTitle(legend, bandVal) || bandVal || 'Road band for this group';
        h += '<tr>';
        h += '<td title="' + escapeHtml(fp) + '">' + escapeHtml(fpDisp) + '</td>';
        h += '<td title="' + escapeHtml(profTip) + '">' + escapeHtml(prof || '—') + '</td>';
        h +=
          '<td title="' +
          escapeHtml(
            gk.llm_model != null && String(gk.llm_model).trim()
              ? tipLlm + ' — tag: ' + String(gk.llm_model)
              : tipLlm
          ) +
          '">' +
          escapeHtml(String(gk.llm_model != null ? gk.llm_model : '—')) +
          '</td>';
        h += '<td>' + escapeHtml(String(g.run_count != null ? g.run_count : '—')) + '</td>';
        h +=
          '<td title="' +
          escapeHtml(tipE) +
          '">' +
          (g.avg_e_expectancy_per_trade != null
            ? fmtD11MaybeNum(g.avg_e_expectancy_per_trade, 4)
            : '—') +
          '</td>';
        h +=
          '<td title="' +
          escapeHtml(tipP) +
          '">' +
          (g.avg_p_process_score != null ? fmtD11MaybeNum(g.avg_p_process_score, 4) : '—') +
          '</td>';
        h +=
          '<td title="' +
          escapeHtml(tipExamE) +
          '">' +
          (g.group_avg_exam_e_score_v1 != null ? fmtD11MaybeNum(g.group_avg_exam_e_score_v1, 4) : '—') +
          '</td>';
        h +=
          '<td title="' +
          escapeHtml(tipExamP) +
          '">' +
          (g.group_avg_exam_p_score_v1 != null ? fmtD11MaybeNum(g.group_avg_exam_p_score_v1, 4) : '—') +
          '</td>';
        h += '<td title="' + escapeHtml(bandTip) + '">' + escapeHtml(bandVal || '—') + '</td>';
        h += '</tr>';
      }
      h += '</tbody></table></div>';
      return h;
    }

    async function refreshStudentPanelD11(opts) {
      const o = opts && typeof opts === 'object' ? opts : {};
      const softRefresh = o.soft === true;
      const root = studentPanelD11RootEl();
      if (!root) return;
      if (studentPanelD11.level !== 1) return;
      const chrome1 = renderStudentPanelD11Chrome(
        1,
        ['<strong>Exam list</strong>'],
        false,
        studentPanelD11.lastVisitedRunId || ''
      );
      let prevScrollTop = 0;
      let prevScrollLeft = 0;
      if (softRefresh) {
        const wrapPrev = root.querySelector('.pg-student-d11-table-wrap');
        if (wrapPrev) {
          prevScrollTop = wrapPrev.scrollTop;
          prevScrollLeft = wrapPrev.scrollLeft;
        }
      }
      if (!softRefresh) {
        root.innerHTML = studentPanelD11Layout(
          chrome1,
          '<p class="caps" style="margin:0">Loading runs…</p>'
        );
      }
      let j = null;
      try {
        j = await pgStudentPanelJsonGet('/api/student-panel/runs?limit=50');
      } catch (e) {
        root.innerHTML = studentPanelD11Layout(
          chrome1,
          '<p class="caps" style="margin:0;color:#a32b2b">Failed to load runs: ' + escapeHtml(String(e)) + '</p>'
        );
        studentPanelD11WireChrome();
        return;
      }
      if (!j || !j.ok || !Array.isArray(j.runs)) {
        root.innerHTML = studentPanelD11Layout(
          chrome1,
          '<p class="caps" style="margin:0;color:#a32b2b">Run list unavailable.</p>'
        );
        studentPanelD11WireChrome();
        return;
      }
      const rows = j.runs;
      const ov = j.l1_road_v1 || {};
      const leg = ov.legend || {};
      const roadBandTitle =
        (leg.band_a ? String(leg.band_a).slice(0, 220) : '') +
        (leg.band_b ? ' | ' + String(leg.band_b).slice(0, 160) : '');
      let scroll =
        '<p class="pg-student-d11-legend" style="margin-top:0"><strong title="Level 1 (L1): list of exam runs from the scorecard">Level 1 — exam list</strong> — Each row is one exam attempt (<code title="API schema name for one run row">student_panel_run_row_v2</code> + <code title="D14 aggregate block on the same response">d14_run_row_v1</code>). Referee rollups and harness signals. Click a row (not ×) for Level 2. <strong title="Remove this scorecard line only">×</strong> removes this scorecard line only. <strong title="Sys BL: system baseline trade win percent — oldest same-fingerprint anchor">Sys BL %</strong> = system baseline trade win % (oldest same-fingerprint anchor). <strong title="Run TW: this run trade win percent from the Referee batch">Run TW %</strong> = this exam&rsquo;s trade win %. <strong title="Greater than baseline: strict beat vs Sys BL; not on anchor row">&gt;BL</strong> = strict beat vs Sys BL (not on anchor). <strong title="L1 road: fingerprint-group band vs baseline">Road</strong> / <strong title="Anchor: baseline ruler vs compare row role">Anchor</strong> / <strong title="Road gaps: merge-time data gap codes">Road gaps</strong> come from <code title="Embedded L1 road payload on this API response">l1_road_v1</code> on this response (same aggregation as <code>GET /api/student-panel/l1-road</code>). Full <code>l1_road_v1.legend</code> copy is in native browser tooltips (<code>title</code>) on column headers and on Profile / LLM / Road cells and the fingerprint table — not a separate on-page legend block. <a href="/docs/student-panel-dictionary" onclick="return pgOpenStudentPanelDictionaryPopout();" title="Glossary in a resizable pop-out">Dictionary</a> · <a href="/api/student-panel/l1-road" target="_blank" rel="noopener noreferrer">L1 road JSON</a></p>' +
        '<div class="pg-student-d11-table-wrap"><table class="pg-student-d11-table"><thead><tr>' +
        '<th title="Run id: unique parallel batch job identifier">run_id</th>' +
        '<th title="UTC timestamp for this scorecard row">time</th>' +
        '<th title="Pattern: operator recipe or policy label">pattern</th>' +
        '<th title="Window: evaluation calendar span (e.g. months of data)">window</th>' +
        '<th title="#tr: trade count for this run, or progress numerator/denominator while running">#tr</th>' +
        '<th title="Sys BL %: system baseline — batch trade win percent of the oldest completed run in this fingerprint chain (same recipe and window anchor)">Sys BL %</th>' +
        '<th title="Run TW %: this run’s Referee batch rollup trade win percent (wins divided by trades with a result)">Run TW %</th>' +
        '<th title="&gt;BL: strictly beat system baseline trade win percent? Not shown on the anchor row. YES / NO / = / —">&gt;BL</th>' +
        '<th title="Batch expectancy_per_trade (Referee rollup). When exam grading exists, L1 uses exam E — see E (exam) column.">E/tr</th>' +
        '<th title="exam_e_score_v1 — exam-pack economic grade (same scalar as L1 band logic when present)"><span title="E: exam economic grade from exam-pack grading">E</span> (exam)</th>' +
        '<th title="exam_p_score_v1 — exam-pack process score 0–1"><span title="P: exam process score from exam-pack grading">P</span> (exam)</th>' +
        '<th title="exam_pass_v1 — PASS or FAIL from exam grading when present"><span title="PASS: exam-pack pass bit">PASS</span></th>' +
        '<th title="l1_e_value_source_v1 — which scalar feeds L1 for E (exam vs proxy)"><span title="E value source for L1">E src</span></th>' +
        '<th title="l1_p_value_source_v1 — which scalar feeds L1 for P"><span title="P value source for L1">P src</span></th>' +
        '<th title="' +
        escapeHtml(
          'Profile: student_brain_profile_v1 from L1 road merge — row cells include l1_road_v1.legend.brain_profiles text'
        ) +
        '">Profile</th>' +
        '<th title="' +
        escapeHtml(
          (typeof leg.llm_model === 'string' && leg.llm_model
            ? leg.llm_model + ' '
            : '') + 'LLM model tag when profile is memory_context_llm_student'
        ) +
        '">LLM</th>' +
        '<th title="' +
        escapeHtml(roadBandTitle || 'Road band vs same-fingerprint baseline (A / B / baseline_ruler / data_gap)') +
        '">Road</th>' +
        '<th title="' +
        escapeHtml(String(leg.band_baseline_ruler || 'Baseline anchor role vs compare')) +
        '">Anchor</th>' +
        '<th title="Road gaps: L1 road merge group_data_gaps; includes process_score_compare:data_gap when process (P) cannot be compared">Road gaps</th>' +
        '<th title="HB: harness behavior changed — YES if memory impact, recall, or signal bias changed replay path">HB</th>' +
        '<th title="SH: student handoff — YES if learning rows were appended or retrieval matched this run">SH</th>' +
        '<th title="outΔ: outcome improved — YES/NO if L1 economic scalar (exam E or batch expectancy) vs prior same-fingerprint run">outΔ</th>' +
        '<th title="PM: memory / recall tier for attribution">PM</th>' +
        '<th class="pg-student-d11-sticky-actions" title="Remove run from scorecard only (D14)">×</th>' +
        '</tr></thead><tbody>';
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i] || {};
        const rid = row.run_id != null ? String(row.run_id) : '';
        const infl = row.is_inflight === true || row.status === 'running';
        const trCls = infl ? ' data-run-inflight="1" style="opacity:0.92"' : '';
        const rv = infl ? null : l1RoadRowMeta(rid, ov);
        const bandForAttr = rv && rv.band ? String(rv.band) : '';
        const bandAttr =
          !infl && bandForAttr && bandForAttr !== 'data_gap'
            ? ' data-l1-band="' + escapeHtml(bandForAttr) + '"'
            : '';
        scroll += '<tr' + bandAttr + trCls + (infl ? '' : ' data-run-row') + ' data-run-id="' + escapeHtml(rid) + '">';
        scroll += '<td title="' + escapeHtml(rid) + '"><code style="font-size:0.7rem">' + escapeHtml(rid.length > 14 ? rid.slice(0, 12) + '…' : rid) + '</code></td>';
        scroll += '<td>' + escapeHtml(String(row.timestamp || '—')) + '</td>';
        scroll += '<td>' + escapeHtml(String(row.pattern || '—')) + '</td>';
        scroll += '<td>' + escapeHtml(String(row.evaluation_window || '—')) + '</td>';
        scroll +=
          '<td>' +
          (row.run_progress
            ? escapeHtml(String(row.run_progress))
            : escapeHtml(row.total_trades != null ? String(row.total_trades) : '—')) +
          '</td>';
        const sysBl = row.harness_baseline_trade_win_percent;
        const runTw =
          row.run_trade_win_percent != null ? row.run_trade_win_percent : row.win_rate_percent;
        scroll += '<td>' + (sysBl != null ? fmtD11MaybeNum(sysBl, 1) : '—') + '</td>';
        scroll += '<td>' + (runTw != null ? fmtD11MaybeNum(runTw, 1) : '—') + '</td>';
        scroll +=
          '<td>' +
          escapeHtml(
            row.beats_system_baseline_trade_win != null ? String(row.beats_system_baseline_trade_win) : '—'
          ) +
          '</td>';
        scroll +=
          '<td title="Shown value is batch expectancy_per_trade; L1 uses exam E when present (see E exam column)">' +
          (row.expectancy_per_trade != null ? fmtD11MaybeNum(row.expectancy_per_trade, 4) : '—') +
          '</td>';
        scroll +=
          '<td title="exam_e_score_v1 — exam economic grade (GT_DIRECTIVE_019/020)">' +
          (infl ? '—' : row.exam_e_score_v1 != null ? fmtD11MaybeNum(row.exam_e_score_v1, 4) : '—') +
          '</td>';
        scroll +=
          '<td title="exam_p_score_v1 — exam process score">' +
          (infl ? '—' : row.exam_p_score_v1 != null ? fmtD11MaybeNum(row.exam_p_score_v1, 4) : '—') +
          '</td>';
        var passDisp =
          infl ? '—' : row.exam_pass_v1 === true ? 'PASS' : row.exam_pass_v1 === false ? 'FAIL' : '—';
        scroll += '<td title="exam_pass_v1">' + escapeHtml(passDisp) + '</td>';
        scroll +=
          '<td title="l1_e_value_source_v1">' +
          escapeHtml(
            infl || row.l1_e_value_source_v1 == null ? '—' : String(row.l1_e_value_source_v1)
          ) +
          '</td>';
        scroll +=
          '<td title="l1_p_value_source_v1">' +
          escapeHtml(
            infl || row.l1_p_value_source_v1 == null ? '—' : String(row.l1_p_value_source_v1)
          ) +
          '</td>';
        const prof0 = rv ? String(rv.student_brain_profile_v1 || '') : '';
        const profBlurb = prof0 ? l1BrainProfileLegendTitle(leg, prof0) : '';
        const profHover =
          (rv ? 'L1 road merge — ' : '') +
          (profBlurb || (rv ? 'student_brain_profile_v1 from scorecard merge' : ''));
        scroll +=
          '<td title="' +
          escapeHtml(profHover) +
          '">' +
          (rv ? escapeHtml(String(rv.student_brain_profile_v1 || '—')) : '—') +
          '</td>';
        const lm = rv && rv.llm_model != null ? String(rv.llm_model).trim() : '';
        const llmLegend = typeof leg.llm_model === 'string' ? leg.llm_model : '';
        const llmHover = (
          rv && lm ? llmLegend + (llmLegend ? ' — ' : '') + 'Model tag: ' + lm : llmLegend || 'L1 road merge'
        ).trim();
        scroll +=
          '<td title="' +
          escapeHtml(llmHover || 'LLM model when profile uses Ollama') +
          '">' +
          (rv && rv.llm_model ? escapeHtml(String(rv.llm_model)) : '—') +
          '</td>';
        const band0 = rv ? String(rv.band || '') : '';
        const bandLeg = l1RoadBandLegendTitle(leg, band0);
        const roadHover = (
          (rv ? 'L1 road band vs fingerprint baseline. ' : '') + (bandLeg || (band0 ? 'Code: ' + band0 : ''))
        ).trim();
        scroll +=
          '<td title="' +
          escapeHtml(roadHover) +
          '">' +
          (rv ? escapeHtml(String(rv.band || '—')) : '—') +
          '</td>';
        let anchorCell = '—';
        let anchorTitle = '';
        if (rv) {
          const role = rv.row_anchor_role_v1;
          if (role === 'ruler') {
            anchorCell = 'Ruler';
            anchorTitle = String(leg.band_baseline_ruler || '');
          } else if (role === 'baseline_anchor') {
            anchorCell = 'Anchor';
            anchorTitle = rv.anchor_job_id ? 'job_id ' + String(rv.anchor_job_id) : '';
          } else {
            anchorCell = 'vs anchor';
            anchorTitle = rv.anchor_job_id ? 'Baseline anchor job_id: ' + String(rv.anchor_job_id) : '';
          }
        }
        scroll +=
          '<td title="' +
          escapeHtml(anchorTitle) +
          '">' +
          escapeHtml(anchorCell) +
          '</td>';
        const gapParts = [];
        if (rv && rv.group_data_gaps && rv.group_data_gaps.length) gapParts.push(rv.group_data_gaps.join(', '));
        if (rv && rv.process_leg === 'data_gap') gapParts.push('process_score_compare:data_gap');
        scroll +=
          '<td title="Road merge data gaps">' +
          escapeHtml(gapParts.length ? gapParts.join(' · ') : '—') +
          '</td>';
        const hbCol = row.harness_behavior_changed != null ? row.harness_behavior_changed : row.behavior_changed;
        const shCol = row.student_handoff_active != null ? row.student_handoff_active : '—';
        scroll +=
          '<td title="Harness behavior changed: memory bundle, recall, or signal bias altered replay vs cold path">' +
          escapeHtml(String(hbCol != null ? hbCol : '—')) +
          '</td>';
        scroll +=
          '<td title="Student handoff: learning store rows appended or retrieval matched during this run">' +
          escapeHtml(String(shCol)) +
          '</td>';
        scroll +=
          '<td title="Outcome improved: L1 economic scalar vs previous completed run in same fingerprint">' +
          escapeHtml(String(row.outcome_improved || '—')) +
          '</td>';
        scroll +=
          '<td title="Promoted memory / harness tier for this run">' +
          escapeHtml(String(row.groundhog_state || '—')) +
          '</td>';
        scroll +=
          '<td class="pg-student-d11-sticky-actions">' +
          (infl
            ? '<button type="button" class="pg-student-d11-row-del" disabled title="Cannot delete until this exam completes">×</button>'
            : '<button type="button" class="pg-student-d11-row-del" data-run-id="' +
              escapeHtml(rid) +
              '" title="Remove run from scorecard only (promoted bundle file unchanged)">×</button>') +
          '</td>';
        scroll += '</tr>';
      }
      scroll += '</tbody></table></div>';
      scroll += renderL1RoadGroupsPreviewFromApi(ov);
      if (!rows.length) {
        scroll =
          '<p class="caps" style="margin:0">No exams in scorecard yet — click <strong>Run exam</strong> in Controls.</p>' +
          renderL1RoadGroupsPreviewFromApi(ov);
      }
      root.innerHTML = studentPanelD11Layout(chrome1, scroll);
      studentPanelD11WireChrome();
      if (softRefresh && (prevScrollTop > 0 || prevScrollLeft > 0)) {
        requestAnimationFrame(function () {
          const wrapNext = root.querySelector('.pg-student-d11-table-wrap');
          if (wrapNext) {
            wrapNext.scrollTop = prevScrollTop;
            wrapNext.scrollLeft = prevScrollLeft;
          }
        });
      }
      const trs = root.querySelectorAll('tr[data-run-row]');
      trs.forEach(function (tr) {
        tr.addEventListener('click', function (ev) {
          if (ev && ev.target && ev.target.closest && ev.target.closest('.pg-student-d11-row-del')) return;
          const id = tr.getAttribute('data-run-id');
          if (id) {
            studentPanelD11.lastVisitedRunId = id;
            void studentPanelD11GotoLevel2(id);
          }
        });
      });
      root.querySelectorAll('.pg-student-d11-row-del').forEach(function (btn) {
        btn.addEventListener('click', function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          if (btn.disabled) return;
          const rid = btn.getAttribute('data-run-id');
          if (!rid) return;
          if (
            !confirm(
              'Remove this run from scorecard history only?\\n\\nPromoted bundle file and engine learning are NOT changed.\\n\\nConfirm to delete.'
            )
          ) {
            return;
          }
          btn.disabled = true;
          fetch('/api/batch-scorecard/run/' + encodeURIComponent(rid), {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: true }),
          })
            .then(function (r) {
              return r.json();
            })
            .then(function (out) {
              if (!out || !out.ok) {
                alert((out && out.error) || 'Delete failed');
                btn.disabled = false;
                return;
              }
              void refreshStudentPanelD11({ soft: true });
            })
            .catch(function () {
              alert('Delete failed (network)');
              btn.disabled = false;
            });
        });
      });
    }

    function resetStudentTriangleStarting() {
      const ho = document.getElementById('pgDevStudentSeamInner');
      if (ho) {
        ho.innerHTML =
          'Exam running — <strong>handoff</strong> (Referee → Student store) and <strong>exam list</strong> update when the exam completes.';
      }
      const d = document.querySelector('details.pg-student-triangle-dock');
      if (d) d.open = true;
      const strip = document.getElementById('pgLearningEventsStrip');
      const btn = document.getElementById('pgForensicOpenBtn');
      if (strip) strip.hidden = true;
      if (btn) btn.hidden = true;
    }
    function renderStudentTriangleBatchFailed(msg) {
      const ho = document.getElementById('pgDevStudentSeamInner');
      if (ho) {
        ho.innerHTML =
          '<span style="color:#a32b2b">Exam did not complete — handoff not updated. ' +
          escapeHtml(String(msg != null ? msg : '').slice(0, 400)) +
          (String(msg || '').length > 400 ? '…' : '') +
          '</span>';
      }
      void refreshStudentPanelD11({ soft: true });
    }
    function renderStudentTriangleFromBatchResult(data) {
      const hoBox = document.getElementById('pgDevStudentSeamInner');
      if (!hoBox || !data || typeof data !== 'object') return;
      const handoff = data.student_loop_directive_09_v1;
      const rowsTop = data.student_learning_rows_appended;
      if (handoff && handoff.skipped) {
        hoBox.innerHTML =
          '<p class="caps" style="margin:0">Student handoff <strong>skipped</strong>: ' +
          escapeHtml(String((handoff.reason != null && handoff.reason !== '') ? handoff.reason : '—')) +
          '</p>';
        void refreshStudentPanelD11({ soft: true });
        return;
      }
      if (!handoff || typeof handoff !== 'object') {
        hoBox.innerHTML =
          '<p class="caps" style="margin:0">No <code>student_loop_directive_09_v1</code> in this result — refresh after upgrading the server.</p>';
        void refreshStudentPanelD11({ soft: true });
        return;
      }
      const nApp = (rowsTop != null && rowsTop !== '') ? rowsTop : handoff.student_learning_rows_appended;
      const tc = handoff.trades_considered != null ? handoff.trades_considered : '—';
      const store = handoff.student_learning_store_path ? String(handoff.student_learning_store_path) : '—';
      const storeShort = store.length > 72 ? ('…' + store.slice(-68)) : store;
      const pri = handoff.primary_trade_shadow_student_v1;
      let priHtml = '';
      if (pri && typeof pri === 'object') {
        const ids = pri.pattern_recipe_ids;
        const idsStr = Array.isArray(ids) ? ids.join(', ') : (ids != null ? String(ids) : '—');
        priHtml =
          '<h3 style="margin:14px 0 6px;font-size:0.82rem;font-weight:800;color:var(--pg-teal);letter-spacing:0.04em;text-transform:uppercase">First closed trade (shadow Student)</h3>' +
          '<dl class="pg-student-tri-dl">' +
          '<dt>Scenario / trade</dt><dd><code style="font-size:0.78rem">' + escapeHtml(String(pri.scenario_id || '—')) + '</code> · <code style="font-size:0.78rem">' + escapeHtml(String(pri.trade_id || '—')) + '</code></dd>' +
          '<dt>Retrieval slices matched</dt><dd>' + escapeHtml(String(pri.retrieval_slice_count != null ? pri.retrieval_slice_count : '—')) +
            ' <span style="color:#5c6b7a;font-weight:500">(prior Student rows retrieved for this context)</span></dd>' +
          '<dt>Student decision ref</dt><dd><code style="font-size:0.78rem">' + escapeHtml(String(pri.student_decision_ref || '—')) + '</code></dd>' +
          '<dt>Pattern recipe ids</dt><dd style="word-break:break-word">' + escapeHtml(idsStr) + '</dd>' +
          '<dt>Confidence (0–1)</dt><dd>' + escapeHtml(String(pri.confidence_01 != null ? pri.confidence_01 : '—')) + '</dd>' +
          '</dl>';
      } else {
        priHtml =
          '<p class="caps" style="margin:10px 0 0">' +
          'No shadow Student row for a first trade (no closed trades in replay, or handoff empty for this batch).</p>';
      }
      let errHtml = '';
      const errs = handoff.errors;
      if (Array.isArray(errs) && errs.length) {
        const show = errs.slice(0, 6);
        errHtml =
          '<p class="pg-student-tri-note"><strong>Handoff notes</strong> (' + errs.length + '): ' +
          show.map(function (x) { return escapeHtml(String(x)); }).join(' · ') +
          (errs.length > 6 ? ' …' : '') +
          '</p>';
      }
      hoBox.innerHTML =
        '<dl class="pg-student-tri-dl">' +
        '<dt>Learning rows written</dt><dd><strong>' + escapeHtml(String(nApp != null ? nApp : '—')) + '</strong> appended to the Student store</dd>' +
        '<dt>Closed trades considered</dt><dd>' + escapeHtml(String(tc)) + '</dd>' +
        '<dt>Store path</dt><dd title="' + escapeHtml(store) + '"><code style="font-size:0.76rem;word-break:break-all">' + escapeHtml(storeShort) + '</code></dd>' +
        '</dl>' +
        priHtml +
        errHtml +
        '<p class="pg-student-tri-note">Referee outcomes: <strong>Results</strong> panel in the focus dock (expand tile above). Plumbing history: expand <strong>Score card</strong>. <strong>Clear Card</strong> does not clear the Student store — use Clear Student Proctor store there.</p>';
      studentPanelD11.level = 1;
      studentPanelD11.selectedDecisionId = null;
      void refreshStudentPanelD11({ soft: true });
      updateLearningEventsStripFromBatch(data, handoff);
      const dock = document.querySelector('details.pg-student-triangle-dock');
      if (dock) {
        dock.open = true;
        try {
          dock.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } catch (e) { /* ignore */ }
      }
    }

    function updateLearningEventsStripFromBatch(data, handoff) {
      const strip = document.getElementById('pgLearningEventsStrip');
      const ul = document.getElementById('pgLearningEventsUl');
      const btn = document.getElementById('pgForensicOpenBtn');
      if (!strip || !ul) return;
      if (!data || !handoff || handoff.skipped) {
        strip.hidden = true;
        if (btn) btn.hidden = true;
        return;
      }
      const nApp = data.student_learning_rows_appended != null ? data.student_learning_rows_appended : handoff.student_learning_rows_appended;
      const retr = data.student_retrieval_matches != null ? data.student_retrieval_matches : handoff.student_retrieval_matches;
      const tc = handoff.trades_considered != null ? handoff.trades_considered : '—';
      const mci = data.batch_timing && data.batch_timing.memory_context_impact_audit_v1;
      const impact =
        mci && typeof mci.memory_impact_yes_no === 'string' ? mci.memory_impact_yes_no : '—';
      ul.innerHTML = '';
      function li(t) {
        const n = document.createElement('li');
        n.textContent = t;
        ul.appendChild(n);
      }
      li('Learning rows appended: ' + (nApp != null ? String(nApp) : '—'));
      li('Retrieval matches (run): ' + (retr != null ? String(retr) : '—'));
      li('Closed trades considered: ' + String(tc));
      li('Memory / context impact (harness audit): ' + impact);
      strip.hidden = false;
      if (btn) btn.hidden = false;
    }

    function renderLiveTelemetryPanel(pj, opts) {
      const el = document.getElementById('liveTelemetryPanel');
      const roll = document.getElementById('telemetryRollingLog');
      if (!el) return;
      const echo = (pj && pj.telemetry_context_echo) || {};
      const telem = (pj && pj.telemetry) || {};
      const rows = Array.isArray(telem.scenarios) ? telem.scenarios.slice() : [];
      const completed = pj && pj.completed != null ? pj.completed : 0;
      const total = pj && pj.total != null ? pj.total : 0;
      const elapsed = opts && opts.elapsedSec != null ? opts.elapsedSec : 0;
      const lm = (pj && pj.last_message) || '';
      const running = pj && pj.status === 'running';
      let hot = null;
      if (rows.length) {
        rows.sort(
          (a, b) => (Number(b.decision_windows_processed) || 0) - (Number(a.decision_windows_processed) || 0)
        );
        hot = rows[0];
      }
      updateMemoryStatusCardFromPanel(null, echo, hot, running);

      const recipe =
        echo.operator_recipe_label || echo.operator_recipe_id || (opts && opts.recipeLabel) || '—';
      const fw =
        echo.policy_framework_id != null && String(echo.policy_framework_id) !== ''
          ? String(echo.policy_framework_id)
          : '—';
      const winM = echo.evaluation_window_calendar_months;
      const winStr =
        winM != null ? String(winM) + ' months' : ((opts && opts.windowLabel) ? opts.windowLabel : '—');
      const lines = [];
      if (running) {
        lines.push('Run: ' + recipe);
        lines.push('Framework: ' + fw);
        lines.push('Window: ' + winStr);
        lines.push('');
        lines.push(
          'Batch: ' + completed + ' / ' + total + ' scenario(s) finished (parallel)' +
          (lm ? (' · last: ' + lm) : '')
        );
        if (hot) {
          const si = hot.scenario_index;
          const st = hot.scenario_total;
          const sid = hot.scenario_id || '—';
          lines.push(
            'Busiest worker — scenario slot ' + (si != null ? si : '?') + '/' + (st != null ? st : '?') +
              ' — ' + sid
          );
          const csa = hot.candidate_search_active === true || echo.candidate_search_active === true;
          if (!csa) {
            lines.push('Candidate phase: baseline only (no multi-replay candidate search)');
          } else {
            const phase = hot.candidate_phase || '—';
            const ci = hot.candidate_index;
            const ct = hot.candidates_total;
            const cpart =
              ci != null && ct != null
                ? 'current index ' + ci + ' / ' + ct
                : ci != null
                  ? 'index ' + ci
                  : '';
            lines.push('Candidate phase: ' + phase + (cpart ? ' (' + cpart + ')' : ''));
          }
          const dw = Number(hot.decision_windows_processed || 0);
          const dset = hot.dataset_bars;
          const dwTot = dset != null ? Number(dset) : null;
          lines.push(
            'Decision windows: ' + dw.toLocaleString() +
              (dwTot != null ? ' / ' + dwTot.toLocaleString() + ' (bars in slice)' : '') +
              ' · bars processed: ' +
              (hot.bars_processed != null ? Number(hot.bars_processed).toLocaleString() : String(dw))
          );
          lines.push(
            'Trades (closed): ' + (hot.trades_closed_so_far != null ? hot.trades_closed_so_far : '0') +
              ' · entry attempts: ' + (hot.entries_attempted_so_far != null ? hot.entries_attempted_so_far : '0')
          );
          lines.push('');
          lines.push(
            'Candidates tested (search progress): ' +
              (hot.candidates_tested_so_far != null ? hot.candidates_tested_so_far : '0') +
              (hot.candidates_total != null ? ' / ' + hot.candidates_total : '')
          );
          lines.push('Recall match windows: ' + (hot.recall_match_windows_so_far != null ? hot.recall_match_windows_so_far : '0'));
          lines.push('Signal bias applications: ' + (hot.signal_bias_applied_so_far != null ? hot.signal_bias_applied_so_far : '0'));
          lines.push('');
          const rate = elapsed > 0.5 ? (dw / elapsed).toFixed(2) : null;
          lines.push(
            'Elapsed: ' + fmtTelemetryHMS(elapsed) +
              (rate != null ? ' · ~' + rate + ' decision windows/s (busiest worker)' : '')
          );
        } else {
          lines.push('');
          lines.push('Workers starting — counters appear when the first decision windows are processed.');
          lines.push('Elapsed: ' + fmtTelemetryHMS(elapsed));
        }
        if (rows.length > 1) {
          lines.push('');
          lines.push('(' + rows.length + ' telemetry file(s); busiest worker shown by decision window count.)');
        }
      } else {
        lines.push('No active batch job in this browser session (or job already finished).');
        lines.push('Last snapshot area below stays for the previous run until a new one starts.');
      }
      const detailText = lines.join('\\n');
      if (detailText !== _lastTelemetryDetailText) {
        el.textContent = detailText;
        _lastTelemetryDetailText = detailText;
      }
      const dwKey = hot ? String(hot.decision_windows_processed || 0) : '0';
      const streamKey =
        (running ? 'run' : 'idle') +
        '|' +
        String(completed) +
        '|' +
        String(total) +
        '|' +
        dwKey +
        '|' +
        String(hot && hot.recall_match_windows_so_far != null ? hot.recall_match_windows_so_far : '') +
        '|' +
        String(hot && hot.candidate_phase != null ? hot.candidate_phase : '');
      if (running && streamKey !== _lastTelemetryStreamKey && roll) {
        _lastTelemetryStreamKey = streamKey;
        const tick = document.createElement('div');
        tick.className = 'telemetry-tick';
        const ts = new Date().toISOString().slice(11, 19);
        tick.textContent =
          '[' +
          ts +
          '] dw=' +
          dwKey +
          ' recall_win=' +
          (hot && hot.recall_match_windows_so_far != null ? hot.recall_match_windows_so_far : '0') +
          ' bias=' +
          (hot && hot.recall_bias_applied_so_far != null ? hot.recall_bias_applied_so_far : '0') +
          ' batch ' +
          completed +
          '/' +
          total;
        roll.appendChild(tick);
        while (roll.children.length > 100) {
          roll.removeChild(roll.firstChild);
        }
        roll.scrollTop = roll.scrollHeight;
      }
      updateTerminalCompactSummary(
        pj, running, completed, total, elapsed, hot, winStr, lm, echo, recipe
      );
      updateFocusTerminalOverviewTile();
    }

    function updateFocusTerminalOverviewTile() {
      const st = document.getElementById('tcsStatus');
      const ln = document.getElementById('liveTelemetryPanel');
      const fs = document.getElementById('focusTileTerminalStatus');
      const fl = document.getElementById('focusTileTerminalLine');
      if (fs && st) fs.textContent = (st.textContent || '—').trim() || '—';
      if (fl && ln) {
        const lines = (ln.textContent || '').trim().split('\\n').filter(Boolean);
        const t = lines.length ? lines.slice(0, 4).join(' ') : '—';
        fl.textContent = t;
      }
    }

    function pgFocusEnterPanel(mode) {
      const dock = document.getElementById('pgFocusDock');
      const ov = document.getElementById('pgFocusOverview');
      const ex = document.getElementById('pgFocusExpanded');
      const pt = document.getElementById('pgFocusPaneTerminal');
      const pr = document.getElementById('pgFocusPaneResults');
      const pm = document.getElementById('pgFocusPaneModules');
      const title = document.getElementById('pgFocusExpandedTitle');
      const tTerm = document.getElementById('pgFocusTabTerminal');
      const tRes = document.getElementById('pgFocusTabResults');
      const tMod = document.getElementById('pgFocusTabModules');
      if (!dock || !ov || !ex || !pt || !pr || !pm) return;
      /* Detail labels differ from tile labels — avoids echoing "Terminal" twice next to the Live output heading. */
      const labels = {
        terminal: 'Tape & memory detail',
        results: 'Referee evidence',
        modules: 'Wiring audit',
      };
      if (!labels[mode]) return;
      dock.setAttribute('data-pg-focus-mode', mode);
      document.body.setAttribute('data-pg-focus-expanded', '1');
      ov.hidden = true;
      ex.hidden = false;
      if (title) title.textContent = labels[mode];
      if (tTerm) { tTerm.classList.toggle('is-active', mode === 'terminal'); tTerm.setAttribute('aria-selected', mode === 'terminal' ? 'true' : 'false'); }
      if (tRes) { tRes.classList.toggle('is-active', mode === 'results'); tRes.setAttribute('aria-selected', mode === 'results' ? 'true' : 'false'); }
      if (tMod) { tMod.classList.toggle('is-active', mode === 'modules'); tMod.setAttribute('aria-selected', mode === 'modules' ? 'true' : 'false'); }
      pt.hidden = mode !== 'terminal';
      pr.hidden = mode !== 'results';
      pm.hidden = mode !== 'modules';
      if (mode === 'modules' && typeof refreshModuleBoard === 'function') {
        void refreshModuleBoard();
      }
    }

    function pgFocusBackToOverview() {
      const dock = document.getElementById('pgFocusDock');
      const ov = document.getElementById('pgFocusOverview');
      const ex = document.getElementById('pgFocusExpanded');
      if (!dock || !ov || !ex) return;
      dock.setAttribute('data-pg-focus-mode', 'overview');
      document.body.removeAttribute('data-pg-focus-expanded');
      ov.hidden = false;
      ex.hidden = true;
    }

    /** True if click target is real UI in an expanded Quick View pane (do not collapse). */
    function pgFocusClickKeepsExpanded(target) {
      if (!target || !target.closest) return true;
      return !!target.closest(
        'button, a, textarea, input, select, option, label, summary, ' +
        '[data-pg-focus-tab], [data-pg-focus-tile], [contenteditable], ' +
        'pre, code, table, thead, tbody, tr, td, th, caption, canvas, svg, ' +
        '.pg-tab, .pg-tab-strip, .pg-status-item, .pg-pill-row, .pg-pill, ' +
        '.live-telemetry-wrap, .live-telemetry-panel, .telemetry-rolling-log, ' +
        '.memory-status-card, .pg-terminal-compact-summary, .pg-terminal-split, .pg-terminal-split-left, ' +
        '.pg-header-drawer-inner, .pg-evidence-panel, .pg-table-scroll, ' +
        '.policy-table, .policy-outcome-panel, .scorecard-table-learning, ' +
        '.pg-scorecard-split, .pg-evidence-scorecard-pane, .batch-drill-panel, ' +
        '.inline-details, details, dl, dt, dd'
      );
    }

    function updateTerminalCompactSummary(pj, running, completed, total, elapsed, hot, winStr, lm, echo, recipe) {
      const st = document.getElementById('tcsStatus');
      const bat = document.getElementById('tcsBatch');
      const win = document.getElementById('tcsWindow');
      const dwEl = document.getElementById('tcsDw');
      const elp = document.getElementById('tcsElapsed');
      if (!st || !bat || !win || !dwEl || !elp) return;
      const status = running
        ? 'Running'
        : pj && pj.status === 'done'
          ? 'Done'
          : pj && pj.status === 'cancelled'
            ? 'Cancelled'
            : pj && pj.status === 'error'
              ? 'Error'
              : 'Idle';
      st.textContent = status;
      bat.textContent =
        total > 0 ? completed + ' / ' + total + ' scenarios' : (pj && pj.status ? String(pj.status) : '—');
      win.textContent = winStr || '—';
      if (hot && running) {
        const dw = Number(hot.decision_windows_processed || 0);
        dwEl.textContent = dw.toLocaleString() + (lm ? ' · ' + String(lm).slice(0, 40) : '');
      } else if (!running && echo && echo.evaluation_window_calendar_months != null) {
        dwEl.textContent = '—';
      } else {
        dwEl.textContent = hot ? Number(hot.decision_windows_processed || 0).toLocaleString() : '—';
      }
      elp.textContent = elapsed > 0 ? fmtTelemetryHMS(elapsed) : '—';
    }

    function resetTelemetryRollingLogForNewRun() {
      const roll = document.getElementById('telemetryRollingLog');
      if (roll) roll.innerHTML = '';
      _lastTelemetryStreamKey = '';
      _lastTelemetryDetailText = '';
    }

    function hideLiveTelemetryPanel() {
      const el = document.getElementById('liveTelemetryPanel');
      if (el) {
        el.textContent = 'Idle — no exam running. Live counters stream here when you click Run exam.';
        _lastTelemetryDetailText = el.textContent;
      }
      resetTelemetryRollingLogForNewRun();
      const echo = {};
      updateMemoryStatusCardFromPanel(null, echo, null, false);
      updateTerminalCompactSummary({ status: 'idle' }, false, 0, 0, 0, null, '—', '', {}, '—');
      updateFocusTerminalOverviewTile();
    }

    function setBannerRun(main, sub) {
      const v = document.getElementById('bannerRunV');
      const s = document.getElementById('bannerRunS');
      if (v && main != null) v.textContent = main;
      if (s && sub != null) s.textContent = sub;
    }
    function syncBannerRunFromStatusLine() {
      const st = document.getElementById('statusLine');
      const t = (st && st.textContent) ? st.textContent.trim() : '';
      if (!t) {
        setBannerRun('Idle', '— run an exam —');
        return;
      }
      if (t.indexOf('Running') === 0 || t.indexOf('Starting') === 0) {
        setBannerRun('Running', t.length > 140 ? t.slice(0, 137) + '…' : t);
        return;
      }
      if (t.indexOf('Finished') === 0) {
        setBannerRun('Done', t.length > 140 ? t.slice(0, 137) + '…' : t);
        return;
      }
      if (t.indexOf('Cancelled') === 0) {
        setBannerRun('Cancelled', t.length > 140 ? t.slice(0, 137) + '…' : t);
        return;
      }
      if (t.indexOf('Failed') === 0 || t.indexOf('Stopped') === 0 || t.indexOf('Client timeout') === 0) {
        setBannerRun('Error', t.length > 140 ? t.slice(0, 137) + '…' : t);
        return;
      }
      if (t.indexOf('Validation failed') === 0 || t.indexOf('Start request failed') === 0 ||
          t.indexOf('Set custom months') === 0 || t.indexOf('Missing JSON') === 0 ||
          t.indexOf('JSON parse failed') === 0) {
        setBannerRun('Error', t.length > 140 ? t.slice(0, 137) + '…' : t);
        return;
      }
      setBannerRun('Idle', t.length > 140 ? t.slice(0, 137) + '…' : t);
    }
    function updateRunStatusLine(msg) {
      if (statusLine) statusLine.textContent = msg;
      syncBannerRunFromStatusLine();
    }
    function setRunFeedbackToast(msg) {
      const el = document.getElementById('runFeedbackToast');
      if (!el) return;
      if (!msg) {
        el.hidden = true;
        el.textContent = '';
        return;
      }
      el.hidden = false;
      el.textContent = msg;
    }
    function setEvidenceTab(tab) {
      const outcomes = document.getElementById('pgEvidenceOutcomes');
      const pre = document.getElementById('out');
      const sn = document.getElementById('sessionLogNote');
      const sc = document.getElementById('pgEvidenceScorecard');
      const tabs = document.querySelectorAll('.pg-tab-strip .pg-tab');
      const id = tab || 'outcomes';
      tabs.forEach((b) => {
        b.classList.toggle('active', b.getAttribute('data-tab') === id);
      });
      if (outcomes) outcomes.style.display = (id === 'outcomes') ? '' : 'none';
      if (pre) pre.style.display = (id === 'json') ? 'block' : 'none';
      if (sn) sn.style.display = (id === 'session') ? 'block' : 'none';
      if (sc) sc.style.display = (id === 'scorecard') ? 'block' : 'none';
    }
    document.querySelectorAll('.pg-tab-strip .pg-tab').forEach((btn) => {
      btn.addEventListener('click', () => setEvidenceTab(btn.getAttribute('data-tab')));
    });

    (function wirePgFocusDock() {
      const dock = document.getElementById('pgFocusDock');
      /* One delegated handler on the dock so clicks on inner spans/strong still open the panel (nearest .closest). */
      if (dock) {
        dock.addEventListener('click', function (ev) {
          const mode0 = dock.getAttribute('data-pg-focus-mode') || 'overview';
          const ex0 = document.getElementById('pgFocusExpanded');
          const t0 = ev.target;
          if (mode0 !== 'overview' && ex0 && !ex0.hidden && t0 && t0.closest) {
            if (t0.closest('#pgFocusOverview')) {
              /* ignore — overview is hidden */
            } else if (t0.closest('.pg-focus-expanded-body')) {
              if (!pgFocusClickKeepsExpanded(t0)) {
                ev.preventDefault();
                pgFocusBackToOverview();
                return;
              }
            } else if (t0.closest('.pg-focus-expanded-head')) {
              if (!t0.closest('button') && !t0.closest('[data-pg-focus-tab]')) {
                ev.preventDefault();
                pgFocusBackToOverview();
                return;
              }
            }
          }
          const back = ev.target && ev.target.closest ? ev.target.closest('#pgFocusBackBtn') : null;
          if (back && dock.contains(back)) {
            ev.preventDefault();
            pgFocusBackToOverview();
            return;
          }
          const tab = ev.target && ev.target.closest ? ev.target.closest('[data-pg-focus-tab]') : null;
          if (tab && dock.contains(tab)) {
            ev.preventDefault();
            const mode = tab.getAttribute('data-pg-focus-tab');
            if (!mode || typeof pgFocusEnterPanel !== 'function') return;
            const cur = dock.getAttribute('data-pg-focus-mode') || 'overview';
            if (cur === mode) { pgFocusBackToOverview(); return; }
            pgFocusEnterPanel(mode);
            return;
          }
          const tile = ev.target && ev.target.closest ? ev.target.closest('[data-pg-focus-tile]') : null;
          if (!tile || !dock.contains(tile)) return;
          ev.preventDefault();
          const mode = tile.getAttribute('data-pg-focus-tile');
          if (!mode || typeof pgFocusEnterPanel !== 'function') return;
          const cur = dock.getAttribute('data-pg-focus-mode') || 'overview';
          if (cur === mode) { pgFocusBackToOverview(); return; }
          pgFocusEnterPanel(mode);
        });
      }
      updateFocusTerminalOverviewTile();
    })();

    function formatUsdPlain(n) {
      const x = Number(n);
      if (Number.isNaN(x)) return '—';
      const abs = Math.abs(x);
      return (x < 0 ? '−' : '') + '$' + abs.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function formatDurationSec(s) {
      const n = Number(s);
      if (Number.isNaN(n)) return '—';
      if (n < 60) return n.toFixed(1) + 's';
      const m = Math.floor(n / 60);
      const sec = n - m * 60;
      return m + 'm ' + sec.toFixed(0) + 's';
    }

    function fmtIntCommas(v) {
      if (v == null || v === '') return '—';
      const n = Number(v);
      if (!Number.isFinite(n)) return '—';
      return n.toLocaleString();
    }

    function fmtFloatShort(v, digits) {
      const n = Number(v);
      if (!Number.isFinite(n)) return '—';
      const d = (digits != null && digits !== undefined) ? digits : 4;
      return n.toFixed(d);
    }

    function pctDisplay(v) {
      if (v == null || v === undefined || Number.isNaN(Number(v))) return '—';
      const n = Number(v);
      return (Math.round(n * 10) / 10).toFixed(1) + '%';
    }

    function tradeWinDisplay(e) {
      const bt = e.batch_trades_count;
      const btN = bt != null ? Number(bt) : 0;
      const pct = (btN > 0 && e.batch_trade_win_pct != null && e.batch_trade_win_pct !== undefined)
        ? e.batch_trade_win_pct
        : e.avg_trade_win_pct;
      const nTr = btN > 0 ? btN : (e.trade_win_rate_n != null ? Number(e.trade_win_rate_n) : 0);
      const p = pctDisplay(pct);
      if (nTr > 0 && p !== '—') {
        return p + ' <span style="color:#6c757d">(' + nTr + ')</span>';
      }
      return p;
    }

    function learningStatusChip(ls) {
      const s = (ls != null && ls !== undefined) ? String(ls) : '';
      if (s === 'learning_active') {
        return '<span class="chip-learn-yes" title="learning_active">ACTIVE</span>';
      }
      if (s === 'execution_only') {
        return '<span class="chip-learn-no" title="execution_only">exec</span>';
      }
      return '<span class="chip-learn-no">—</span>';
    }

    function workUnitsCell(e) {
      const w = e.work_units_v1;
      if (w != null && String(w).trim()) {
        const t = String(w);
        return escapeHtml(t.length > 72 ? t.slice(0, 70) + '…' : t);
      }
      const proc = e.total_processed;
      const tot = e.total_scenarios;
      if (proc != null || tot != null) {
        return escapeHtml(String(proc != null ? proc : '—') + ' / ' + String(tot != null ? tot : '—') + ' scen');
      }
      return '—';
    }

    function updateScorecardLearningSummaryFromRow(row) {
      const wrap = document.getElementById('scorecardLearningSummary');
      const body = document.getElementById('scorecardLearningSummaryBody');
      if (!wrap || !body) return;
      const lines = row && row.operator_learning_table_summary_v1;
      if (!row || !Array.isArray(lines) || !lines.length) {
        wrap.hidden = true;
        return;
      }
      wrap.hidden = false;
      const active = row.learning_status === 'learning_active';
      wrap.classList.toggle('exec-only', !active);
      body.innerHTML = lines.map(function (ln) {
        return '<p class="sls-line">' + escapeHtml(String(ln)) + '</p>';
      }).join('');
    }

    function updateLastBatchRunLine(bt) {
      const el = document.getElementById('lastBatchRunLine');
      if (!el || !bt) return;
      const proc = (bt.total_processed != null) ? bt.total_processed : '—';
      const tot = (bt.total_scenarios != null) ? bt.total_scenarios : '—';
      const ro = bt.run_ok_pct;
      const rw = bt.referee_win_pct;
      const atw = bt.avg_trade_win_pct;
      let pctBit = '';
      if (ro != null && ro !== undefined && !Number.isNaN(Number(ro))) {
        pctBit += ' · run OK ' + (Math.round(Number(ro) * 10) / 10).toFixed(1) + '%';
      }
      if (rw != null && rw !== undefined && !Number.isNaN(Number(rw))) {
        pctBit += ' · session WIN ' + (Math.round(Number(rw) * 10) / 10).toFixed(1) + '%';
      }
      const btc = bt.batch_trades_count;
      if (btc != null && Number(btc) > 0 && bt.batch_trade_win_pct != null) {
        pctBit += ' · trade win (batch) ' + pctDisplay(bt.batch_trade_win_pct) + ' on ' + btc + ' trades';
      } else if (atw != null && atw !== undefined && !Number.isNaN(Number(atw))) {
        pctBit += ' · trade win (mean) ' + pctDisplay(atw) +
          (bt.trade_win_rate_n != null ? ' (n=' + bt.trade_win_rate_n + ' scen)' : '');
      }
      const bmj = bt.batch_sessions_judged;
      if (bmj != null && Number(bmj) > 0 && rw != null) {
        pctBit += ' · sessions judged ' + bmj;
      }
      const ls0 = bt.operator_learning_table_summary_v1;
      let learn0 = '';
      if (Array.isArray(ls0) && ls0.length) {
        learn0 = ' · ' + ls0[0];
      }
      el.textContent = 'Last completed exam: start ' + (bt.started_at_utc || '—') +
        ' → end ' + (bt.ended_at_utc || '—') + ' · duration ' + formatDurationSec(bt.duration_sec) +
        ' · rows ' + proc + ' / planned ' + tot + pctBit + learn0;
      updateMemoryContextImpactFromScorecardRow({
        job_id: (bt && bt.job_id != null) ? bt.job_id : null,
        memory_context_impact_audit_v1: bt ? bt.memory_context_impact_audit_v1 : null,
      });
    }

    let selectedScorecardJobId = null;
    /** Last terminal parallel job from this page session (for Ask DATA when no row selected). */
    let askDataLastRunJobId = null;
    /** Latest rows from GET /api/batch-scorecard (newest first) — for scorecard row click handlers. */
    let __scorecardEntriesCache = [];
    const PML_MEM_BASELINE_SS = 'pml_memory_off_baseline_v1';

    function readMemoryOffBaselineMap() {
      try { return JSON.parse(sessionStorage.getItem(PML_MEM_BASELINE_SS) || '{}'); } catch (_e) { return {}; }
    }
    function writeMemoryOffBaselineMap(m) {
      try { sessionStorage.setItem(PML_MEM_BASELINE_SS, JSON.stringify(m)); } catch (_e) { /* ignore */ }
    }

    function updateMemoryContextImpactFromScorecardRow(row) {
      const wrap = document.getElementById('memoryContextImpactPanel');
      const body = document.getElementById('memoryContextImpactBody');
      const barneyEl = document.getElementById('memoryContextBarneyLine');
      if (!wrap || !body) return;
      const mca = row && row.memory_context_impact_audit_v1;
      if (!mca || typeof mca !== 'object') {
        wrap.hidden = true;
        body.innerHTML = '';
        if (barneyEl) barneyEl.textContent = '';
        return;
      }
      wrap.hidden = false;
      const yes = String(mca.memory_impact_yes_no || 'NO').toUpperCase() === 'YES';
      const cmem = String(mca.context_signature_memory_mode_echo || '').toLowerCase();
      const fp = String(mca.run_config_fingerprint_sha256_40 || '');
      const map = readMemoryOffBaselineMap();
      const tradesSum = (mca.trades_count_sum_ok_scenarios != null) ? Number(mca.trades_count_sum_ok_scenarios) : 0;
      const pnlSum = (mca.cumulative_pnl_sum_ok_scenarios != null) ? Number(mca.cumulative_pnl_sum_ok_scenarios) : 0;
      const chkJoin = Array.isArray(mca.validation_checksums_ok_scenarios) ? mca.validation_checksums_ok_scenarios.join('|') : '';

      if (!yes && (!cmem || cmem === 'off')) {
        if (fp) {
          map[fp] = { trades: tradesSum, pnl: pnlSum, checksums: chkJoin, job_id: row.job_id };
          writeMemoryOffBaselineMap(map);
        }
      }

      let tradeChanged = '—';
      let tradeDetail = '';
      if (yes) {
        const b = fp ? map[fp] : null;
        if (b && typeof b.trades === 'number') {
          const dt = tradesSum - b.trades;
          const dpnl = pnlSum - (typeof b.pnl === 'number' ? b.pnl : 0);
          const chg = (dt !== 0 || Math.abs(dpnl) > 1e-9 || chkJoin !== (b.checksums || ''));
          tradeChanged = chg ? 'YES' : 'NO';
          tradeDetail = 'Δ trades ' + dt + ', Δ combined PnL ' + dpnl + ' vs browser-stored baseline (same fingerprint).';
        } else {
          tradeDetail = 'No baseline for this fingerprint in this browser session yet — run once with the same recipe/window, then compare the next run.';
        }
      } else if (cmem === 'read' || cmem === 'read_write') {
        tradeChanged = 'N/A';
        tradeDetail = 'Audit counters show no bundle merge and no fusion/signal recall bias — deterministic.';
      } else {
        tradeDetail = 'No recall bias in audit; when a baseline exists for this fingerprint, trade-set deltas use it.';
      }

      const ns = function (n) { return (n != null && n !== '') ? String(n) : '0'; };
      const bun = mca.memory_bundle_applied_any ? 'true' : 'false';
      const keys = (Array.isArray(mca.memory_keys_applied_union) && mca.memory_keys_applied_union.length)
        ? mca.memory_keys_applied_union.join(', ')
        : '—';
      const ynClass = yes ? 'mci-yes' : 'mci-no';
      const ynTxt = yes ? 'YES' : 'NO';
      body.innerHTML =
        '<span class="mci-k">Memory Impact</span><span class="' + ynClass + '">' + escapeHtml(ynTxt) + '</span>' +
        '<span class="mci-k">Memory bundle applied (any)</span><span>' + escapeHtml(bun) + '</span>' +
        '<span class="mci-k">Recall matches (windows, sum)</span><span>' + escapeHtml(ns(mca.recall_match_windows_total_sum)) + '</span>' +
        '<span class="mci-k">Bias applied (fusion, sum)</span><span>' + escapeHtml(ns(mca.recall_bias_applied_total_sum)) + '</span>' +
        '<span class="mci-k">Signal bias applied (sum)</span><span>' + escapeHtml(ns(mca.recall_signal_bias_applied_total_sum)) + '</span>' +
        '<span class="mci-k">Memory keys (union)</span><span>' + escapeHtml(keys) + '</span>' +
        '<span class="mci-k">Trade set changed vs baseline</span><span>' + escapeHtml(tradeChanged) +
        (tradeDetail ? '<br/><span style="font-weight:400;color:#5c6b7a">' + escapeHtml(tradeDetail) + '</span>' : '') + '</span>' +
        '<span class="mci-k">Config fingerprint (baseline key)</span><span><code style="font-size:0.7rem">' + escapeHtml(fp || '—') + '</code></span>';
      if (barneyEl) {
        barneyEl.textContent = String(mca.barney_operator_truth_line_v1 || '');
      }
    }

    function askDataPreferredJobId() {
      if (selectedScorecardJobId && String(selectedScorecardJobId).trim()) {
        return String(selectedScorecardJobId).trim();
      }
      if (askDataLastRunJobId && String(askDataLastRunJobId).trim()) {
        return String(askDataLastRunJobId).trim();
      }
      return '';
    }

    function buildAskDataUiContext() {
      const recipeEl = document.getElementById('operatorRecipePick');
      const rid = recipeEl ? String(recipeEl.value || '').trim() : '';
      const wm = document.getElementById('evaluationWindowPick');
      const wmv = wm ? String(wm.value || '').trim() : '';
      let customM = null;
      if (wmv === 'custom') {
        const cEl = document.getElementById('evaluationWindowCustomMonths');
        const n = cEl ? parseInt(cEl.value, 10) : NaN;
        if (n > 0) customM = n;
      }
      const useUp = document.getElementById('useOperatorUploadedStrategy');
      let scenariosSource = 'recipe';
      if (rid === 'custom') {
        scenariosSource = 'custom_textarea';
      } else if (useUp && useUp.checked) {
        scenariosSource = 'operator_upload';
      }
      return {
        operator_recipe_id: rid || undefined,
        evaluation_window_mode: wmv || undefined,
        evaluation_window_custom_months: customM != null ? customM : undefined,
        context_signature_memory_mode: contextSignatureMemoryModeForExamRunV1(),
        use_operator_uploaded_strategy: !!(useUp && useUp.checked),
        scenarios_source: scenariosSource,
        recipe_label: recipeLabelFromDom(),
        pattern_game_web_ui_version: PATTERN_GAME_UI_VERSION_STR,
      };
    }

    function appendAskDataBubble(role, text) {
      const thread = document.getElementById('askDataThread');
      if (!thread) return;
      const wrap = document.createElement('div');
      wrap.className = 'pg-ask-msg ' + (role === 'user' ? 'pg-ask-msg-user' : 'pg-ask-msg-assistant');
      const lab = document.createElement('div');
      lab.className = 'pg-ask-msg-role';
      lab.textContent = role === 'user' ? 'You' : 'System';
      const body = document.createElement('div');
      body.textContent = text;
      wrap.appendChild(lab);
      wrap.appendChild(body);
      thread.appendChild(wrap);
      thread.scrollTop = thread.scrollHeight;
    }

    function appendAskDataFeedbackStrip(interactionId) {
      const thread = document.getElementById('askDataThread');
      if (!thread || !interactionId) return;
      const row = document.createElement('div');
      row.className = 'pg-ask-feedback';
      const lab = document.createElement('span');
      lab.className = 'pg-ask-feedback-label';
      lab.textContent = 'Was this helpful?';
      const send = async (rating) => {
        if (row.dataset.sent) return;
        try {
          const r = await fetch('/api/ask-data/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ interaction_id: interactionId, rating: rating, tags: [] }),
          });
          const fj = await r.json();
          if (!r.ok || !fj.ok) {
            lab.textContent = fj.error || ('HTTP ' + r.status);
            return;
          }
          row.dataset.sent = '1';
          lab.textContent = 'Thanks — signal recorded.';
          row.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
        } catch (e) {
          lab.textContent = 'Feedback failed: ' + friendlyFetchError(e);
        }
      };
      const mkBtn = function (label, rating) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'pg-ask-feedback-btn';
        b.textContent = label;
        b.addEventListener('click', function () { send(rating); });
        return b;
      };
      row.appendChild(lab);
      row.appendChild(mkBtn('Helpful', 'up'));
      row.appendChild(mkBtn('Not helpful', 'down'));
      row.appendChild(mkBtn('Skip', 'neutral'));
      thread.appendChild(row);
      thread.scrollTop = thread.scrollHeight;
    }

    async function sendAskData() {
      const inp = document.getElementById('askDataInput');
      const st = document.getElementById('askDataStatus');
      const btn = document.getElementById('askDataSendBtn');
      if (!inp) return;
      const q = String(inp.value || '').trim();
      if (!q) {
        if (st) st.textContent = 'Type a question first.';
        return;
      }
      appendAskDataBubble('user', q);
      inp.value = '';
      if (st) st.textContent = 'Loading…';
      setOpButtonBusy(btn, true, 'Sending…', true);
      try {
        const jid = askDataPreferredJobId();
        const r = await fetch('/api/ask-data', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: q,
            job_id: jid || undefined,
            ui_context: buildAskDataUiContext(),
          }),
        });
        const j = await r.json();
        if (!r.ok || !j.ok) {
          appendAskDataBubble('assistant', 'Ask DATA: ' + (j.error || ('HTTP ' + r.status)));
          if (st) st.textContent = '';
          return;
        }
        const reply = (j.text || '').trim() || '—';
        appendAskDataBubble('assistant', reply);
        if (j.interaction_id) {
          appendAskDataFeedbackStrip(j.interaction_id);
        }
        const src = j.answer_source ? (' · source: ' + j.answer_source) : '';
        if (st) st.textContent = (j.bundle_meta && j.bundle_meta.job_resolution ? ('Context: ' + j.bundle_meta.job_resolution) : '') + src;
      } catch (e) {
        appendAskDataBubble('assistant', 'Ask DATA failed: ' + friendlyFetchError(e));
        if (st) st.textContent = '';
      } finally {
        setOpButtonBusy(btn, false);
      }
    }

    function clearAskDataUi() {
      const inp = document.getElementById('askDataInput');
      const st = document.getElementById('askDataStatus');
      const thread = document.getElementById('askDataThread');
      if (inp) inp.value = '';
      if (thread) thread.innerHTML = '';
      if (st) st.textContent = '';
    }

    function fileLink(jobId, scenarioId, kind) {
      const q = 'job_id=' + encodeURIComponent(jobId) + '&scenario_id=' + encodeURIComponent(scenarioId) + '&kind=' + encodeURIComponent(kind);
      return '/api/batch-scenario-file?' + q;
    }

    async function loadBatchDrill(jobId) {
      const panel = document.getElementById('batchDrillPanel');
      if (!panel) return;
      panel.classList.add('visible');
      panel.innerHTML = '<p>Loading batch…</p>';
      try {
        const r = await fetch('/api/batch-detail?job_id=' + encodeURIComponent(jobId));
        const j = await r.json();
        if (!r.ok || !j.ok) {
          panel.innerHTML = '<p class="err">' + escapeHtml(j.error || 'Failed to load batch') + '</p>';
          return;
        }
        const sc = j.scorecard || {};
        const csvHref = '/api/batch-detail.csv?job_id=' + encodeURIComponent(jobId);
        let meta = '<h3>Batch detail</h3><div class="batch-drill-meta">';
        meta += '<strong>job_id</strong> <code>' + escapeHtml(String(sc.job_id || '')) + '</code><br/>';
        meta += '<strong>started</strong> ' + escapeHtml(String(sc.started_at_utc || '—')) +
          ' → <strong>ended</strong> ' + escapeHtml(String(sc.ended_at_utc || '—')) +
          ' · <strong>duration</strong> ' + escapeHtml(formatDurationSec(sc.duration_sec)) + '<br/>';
        meta += '<strong>scenarios</strong> ' + escapeHtml(String(sc.total_processed != null ? sc.total_processed : '—')) +
          ' / ' + escapeHtml(String(sc.total_scenarios != null ? sc.total_scenarios : '—')) +
          ' · <strong>ok</strong> ' + escapeHtml(String(sc.ok_count != null ? sc.ok_count : '—')) +
          ' · <strong>failed</strong> ' + escapeHtml(String(sc.failed_count != null ? sc.failed_count : '—')) +
          ' · <strong>workers</strong> ' + escapeHtml(String(sc.workers_used != null ? sc.workers_used : '—')) +
          ' · <strong>status</strong> ' + escapeHtml(String(sc.status || '—')) + '<br/>';
        meta += '<strong>session_log_batch_dir</strong> ' + escapeHtml(String(sc.session_log_batch_dir || '(none)')) + '<br/>';
        meta += '<a href="' + csvHref + '">Download this batch (CSV, scenarios)</a>';
        meta += '</div>';
        const la = sc.learning_audit_v1;
        if (la && typeof la === 'object') {
          meta += '<h4>learning_audit_v1</h4><pre class="drill-pre">' +
            escapeHtml(JSON.stringify(la, null, 2)) + '</pre>';
        }
        const oba = sc.operator_batch_audit;
        if (oba && typeof oba === 'object' && Object.keys(oba).length) {
          meta += '<h4>operator_batch_audit</h4><pre class="drill-pre">' +
            escapeHtml(JSON.stringify(oba, null, 2)) + '</pre>';
        }
        const lba = sc.learning_batch_audit_v1;
        if (lba && typeof lba === 'object') {
          meta += '<h4>learning_batch_audit_v1</h4><pre class="drill-pre">' +
            escapeHtml(JSON.stringify(lba, null, 2)) + '</pre>';
        }
        const mci = sc.memory_context_impact_audit_v1;
        if (mci && typeof mci === 'object') {
          meta += '<h4>memory_context_impact_audit_v1</h4><pre class="drill-pre">' +
            escapeHtml(JSON.stringify(mci, null, 2)) + '</pre>';
        }
        if (j.scenario_list_error) {
          meta += '<p style="color:#b7772c">' + escapeHtml(j.scenario_list_error) + '</p>';
        }
        const scenarios = j.scenarios || [];
        if (!scenarios.length) {
          panel.innerHTML = meta + '<p>No scenario rows (session logs missing or empty folder).</p>';
          return;
        }
        let tbl = '<table class="drill-scenario-table"><thead><tr>' +
          '<th title="Scenario id within this batch">scenario</th>' +
          '<th title="Referee session: WIN, LOSS, or other judged outcome">session</th>' +
          '<th title="Memory applied: whether engine memory influenced this scenario">memory</th>' +
          '<th title="Promoted memory bundle lane">Promoted</th>' +
          '<th title="Report links: HUMAN readable log vs machine JSON">reports</th>' +
          '</tr></thead><tbody>';
        for (const s of scenarios) {
          const sid = String(s.scenario_id != null ? s.scenario_id : '');
          const mem = s.memory_applied
            ? '<span class="mem-pill mem-yes">yes</span>'
            : '<span class="mem-pill mem-no">no</span>';
          const gh = (s.groundhog_mode === 'active')
            ? '<span class="mem-pill gh-on">active</span>'
            : '<span class="mem-pill gh-off">inactive</span>';
          const rs = s.referee_session != null ? String(s.referee_session) : '—';
          tbl += '<tr><td><code>' + escapeHtml(sid) + '</code></td>' +
            '<td>' + escapeHtml(rs) + '</td>' +
            '<td>' + mem + '</td>' +
            '<td>' + gh + '</td>' +
            '<td>' +
            '<a href="' + fileLink(jobId, sid, 'human') + '" target="_blank" rel="noopener">HUMAN</a> · ' +
            '<a href="' + fileLink(jobId, sid, 'json') + '" target="_blank" rel="noopener">JSON</a>' +
            '</td></tr>';
        }
        tbl += '</tbody></table>';
        panel.innerHTML = meta + tbl;
      } catch (err) {
        panel.innerHTML = '<p class="err">' + escapeHtml(friendlyFetchError(err)) + '</p>';
      }
    }

    async function refreshScorecardHistory() {
      const tbody = document.getElementById('scorecardHistoryTbody');
      const hint = document.getElementById('scorecardPathHint');
      const clickHint = document.getElementById('scorecardClickHint');
      const csvLink = document.getElementById('scorecardCsvLink');
      if (!tbody) return;
      tbody.innerHTML = '';
      if (clickHint) {
        clickHint.style.display = 'none';
        clickHint.textContent = '';
      }
      try {
        const r = await fetch('/api/batch-scorecard?limit=15');
        const j = await r.json();
        if (!r.ok) {
          if (hint) hint.textContent = 'Could not load scorecard history.';
          return;
        }
        if (hint && j.path) {
          let line = 'Persisted at: ' + j.path + ' (append-only JSONL; set PATTERN_GAME_MEMORY_ROOT for tmpfs)';
          const inf = j.inflight_batches;
          if (typeof inf === 'number' && inf > 0) {
            line += ' · ' + inf + ' batch(es) in progress at top (live from server; not yet in JSONL).';
          }
          hint.textContent = line;
        }
        if (csvLink) {
          csvLink.href = '/api/batch-scorecard.csv?limit=50';
        }
        const rows = j.entries || [];
        __scorecardEntriesCache = Array.isArray(rows) ? rows.slice() : [];
        if (rows.length) {
          updateScorecardLearningSummaryFromRow(rows[0]);
          updateMemoryContextImpactFromScorecardRow(rows[0]);
        } else {
          updateScorecardLearningSummaryFromRow(null);
          updateMemoryContextImpactFromScorecardRow(null);
        }
        if (!rows.length) {
          const tr = document.createElement('tr');
          tr.innerHTML = '<td colspan="33" style="color:#8b98a5">No batches logged yet.</td>';
          tbody.appendChild(tr);
          return;
        }
        for (const e of rows) {
          const inflightRow = !!(e.scorecard_inflight || e.status === 'running');
          const tr = document.createElement('tr');
          tr.className = 'scorecard-row' + (inflightRow ? ' scorecard-row-inflight' : '');
          const jid = (e.job_id != null && e.job_id !== undefined) ? String(e.job_id) : '';
          tr.setAttribute('data-job-id', jid);
          if (selectedScorecardJobId && jid === selectedScorecardJobId) {
            tr.classList.add('selected');
          }
          const st = inflightRow
            ? '<span class="st-running" title="Still running — JSONL line appears when the batch completes">running</span>'
            : (e.status === 'done'
              ? '<span class="st-ok">done</span>'
              : '<span class="st-err">' + escapeHtml(e.status || '—') + '</span>');
          const dur = (e.duration_sec != null) ? formatDurationSec(e.duration_sec) : '—';
          const memY = (e.memory_used === true || e.memory_used === 'yes' || e.memory_used === 1);
          const memCell = (e.memory_used != null && e.memory_used !== '')
            ? (memY ? '<span title="memory_used">Y</span>' : '<span title="memory_used">N</span>')
            : '—';
          tr.innerHTML =
            '<td title="' + escapeHtml(jid) + '"><code style="font-size:0.68rem">' + escapeHtml(jid ? (jid.length > 14 ? jid.slice(0, 12) + '…' : jid) : '—') + '</code></td>' +
            '<td>' + escapeHtml(e.started_at_utc || '—') + '</td>' +
            '<td>' + escapeHtml(e.ended_at_utc || '—') + '</td>' +
            '<td>' + escapeHtml(dur) + '</td>' +
            '<td title="' + escapeHtml(e.work_units_v1 != null ? String(e.work_units_v1) : '') + '">' + workUnitsCell(e) + '</td>' +
            '<td>' + learningStatusChip(e.learning_status) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.decision_windows_total)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.bars_processed)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.candidate_count)) + '</td>' +
            '<td>' + escapeHtml(e.selected_candidate_id != null ? String(e.selected_candidate_id) : '—') + '</td>' +
            '<td>' + escapeHtml(e.winner_vs_control_delta != null ? String(e.winner_vs_control_delta) : '—') + '</td>' +
            '<td>' + memCell + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.memory_records_loaded)) + '</td>' +
            '<td>' + escapeHtml(e.groundhog_status != null ? String(e.groundhog_status) : '—') + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.recall_attempts)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.recall_matches)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.recall_bias_applied)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.signal_bias_applied_count)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.suppressed_modules_count)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.trade_entries_total)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.trade_exits_total)) + '</td>' +
            '<td>' + tradeWinDisplay(e) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.batch_trades_count)) + '</td>' +
            '<td>' + escapeHtml(fmtFloatShort(e.expectancy_per_trade, 4)) + '</td>' +
            '<td>' + escapeHtml(fmtFloatShort(e.exit_efficiency, 4)) + '</td>' +
            '<td>' + escapeHtml(fmtFloatShort(e.win_loss_size_ratio, 4)) + '</td>' +
            '<td title="referee session WIN % (denominator = #Sess)">' + escapeHtml(pctDisplay(e.referee_win_pct)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.batch_sessions_judged)) + '</td>' +
            '<td>' + escapeHtml(pctDisplay(e.run_ok_pct)) + '</td>' +
            '<td>' + escapeHtml(e.ok_count != null ? String(e.ok_count) : '—') + '</td>' +
            '<td>' + escapeHtml(e.failed_count != null ? String(e.failed_count) : '—') + '</td>' +
            '<td>' + escapeHtml(e.workers_used != null ? String(e.workers_used) : '—') + '</td>' +
            '<td>' + st + '</td>';
          tr.addEventListener('click', () => {
            if (inflightRow) {
              const ch = document.getElementById('scorecardClickHint');
              if (ch) {
                ch.style.display = 'block';
                ch.textContent = 'This batch is still running — start time and progress counts update here. Batch detail opens after the run finishes (row is then read from batch_scorecard.jsonl).';
              }
              return;
            }
            document.querySelectorAll('#scorecardHistoryTbody tr.scorecard-row').forEach(function (x) {
              x.classList.remove('selected');
            });
            tr.classList.add('selected');
            selectedScorecardJobId = jid;
            const pick = (__scorecardEntriesCache || []).find(function (x) { return String(x.job_id || '') === jid; });
            updateScorecardLearningSummaryFromRow(pick || null);
            updateMemoryContextImpactFromScorecardRow(pick || null);
            if (jid) loadBatchDrill(jid);
          });
          tbody.appendChild(tr);
        }
      } catch (err) {
        if (hint) hint.textContent = 'Scorecard history: ' + friendlyFetchError(err);
      }
    }

    const RESET_LEARNING_CONFIRM_PHRASE = 'RESET_PATTERN_GAME_LEARNING';
    const clearScorecardBtn = document.getElementById('clearScorecardBtn');
    if (clearScorecardBtn) {
      clearScorecardBtn.onclick = async () => {
        if (!window.confirm(
          'Clear the scorecard log (batch_scorecard.jsonl) only?\\n\\n' +
            'Engine memory, bundles, and the Student Proctor learning store are not cleared.'
        )) {
          return;
        }
        setOpButtonBusy(clearScorecardBtn, true, 'Clearing…', true);
        try {
          const r = await fetch('/api/batch-scorecard/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: true }),
          });
          const j = await r.json();
          if (!r.ok || !j.ok) {
            await show(null, null, j.error || ('Clear failed: ' + r.status));
            return;
          }
          selectedScorecardJobId = null;
          askDataLastRunJobId = null;
          const drill = document.getElementById('batchDrillPanel');
          if (drill) drill.innerHTML = '';
          updateScorecardLearningSummaryFromRow(null);
          updateMemoryContextImpactFromScorecardRow(null);
          const lr = document.getElementById('lastBatchRunLine');
          if (lr) {
            lr.textContent = 'Last completed exam: — (scorecard file cleared; engine memory, bundles, and Student Proctor store unchanged)';
          }
          if (typeof refreshStudentProctorStoreLine === 'function') void refreshStudentProctorStoreLine();
          await refreshScorecardHistory();
        } catch (e) {
          await show(null, null, friendlyFetchError(e));
        } finally {
          setOpButtonBusy(clearScorecardBtn, false);
        }
      };
    }
    const clearPromotedBundleBtn = document.getElementById('clearPromotedBundleBtn');
    if (clearPromotedBundleBtn) {
      clearPromotedBundleBtn.onclick = async () => {
        if (!window.confirm(
          'Delete the promoted parameter bundle file (ATR container) if it exists?\\n\\n' +
            'Scorecard rows, experience log, run memory, and context signature memory are not changed.'
        )) {
          return;
        }
        setOpButtonBusy(clearPromotedBundleBtn, true, 'Clearing…', true);
        try {
          const r = await fetch('/api/promoted-bundle/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: true }),
          });
          const j = await r.json();
          if (!r.ok || !j.ok) {
            await show(null, null, j.error || ('Clear failed: ' + r.status));
            return;
          }
          if (typeof refreshReasoningModelBanner === 'function') refreshReasoningModelBanner();
        } catch (e) {
          await show(null, null, friendlyFetchError(e));
        } finally {
          setOpButtonBusy(clearPromotedBundleBtn, false);
        }
      };
    }
    const clearContextSignatureMemoryBtn = document.getElementById('clearContextSignatureMemoryBtn');
    if (clearContextSignatureMemoryBtn) {
      clearContextSignatureMemoryBtn.onclick = async () => {
        if (!window.confirm(
          'Truncate context signature memory (DCR / recall JSONL) to empty?\\n\\n' +
            'Promoted bundle file, scorecard history, experience log, and run memory are not changed.'
        )) {
          return;
        }
        setOpButtonBusy(clearContextSignatureMemoryBtn, true, 'Clearing…', true);
        try {
          const r = await fetch('/api/context-signature-memory/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: true }),
          });
          const j = await r.json();
          if (!r.ok || !j.ok) {
            await show(null, null, j.error || ('Clear failed: ' + r.status));
            return;
          }
        } catch (e) {
          await show(null, null, friendlyFetchError(e));
        } finally {
          setOpButtonBusy(clearContextSignatureMemoryBtn, false);
        }
      };
    }
    const resetLearningStateBtn = document.getElementById('resetLearningStateBtn');
    if (resetLearningStateBtn) {
      resetLearningStateBtn.onclick = async () => {
        if (!window.confirm(
          'DANGER: Reset Learning State will truncate the experience log and run memory JSONL, ' +
            'truncate context signature memory (recall / signature store), and delete the promoted parameter bundle file if present.\\n\\n' +
            'It does NOT clear the scorecard table file, retrospective notes, or the Student Proctor learning store.\\n\\nContinue?'
        )) {
          return;
        }
        const typed = window.prompt(
          'Type the confirmation phrase exactly (case-sensitive):\\n' + RESET_LEARNING_CONFIRM_PHRASE
        );
        if (typed !== RESET_LEARNING_CONFIRM_PHRASE) {
          if (typed !== null) window.alert('Confirmation mismatch — nothing was changed.');
          return;
        }
        setOpButtonBusy(resetLearningStateBtn, true, 'Resetting…', true);
        try {
          const r = await fetch('/api/pattern-game/reset-learning', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: RESET_LEARNING_CONFIRM_PHRASE }),
          });
          const j = await r.json();
          if (!r.ok || !j.ok) {
            await show(null, null, j.error || JSON.stringify(j.errors || j));
            return;
          }
          await show(null, j, null);
          if (typeof refreshReasoningModelBanner === 'function') refreshReasoningModelBanner();
          if (typeof refreshStudentProctorStoreLine === 'function') void refreshStudentProctorStoreLine();
        } catch (e) {
          await show(null, null, friendlyFetchError(e));
        } finally {
          setOpButtonBusy(resetLearningStateBtn, false);
        }
      };
    }

    const RESET_STUDENT_PROCTOR_CONFIRM = 'RESET_STUDENT_PROCTOR_LEARNING_STORE';
    async function refreshStudentProctorStoreLine() {
      const el = document.getElementById('studentProctorStoreLine');
      if (!el) return;
      try {
        const r = await fetch('/api/student-proctor/learning-store');
        const j = await r.json();
        if (!r.ok || !j.ok) {
          el.textContent = 'Could not read store status.';
          return;
        }
        const lines = (j.line_count !== undefined) ? j.line_count : '—';
        el.textContent = ' Path: ' + (j.path || '—') + ' — lines: ' + lines + '.';
      } catch (e) {
        el.textContent = ' Store status error: ' + friendlyFetchError(e);
      }
    }
    const clearStudentProctorStoreBtn = document.getElementById('clearStudentProctorStoreBtn');
    if (clearStudentProctorStoreBtn) {
      clearStudentProctorStoreBtn.onclick = async () => {
        if (!window.confirm(
          'Truncate ONLY the Student Proctor learning store (cross-run JSONL)?\\n\\n' +
            'Scorecard history and engine learning files will not be changed.'
        )) {
          return;
        }
        const typed = window.prompt(
          'Type the confirmation phrase exactly (case-sensitive):\\n' + RESET_STUDENT_PROCTOR_CONFIRM
        );
        if (typed !== RESET_STUDENT_PROCTOR_CONFIRM) {
          if (typed !== null) window.alert('Confirmation mismatch — nothing was changed.');
          return;
        }
        setOpButtonBusy(clearStudentProctorStoreBtn, true, 'Clearing…', true);
        try {
          const r = await fetch('/api/student-proctor/learning-store/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: RESET_STUDENT_PROCTOR_CONFIRM }),
          });
          const j = await r.json();
          if (!r.ok || !j.ok) {
            await show(null, null, j.error || JSON.stringify(j));
            return;
          }
          await show(null, j, null);
          void refreshStudentProctorStoreLine();
        } catch (e) {
          await show(null, null, friendlyFetchError(e));
        } finally {
          setOpButtonBusy(clearStudentProctorStoreBtn, false);
        }
      };
    }

    function renderPolicyOutcomePanel(data) {
      const panel = document.getElementById('policyOutcomePanel');
      const tbody = document.getElementById('policyOutcomeTbody');
      if (!panel || !tbody) return;
      tbody.innerHTML = '';
      let rows = [];
      if (data && Array.isArray(data.results)) {
        rows = data.results;
      }
      if (!rows.length) {
        panel.hidden = true;
        return;
      }
      panel.hidden = false;
      for (const r of rows) {
        const pc = r.policy_contract || {};
        const summ = r.summary || {};
        const sigs = (pc.signal_modules && pc.signal_modules.length) ? pc.signal_modules.join(', ') : '—';
        const wr = (summ.win_rate != null && summ.win_rate !== undefined)
          ? (Math.round(Number(summ.win_rate) * 1000) / 10 + '%')
          : '—';
        const trades = (summ.trades != null && summ.trades !== undefined) ? String(summ.trades) : '—';
        const pnl = summ.cumulative_pnl;
        let outc = r.referee_session;
        if (!outc) {
          outc = r.ok ? 'LOSS' : 'ERROR';
        }
        const tagClass = outc === 'WIN' ? 'tag-win' : (outc === 'LOSS' ? 'tag-loss' : 'tag-err');
        const sid = r.scenario_id != null ? String(r.scenario_id) : ('—');
        const strat = pc.strategy_id ? String(pc.strategy_id) : '—';
        const fus = pc.fusion_module ? String(pc.fusion_module) : '—';
        const tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + escapeHtml(sid) + '</td>' +
          '<td><span class="' + tagClass + '">' + escapeHtml(outc) + '</span></td>' +
          '<td>' + escapeHtml(formatUsdPlain(pnl)) + '</td>' +
          '<td>' + escapeHtml(wr) + '</td>' +
          '<td>' + escapeHtml(trades) + '</td>' +
          '<td class="signals-cell">' + escapeHtml(sigs) + '</td>' +
          '<td>' + escapeHtml(fus) + '</td>' +
          '<td>' + escapeHtml(strat.length > 56 ? strat.slice(0, 54) + '…' : strat) + '</td>';
        tbody.appendChild(tr);
      }
    }

    async function show(el, data, err) {
      const pre = document.getElementById('out');
      if (typeof pgFocusEnterPanel === 'function') pgFocusEnterPanel('results');
      if (!pre) {
        console.error('Pattern Machine learning UI: missing #out element');
        return;
      }
      if (err) {
        pre.innerHTML = '<span class="err">' + escapeHtml(String(err)) + '</span>';
        renderPolicyOutcomePanel(null);
        setEvidenceTab('json');
        return;
      }
      pre.textContent = JSON.stringify(data, null, 2);
      renderPolicyOutcomePanel(data);
      if (data && data.batch_timing) updateLastBatchRunLine(data.batch_timing);
      if (data && Array.isArray(data.results)) {
        updateMemoryStatusFromBatchResultPayload(data);
      }
      if (data && typeof data === 'object') {
        renderStudentTriangleFromBatchResult(data);
      }
      updateFocusResultsTileFromPayload(data);
      setEvidenceTab('outcomes');
    }

    function updateFocusResultsTileFromPayload(data) {
      const pnlEl = document.getElementById('focusTileResultsPnl');
      const twEl = document.getElementById('focusTileResultsTw');
      const trEl = document.getElementById('focusTileResultsTr');
      const tcsPnl = document.getElementById('tcsLastPnl');
      const tcsTw = document.getElementById('tcsLastTw');
      if (!pnlEl || !twEl || !trEl) return;
      if (!data || typeof data !== 'object' || !data.pnl_summary) {
        pnlEl.textContent = 'P&L —';
        twEl.textContent = 'Trade win —';
        trEl.textContent = '—';
        if (tcsPnl) tcsPnl.textContent = '—';
        if (tcsTw) tcsTw.textContent = '—';
        return;
      }
      const p = data.pnl_summary;
      const d = Number(p.batch_total_pnl_usd);
      if (Math.abs(d) < 1e-9) pnlEl.textContent = 'P&L $0.00';
      else pnlEl.textContent = 'P&L ' + (d >= 0 ? '+' : '−') + formatUsdPlain(Math.abs(d));
      const bt = data.batch_timing && typeof data.batch_timing === 'object' ? data.batch_timing : {};
      let tw = bt.batch_trade_win_pct;
      if (tw == null) tw = bt.avg_trade_win_pct;
      twEl.textContent = tw != null && tw !== '' ? 'TW ' + Number(tw).toFixed(1) + '%' : 'TW —';
      let trn = bt.batch_trades_count;
      if (trn == null && Array.isArray(data.results)) {
        trn = 0;
        for (const r of data.results) {
          const s = r && r.summary && typeof r.summary.trades === 'number' ? r.summary.trades : null;
          if (s != null) trn += s;
        }
      }
      trEl.textContent = trn != null && trn !== '' ? '#' + String(trn) : '—';
      if (tcsPnl) {
        if (Math.abs(d) < 1e-9) tcsPnl.textContent = '$0.00';
        else tcsPnl.textContent = (d >= 0 ? '+' : '−') + formatUsdPlain(Math.abs(d));
      }
      if (tcsTw) {
        tcsTw.textContent = tw != null && tw !== '' ? Number(tw).toFixed(1) + '%' : '—';
      }
    }

    function openRunControlsPanel() {
      const p = document.querySelector('details.pg-panel-controls');
      if (p) p.open = true;
    }
    function scrollRunStatusIntoView() {
      const el = document.getElementById('statusLine') || document.getElementById('progressWrap');
      if (el && typeof el.scrollIntoView === 'function') {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }

    function formatUsd(n) {
      const x = Number(n);
      if (Number.isNaN(x)) return '$—';
      const abs = Math.abs(x);
      const s = (x < 0 ? '-' : '') + '$' + abs.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      return s;
    }

    const PG_PAPER_BASELINE_LS = 'pattern_game_paper_baseline_usd_v1';
    let _lastPnlStripPayload = null;

    function getPaperBaselineUsd() {
      const el = document.getElementById('paperBaselineSlider');
      const v = el ? parseInt(el.value, 10) : NaN;
      if (Number.isFinite(v) && v >= 500 && v <= 10000) return v;
      return 1000;
    }

    function formatVsBaselinePhrase(usd) {
      const x = Number(usd);
      if (!Number.isFinite(x) || x <= 0) return 'vs —';
      if (x >= 1000) {
        const k = x / 1000;
        const s = (Math.round(k * 10) / 10).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 });
        return 'vs $' + s + 'k';
      }
      return 'vs $' + Math.round(x).toLocaleString();
    }

    function syncPaperBaselineLabel() {
      const lab = document.getElementById('paperBaselineLabel');
      if (lab) lab.textContent = '$' + getPaperBaselineUsd().toLocaleString();
    }

    function refreshPnlBannerDisplay() {
      if (_lastPnlStripPayload) updatePnlStrip(_lastPnlStripPayload);
      else resetPnlStrip();
    }

    function updatePnlStrip(pnl) {
      if (!pnl || typeof pnl.ending_equity_usd !== 'number') return;
      _lastPnlStripPayload = pnl;
      const end = pnl.ending_equity_usd;
      const delta = pnl.batch_total_pnl_usd;
      const amt = document.getElementById('bannerPnlAmt');
      if (amt) {
        if (Math.abs(delta) < 1e-9) {
          amt.textContent = '$0.00';
          amt.className = 'banner-pnl-amt neutral';
        } else {
          const sign = delta >= 0 ? '+' : '−';
          amt.textContent = sign + formatUsd(Math.abs(delta));
          amt.className = 'banner-pnl-amt ' + (delta >= 0 ? 'up' : 'down');
        }
      }
      const baseDisplay = getPaperBaselineUsd();
      const sub = document.getElementById('bannerPnlS');
      if (sub) sub.textContent = formatVsBaselinePhrase(baseDisplay);
      const lo = 0;
      const hi = Math.max(2000, baseDisplay * 2);
      const endClamped = Math.max(lo, Math.min(end, hi));
      const pctEnd = (endClamped / hi) * 100;
      const baselinePct = (baseDisplay / hi) * 100;
      const fill = document.getElementById('bannerPnlMicroFill');
      if (fill) {
        const left = Math.min(baselinePct, pctEnd);
        const width = Math.abs(pctEnd - baselinePct);
        fill.style.left = left + '%';
        fill.style.width = Math.max(width, 0.5) + '%';
        fill.className = 'pg-banner-pnl-micro-fill ' + (end >= baseDisplay ? 'up' : 'down');
      }
      const card = document.getElementById('bannerPnlCard');
      if (card) {
        const note = (pnl.note || '').trim();
        card.title =
          (note ? note + ' ' : '') +
          'Batch Δ P&amp;L vs paper baseline (' + formatUsdPlain(baseDisplay) + '). Micro bar: $0–$' +
          Math.round(hi).toLocaleString() + ' (display scale; slider adjusts baseline only).';
      }
    }

    function resetPnlStrip() {
      _lastPnlStripPayload = null;
      const amt = document.getElementById('bannerPnlAmt');
      if (amt) {
        amt.textContent = '—';
        amt.className = 'banner-pnl-amt neutral';
      }
      const baseDisplay = getPaperBaselineUsd();
      const sub = document.getElementById('bannerPnlS');
      if (sub) sub.textContent = formatVsBaselinePhrase(baseDisplay);
      const fill = document.getElementById('bannerPnlMicroFill');
      if (fill) {
        fill.style.left = '50%';
        fill.style.width = '0';
        fill.className = 'pg-banner-pnl-micro-fill up';
      }
      const card = document.getElementById('bannerPnlCard');
      if (card) {
        card.title =
          'Referee paper P&amp;L for the last completed batch. Set paper baseline with the slider (display scale for Δ vs baseline).';
      }
    }

    function initPaperBaselineSlider() {
      const s = document.getElementById('paperBaselineSlider');
      if (!s) return;
      try {
        const raw = localStorage.getItem(PG_PAPER_BASELINE_LS);
        if (raw) {
          const n = parseInt(raw, 10);
          if (Number.isFinite(n) && n >= 500 && n <= 10000) s.value = String(n);
        }
      } catch (e) {}
      syncPaperBaselineLabel();
      s.addEventListener('input', function () {
        try {
          localStorage.setItem(PG_PAPER_BASELINE_LS, String(getPaperBaselineUsd()));
        } catch (e2) {}
        syncPaperBaselineLabel();
        refreshPnlBannerDisplay();
      });
    }

    initPaperBaselineSlider();
    resetPnlStrip();

    function friendlyFetchError(e) {
      const m = (e && (e.message || String(e))) || '';
      const isNet =
        (e && e.name === 'TypeError' && (m.indexOf('NetworkError') >= 0 || m.indexOf('Failed to fetch') >= 0 || m.indexOf('Load failed') >= 0)) ||
        (e && e.name === 'AbortError');
      if (isNet && e && e.name !== 'AbortError') {
        return 'Connection lost while talking to the server. Common causes: the app was restarted or killed mid-run, Wi‑Fi/VPN blip, or the page URL changed. Hard-refresh this page (reload) and click Run exam again.';
      }
      return String(e);
    }

    function clearBatchConcurrencyBanner() {
      const b = document.getElementById('batchConcurrencyBanner');
      if (b) {
        b.innerHTML = '';
        b.classList.remove('visible');
      }
    }

    function showBatchConcurrencyBanner(total, workers, mode) {
      const b = document.getElementById('batchConcurrencyBanner');
      if (!b) return;
      if (mode === 'clear' || total == null || total === 0) {
        clearBatchConcurrencyBanner();
        return;
      }
      const w = (workers != null && workers !== undefined) ? String(workers) : '?';
      const t = Math.max(0, parseInt(String(total), 10) || 0);
      const wn = parseInt(w, 10);
      const eff = (!Number.isNaN(wn) && wn > 0 && t > 0) ? Math.min(t, wn) : '—';
      b.classList.add('visible');
      if (mode === 'done') {
        b.innerHTML =
          '<strong>Batch finished</strong> — <strong>' + t + '</strong> scenario(s) completed · parallel processes used: <strong>' +
          w + '</strong> <span style="color:#8b98a5;font-weight:400">(min of scenario count and slider — one scenario always uses one process)</span>. Result is below.';
        return;
      }
      if (mode === 'error') {
        b.innerHTML = '<strong>Batch stopped</strong> — see Result for details.';
        return;
      }
      let oneWarn = '';
      if (t === 1) {
        oneWarn =
          '<span class="warn"> Only one scenario in the array — one replay at a time. Add more scenarios to the JSON (or use &quot;Suggest next hunters&quot;) to use more cores.</span>';
      }
      b.innerHTML =
        '<strong>Parallelism</strong> — <strong>' + t + '</strong> scenario(s) in this batch · up to <strong>' + w +
        '</strong> parallel process(es) at once (at most <strong>' + eff + '</strong> replays run in parallel until one finishes).' +
        oneWarn;
    }

    const suggestHuntersBtn = document.getElementById('suggestHuntersBtn');
    if (suggestHuntersBtn) {
      suggestHuntersBtn.onclick = async () => {
        const hint = document.getElementById('hunterSuggestHint');
        const ta = document.getElementById('scenarios');
        if (hint) hint.textContent = 'Loading memory-aware suggestion…';
        setOpButtonBusy(suggestHuntersBtn, true, 'Working…', true);
        try {
          const r = await fetch('/api/suggest-hunters');
          const j = await r.json();
          if (!r.ok || !j.ok) {
            if (hint) hint.textContent = j.error || 'Suggestion failed.';
            return;
          }
          ta.value = JSON.stringify(j.scenarios, null, 2);
          refreshWorkerEffectiveLine();
          const w = j.warnings || [];
          const short = w.length ? (w.join(' ')) : ('Ladder round ' + (j.ladder_round != null ? j.ladder_round : '?') +
            ', bias ' + (j.bias || '?') + '. Full rationale in API JSON.');
          if (hint) hint.textContent = short;
        } catch (e) {
          if (hint) hint.textContent = friendlyFetchError(e);
        } finally {
          setOpButtonBusy(suggestHuntersBtn, false);
        }
      };
    }

    const chefAtrSweepBtn = document.getElementById('chefAtrSweepBtn');
    if (chefAtrSweepBtn) {
      chefAtrSweepBtn.onclick = async () => {
        const hint = document.getElementById('chefHint');
        const ta = document.getElementById('scenarios');
        const mpEl = document.getElementById('chefManifestPath');
        const mp = mpEl ? String(mpEl.value || '').trim() : '';
        if (hint) hint.textContent = 'Building catalog ATR sweep…';
        setOpButtonBusy(chefAtrSweepBtn, true, 'Building…', true);
        try {
          const r = await fetch('/api/catalog-batch-generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              mode: 'atr_sweep',
              manifest_path: mp,
              max_scenarios: 24,
            }),
          });
          const j = await r.json();
          if (!r.ok || !j.ok) {
            if (hint) hint.textContent = j.error || 'Chef batch failed.';
            return;
          }
          ta.value = JSON.stringify(j.scenarios, null, 2);
          refreshWorkerEffectiveLine();
          const w = j.warnings || [];
          const extra = w.length ? (' · ' + w.join(' ')) : '';
          if (hint) hint.textContent = 'Chef: ' + (j.count || (j.scenarios || []).length) +
            ' scenarios (ATR sweep).' + extra;
        } catch (e) {
          if (hint) hint.textContent = friendlyFetchError(e);
        } finally {
          setOpButtonBusy(chefAtrSweepBtn, false);
        }
      };
    }

    function setProgressUI(completed, total, subtext) {
      const fill = document.getElementById('progressFill');
      const sub = document.getElementById('progressSub');
      if (!fill || !sub || !progressWrap) return;
      const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
      fill.style.width = pct + '%';
      progressWrap.setAttribute('aria-valuenow', String(pct));
      if (subtext) sub.textContent = subtext;
      else sub.textContent = total > 0 ? ('Scenarios ' + completed + ' / ' + total + ' complete (replay is CPU-bound; each bar can take minutes).') : '';
    }

    /** Prefer API total; never default to 1 (that showed 0/1 for 15-scenario batches if total was missing). */
    function resolveScenarioBatchTotal(apiTotal, textareaValue) {
      const n = Number(apiTotal);
      if (Number.isFinite(n) && n >= 1) return n;
      try {
        const raw = JSON.parse(textareaValue);
        const arr = Array.isArray(raw) ? raw : (raw && Array.isArray(raw.scenarios) ? raw.scenarios : null);
        if (arr && arr.length >= 1) return arr.length;
      } catch (e) {}
      return 1;
    }

    function statusPollTotal(pj, fallbackTotal) {
      const n = Number(pj.total);
      if (Number.isFinite(n) && n >= 1) return n;
      return fallbackTotal;
    }

    async function fetchBarneySummary(jobId) {
      const el = document.getElementById('barneySummaryBody');
      if (!el || !jobId) return;
        el.textContent = 'Loading batch recap…';
      try {
        const r = await fetch('/api/barney-summary', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: jobId }),
        });
        const j = await r.json();
        if (!r.ok || !j.ok) {
          el.textContent = 'Batch recap unavailable: ' + (j.error || String(r.status));
          return;
        }
        el.textContent = (j.text || '').trim() || '—';
      } catch (e) {
        el.textContent = 'Batch recap failed: ' + friendlyFetchError(e);
      }
    }

    (function wireForensicDrillDialog() {
      const dlg = document.getElementById('pgForensicDrillDialog');
      const openB = document.getElementById('pgForensicOpenBtn');
      const closeB = document.getElementById('pgForensicDrillClose');
      if (openB && dlg) {
        openB.addEventListener('click', function () {
          try {
            dlg.showModal();
          } catch (e) { /* ignore */ }
        });
      }
      if (closeB && dlg) {
        closeB.addEventListener('click', function () {
          try {
            dlg.close();
          } catch (e) { /* ignore */ }
        });
      }
    })();

    function buildExamRunContractV1ForStart() {
      const skipEl = document.getElementById('examSkipColdBaselineIfAnchor');
      const pvEl = document.getElementById('examPromptVersion');
      const llmModelEl = document.getElementById('examLlmModelPick');
      const PROFILE_LLM = 'memory_context_llm_student';
      const PROFILE_COLD = 'baseline_no_memory_no_llm';
      const MODE_GATED = 'baseline_gated';
      const profile = resolveExamBrainProfileV1ForStart();
      const modeEl = document.getElementById('examStudentExecutionModePick');
      const skipCold = !!(skipEl && skipEl.checked);
      const pv =
        pvEl && pvEl.value.trim()
          ? pvEl.value.trim()
          : 'pattern_game_web_ui_v' + PATTERN_GAME_UI_VERSION_STR;
      const studentExecMode =
        modeEl && modeEl.value ? String(modeEl.value).trim() : MODE_GATED;
      const out = {
        student_brain_profile_v1: profile,
        student_reasoning_mode: profile,
        skip_cold_baseline_if_anchor: skipCold,
        prompt_version: pv,
        retrieved_context_ids: [],
        student_controlled_execution_v1: profile !== PROFILE_COLD,
      };
      if (profile !== PROFILE_COLD) {
        out.student_execution_mode_v1 = studentExecMode;
      }
      if (profile === PROFILE_LLM) {
        const model =
          llmModelEl && llmModelEl.value ? String(llmModelEl.value).trim() : 'qwen2.5:7b';
        out.student_llm_v1 = {
          llm_provider: 'ollama',
          llm_model: model,
          llm_role: 'single_shot_student_output_v1',
        };
      } else {
        out.student_llm_v1 = {};
      }
      return out;
    }

    (function wireExamBrainProfileUi() {
      const pick = document.getElementById('examStudentReasoningModePick');
      const leg = document.getElementById('pgExamLegacyBrainProfileOverride');
      const wrap = document.getElementById('examLlmModelWrap');
      const modeRow = document.getElementById('examStudentExecutionModeWrap');
      function effProfile() {
        if (leg && String(leg.value || '').trim()) return String(leg.value).trim();
        return pick && pick.value ? String(pick.value).trim() : 'memory_context_llm_student';
      }
      function syncExamLlmWrap() {
        if (!wrap) return;
        wrap.style.display = effProfile() === 'memory_context_llm_student' ? 'block' : 'none';
      }
      function syncStudentExecutionModeRow() {
        if (!modeRow) return;
        modeRow.style.display = effProfile() === 'baseline_no_memory_no_llm' ? 'none' : 'block';
      }
      function syncAll() {
        syncExamLlmWrap();
        syncStudentExecutionModeRow();
      }
      if (pick) {
        pick.addEventListener('change', syncAll);
      }
      if (leg) {
        leg.addEventListener('change', syncAll);
      }
      syncAll();
    })();

    function friendlyParallelBackendError(msg) {
      const m = String(msg != null ? msg : '');
      if (
        m.indexOf('No runnable scenarios') !== -1 ||
        m.indexOf('Missing scenarios_json') !== -1 ||
        m.indexOf('Invalid scenarios') !== -1 ||
        m.toLowerCase().indexOf('scenario_validation') !== -1
      ) {
        return 'No valid scenarios to run — ' + m;
      }
      if (
        m.indexOf('replay_noop_batch') !== -1 ||
        m.indexOf('parallel_batch_empty_results') !== -1 ||
        m.indexOf('internal_empty_scenarios') !== -1
      ) {
        return 'Run did not execute replay (no-op batch) — classified as failure, not success. ' + m;
      }
      return m;
    }

    (function wireRunBatchButton() {
      const runBtn = document.getElementById('runBtn');
      if (!runBtn) {
        console.error('Pattern Machine learning UI: #runBtn missing — Run wiring skipped; check HTML structure.');
        return;
      }
      runBtn.onclick = async () => {
      const btn = document.getElementById('runBtn');
      const parallelCancelBtn = document.getElementById('parallelCancelBtn');
      if (parallelCancelBtn) {
        parallelCancelBtn.style.display = 'none';
        parallelCancelBtn.disabled = false;
      }
      setRunFeedbackToast('');
      setOpButtonBusy(btn, true, 'Running exam…', true);
      openRunControlsPanel();
      clearBatchConcurrencyBanner();
      resetTelemetryRollingLogForNewRun();
      const sn = document.getElementById('sessionLogNote');
      if (sn) sn.textContent = '';
      updateRunStatusLine('Starting exam…');
      scrollRunStatusIntoView();
      const psEl = document.getElementById('progressSub');
      if (psEl) psEl.textContent = '';
      setProgressUI(0, 0, '');
      if (progressWrap) progressWrap.classList.add('active');
      document.body.classList.add('pg-run-active');
      const t0 = Date.now();
      let runWorkersCap = null;
      let jobId = null;
      try {
        let mw = rangeEl ? parseInt(rangeEl.value, 10) : NaN;
        if (isNaN(mw)) mw = null;
        if (mw !== null && rangeEl && workersVal) {
          mw = Math.max(1, Math.min(mw, LIMITS.hard_cap_workers));
          rangeEl.value = String(mw);
          workersVal.textContent = String(mw);
        }
        const recipeId = document.getElementById('operatorRecipePick') ? document.getElementById('operatorRecipePick').value : 'custom';
        const scenariosTa = document.getElementById('scenarios') ? document.getElementById('scenarios').value : '';
        const wm = document.getElementById('evaluationWindowPick') ? document.getElementById('evaluationWindowPick').value : '12';
        let customM = null;
        if (wm === 'custom') {
          const cEl = document.getElementById('evaluationWindowCustomMonths');
          customM = cEl ? parseInt(cEl.value, 10) : null;
          if (!customM || customM < 1) {
            await show(null, null, 'Evaluation window is Custom — enter a valid number of months (1–600).');
            updateRunStatusLine('Set custom months before run.');
            hideLiveTelemetryPanel();
            return;
          }
        }
        if (recipeId === 'custom') {
          if (!scenariosTa || !scenariosTa.trim()) {
            await show(null, null, 'Pattern is Custom — paste valid scenario JSON under Advanced → Custom scenario.');
            updateRunStatusLine('Missing JSON for Custom pattern.');
            hideLiveTelemetryPanel();
            return;
          }
          try {
            const p = JSON.parse(scenariosTa.trim());
            const arr = Array.isArray(p) ? p : (p && Array.isArray(p.scenarios) ? p.scenarios : null);
            if (!arr || arr.length < 1) throw new Error('need a non-empty scenario array');
          } catch (ve) {
            await show(null, null, 'Invalid JSON: ' + String(ve && ve.message ? ve.message : ve));
            updateRunStatusLine('JSON parse failed.');
            hideLiveTelemetryPanel();
            return;
          }
        }
        const doLogEl = document.getElementById('doLog');
        const cmem = contextSignatureMemoryModeForExamRunV1();
        const ltpPrep = document.getElementById('liveTelemetryPanel');
        if (ltpPrep) {
          ltpPrep.textContent = 'Live telemetry — preparing exam…';
          _lastTelemetryDetailText = ltpPrep.textContent;
        }
        updateMemoryStatusCardFromPanel(null, { context_signature_memory_mode: cmem }, null, true);
        const useUpEl = document.getElementById('useOperatorUploadedStrategy');
        const useUploaded = !!(useUpEl && useUpEl.checked);
        const twm = document.getElementById('tradeWindowPick') ? document.getElementById('tradeWindowPick').value : '5m';
        const body = {
          scenarios_json: recipeId === 'custom' ? scenariosTa : '[]',
          max_workers: mw,
          log_path: !!(doLogEl && doLogEl.checked),
          operator_recipe_id: recipeId,
          evaluation_window_mode: wm,
          evaluation_window_custom_months: customM,
          trade_window_mode: twm,
          context_signature_memory_mode: cmem,
          use_operator_uploaded_strategy: useUploaded,
          exam_run_contract_v1: buildExamRunContractV1ForStart(),
        };
        const startR = await fetch('/api/run-parallel/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const startRaw = await startR.text();
        let startJ;
        try {
          startJ = startRaw ? JSON.parse(startRaw) : {};
        } catch (pe) {
          await show(
            null,
            null,
            'Server returned non-JSON from /api/run-parallel/start (HTTP ' + startR.status + '): ' + String(pe && pe.message ? pe.message : pe) + ' — body: ' + (startRaw || '').slice(0, 1200)
          );
          updateRunStatusLine('Start request failed — see Result (Results panel in the focus dock).');
          hideLiveTelemetryPanel();
          return;
        }
        if (!startR.ok) {
          await show(null, null, friendlyParallelBackendError(startJ.error || JSON.stringify(startJ)));
          updateRunStatusLine('Validation failed — see Result.');
          hideLiveTelemetryPanel();
          return;
        }
        jobId = startJ.job_id;
        pgSetInflightJobId(jobId);
        resetStudentTriangleStarting();
        const total = resolveScenarioBatchTotal(startJ.total, scenariosTa);
        runWorkersCap = startJ.workers_used != null ? startJ.workers_used : null;
        const ltp = document.getElementById('liveTelemetryPanel');
        if (ltp) {
          ltp.textContent = 'Live telemetry — waiting for worker snapshots…';
          _lastTelemetryDetailText = ltp.textContent;
        }
        showBatchConcurrencyBanner(total, runWorkersCap, 'run');
        updateRunStatusLine(
          'Running — ' + total + ' scenario(s) · up to ' + (runWorkersCap != null ? runWorkersCap : '?') +
          ' parallel process(es) (min of batch size and slider) · updates every 1.5s below.'
        );
        setProgressUI(0, total, 'Queued — up to ' + (runWorkersCap != null ? runWorkersCap : '?') + ' process(es) · waiting for first replay to finish…');
        void refreshScorecardHistory();
        setRunFeedbackToast(
          'Batch started — job ' + jobId + ' · ' + total + ' scenario(s). Header shows Running; scorecard adds an in-flight row with start time (refreshes while this page polls).'
        );
        const scorePanel = document.querySelector('details.pg-panel-score');
        if (scorePanel) scorePanel.open = true;
        scrollRunStatusIntoView();
        if (parallelCancelBtn) {
          parallelCancelBtn.style.display = 'inline-block';
          parallelCancelBtn.disabled = false;
        }

        const pollOnce = async () => {
          const pr = await fetch('/api/run-parallel/status/' + jobId);
          const prText = await pr.text();
          let pj;
          try {
            pj = prText ? JSON.parse(prText) : {};
          } catch (e) {
            throw new Error(
              'Status poll returned non-JSON (HTTP ' + pr.status + '): ' + String(e && e.message ? e.message : e) +
                ' — ' + (prText || '').slice(0, 500)
            );
          }
          if (!pr.ok) {
            throw new Error(pj.error || 'status failed');
          }
          const elapsed = Math.floor((Date.now() - t0) / 1000);
          const elapsedStr = elapsed >= 60 ? (Math.floor(elapsed / 60) + 'm ' + (elapsed % 60) + 's') : (elapsed + 's');
          const wCap = pj.workers_used != null ? pj.workers_used : runWorkersCap;
          if (pj.status === 'running') {
            const c = pj.completed || 0;
            const t = statusPollTotal(pj, total);
            const lm = pj.last_message || '';
            const sub = (lm ? (lm + ' · ') : '') + 'up to ' + (wCap != null ? wCap : '?') + ' parallel · ' + elapsedStr;
            setProgressUI(c, t, sub);
            updateRunStatusLine(
              'Running — ' + c + '/' + t + ' scenario(s) finished · up to ' + (wCap != null ? wCap : '?') +
              ' parallel process(es) · ' + elapsedStr + ' elapsed'
            );
            renderLiveTelemetryPanel(pj, {
              elapsedSec: elapsed,
              recipeLabel: recipeLabelFromDom(),
              windowLabel: evaluationWindowLabelFromDom(),
            });
            void refreshScorecardHistory();
            void refreshStudentPanelD11({ soft: true });
            return false;
          }
          if (pj.status === 'error') {
            pgSetInflightJobId(null);
            const rollE = document.getElementById('telemetryRollingLog');
            if (rollE) {
              const t = document.createElement('div');
              t.className = 'telemetry-tick';
              t.textContent = '[' + new Date().toISOString().slice(11, 19) + '] Batch error: ' + String(pj.error || 'unknown');
              rollE.appendChild(t);
            }
            updateMemoryStatusCardFromPanel(null, pj.telemetry_context_echo || {}, null, false);
            renderLiveTelemetryPanel(pj, {
              elapsedSec: elapsed,
              recipeLabel: recipeLabelFromDom(),
              windowLabel: evaluationWindowLabelFromDom(),
            });
            showBatchConcurrencyBanner(total, wCap, 'error');
            if (pj.batch_timing) updateLastBatchRunLine(pj.batch_timing);
            refreshScorecardHistory();
            askDataLastRunJobId = jobId;
            void fetchBarneySummary(jobId);
            await show(null, null, friendlyParallelBackendError(pj.error || 'Job failed'));
            renderStudentTriangleBatchFailed(pj.error || 'Job failed');
            updateRunStatusLine('Failed — see Result.');
            setRunFeedbackToast('Batch failed — open Results (focus dock) → Raw JSON tab for the error.');
            setProgressUI(pj.completed || 0, statusPollTotal(pj, total), pj.error || '');
            return true;
          }
          if (pj.status === 'cancelled') {
            pgSetInflightJobId(null);
            updateMemoryStatusCardFromPanel(null, pj.telemetry_context_echo || {}, null, false);
            renderLiveTelemetryPanel(pj, {
              elapsedSec: elapsed,
              recipeLabel: recipeLabelFromDom(),
              windowLabel: evaluationWindowLabelFromDom(),
            });
            showBatchConcurrencyBanner(total, wCap, 'error');
            if (pj.batch_timing) updateLastBatchRunLine(pj.batch_timing);
            refreshScorecardHistory();
            askDataLastRunJobId = jobId;
            void fetchBarneySummary(jobId);
            await show(null, null, String(pj.error || 'Batch cancelled.'));
            renderStudentTriangleBatchFailed(String(pj.error || 'Batch cancelled.'));
            updateRunStatusLine('Cancelled — see scorecard (status cancelled).');
            setRunFeedbackToast('Batch cancelled — partial aggregates may appear on the scorecard.');
            setProgressUI(pj.completed || 0, statusPollTotal(pj, total), pj.error || 'cancelled');
            return true;
          }
          if (pj.status === 'done') {
            pgSetInflightJobId(null);
            if (pj.result) {
              updateMemoryStatusFromBatchResultPayload(pj.result);
            }
            const rollD = document.getElementById('telemetryRollingLog');
            if (rollD) {
              const t = document.createElement('div');
              t.className = 'telemetry-tick';
              t.textContent = '[' + new Date().toISOString().slice(11, 19) + '] Batch finished — final memory row above.';
              rollD.appendChild(t);
              while (rollD.children.length > 100) {
                rollD.removeChild(rollD.firstChild);
              }
            }
            const ltpDone = document.getElementById('liveTelemetryPanel');
            if (ltpDone && ltpDone.textContent) {
              ltpDone.textContent = ltpDone.textContent + '\\n\\n--- Batch finished ---';
              _lastTelemetryDetailText = ltpDone.textContent;
            }
            const tDone = statusPollTotal(pj, total);
            const cDone = (pj.completed != null && pj.completed >= 0) ? pj.completed : tDone;
            setProgressUI(cDone, tDone, '');
            if (pj.result) {
              const j = pj.result;
              const doneN = j.ran != null ? j.ran : tDone;
              const doneW = j.workers_used != null ? j.workers_used : wCap;
              showBatchConcurrencyBanner(doneN, doneW, 'done');
              setProgressUI(doneN, doneN, 'All ' + doneN + ' scenario(s) finished · parallel processes used: ' + (doneW != null ? doneW : '?') + ' · ' + elapsedStr);
              if (j.pnl_summary) {
                updatePnlStrip(j.pnl_summary);
                updateFocusResultsTileFromPayload(j);
              }
              const sl = document.getElementById('sessionLogNote');
              if (sl) {
                sl.textContent = j.session_log_batch_dir
                  ? ('Session logs (human-readable): ' + j.session_log_batch_dir)
                  : '';
              }
              await show(null, j, null);
              refreshScorecardHistory();
              askDataLastRunJobId = jobId;
              void fetchBarneySummary(jobId);
              updateRunStatusLine(
                'Finished — ' + doneN + ' scenario(s) · parallel processes used: ' + (doneW != null ? doneW : '?') +
                ' (not the same as the slider when you only have one scenario) · see Result below.'
              );
              setRunFeedbackToast('Batch finished — see scorecard for timing; open Results in the focus dock for JSON.');
            } else {
              showBatchConcurrencyBanner(tDone, wCap, 'done');
              setProgressUI(cDone, tDone, 'Batch marked done — full JSON not in this response; see scorecard below.');
              refreshScorecardHistory();
              askDataLastRunJobId = jobId;
              void fetchBarneySummary(jobId);
              updateRunStatusLine(
                'Finished — ' + cDone + '/' + tDone + ' (details in scorecard; hard-refresh if Result is empty).'
              );
              setRunFeedbackToast('Batch finished — see scorecard.');
            }
            renderLiveTelemetryPanel(pj, {
              elapsedSec: elapsed,
              recipeLabel: recipeLabelFromDom(),
              windowLabel: evaluationWindowLabelFromDom(),
            });
            return true;
          }
          /* Missing or unknown status: keep polling (treating as non-terminal avoids silent no-op). */
          return false;
        };

        const deadline = Date.now() + RUN_TIMEOUT_MS;
        while (Date.now() < deadline) {
          const done = await pollOnce();
          if (done) break;
          await new Promise((r) => setTimeout(r, 1500));
        }
        if (Date.now() >= deadline) {
          pgSetInflightJobId(null);
          renderLiveTelemetryPanel(
            { status: 'error', completed: 0, total: 0, telemetry_context_echo: {} },
            {
              elapsedSec: Math.floor(RUN_TIMEOUT_MS / 1000),
              recipeLabel: recipeLabelFromDom(),
              windowLabel: evaluationWindowLabelFromDom(),
            }
          );
          await show(null, null, 'Timed out after ' + (RUN_TIMEOUT_MS / 60000) + ' minutes — job may still be running on the server; open /api/run-parallel/status/<job_id> or check logs.');
          renderStudentTriangleBatchFailed('Client timeout — job may still be running on the server.');
          updateRunStatusLine('Client timeout — check server or logs.');
        }
      } catch (e) {
        if (!jobId) {
          hideLiveTelemetryPanel();
        }
        if (runWorkersCap != null) {
          showBatchConcurrencyBanner(1, 1, 'error');
        } else {
          clearBatchConcurrencyBanner();
        }
        await show(null, null, friendlyFetchError(e));
        if (jobId) {
          pgSetInflightJobId(null);
          renderStudentTriangleBatchFailed(friendlyFetchError(e));
        }
        updateRunStatusLine('Stopped or failed — see Result.');
      } finally {
        if (parallelCancelBtn) {
          parallelCancelBtn.style.display = 'none';
          parallelCancelBtn.disabled = false;
        }
        if (progressWrap) progressWrap.classList.remove('active');
        document.body.classList.remove('pg-run-active');
        setOpButtonBusy(btn, false);
        syncBannerRunFromStatusLine();
      }
    };
      const parallelCancelBtnGlobal = document.getElementById('parallelCancelBtn');
      if (parallelCancelBtnGlobal) {
        parallelCancelBtnGlobal.onclick = async () => {
          const jid = pgGetInflightJobId();
          if (!jid) {
            setRunFeedbackToast('No active batch job on this page.');
            return;
          }
          parallelCancelBtnGlobal.disabled = true;
          try {
            const r = await fetch('/api/run-parallel/cancel/' + encodeURIComponent(jid), { method: 'POST' });
            const j = await r.json().catch(function () { return {}; });
            if (!r.ok || !j.ok) {
              setRunFeedbackToast((j && j.error) ? String(j.error) : ('Cancel failed HTTP ' + r.status));
              parallelCancelBtnGlobal.disabled = false;
              return;
            }
            setRunFeedbackToast('Cancel requested — pending scenarios will not start; in-flight workers may still finish.');
          } catch (e) {
            setRunFeedbackToast(friendlyFetchError(e));
            parallelCancelBtnGlobal.disabled = false;
          }
        };
      }
    })();

    function applyEvaluationWindowCapFromPayload(h) {
      const maxM = h && typeof h.max_evaluation_window_calendar_months === 'number' ? h.max_evaluation_window_calendar_months : null;
      const ew = document.getElementById('evaluationWindowPick');
      if (!ew) return;
      if (maxM == null || maxM < 1) {
        Array.from(ew.options).forEach(function (opt) { opt.disabled = false; });
        ew.title = '';
        const cm0 = document.getElementById('evaluationWindowCustomMonths');
        if (cm0) cm0.removeAttribute('max');
        return;
      }
      const spanD = h && h.replay_tape_span_days_approx;
      const spanStr = (typeof spanD === 'number' && !Number.isNaN(spanD)) ? ('~' + Math.round(spanD) + 'd tape → max ' + maxM + ' mo') : ('max ' + maxM + ' mo (data limit)');
      Array.from(ew.options).forEach(function (opt) {
        const v = opt.value;
        if (v === 'custom') {
          opt.disabled = false;
          return;
        }
        const mo = parseInt(v, 10);
        opt.disabled = !Number.isFinite(mo) || mo > maxM;
      });
      ew.title = spanStr;
      const cm = document.getElementById('evaluationWindowCustomMonths');
      if (cm) {
        cm.max = String(maxM);
        if (!cm.min) cm.min = '1';
      }
      const cur = ew.value;
      if (cur !== 'custom') {
        const mo = parseInt(cur, 10);
        if (Number.isFinite(mo) && mo > maxM) {
          let pick = 'custom';
          if (maxM >= 24) pick = '24';
          else if (maxM >= 18) pick = '18';
          else if (maxM >= 12) pick = '12';
          ew.value = pick;
          if (pick === 'custom' && cm) cm.value = String(maxM);
          if (typeof syncCustomMonthsVisibility === 'function') syncCustomMonthsVisibility();
          if (typeof refreshStructuredMetadata === 'function') void refreshStructuredMetadata();
        }
      } else if (cm) {
        const c = parseInt(cm.value, 10);
        if (Number.isFinite(c) && c > maxM) {
          cm.value = String(maxM);
          if (typeof refreshStructuredMetadata === 'function') void refreshStructuredMetadata();
        }
      }
    }

    fetch('/api/capabilities').then(function (r) { return r.json(); }).then(function (c) {
      applyEvaluationWindowCapFromPayload(c);
    }).catch(function () {});

    async function refreshDataHealth() {
      const dot = document.getElementById('healthDot');
      const text = document.getElementById('healthText');
      const bannerV = document.getElementById('bannerFinancialV');
      if (!text) return;
      try {
        const r = await fetch('/api/data-health');
        const j = await r.json();
        if (dot) {
          dot.className = 'status-dot ' + (j.overall_ok ? 'ok' : 'bad');
          dot.title = j.overall_ok ? 'Data OK' : 'Data issue — see text';
        }
        if (bannerV) bannerV.textContent = j.overall_ok ? 'OK' : 'Issue';
        if (j.summary_line) {
          text.textContent = j.summary_line;
        } else if (j.error) {
          text.textContent = j.error;
        } else {
          text.textContent = 'Unknown status';
        }
        applyEvaluationWindowCapFromPayload(j);
      } catch (e) {
        if (dot) {
          dot.className = 'status-dot bad';
          dot.title = 'Health request failed';
        }
        if (bannerV) bannerV.textContent = '—';
        text.textContent = 'Health check failed: ' + friendlyFetchError(e);
      }
    }
    refreshDataHealth();
    setInterval(refreshDataHealth, 45000);

    function refreshReasoningModelTileClass(tile, color) {
      if (!tile) return;
      tile.classList.remove('rm-sig-green', 'rm-sig-amber', 'rm-sig-red', 'rm-sig-blue');
      var c = String(color || 'amber');
      if (c === 'green') tile.classList.add('rm-sig-green');
      else if (c === 'red') tile.classList.add('rm-sig-red');
      else if (c === 'blue') tile.classList.add('rm-sig-blue');
      else tile.classList.add('rm-sig-amber');
    }
    async function refreshReasoningModelBanner() {
      const st = document.getElementById('reasoningModelHeadV');
      const core = document.getElementById('reasoningModelCoreS');
      const cost = document.getElementById('reasoningModelCostS');
      const tile = document.getElementById('reasoningModelBannerTile');
      const gw = document.getElementById('rmExtGatewayChk');
      const addFunds = document.getElementById('rmAddFundsLink');
      if (!st) return;
      var q = '';
      try {
        if (typeof askDataPreferredJobId === 'function') {
          var jid0 = askDataPreferredJobId();
          if (jid0 && String(jid0).trim()) q = '?job_id=' + encodeURIComponent(String(jid0).trim());
        }
      } catch (_e) { /* */ }
      try {
        const r = await fetch('/api/reasoning-model/status' + q);
        const j = await r.json();
        if (!r.ok || !j.ok) {
          st.textContent = '—';
          if (core) core.textContent = 'Status unavailable';
          if (cost) cost.textContent = '';
          refreshReasoningModelTileClass(tile, 'red');
          return;
        }
        var f = j.fields_v1 || {};
        st.textContent = (f.headline_badge_v1 != null) ? String(f.headline_badge_v1) : (j.status_headline_v1 || '—');
        if (j.external_api_proof_line_v1) {
          st.setAttribute('data-external-line', String(j.external_api_proof_line_v1));
        } else {
          st.removeAttribute('data-external-line');
        }
        if (core) {
          var lines = f.ui_core_lines_v1;
          if (Array.isArray(lines) && lines.length) {
            core.innerHTML = lines.map(function (l) { return escapeHtml(String(l)); }).join('<br/>');
          } else {
            var extPl = f.external_api_proof_line_v1 != null ? String(f.external_api_proof_line_v1) : '—';
            core.textContent = extPl;
          }
        }
        if (cost) {
          var costS = (f.run_cost_display_v1 != null) ? String(f.run_cost_display_v1) : '$0.00';
          var capS = (f.budget_cap_display_v1 != null) ? String(f.budget_cap_display_v1) : '—';
          var lastR = (f.last_external_call_result_v1 != null) ? String(f.last_external_call_result_v1) : '—';
          var runBal = f.external_api_balance_status_v1 != null ? String(f.external_api_balance_status_v1) : '—';
          cost.textContent = 'Run cost: ' + costS + ' · Budget cap: ' + capS + ' · Run headroom: ' + runBal + ' · Last call: ' + lastR;
        }
        if (addFunds && j.add_funds_billing_url_v1) {
          addFunds.href = String(j.add_funds_billing_url_v1);
        }
        refreshReasoningModelTileClass(tile, j.tile_color_v1 || 'amber');
        if (tile) {
          var br = f.block_reasons_v1;
          var tok = f.tokens_current_run_v1 || {};
          var sum1 = (j.escalation_summary_v1 != null) ? String(j.escalation_summary_v1) : '';
          var code1 = (j.primary_escalation_code_v1 != null) ? String(j.primary_escalation_code_v1) : '';
          var dbg = (j.job_id_scoped != null) ? 'job_id (trace scope): ' + j.job_id_scoped : 'No job in URL — add ?job_id= to scope a run.';
          var msg = (f.operator_block_message_v1 != null && String(f.operator_block_message_v1).trim()) ? f.operator_block_message_v1 : '';
          tile.title = [
            (j.external_api_proof_line_v1 != null) ? String(j.external_api_proof_line_v1) : '',
            f.headline_badge_v1 != null ? 'Banner: ' + f.headline_badge_v1 : '',
            (msg || sum1) ? (msg || sum1) : '',
            (code1 ? 'Internal code (debug): ' + code1 : ''),
            dbg,
            f.funding_note_v1 != null ? String(f.funding_note_v1) : '',
            'Account balance (not queried on server): ' + (f.funding_account_balance_v1 || 'Unknown'),
            'Raw last_external_call: ' + (f.last_external_call || '—') + ' · tokens: ' + (tok && tok.input != null ? tok.input : '—') + ' in, ' + (tok && tok.output != null ? tok.output : '—') + ' out',
            (br && br.length) ? 'Blockers: ' + br.join(', ') : '',
          ].filter(function (x) { return x; }).join(String.fromCharCode(10));
        }
        if (gw && j.operator_external_api_gateway_allows_v1 != null) {
          gw.checked = !!j.operator_external_api_gateway_allows_v1;
        }
      } catch (e) {
        st.textContent = '—';
        if (core) core.textContent = friendlyFetchError(e);
        if (cost) cost.textContent = '';
        refreshReasoningModelTileClass(tile, 'red');
      }
    }
    (function wireReasoningModelGatewayToggle() {
      const gw = document.getElementById('rmExtGatewayChk');
      if (!gw) return;
      gw.addEventListener('change', async function () {
        const want = !!gw.checked;
        try {
          const r = await fetch('/api/reasoning-model/external-gateway', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ external_api_gateway_enabled: want }),
          });
          const j = await r.json();
          if (!r.ok || !j.ok) {
            gw.checked = !want;
            return;
          }
          void refreshReasoningModelBanner();
        } catch (_e) {
          gw.checked = !want;
        }
      });
    })();
    refreshReasoningModelBanner();
    setInterval(refreshReasoningModelBanner, 45000);

    function openModuleModal(m) {
      const d = document.getElementById('moduleDetailDialog');
      const t = document.getElementById('moduleModalTitle');
      const rr = document.getElementById('moduleModalRole');
      const b = document.getElementById('moduleModalBody');
      if (!d || !t || !b) return;
      t.textContent = m.title || m.label || m.id || 'Module';
      const roleMap = {
        ui: 'UI shell',
        core_replay: 'Core replay (Referee path)',
        evidence: 'Evidence / audit (does not change next run by itself)',
        behavioral_memory: 'Behavioral memory (promoted bundle may merge into manifest)',
        interpretation: 'Interpretation / notes',
        ops_suggestion: 'Suggestion / planning (not Referee truth)',
        narrative: 'Narrative / reporting (not Referee scoring)',
      };
      const rn = m.role ? (roleMap[m.role] || m.role) : '';
      if (rr) rr.textContent = rn ? ('Category: ' + rn) : '';
      b.textContent = (m.body != null && String(m.body).trim()) ? String(m.body) : String(m.detail || '');
      if (d.showModal) d.showModal();
    }
    (function wireModuleModalClose() {
      const d = document.getElementById('moduleDetailDialog');
      const c = document.getElementById('moduleModalClose');
      const inner = d ? d.querySelector('.pg-module-dialog-inner') : null;
      if (c && d) {
        c.addEventListener('click', function (ev) {
          ev.stopPropagation();
          if (d.close) d.close();
        });
      }
      if (inner && d && d.close) {
        inner.addEventListener('click', function () { d.close(); });
      }
      if (d) {
        d.addEventListener('click', function (ev) {
          if (ev.target === d && d.close) d.close();
        });
      }
    })();

    (function wireHowToDialog() {
      const d = document.getElementById('pgHowToDialog');
      const o = document.getElementById('pgHowToOpenBtn');
      const c = document.getElementById('pgHowToClose');
      if (o && d && d.showModal) {
        o.addEventListener('click', function () { d.showModal(); });
      }
      if (c && d) {
        c.addEventListener('click', function () { if (d.close) d.close(); });
      }
      if (d) {
        d.addEventListener('click', function (ev) {
          if (ev.target === d && d.close) d.close();
        });
      }
    })();

    async function refreshModuleBoard() {
      const list = document.getElementById('moduleBoardList');
      const dot = document.getElementById('moduleBannerDot');
      const bv = document.getElementById('bannerModulesV');
      const bs = document.getElementById('bannerModulesS');
      function moduleRowSignal(m) {
        if (m.signal === 'green' || m.signal === 'yellow' || m.signal === 'red') return m.signal;
        return m.ok ? 'green' : 'red';
      }
      function signalToDotClass(sig) {
        if (sig === 'green') return 'ok';
        if (sig === 'yellow') return 'warn';
        return 'bad';
      }
      function setModuleBanner(okCount, total, sub, bannerDotClass) {
        if (bv) bv.textContent = (total > 0) ? (okCount + '/' + total + ' passed') : '—';
        if (bs) bs.textContent = sub || '';
        if (dot) {
          if (!total) dot.className = 'status-dot';
          else dot.className = 'status-dot ' + (bannerDotClass || (okCount === total ? 'ok' : 'bad'));
        }
        const fSt = document.getElementById('focusTileModulesSt');
        const fLn = document.getElementById('focusTileModulesLine');
        if (fSt) fSt.textContent = (total > 0) ? (okCount + '/' + total) : '—';
        if (fLn) fLn.textContent = sub || '';
      }
      if (!list) return;
      try {
        const r = await fetch('/api/module-board');
        const j = await r.json();
        const errHtml = '<p class="caps pg-module-board-msg">Could not load module board.</p>';
        if (!r.ok || !j.ok) {
          list.innerHTML = errHtml;
          setModuleBanner(0, 0, 'Module API unavailable', '');
          return;
        }
        const mods = j.modules || [];
        if (!mods.length) {
          list.innerHTML = '<p class="caps pg-module-board-msg">No modules.</p>';
          setModuleBanner(0, 0, 'No rows', '');
          return;
        }
        list.innerHTML = '';
        let okCount = 0;
        let anyRed = false;
        let anyWarn = false;
        for (const m of mods) {
          const sig = moduleRowSignal(m);
          if (sig !== 'red') okCount++;
          if (sig === 'red') anyRed = true;
          else if (sig === 'yellow') anyWarn = true;
          const row = document.createElement('div');
          row.className = 'pg-status-item';
          row.setAttribute('role', 'button');
          row.setAttribute('tabindex', '0');
          const det = (m.detail != null) ? String(m.detail) : '';
          const dotCls = signalToDotClass(sig);
          row.innerHTML =
            '<span class="status-dot ' + dotCls + '" title="' + escapeHtml(det.slice(0, 500)) + '"></span>' +
            '<div><div class="pg-status-name">' + escapeHtml(m.label || m.id || '—') + '</div>' +
            '<div class="pg-status-meta">' + escapeHtml(det.slice(0, 280)) + '</div></div>';
          row.addEventListener('click', function () { openModuleModal(m); });
          row.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
              ev.preventDefault();
              openModuleModal(m);
            }
          });
          list.appendChild(row);
        }
        let bannerCls = 'ok';
        if (anyRed) bannerCls = 'bad';
        else if (anyWarn) bannerCls = 'warn';
        let sub = 'All wiring checks passed';
        if (anyRed) {
          const faults = mods.length - okCount;
          sub = okCount + ' ok · ' + faults + ' fault(s)';
        } else if (anyWarn) {
          sub = 'No faults · amber = idle/waiting (see Reasoning Model banner)';
        }
        setModuleBanner(okCount, mods.length, sub, bannerCls);
      } catch (e) {
        list.innerHTML = '<p class="caps pg-module-board-msg">' + escapeHtml(friendlyFetchError(e)) + '</p>';
        setModuleBanner(0, 0, 'Fetch failed', 'bad');
        if (dot) dot.className = 'status-dot bad';
      }
    }
    refreshModuleBoard();
    setInterval(refreshModuleBoard, 90000);

    (function wireStudentTrianglePersist() {
      try {
        const LS_H = 'patternGame.studentTriangle.foldBodyHeightPx';
        const LS_OPEN = 'patternGame.studentTriangle.detailsOpen';
        const details = document.getElementById('pgStudentTriangleDock');
        const body = document.getElementById('studentTriangleFoldBody');
        if (!details || !body) return;
        function clampHeightPx(h) {
          const minPx = 224;
          const maxPx = Math.max(minPx + 40, Math.floor(window.innerHeight * 0.88));
          let n = Math.round(Number(h));
          if (!Number.isFinite(n)) return null;
          return Math.max(minPx, Math.min(maxPx, n));
        }
        function applySavedHeight() {
          try {
            const raw = localStorage.getItem(LS_H);
            if (raw == null || raw === '') return;
            const yn = parseInt(raw, 10);
            const c = clampHeightPx(yn);
            if (c != null) body.style.height = c + 'px';
          } catch (_e) { /* ignore */ }
        }
        function persistHeightPx(h) {
          const c = clampHeightPx(h);
          if (c == null) return;
          try {
            localStorage.setItem(LS_H, String(c));
          } catch (_e) { /* ignore */ }
        }
        function persistOpen() {
          try {
            localStorage.setItem(LS_OPEN, details.open ? '1' : '0');
          } catch (_e) { /* ignore */ }
        }
        try {
          const o = localStorage.getItem(LS_OPEN);
          if (o === '1') details.open = true;
          else if (o === '0') details.open = false;
        } catch (_e) { /* ignore */ }
        requestAnimationFrame(function () { applySavedHeight(); });
        let baselineH = -1;
        let persistEnabled = false;
        setTimeout(function () {
          if (details.open) baselineH = body.offsetHeight;
          persistEnabled = true;
        }, 650);
        window.addEventListener('resize', function () {
          if (!details.open) return;
          var cur = body.offsetHeight;
          var c = clampHeightPx(cur);
          if (c != null && cur > c) {
            body.style.height = c + 'px';
            persistHeightPx(c);
          }
        }, { passive: true });
        if (typeof ResizeObserver === 'function') {
          let roTimer = null;
          var ro = new ResizeObserver(function () {
            if (!persistEnabled || !details.open) return;
            var h = body.offsetHeight;
            if (h < 8) return;
            if (baselineH >= 0 && Math.abs(h - baselineH) < 3) return;
            baselineH = h;
            clearTimeout(roTimer);
            roTimer = setTimeout(function () {
              persistHeightPx(h);
            }, 200);
          });
          ro.observe(body);
        }
        details.addEventListener('toggle', function () {
          persistOpen();
          if (details.open) {
            baselineH = body.offsetHeight;
          }
        });
        try {
          if (window.location.hash === '#pgStudentTriangleDock') {
            details.open = true;
            try {
              localStorage.setItem(LS_OPEN, '1');
            } catch (_h) { /* ignore */ }
            requestAnimationFrame(function () {
              try {
                details.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
              } catch (_s) { /* ignore */ }
            });
          }
        } catch (_g) { /* ignore */ }
      } catch (_e) { /* persist must never break the rest of the page */
      }
    })();

    async function refreshSearchSpaceEstimate() {
      const el = document.getElementById('searchSpaceStrip');
      if (!el) return;
      try {
        const w = rangeEl ? (parseInt(rangeEl.value, 10) || 1) : 1;
        const batchN = getEffectiveScenarioCount();
        const q = batchN > 0
          ? ('?batch_size=' + encodeURIComponent(batchN) + '&workers=' + encodeURIComponent(w))
          : ('?workers=' + encodeURIComponent(w));
        const r = await fetch('/api/search-space-estimate' + q);
        const j = await r.json();
        const m = j.catalog && j.catalog.signals_count;
        const sub = j.combinatorics && j.combinatorics.non_empty_signal_subsets_upper_bound;
        const bars = j.dataset && j.dataset.market_bars_5m_count;
        const rounds = j.workload_hints && j.workload_hints.parallel_rounds_ceil_batch_over_workers;
        const br = j.bar_replay_units;
        let line = '<strong>Search space</strong> — ';
        if (m != null && sub != null) {
          line += m + ' catalog signals → up to <strong>' + sub + '</strong> non-empty signal subsets (2^' + m + '−1; validation may disallow some). ';
        }
        if (bars != null) {
          line += '<strong>' + bars.toLocaleString() + '</strong> rows in <code>market_bars_5m</code>. ';
        } else if (j.dataset && j.dataset.error) {
          line += 'Bars: unavailable (' + String(j.dataset.error).slice(0, 120) + '). ';
        }
        if (batchN > 0 && rounds != null) {
          line += 'This batch: <strong>' + batchN + '</strong> scenario(s), <strong>' + w + '</strong> workers → ~<strong>' + rounds + '</strong> parallel round(s). ';
        } else {
          line += 'Pick a pattern (or Custom JSON) to see batch rounds; workers use slider (' + w + '). ';
        }
        if (br != null && batchN > 0) {
          line += 'Coarse bar steps ≈ ' + br.toLocaleString() + ' (scenarios×bars).';
        }
        el.innerHTML = line;
      } catch (e) {
        el.innerHTML = '<strong>Search space</strong> — could not load estimate. ' + friendlyFetchError(e);
      }
    }

    const operatorRecipePick = document.getElementById('operatorRecipePick');
    const evaluationWindowPick = document.getElementById('evaluationWindowPick');
    const tradeWindowPick = document.getElementById('tradeWindowPick');
    const evaluationWindowCustomMonths = document.getElementById('evaluationWindowCustomMonths');
    const customMonthsWrap = document.getElementById('customMonthsWrap');
    const examplesFilePick = document.getElementById('examplesFilePick');
    const scenariosEl = document.getElementById('scenarios');
    let PG_OPERATOR_RECIPES = [];
    let PG_POLICY_CATALOG = [];

    function recipeMeta(rid) {
      return PG_OPERATOR_RECIPES.find(function (x) { return x.recipe_id === rid; }) || null;
    }

    const CUSTOM_MODE_CARD = {
      sections: [
        {
          k: 'What it does',
          v: 'You define every scenario in JSON under Advanced. Each scenario runs one standard replay on historical bars using the manifest and fields you supply.',
        },
        {
          k: 'Candidates',
          v: 'No — this path does not run the operator harness. There is no built-in control-plus-candidate search here. Use Pattern Machine Learning (PML) or Reference Comparison if you need that.',
        },
        {
          k: 'Prior memory',
          v: 'Only if your JSON sets memory_bundle_path, or promoted-bundle auto-merge is on and the file exists. Otherwise replays use manifest defaults only.',
        },
        {
          k: 'Writes new memory',
          v: 'Not automatically. Optional experience log lines are audit only. Run does not promote parameters into the bundle file by itself.',
        },
        {
          k: 'Winner',
          v: 'No harness winner. You still get Referee outcome and PnL per scenario row on the scorecard.',
        },
        {
          k: 'Carries forward',
          v: 'Nothing automatic. Persistence requires explicit operator actions (for example POST promoted bundle or tools), not Run alone.',
        },
        {
          k: 'Use this when',
          v: 'Imports, uploads, one-off experiments, or anything not covered by the two curated patterns.',
        },
      ],
    };

    function renderPatternModeExplanation() {
      const host = document.getElementById('patternModeExplanationBody');
      if (!host) return;
      const rid = operatorRecipePick && operatorRecipePick.value;
      let card = null;
      if (rid === 'custom') {
        card = CUSTOM_MODE_CARD;
      } else {
        const m = recipeMeta(rid);
        card = m && m.operator_mode_card_v1;
      }
      if (!card || !card.sections || !card.sections.length) {
        if (rid && rid !== 'custom' && (!PG_OPERATOR_RECIPES || !PG_OPERATOR_RECIPES.length)) {
          host.textContent = 'Loading pattern details…';
        } else {
          host.textContent = '';
        }
        return;
      }
      const cardTitle = (card && card.title) ? String(card.title) : 'This pattern (read before Run)';
      let h = '<h3 class="pg-pattern-mode-h">' + escapeHtml(cardTitle) + '</h3><dl class="pg-pattern-mode-dl">';
      for (let i = 0; i < card.sections.length; i++) {
        const s = card.sections[i];
        h += '<dt>' + escapeHtml(s.k) + '</dt><dd>' + escapeHtml(s.v) + '</dd>';
      }
      h += '</dl>';
      host.innerHTML = h;
    }

    function syncCustomMonthsVisibility() {
      if (!customMonthsWrap || !evaluationWindowPick) return;
      customMonthsWrap.style.display = evaluationWindowPick.value === 'custom' ? '' : 'none';
    }

    function evaluationWindowLabel() {
      if (!evaluationWindowPick) return '—';
      const wm = evaluationWindowPick.value;
      if (wm === 'custom') {
        const cm = evaluationWindowCustomMonths ? parseInt(evaluationWindowCustomMonths.value, 10) : 0;
        return (cm && cm > 0) ? (String(cm) + ' months (custom)') : 'Custom months (set value)';
      }
      return wm + ' months';
    }

    function syncPolicyPickUi() {
      const multi = document.getElementById('policyMultiWrap');
      const ro = document.getElementById('policyReadonly');
      const pick = document.getElementById('policyPick');
      if (!multi || !ro || !pick) return;
      if (!PG_POLICY_CATALOG.length) {
        multi.style.display = 'none';
        ro.style.display = 'none';
        return;
      }
      if (PG_POLICY_CATALOG.length === 1) {
        multi.style.display = 'none';
        ro.style.display = 'block';
        ro.textContent = 'Policy: ' + (PG_POLICY_CATALOG[0].display_label || PG_POLICY_CATALOG[0].manifest_path);
      } else {
        ro.style.display = 'none';
        multi.style.display = 'block';
        pick.innerHTML = '';
        PG_POLICY_CATALOG.forEach(function (p) {
          const o = document.createElement('option');
          o.value = p.manifest_path;
          o.textContent = p.display_label || p.policy_id;
          pick.appendChild(o);
        });
      }
    }

    function policyLineForRunConfig() {
      if (PG_POLICY_CATALOG.length === 1) {
        return PG_POLICY_CATALOG[0].display_label || PG_POLICY_CATALOG[0].manifest_path;
      }
      const pick = document.getElementById('policyPick');
      const sel = pick && pick.selectedOptions && pick.selectedOptions[0];
      return sel ? sel.textContent : '—';
    }

    function updateRunConfigurationPanel() {
      const rr = document.getElementById('runConfigPattern');
      const rp = document.getElementById('runConfigPolicy');
      const rw = document.getElementById('runConfigWindow');
      const rtw = document.getElementById('runConfigTradeWindow');
      const rg = document.getElementById('runConfigGoalSummary');
      const rid = operatorRecipePick && operatorRecipePick.value;
      if (rr) rr.textContent = (operatorRecipePick && operatorRecipePick.selectedOptions[0])
        ? operatorRecipePick.selectedOptions[0].textContent : '—';
      if (rp) rp.textContent = policyLineForRunConfig();
      if (rw) rw.textContent = evaluationWindowLabel();
      if (rtw) rtw.textContent = tradeWindowLabel();
      if (!rg) return;
      if (!rid || rid === 'custom') {
        rg.textContent = 'Defined in your JSON (Advanced).';
      } else {
        const m = recipeMeta(rid);
        const gs = m && m.goal_summary;
        rg.textContent = gs && gs.title ? gs.title : '—';
      }
      const gTitle = document.getElementById('goalReadonlyTitle');
      const gMet = document.getElementById('goalReadonlyMetrics');
      const gCon = document.getElementById('goalReadonlyConstraints');
      const gNote = document.getElementById('goalReadonlyNote');
      if (rid === 'custom') {
        if (gTitle) gTitle.textContent = 'Custom scenario';
        if (gMet) gMet.textContent = 'Goal, manifest, and window must appear in your JSON (or rely on server merge for evaluation window + trade window from Controls above).';
        if (gCon) gCon.textContent = '';
        if (gNote) gNote.textContent = 'Open Advanced → Custom scenario (JSON) to edit.';
      } else {
        const m = recipeMeta(rid);
        const gs = m && m.goal_summary;
        if (gTitle) gTitle.textContent = gs && gs.title ? gs.title : '—';
        if (gMet) gMet.textContent = (gs && gs.primary_metric)
          ? ('Primary metric: ' + gs.primary_metric + (gs.goal_name && gs.goal_name !== '—' ? ' · Goal id: ' + gs.goal_name : ''))
          : '';
        if (gCon) gCon.textContent = (gs && gs.constraints_line) ? ('Constraints: ' + gs.constraints_line) : '';
        if (gNote) gNote.textContent = (gs && gs.note) ? gs.note : '';
      }
      renderPatternModeExplanation();
    }

    function applyRecipeModeToTextarea() {
      const rid = operatorRecipePick && operatorRecipePick.value;
      const isCustom = rid === 'custom';
      const hint = document.getElementById('structuredJsonHint');
      const ad = document.getElementById('advancedJsonDetails');
      if (scenariosEl) {
        scenariosEl.disabled = !isCustom;
        scenariosEl.title = isCustom ? 'Edit scenario JSON for this run' : 'Disabled — server builds scenarios for curated patterns.';
      }
      if (hint) {
        hint.textContent = isCustom
          ? 'Edit JSON below. It is validated on Run (same contract as before).'
          : 'Disabled for curated patterns — server injects manifest, evaluation window, goal, and pattern metadata.';
      }
      const routeHint = document.getElementById('customScenarioRouteHint');
      if (routeHint) routeHint.hidden = !isCustom;
      if (isCustom) {
        const pif = document.getElementById('patternInfoFold');
        const aop = document.getElementById('advancedOperatorPanel');
        const ajd = document.getElementById('advancedJsonDetails');
        if (pif) pif.open = true;
        if (aop) aop.open = true;
        if (ajd) ajd.open = true;
        if (scenariosEl) {
          requestAnimationFrame(function () {
            try {
              scenariosEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            } catch (e) { /* ignore */ }
          });
        }
      }
      if (!isCustom && scenariosEl) {
        scenariosEl.value = '';
      }
    }

    async function refreshStructuredMetadata() {
      if (!operatorRecipePick || !evaluationWindowPick) return;
      const rid = operatorRecipePick.value;
      syncCustomMonthsVisibility();
      applyRecipeModeToTextarea();
      updateRunConfigurationPanel();
      if (rid === 'custom') {
        STRUCTURED_SCENARIO_COUNT = 1;
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
        return;
      }
      const wm = evaluationWindowPick.value;
      let url = '/api/operator-recipe-preview?recipe_id=' + encodeURIComponent(rid) +
        '&evaluation_window_mode=' + encodeURIComponent(wm);
      if (wm === 'custom') {
        const cm = evaluationWindowCustomMonths ? parseInt(evaluationWindowCustomMonths.value, 10) : 36;
        url += '&evaluation_window_custom_months=' + encodeURIComponent(String(cm && cm > 0 ? cm : 36));
      }
      try {
        const r = await fetch(url);
        const j = await r.json();
        if (!r.ok || !j.ok) {
          const preErr = document.getElementById('out');
          if (preErr) preErr.innerHTML = '<span class="err">Run setup: ' + escapeHtml(j.error || r.status) + '</span>';
          pgFocusEnterPanel('results');
          setEvidenceTab('json');
          return;
        }
        STRUCTURED_SCENARIO_COUNT = typeof j.scenario_count === 'number' && j.scenario_count > 0 ? j.scenario_count : 1;
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
      } catch (e) {
        const preCatch = document.getElementById('out');
        if (preCatch) preCatch.innerHTML = '<span class="err">' + escapeHtml(friendlyFetchError(e)) + '</span>';
        pgFocusEnterPanel('results');
        setEvidenceTab('json');
      }
    }

    async function loadOperatorRecipesApi() {
      try {
        const r = await fetch('/api/operator-recipes');
        const j = await r.json();
        if (!r.ok || !j.ok) return;
        PG_OPERATOR_RECIPES = j.recipes || [];
        PG_POLICY_CATALOG = j.policy_catalog || [];
        syncPolicyPickUi();
        updateRunConfigurationPanel();
        if (typeof refreshStrategyUploadState === 'function') await refreshStrategyUploadState();
      } catch (e) { /* non-fatal */ }
    }

    async function refreshStrategyUploadState() {
      const stage = document.getElementById('strategyUploadStageLine');
      const ul = document.getElementById('strategyUploadChecklist');
      if (!ul) return;
      try {
        const r = await fetch('/api/operator-strategy-upload/state');
        const st = await r.json();
        if (!st.ok) throw new Error(st.error || 'state');
        const items = [];
        const yn = function (b) { return b ? 'YES' : 'NO'; };
        if (st.has_active_upload) {
          if (stage) stage.textContent = 'Active operator strategy is loaded — use the checkbox below to apply it on the next run.';
          items.push({ cls: 'su-ok', t: 'Strategy uploaded: ' + yn(st.strategy_uploaded) });
          items.push({ cls: 'su-ok', t: 'Strategy validated: ' + yn(st.strategy_validated) });
          items.push({ cls: 'su-ok', t: 'Strategy loaded: ' + yn(st.strategy_loaded) });
          items.push({
            cls: 'su-ok',
            t:
              'Loaded strategy — id: ' +
              escapeHtml(String(st.strategy_id || '—')) +
              ' · name: ' +
              escapeHtml(String(st.strategy_name || '—')),
          });
          items.push({ cls: 'su-ok', t: 'Manifest path: ' + escapeHtml(String(st.manifest_repo_relative || '—')) });
          items.push({ cls: 'su-ok', t: 'Ready to run: ' + yn(st.ready_to_run) + ' (with “Use uploaded strategy” checked)' });
          if (st.pattern_recommendation) {
            const pr = st.pattern_recommendation;
            items.push({
              cls: 'su-warn',
              t:
                'Recommended Pattern: ' +
                escapeHtml(String(pr.label || pr.primary_recipe_id || '')) +
                ' — ' +
                escapeHtml(String(pr.reason || '')),
            });
          }
        } else {
          if (stage) stage.textContent = 'No operator-uploaded strategy is active — runs use each scenario’s manifest (curated recipes default to baseline).';
          items.push({ cls: 'su-warn', t: 'Strategy uploaded (active): NO' });
          items.push({
            cls: 'su-warn',
            t: 'Built-in default manifest: ' + escapeHtml(String(st.default_baseline_manifest || '')),
          });
        }
        ul.innerHTML = items
          .map(function (it) {
            return '<li class="' + it.cls + '">' + it.t + '</li>';
          })
          .join('');
      } catch (e) {
        if (stage) stage.textContent = 'Could not read strategy upload state.';
        ul.innerHTML = '<li class="su-fail">' + escapeHtml(String(e && e.message ? e.message : e)) + '</li>';
      }
    }

    async function postStrategyIdeaUpload(file) {
      if (!file) return;
      const stage = document.getElementById('strategyUploadStageLine');
      const ul = document.getElementById('strategyUploadChecklist');
      if (stage) stage.textContent = 'Uploading → validating → converting → loading…';
      if (ul) ul.innerHTML = '<li class="su-warn">Processing…</li>';
      const fd = new FormData();
      fd.append('file', file, file.name);
      try {
        const r = await fetch('/api/operator-strategy-upload', { method: 'POST', body: fd });
        const j = await r.json();
        if (ul && j.stages && j.stages.length) {
          ul.innerHTML = j.stages
            .map(function (s) {
              const ok = s.ok ? 'su-ok' : 'su-fail';
              return '<li class="' + ok + '">' + escapeHtml(s.name) + ': ' + escapeHtml(s.detail || '') + '</li>';
            })
            .join('');
        }
        if (!r.ok || !j.ok) {
          if (stage) stage.textContent = 'Upload finished with failure — see checklist and errors below.';
          if (ul && j.errors && j.errors.length) {
            j.errors.forEach(function (err) {
              ul.insertAdjacentHTML('beforeend', '<li class="su-fail">' + escapeHtml(String(err)) + '</li>');
            });
          }
          await show(null, null, String(j.error || (j.errors && j.errors[0]) || 'Strategy upload failed'));
        } else {
          if (stage) stage.textContent = 'Success — strategy is loaded. Review recommendation, then Run.';
          if (j.pattern_recommendation && document.getElementById('operatorRecipePick')) {
            const pid = j.pattern_recommendation.primary_recipe_id;
            const sel = document.getElementById('operatorRecipePick');
            if (pid && sel && Array.from(sel.options).some(function (o) { return o.value === pid; })) {
              sel.value = pid;
              refreshStructuredMetadata();
            }
          }
        }
      } catch (e) {
        if (stage) stage.textContent = 'Network or server error during upload.';
        if (ul) ul.innerHTML = '<li class="su-fail">' + escapeHtml(String(e && e.message ? e.message : e)) + '</li>';
      }
      await refreshStrategyUploadState();
    }

    async function loadExamplesFile(name) {
      if (!name) return;
      const r = await fetch('/api/scenario-preset?name=' + encodeURIComponent(name));
      if (!r.ok) {
        const preEx = document.getElementById('out');
        if (preEx) preEx.innerHTML = '<span class="err">Example file load failed: ' + r.status + '</span>';
        pgFocusEnterPanel('results');
        setEvidenceTab('json');
        return;
      }
      const j = await r.json();
      if (j.ok) {
        if (!scenariosEl) return;
        scenariosEl.value = j.content;
        if (operatorRecipePick) operatorRecipePick.value = 'custom';
        applyRecipeModeToTextarea();
        updateRunConfigurationPanel();
        const ad = document.getElementById('advancedJsonDetails');
        const outer = document.getElementById('advancedOperatorPanel');
        if (outer && outer.open === false) outer.open = true;
        if (ad) ad.open = true;
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
      }
    }

    function updateRenameButton() {
      const btn = document.getElementById('presetRenameBtn');
      const v = examplesFilePick && examplesFilePick.value;
      if (btn) btn.disabled = !v || v.indexOf('user_') !== 0;
    }

    async function populateExamplesFileDropdown(selectFilename) {
      const r = await fetch('/api/scenario-presets');
      const rows = await r.json();
      if (!examplesFilePick) return rows;
      examplesFilePick.innerHTML = '<option value="">— pick file —</option>';
      rows.forEach((row) => {
        const o = document.createElement('option');
        o.value = row.filename;
        o.textContent = row.label || row.filename;
        examplesFilePick.appendChild(o);
      });
      if (selectFilename) {
        const has = Array.from(examplesFilePick.options).some(function (opt) { return opt.value === selectFilename; });
        if (has) examplesFilePick.value = selectFilename;
      }
      updateRenameButton();
      return rows;
    }

    let pendingUploadFile = null;

    function resetUploadDialog() {
      const res = document.getElementById('uploadPresetResult');
      const sp = document.getElementById('uploadDialogSpinner');
      const sub = document.getElementById('uploadPresetSubmitBtn');
      const done = document.getElementById('uploadPresetDoneBtn');
      const ni = document.getElementById('uploadPresetNameInput');
      if (res) { res.className = 'pg-upload-result'; res.textContent = ''; res.classList.remove('visible', 'ok', 'err'); }
      if (sp) sp.classList.remove('visible');
      if (sub) {
        sub.style.display = '';
        setOpButtonBusy(sub, false);
      }
      if (done) done.style.display = 'none';
      if (ni) ni.value = '';
      pendingUploadFile = null;
      var fiClear = document.getElementById('presetFileInput');
      if (fiClear) fiClear.value = '';
    }

    const presetUploadBtn = document.getElementById('presetUploadBtn');
    const presetFileInput = document.getElementById('presetFileInput');
    const uploadDlg = document.getElementById('uploadPresetDialog');
    const uploadPresetNameInput = document.getElementById('uploadPresetNameInput');
    const uploadPresetResult = document.getElementById('uploadPresetResult');
    const uploadDialogSpinner = document.getElementById('uploadDialogSpinner');
    const uploadPresetSubmitBtn = document.getElementById('uploadPresetSubmitBtn');
    const uploadPresetCancelBtn = document.getElementById('uploadPresetCancelBtn');
    const uploadPresetDoneBtn = document.getElementById('uploadPresetDoneBtn');
    const uploadChosenFileLabel = document.getElementById('uploadChosenFileLabel');

    if (presetUploadBtn && presetFileInput) {
      presetUploadBtn.addEventListener('click', function () { presetFileInput.click(); });
      presetFileInput.addEventListener('change', function () {
        const f = presetFileInput.files && presetFileInput.files[0];
        pendingUploadFile = f || null;
        if (!f) return;
        if (uploadChosenFileLabel) {
          uploadChosenFileLabel.textContent = 'Selected file: ' + f.name + ' (' + (f.size / 1024).toFixed(1) + ' KB)';
        }
        resetUploadDialog();
        if (uploadPresetNameInput) uploadPresetNameInput.value = f.name.replace(/\\.json$/i, '').replace(/[_-]+/g, ' ');
        if (uploadPresetResult) { uploadPresetResult.classList.remove('visible', 'ok', 'err'); uploadPresetResult.textContent = ''; }
        if (uploadDlg && uploadDlg.showModal) uploadDlg.showModal();
        if (uploadPresetNameInput) uploadPresetNameInput.focus();
      });
    }

    if (uploadPresetCancelBtn && uploadDlg) {
      uploadPresetCancelBtn.addEventListener('click', function () {
        if (uploadDlg.close) uploadDlg.close();
        resetUploadDialog();
      });
    }

    if (uploadPresetSubmitBtn) {
      uploadPresetSubmitBtn.addEventListener('click', async function () {
        if (!pendingUploadFile) {
          if (uploadPresetResult) {
            uploadPresetResult.className = 'pg-upload-result visible err';
            uploadPresetResult.textContent = 'FAIL — choose a .json file first (use Upload preset…).';
          }
          return;
        }
        const name = (uploadPresetNameInput && uploadPresetNameInput.value) ? uploadPresetNameInput.value.trim() : '';
        if (!name) {
          if (uploadPresetResult) {
            uploadPresetResult.className = 'pg-upload-result visible err';
            uploadPresetResult.textContent = 'FAIL — enter a preset name.';
          }
          return;
        }
        if (uploadDialogSpinner) uploadDialogSpinner.classList.add('visible');
        if (uploadPresetResult) {
          uploadPresetResult.className = 'pg-upload-result visible';
          uploadPresetResult.style.background = '#f4f1ea';
          uploadPresetResult.style.border = '1px solid var(--pg-line)';
          uploadPresetResult.textContent = 'Validating…';
        }
        setOpButtonBusy(uploadPresetSubmitBtn, true, 'Saving…', true);
        const fd = new FormData();
        fd.append('file', pendingUploadFile, pendingUploadFile.name);
        fd.append('preset_name', name);
        try {
          const r = await fetch('/api/scenario-preset-upload', { method: 'POST', body: fd });
          const j = await r.json();
          if (j.ok) {
            if (uploadPresetResult) {
              uploadPresetResult.className = 'pg-upload-result visible ok';
              uploadPresetResult.textContent = 'PASS — Saved as ' + j.filename + '. Appears under Advanced → Load example file; switch Pattern to Custom to run.';
            }
            if (uploadPresetSubmitBtn) uploadPresetSubmitBtn.style.display = 'none';
            if (uploadPresetDoneBtn) uploadPresetDoneBtn.style.display = '';
            await populateExamplesFileDropdown(j.filename);
            await loadExamplesFile(j.filename);
            if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
            refreshWorkerEffectiveLine();
          } else {
            if (uploadPresetResult) {
              uploadPresetResult.className = 'pg-upload-result visible err';
              uploadPresetResult.textContent = 'FAIL — ' + (j.error || r.status);
            }
          }
        } catch (e) {
          if (uploadPresetResult) {
            uploadPresetResult.className = 'pg-upload-result visible err';
            uploadPresetResult.textContent = 'FAIL — ' + friendlyFetchError(e);
          }
        } finally {
          if (uploadDialogSpinner) uploadDialogSpinner.classList.remove('visible');
          setOpButtonBusy(uploadPresetSubmitBtn, false);
        }
      });
    }

    if (uploadPresetDoneBtn && uploadDlg) {
      uploadPresetDoneBtn.addEventListener('click', function () {
        if (uploadDlg.close) uploadDlg.close();
        resetUploadDialog();
      });
    }

    const renameDlg = document.getElementById('renamePresetDialog');
    const renamePresetBtn = document.getElementById('presetRenameBtn');
    const renamePresetInput = document.getElementById('renamePresetInput');
    const renamePresetResult = document.getElementById('renamePresetResult');
    const renameDialogSpinner = document.getElementById('renameDialogSpinner');
    const renamePresetSubmitBtn = document.getElementById('renamePresetSubmitBtn');
    const renamePresetCancelBtn = document.getElementById('renamePresetCancelBtn');

    if (renamePresetBtn && renameDlg && renameDlg.showModal) {
      renamePresetBtn.addEventListener('click', function () {
        const v = examplesFilePick && examplesFilePick.value;
        if (!v || v.indexOf('user_') !== 0) return;
        if (renamePresetResult) { renamePresetResult.className = 'pg-upload-result'; renamePresetResult.textContent = ''; }
        if (renamePresetInput) renamePresetInput.value = v.replace(/^user_/, '').replace(/\\.json$/, '').replace(/_/g, ' ');
        renameDlg.showModal();
        if (renamePresetInput) renamePresetInput.focus();
      });
    }
    if (renamePresetCancelBtn && renameDlg) {
      renamePresetCancelBtn.addEventListener('click', function () { if (renameDlg.close) renameDlg.close(); });
    }
    if (renamePresetSubmitBtn) {
      renamePresetSubmitBtn.addEventListener('click', async function () {
        const oldFn = examplesFilePick && examplesFilePick.value;
        const newName = (renamePresetInput && renamePresetInput.value) ? renamePresetInput.value.trim() : '';
        if (!oldFn || !newName) return;
        if (renameDialogSpinner) renameDialogSpinner.classList.add('visible');
        setOpButtonBusy(renamePresetSubmitBtn, true, 'Renaming…', true);
        try {
          const r = await fetch('/api/scenario-preset-rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_filename: oldFn, new_preset_name: newName }),
          });
          const j = await r.json();
          if (j.ok) {
            if (renamePresetResult) {
              renamePresetResult.className = 'pg-upload-result visible ok';
              renamePresetResult.textContent = 'PASS — Renamed to ' + j.filename;
            }
            await populateExamplesFileDropdown(j.filename);
            await loadExamplesFile(j.filename);
            if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
            refreshWorkerEffectiveLine();
            setTimeout(function () { if (renameDlg.close) renameDlg.close(); }, 900);
          } else {
            if (renamePresetResult) {
              renamePresetResult.className = 'pg-upload-result visible err';
              renamePresetResult.textContent = 'FAIL — ' + (j.error || 'rename failed');
            }
          }
        } catch (e) {
          if (renamePresetResult) {
            renamePresetResult.className = 'pg-upload-result visible err';
            renamePresetResult.textContent = 'FAIL — ' + friendlyFetchError(e);
          }
        } finally {
          if (renameDialogSpinner) renameDialogSpinner.classList.remove('visible');
          setOpButtonBusy(renamePresetSubmitBtn, false);
        }
      });
    }

    (async function initOperatorUi() {
      try {
        await loadOperatorRecipesApi();
        await populateExamplesFileDropdown(null);
        if (operatorRecipePick) operatorRecipePick.value = 'pattern_learning';
        syncCustomMonthsVisibility();
        applyRecipeModeToTextarea();
        await refreshStructuredMetadata();
        if (typeof refreshSearchSpaceEstimate === 'function') await refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
      } catch (e) {
        console.error('initOperatorUi failed:', e);
      }
    })();

    const strategyIdeaFileInput = document.getElementById('strategyIdeaFileInput');
    const strategyUploadPickBtn = document.getElementById('strategyUploadPickBtn');
    if (strategyUploadPickBtn && strategyIdeaFileInput) {
      strategyUploadPickBtn.addEventListener('click', function () {
        strategyIdeaFileInput.click();
      });
    }
    if (strategyIdeaFileInput) {
      strategyIdeaFileInput.addEventListener('change', function () {
        const f = strategyIdeaFileInput.files && strategyIdeaFileInput.files[0];
        strategyIdeaFileInput.value = '';
        if (f) postStrategyIdeaUpload(f);
      });
    }
    const strategyUploadClearBtn = document.getElementById('strategyUploadClearBtn');
    if (strategyUploadClearBtn) {
      strategyUploadClearBtn.addEventListener('click', async function () {
        try {
          await fetch('/api/operator-strategy-upload/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
          });
        } catch (e) {}
        await refreshStrategyUploadState();
      });
    }

    if (evaluationWindowPick) evaluationWindowPick.addEventListener('change', function () {
      syncCustomMonthsVisibility();
      refreshStructuredMetadata();
    });
    if (tradeWindowPick) tradeWindowPick.addEventListener('change', function () {
      updateRunConfigurationPanel();
      refreshStructuredMetadata();
    });
    if (evaluationWindowCustomMonths) evaluationWindowCustomMonths.addEventListener('change', function () {
      refreshStructuredMetadata();
    });
    if (evaluationWindowCustomMonths) evaluationWindowCustomMonths.addEventListener('input', function () {
      const cm = evaluationWindowCustomMonths;
      const maxS = cm.getAttribute('max');
      if (!maxS) return;
      const mx = parseInt(maxS, 10);
      const v = parseInt(cm.value, 10);
      if (Number.isFinite(mx) && Number.isFinite(v) && v > mx) cm.value = String(mx);
    });
    if (operatorRecipePick) operatorRecipePick.addEventListener('change', function () {
      refreshStructuredMetadata();
    });

    if (scenariosEl) {
      scenariosEl.addEventListener('input', () => {
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
      });
    }

    if (examplesFilePick) examplesFilePick.addEventListener('change', function () {
      updateRenameButton();
      const name = examplesFilePick.value;
      if (!name) {
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
        return;
      }
      loadExamplesFile(name)
        .then(function () {
          if (typeof refreshSearchSpaceEstimate === 'function') return refreshSearchSpaceEstimate();
        })
        .then(function () { refreshWorkerEffectiveLine(); })
        .catch(function (e) {
          const preCatch2 = document.getElementById('out');
          if (preCatch2) preCatch2.innerHTML = '<span class="err">' + String(e) + '</span>';
          pgFocusEnterPanel('results');
          setEvidenceTab('json');
        });
    });

    if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
    refreshWorkerEffectiveLine();
    const askDataSendBtn = document.getElementById('askDataSendBtn');
    const askDataClearBtn = document.getElementById('askDataClearBtn');
    const askDataInputEl = document.getElementById('askDataInput');
    if (askDataSendBtn) {
      askDataSendBtn.addEventListener('click', function () { void sendAskData(); });
    }
    if (askDataClearBtn) {
      askDataClearBtn.addEventListener('click', function () { clearAskDataUi(); });
    }
    if (askDataInputEl) {
      askDataInputEl.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) {
          ev.preventDefault();
          void sendAskData();
        }
      });
    }
    (function wireAskDataStarterChips() {
      const col = document.querySelector('.pg-barney-ask-col--ask');
      const inp = document.getElementById('askDataInput');
      if (!col || !inp) return;
      col.addEventListener('click', function (ev) {
        const t = ev.target;
        if (!t || !t.closest) return;
        const chip = t.closest('button.pg-askdata-chip[data-ask]');
        if (!chip || !col.contains(chip)) return;
        const q = chip.getAttribute('data-ask');
        if (!q) return;
        ev.preventDefault();
        inp.value = q;
        void sendAskData();
      });
    })();

    (function wireAskDataReplyShellDrag() {
      const LS_H = 'patternGame.askDataReplyShellHeightPx';
      const shell = document.getElementById('pgAskDataReplyShell');
      const drag = document.getElementById('pgAskDataReplyDrag');
      const grid = document.querySelector('.pg-barney-ask-unified .pg-barney-ask-grid');
      const details = document.getElementById('pgBarneyAskUnified');
      if (!shell || !drag || !grid) return;

      function maxShellPx() {
        try {
          const gr = grid.getBoundingClientRect();
          if (gr.height < 100) return 560;
          const recapMin = 120;
          const pad = 36;
          return Math.max(200, Math.floor(gr.height - recapMin - pad));
        } catch (_e) {
          return 520;
        }
      }

      function clampPx(h) {
        const minPx = 140;
        const maxPx = maxShellPx();
        let n = Math.round(Number(h));
        if (!Number.isFinite(n)) return null;
        return Math.max(minPx, Math.min(maxPx, n));
      }

      function applySavedHeight() {
        try {
          const raw = localStorage.getItem(LS_H);
          if (raw == null || raw === '') return;
          const y = parseInt(raw, 10);
          const c = clampPx(y);
          if (c == null) return;
          shell.classList.add('pg-askdata-reply-shell--sized');
          shell.style.height = c + 'px';
        } catch (_e) { /* ignore */ }
      }

      function persistHeightPx(h) {
        const c = clampPx(h);
        if (c == null) return;
        try {
          localStorage.setItem(LS_H, String(c));
        } catch (_e) { /* ignore */ }
      }

      requestAnimationFrame(function () {
        applySavedHeight();
      });

      drag.addEventListener('mousedown', function (ev) {
        if (ev.button !== 0) return;
        ev.preventDefault();
        shell.classList.add('pg-askdata-reply-shell--sized');
        const startY = ev.clientY;
        const startH = shell.getBoundingClientRect().height;
        document.body.style.cursor = 'row-resize';
        document.body.style.userSelect = 'none';

        function onMove(e) {
          const dy = e.clientY - startY;
          const nh = clampPx(startH + dy);
          if (nh != null) shell.style.height = nh + 'px';
        }
        function onUp() {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          document.body.style.cursor = '';
          document.body.style.userSelect = '';
          persistHeightPx(shell.getBoundingClientRect().height);
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      });

      window.addEventListener(
        'resize',
        function () {
          if (!details || !details.open) return;
          const cur = shell.getBoundingClientRect().height;
          const c = clampPx(cur);
          if (c != null && cur > c) {
            shell.style.height = c + 'px';
            persistHeightPx(c);
          }
        },
        { passive: true }
      );

      if (details) {
        details.addEventListener('toggle', function () {
          if (details.open) requestAnimationFrame(applySavedHeight);
        });
      }
    })();
    async function resumeParallelJobFromStorageIfAny() {
      let jid = null;
      try {
        jid = localStorage.getItem(PG_PARALLEL_INFLIGHT_JOB_LS);
      } catch (e) {
        return;
      }
      if (!jid || !/^[a-f0-9]{32}$/i.test(String(jid).trim())) return;
      jid = String(jid).trim();
      let pj0 = null;
      try {
        const pr = await fetch('/api/run-parallel/status/' + encodeURIComponent(jid));
        pj0 = await pr.json();
        if (!pr.ok) {
          pgSetInflightJobId(null);
          return;
        }
      } catch (e) {
        return;
      }
      if (pj0.status === 'running') {
        document.body.classList.add('pg-run-active');
        resetStudentTriangleStarting();
        void refreshStudentPanelD11({ soft: true });
        updateRunStatusLine('Resuming — batch still running (page was refreshed)…');
        const resumeT0 = Date.now();
        renderLiveTelemetryPanel(pj0, {
          elapsedSec: 0,
          recipeLabel: recipeLabelFromDom(),
          windowLabel: evaluationWindowLabelFromDom(),
        });
        const resumeCancelBtn = document.getElementById('parallelCancelBtn');
        if (resumeCancelBtn) {
          resumeCancelBtn.style.display = 'inline-block';
          resumeCancelBtn.disabled = false;
        }
        const deadline = Date.now() + RUN_TIMEOUT_MS;
        while (Date.now() < deadline) {
          let pj = null;
          try {
            const pr2 = await fetch('/api/run-parallel/status/' + encodeURIComponent(jid));
            pj = await pr2.json();
            if (!pr2.ok) break;
          } catch (e) {
            break;
          }
          if (pj.status === 'error') {
            pgSetInflightJobId(null);
            document.body.classList.remove('pg-run-active');
            if (resumeCancelBtn) {
              resumeCancelBtn.style.display = 'none';
              resumeCancelBtn.disabled = false;
            }
            const resumeElapsedErr = Math.floor((Date.now() - resumeT0) / 1000);
            renderLiveTelemetryPanel(pj, {
              elapsedSec: resumeElapsedErr,
              recipeLabel: recipeLabelFromDom(),
              windowLabel: evaluationWindowLabelFromDom(),
            });
            renderStudentTriangleBatchFailed(pj.error || 'Job failed');
            if (pj.batch_timing) updateLastBatchRunLine(pj.batch_timing);
            await show(null, null, friendlyParallelBackendError(pj.error || 'Job failed'));
            void refreshStudentPanelD11({ soft: true });
            refreshScorecardHistory();
            return;
          }
          if (pj.status === 'cancelled') {
            pgSetInflightJobId(null);
            document.body.classList.remove('pg-run-active');
            if (resumeCancelBtn) {
              resumeCancelBtn.style.display = 'none';
              resumeCancelBtn.disabled = false;
            }
            const resumeElapsedCan = Math.floor((Date.now() - resumeT0) / 1000);
            renderLiveTelemetryPanel(pj, {
              elapsedSec: resumeElapsedCan,
              recipeLabel: recipeLabelFromDom(),
              windowLabel: evaluationWindowLabelFromDom(),
            });
            if (pj.batch_timing) updateLastBatchRunLine(pj.batch_timing);
            await show(null, null, String(pj.error || 'Batch cancelled.'));
            renderStudentTriangleBatchFailed(String(pj.error || 'Batch cancelled.'));
            void refreshStudentPanelD11({ soft: true });
            refreshScorecardHistory();
            updateRunStatusLine('Cancelled — see scorecard (status cancelled).');
            return;
          }
          if (pj.status === 'done') {
            pgSetInflightJobId(null);
            document.body.classList.remove('pg-run-active');
            if (resumeCancelBtn) {
              resumeCancelBtn.style.display = 'none';
              resumeCancelBtn.disabled = false;
            }
            const resumeElapsedDone = Math.floor((Date.now() - resumeT0) / 1000);
            renderLiveTelemetryPanel(pj, {
              elapsedSec: resumeElapsedDone,
              recipeLabel: recipeLabelFromDom(),
              windowLabel: evaluationWindowLabelFromDom(),
            });
            if (pj.result) {
              updateMemoryStatusFromBatchResultPayload(pj.result);
              await show(null, pj.result, null);
            }
            refreshScorecardHistory();
            askDataLastRunJobId = jid;
            void fetchBarneySummary(jid);
            void refreshStudentPanelD11({ soft: true });
            updateRunStatusLine('Finished — batch completed (restored after refresh).');
            return;
          }
          const resumeElapsedPoll = Math.floor((Date.now() - resumeT0) / 1000);
          renderLiveTelemetryPanel(pj, {
            elapsedSec: resumeElapsedPoll,
            recipeLabel: recipeLabelFromDom(),
            windowLabel: evaluationWindowLabelFromDom(),
          });
          void refreshStudentPanelD11({ soft: true });
          refreshScorecardHistory();
          await new Promise(function (r) {
            setTimeout(r, 1500);
          });
        }
        pgSetInflightJobId(null);
        document.body.classList.remove('pg-run-active');
        if (resumeCancelBtn) {
          resumeCancelBtn.style.display = 'none';
          resumeCancelBtn.disabled = false;
        }
        renderLiveTelemetryPanel(
          { status: 'error', completed: 0, total: 0, telemetry_context_echo: {} },
          {
            elapsedSec: Math.floor(RUN_TIMEOUT_MS / 1000),
            recipeLabel: recipeLabelFromDom(),
            windowLabel: evaluationWindowLabelFromDom(),
          }
        );
        await show(
          null,
          null,
          'Timed out while resuming — job may still run on server; open /api/run-parallel/status/' + jid
        );
        renderStudentTriangleBatchFailed('Resume timeout — job may still be running on the server.');
        void refreshStudentPanelD11({ soft: true });
        return;
      }
      if (pj0.status === 'done') {
        pgSetInflightJobId(null);
        renderLiveTelemetryPanel(pj0, {
          elapsedSec: 0,
          recipeLabel: recipeLabelFromDom(),
          windowLabel: evaluationWindowLabelFromDom(),
        });
        if (pj0.result) {
          updateMemoryStatusFromBatchResultPayload(pj0.result);
          await show(null, pj0.result, null);
        }
        void refreshStudentPanelD11({ soft: true });
        refreshScorecardHistory();
        return;
      }
      if (pj0.status === 'error') {
        pgSetInflightJobId(null);
        renderLiveTelemetryPanel(pj0, {
          elapsedSec: 0,
          recipeLabel: recipeLabelFromDom(),
          windowLabel: evaluationWindowLabelFromDom(),
        });
        renderStudentTriangleBatchFailed(pj0.error || 'Job failed');
        await show(null, null, friendlyParallelBackendError(pj0.error || 'Job failed'));
        void refreshStudentPanelD11({ soft: true });
        return;
      }
      if (pj0.status === 'cancelled') {
        pgSetInflightJobId(null);
        updateMemoryStatusCardFromPanel(null, pj0.telemetry_context_echo || {}, null, false);
        renderLiveTelemetryPanel(pj0, {
          elapsedSec: 0,
          recipeLabel: recipeLabelFromDom(),
          windowLabel: evaluationWindowLabelFromDom(),
        });
        void refreshStudentPanelD11({ soft: true });
        refreshScorecardHistory();
        updateRunStatusLine('Cancelled — see scorecard (status cancelled).');
        return;
      }
      pgSetInflightJobId(null);
    }

    void refreshStudentProctorStoreLine();
    void resumeParallelJobFromStorageIfAny();
    void refreshStudentPanelD11();
    refreshScorecardHistory();
    setEvidenceTab('outcomes');
  </script>
</body>
</html>
"""


def main() -> None:
    import argparse

    apply_main_process_runtime_env_defaults()
    ensure_pml_runtime_dirs()
    print(describe_pml_runtime_for_startup(), flush=True)

    p = argparse.ArgumentParser(description="Pattern Machine learning local web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    configure_web_server_file_logging()
    app = create_app()
    print(f"[web_app] Open http://{args.host}:{args.port}/  (PYTHONPATH must include repo root)")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
