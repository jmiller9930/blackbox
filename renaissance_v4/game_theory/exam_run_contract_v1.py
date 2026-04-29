"""
GT_DIRECTIVE_015 — exam run contract: **Student brain profile**, nested LLM metadata, scorecard fields.

**Student brain profile** (primary, persisted on scorecard): ``baseline_no_memory_no_llm`` (operator **Baseline**)
| ``memory_context_llm_student`` (operator **Student**). The internal profile ``memory_context_student``
(stub / no Ollama) remains for tests and the Advanced legacy override, not the primary two-value selector.
Legacy ``student_reasoning_mode`` **input** strings are still accepted and normalized to a profile.

**LLM** is metadata under the ``memory_context_llm_student`` profile: ``student_llm_v1`` with
``llm_provider``, ``llm_model``, ``llm_role``. The Student Ollama model is **fixed** to
``qwen2.5:7b`` at ``student_ollama_base_url_v1()`` (see ``STUDENT_LLM_APPROVED_MODEL_V1``) —
any other ``llm_model`` in the request is **rejected** (no silent fallback).

Parallel replay **still executes** for every batch in v1; ``skip_cold_baseline`` records whether a
**prior comparable baseline** existed (comparison validity), not a physical skip of Referee work.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.batch_scorecard import read_batch_scorecard_recent
from renaissance_v4.game_theory.candle_timeframe_runtime import is_allowed_candle_timeframe_minutes_v1

# --- Canonical Student brain profiles (GT_DIRECTIVE_015 v2) ---

STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1 = "baseline_no_memory_no_llm"
STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1 = "memory_context_student"
STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1 = "memory_context_llm_student"

CANONICAL_STUDENT_BRAIN_PROFILES_V1: frozenset[str] = frozenset(
    {
        STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    }
)

# --- GT_DIRECTIVE_024C closeout — explicit Student execution mode (vocabulary) ---

STUDENT_EXECUTION_MODE_OFF_V1 = "off"
STUDENT_EXECUTION_MODE_BASELINE_GATED_V1 = "baseline_gated"
# GT-024D — Student may open via fusion-veto path (fusion no_trade + aligned signal + intent); still risk-gated.
STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1 = "student_full_control"
STUDENT_FULL_CONTROL_STATUS_NOT_IMPLEMENTED_V1 = "not_implemented"
STUDENT_FULL_CONTROL_STATUS_ENABLED_V1 = "enabled"


def student_lane_authority_truth_v1(
    *,
    student_execution_mode_v1: str,
    student_controlled_execution: bool,
    profile: str,
) -> str:
    """
    Non-ambiguous copy for scorecard, trace evidence, and UI: baseline-gated vs full control.
    """
    if not student_controlled_execution or student_execution_mode_v1 == STUDENT_EXECUTION_MODE_OFF_V1:
        return (
            "Student lane automation was not enabled for this run "
            "(student_controlled_execution_v1 false or student_execution_mode_v1 off)."
        )
    if profile == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
        return "Student lane is not used for cold baseline profile runs."
    if student_execution_mode_v1 == STUDENT_EXECUTION_MODE_BASELINE_GATED_V1:
        return (
            "Student lane is baseline-gated. Student can modify a baseline-eligible entry, but cannot "
            "create a new entry when baseline/fusion says no_trade. student_full_control: not_implemented."
        )
    if student_execution_mode_v1 == STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1:
        return (
            "Student full-control lane (024D): in addition to baseline-gated behavior when fusion is "
            "directional, replay may open when fusion is no_trade if a directional signal aligns with the "
            "validated student_execution_intent_v1 and risk allows. No entry without a matching active signal."
        )
    return f"See student_execution_mode_v1={student_execution_mode_v1!r} and exam contract."

# Legacy **input** tokens (UI/API/scripts). Normalize maps these → brain profile.
LEGACY_STUDENT_REASONING_INPUT_COLD_BASELINE_V1 = "cold_baseline"
LEGACY_STUDENT_REASONING_INPUT_REPEAT_ANNA_V1 = "repeat_anna_memory_context"
LEGACY_STUDENT_REASONING_INPUT_MEMORY_CONTEXT_ONLY_V1 = "memory_context_only"
LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1 = "llm_assisted_anna_qwen"
LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_ALIAS_V1 = "llm_qwen2_5_7b"
LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_V1 = "llm_assisted_anna_deepseek_r1_14b"
LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_ALIAS_V1 = "llm_deepseek_r1_14b"

LEGACY_STUDENT_REASONING_INPUTS_V1: frozenset[str] = frozenset(
    {
        LEGACY_STUDENT_REASONING_INPUT_COLD_BASELINE_V1,
        LEGACY_STUDENT_REASONING_INPUT_REPEAT_ANNA_V1,
        LEGACY_STUDENT_REASONING_INPUT_MEMORY_CONTEXT_ONLY_V1,
        LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1,
        LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_ALIAS_V1,
        LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_V1,
        LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_ALIAS_V1,
    }
)

# Back-compat names for imports (values are legacy **inputs**, not persisted profile ids).
STUDENT_REASONING_MODE_COLD_BASELINE_V1 = LEGACY_STUDENT_REASONING_INPUT_COLD_BASELINE_V1
STUDENT_REASONING_MODE_REPEAT_ANNA_V1 = LEGACY_STUDENT_REASONING_INPUT_REPEAT_ANNA_V1
STUDENT_REASONING_MODE_LLM_QWEN_V1 = LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1
STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1 = LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_V1

STUDENT_REASONING_MODES_V1: frozenset[str] = frozenset(
    CANONICAL_STUDENT_BRAIN_PROFILES_V1 | LEGACY_STUDENT_REASONING_INPUTS_V1
)

_LEGACY_INPUT_TO_PROFILE_V1: dict[str, str] = {
    LEGACY_STUDENT_REASONING_INPUT_COLD_BASELINE_V1: STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    LEGACY_STUDENT_REASONING_INPUT_REPEAT_ANNA_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    LEGACY_STUDENT_REASONING_INPUT_MEMORY_CONTEXT_ONLY_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_ALIAS_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_ALIAS_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
}

_DEFAULT_LLM_ROLE_V1 = "single_shot_student_output_v1"
_DEFAULT_LLM_PROVIDER_V1 = "ollama"
# Only model allowed on the Student (memory_context_llm_student) Ollama path — no other default.
STUDENT_LLM_APPROVED_MODEL_V1 = "qwen2.5:7b"


def default_ollama_base_url_v1() -> str:
    """Student Ollama base URL (``STUDENT_OLLAMA_BASE_URL`` or lab default **172.20.2.230:11434**)."""
    from renaissance_v4.game_theory.ollama_role_routing_v1 import student_ollama_base_url_v1

    return student_ollama_base_url_v1()


def normalize_student_reasoning_mode_v1(raw: str | None) -> str:
    """
    Return canonical **Student brain profile** id.

    Legacy ``student_reasoning_mode`` **lane** strings still map to profiles; the resolved Student LLM
    model is always ``STUDENT_LLM_APPROVED_MODEL_V1`` when the profile is ``memory_context_llm_student``.
    """
    s = (raw or "").strip()
    if not s:
        return STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1
    if s in CANONICAL_STUDENT_BRAIN_PROFILES_V1:
        return s
    if s in _LEGACY_INPUT_TO_PROFILE_V1:
        return _LEGACY_INPUT_TO_PROFILE_V1[s]
    return s


def validate_student_reasoning_mode_v1(mode: str | None) -> str | None:
    """Return error message if input is unknown (legacy lane string or brain profile)."""
    s = (mode or "").strip()
    if not s:
        return None
    if s in CANONICAL_STUDENT_BRAIN_PROFILES_V1 or s in LEGACY_STUDENT_REASONING_INPUTS_V1:
        return None
    return f"unknown student_reasoning_mode or student_brain_profile_v1: {mode!r}"


def _normalize_student_llm_block_v1(
    block: dict[str, Any],
    *,
    profile: str,
    legacy_reasoning_input: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Returns ``(student_llm_v1_dict, error)``."""
    _ = legacy_reasoning_input
    if profile != STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        return {}, None
    raw = block.get("student_llm_v1")
    slm: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    model = str(slm.get("llm_model") or "").strip()
    if not model:
        model = STUDENT_LLM_APPROVED_MODEL_V1
    if model != STUDENT_LLM_APPROVED_MODEL_V1:
        return None, (
            f"student_llm_v1.llm_model must be {STUDENT_LLM_APPROVED_MODEL_V1!r} for "
            f"memory_context_llm_student (got {model!r})"
        )
    if len(model) > 128:
        return None, "llm_model too long"
    provider = str(slm.get("llm_provider") or _DEFAULT_LLM_PROVIDER_V1).strip().lower() or _DEFAULT_LLM_PROVIDER_V1
    if provider != "ollama":
        return None, "llm_provider must be ollama in v1"
    role = str(slm.get("llm_role") or _DEFAULT_LLM_ROLE_V1).strip() or _DEFAULT_LLM_ROLE_V1
    if len(role) > 128:
        return None, "llm_role too long"
    return {
        "schema": "student_llm_v1",
        "llm_provider": provider,
        "llm_model": model,
        "llm_role": role,
    }, None


def resolved_llm_for_exam_contract_v1(
    req: dict[str, Any] | None,
) -> tuple[str | None, str, dict[str, Any], list[str]]:
    """
    For ``memory_context_llm_student``: approved Ollama model, base URL, ``student_llm_v1`` echo
    (includes ``student_llm_resolution_v1``), and error list. Otherwise:
    ``(None, default_url, {}, [])``.
    """
    r = dict(req or {})
    prof = normalize_student_reasoning_mode_v1(
        str(r.get("student_brain_profile_v1") or r.get("student_reasoning_mode") or "")
    )
    base = default_ollama_base_url_v1()
    if prof != STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        return None, base, {}, []
    slm = r.get("student_llm_v1")
    if not isinstance(slm, dict):
        slm = {}
    requested = str(slm.get("llm_model") or "").strip()
    if requested and requested != STUDENT_LLM_APPROVED_MODEL_V1:
        return (
            None,
            base,
            {},
            [
                f"student_llm_model_rejected_v1: memory_context_llm_student requires llm_model "
                f"{STUDENT_LLM_APPROVED_MODEL_V1!r} (got {requested!r})"
            ],
        )
    resolved = STUDENT_LLM_APPROVED_MODEL_V1
    res_block = {
        "schema": "student_llm_resolution_v1",
        "requested_model": requested or None,
        "resolved_model": resolved,
        "ollama_base_url_used": base,
    }
    out_slm = {
        "schema": "student_llm_v1",
        "llm_provider": str(slm.get("llm_provider") or _DEFAULT_LLM_PROVIDER_V1).strip().lower()
        or _DEFAULT_LLM_PROVIDER_V1,
        "llm_model": resolved,
        "llm_role": str(slm.get("llm_role") or _DEFAULT_LLM_ROLE_V1).strip() or _DEFAULT_LLM_ROLE_V1,
        "student_llm_resolution_v1": res_block,
    }
    return resolved, base, out_slm, []


def resolved_llm_model_and_url_for_student_mode_v1(mode: str) -> tuple[str | None, str]:
    """Backward-compat: legacy lane → profile; model is always ``STUDENT_LLM_APPROVED_MODEL_V1``."""
    m = normalize_student_reasoning_mode_v1(mode)
    if m != STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        return None, default_ollama_base_url_v1()
    return STUDENT_LLM_APPROVED_MODEL_V1, default_ollama_base_url_v1()


def preview_run_config_fingerprint_sha256_40_v1(
    scenarios: list[dict[str, Any]],
    operator_batch_audit: dict[str, Any],
) -> str:
    oba = operator_batch_audit or {}
    ok_rows = [x for x in scenarios if isinstance(x, dict)]
    fp_parts = [
        str(oba.get("operator_recipe_id") or ""),
        str(oba.get("evaluation_window_effective_calendar_months") or ""),
        str(oba.get("candle_timeframe_minutes") or ""),
        str(oba.get("manifest_path_primary") or ""),
        str(oba.get("policy_framework_path") or ""),
    ]
    for r in sorted(ok_rows, key=lambda x: str(x.get("scenario_id") or "")):
        fp_parts.append(str(r.get("scenario_id") or ""))
        mp = r.get("manifest_path")
        if mp:
            fp_parts.append(str(mp))
    return hashlib.sha256("\n".join(fp_parts).encode("utf-8")).hexdigest()[:40]


def find_prior_baseline_job_id_for_fingerprint_v1(
    fp: str,
    *,
    scorecard_path: Path | None = None,
    limit: int = 800,
) -> str | None:
    if not fp:
        return None
    rows = read_batch_scorecard_recent(limit, path=scorecard_path)
    chronological = list(reversed(rows))
    oldest: str | None = None
    for r in chronological:
        if str(r.get("status") or "") != "done":
            continue
        mci = r.get("memory_context_impact_audit_v1")
        if not isinstance(mci, dict):
            continue
        rfp = str(mci.get("run_config_fingerprint_sha256_40") or "").strip()
        if rfp != fp:
            continue
        jid = str(r.get("job_id") or "").strip()
        if not jid:
            continue
        oldest = jid
        break
    return oldest


def _memory_context_used_flag_v1(operator_batch_audit: dict[str, Any] | None) -> bool:
    oba = operator_batch_audit or {}
    cmem = str(oba.get("context_signature_memory_mode") or "").strip().lower()
    return cmem in ("read", "read_write")


def _apply_optional_026b_lifecycle_fields_v1(
    out: dict[str, Any],
    block: dict[str, Any],
    data: dict[str, Any],
) -> str | None:
    """
    GT_DIRECTIVE_026B — optional forward tape and lifecycle controls from ``exam_run_contract_v1``
    (or top-level request keys) for merge into the student decision packet in the operator seam.
    """
    keys = (
        "bars_trade_lifecycle_inclusive_v1",
        "entry_bar_index_for_lifecycle_v1",
        "unified_agent_router_lifecycle_v1",
        "max_hold_bars_lifecycle_v1",
    )
    for key in keys:
        v: Any = block.get(key)
        if v is None:
            v = data.get(key)
        if v is None:
            continue
        if key == "bars_trade_lifecycle_inclusive_v1":
            if not isinstance(v, list) or len(v) < 2:
                return "bars_trade_lifecycle_inclusive_v1 must be a list with at least 2 bar dicts"
            for i, b in enumerate(v):
                if not isinstance(b, dict):
                    return f"bars_trade_lifecycle_inclusive_v1[{i}] must be a dict"
            out[key] = [dict(b) for b in v]
        elif key == "entry_bar_index_for_lifecycle_v1":
            try:
                out[key] = int(v)
            except (TypeError, ValueError):
                return f"invalid entry_bar_index_for_lifecycle_v1: {v!r}"
        elif key == "max_hold_bars_lifecycle_v1":
            try:
                m = int(v)
            except (TypeError, ValueError):
                return f"invalid max_hold_bars_lifecycle_v1: {v!r}"
            if m < 1 or m > 10_000:
                return "max_hold_bars_lifecycle_v1 out of range (1..10000)"
            out[key] = m
        elif key == "unified_agent_router_lifecycle_v1":
            if isinstance(v, str):
                out[key] = v.strip().lower() in ("1", "true", "yes", "on")
            else:
                out[key] = bool(v)
    return None


def parse_exam_run_contract_request_v1(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """
    Parse ``exam_run_contract_v1`` (or flat keys). Primary: ``student_brain_profile_v1``;
    ``student_reasoning_mode`` is accepted as legacy **or** mirror of profile.
    """
    src = data.get("exam_run_contract_v1")
    if isinstance(src, dict):
        block = dict(src)
    else:
        block = {}
    if data.get("student_brain_profile_v1") is not None:
        block["student_brain_profile_v1"] = data.get("student_brain_profile_v1")
    if data.get("student_reasoning_mode") is not None:
        block["student_reasoning_mode"] = data.get("student_reasoning_mode")
    if data.get("student_llm_v1") is not None:
        block["student_llm_v1"] = data.get("student_llm_v1")
    if data.get("skip_cold_baseline_if_anchor") is not None:
        block["skip_cold_baseline_if_anchor"] = data.get("skip_cold_baseline_if_anchor")
    if data.get("prompt_version") is not None:
        block["prompt_version"] = data.get("prompt_version")
    if data.get("retrieved_context_ids") is not None:
        block["retrieved_context_ids"] = data.get("retrieved_context_ids")
    if data.get("candle_timeframe_minutes") is not None:
        block["candle_timeframe_minutes"] = data.get("candle_timeframe_minutes")
    if data.get("student_decision_authority_mode_v1") is not None:
        block["student_decision_authority_mode_v1"] = data.get("student_decision_authority_mode_v1")
    if data.get("student_test_mode_v1") is not None:
        block["student_test_mode_v1"] = data.get("student_test_mode_v1")
    if data.get("skip_student_probe_v1") is not None:
        block["skip_student_probe_v1"] = data.get("skip_student_probe_v1")

    raw_profile = block.get("student_brain_profile_v1")
    raw_mode = block.get("student_reasoning_mode")
    pick = raw_profile if isinstance(raw_profile, str) and raw_profile.strip() else raw_mode
    err = validate_student_reasoning_mode_v1(pick if isinstance(pick, str) else None)
    if err:
        return None, err
    profile = normalize_student_reasoning_mode_v1(pick if isinstance(pick, str) else None)
    legacy_input = (
        str(raw_mode).strip()
        if isinstance(raw_mode, str) and raw_mode.strip() in LEGACY_STUDENT_REASONING_INPUTS_V1
        else None
    )
    slm, slm_err = _normalize_student_llm_block_v1(block, profile=profile, legacy_reasoning_input=legacy_input)
    if slm_err:
        return None, slm_err

    skip_req = block.get("skip_cold_baseline_if_anchor")
    if isinstance(skip_req, str):
        skip_req = skip_req.strip().lower() in ("1", "true", "yes", "on")
    skip_req = bool(skip_req)

    pv = block.get("prompt_version")
    if pv is None or str(pv).strip() == "":
        pv = "shadow_student_stub_v1"
    else:
        pv = str(pv).strip()[:256]

    rcids = block.get("retrieved_context_ids")
    if rcids is None:
        rcids_out: list[str] = []
    elif isinstance(rcids, list):
        rcids_out = [str(x).strip() for x in rcids if str(x).strip()][:128]
    else:
        return None, "retrieved_context_ids must be a list of strings when set"

    if profile == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        base = default_ollama_base_url_v1()
        if not base or not (base.startswith("http://") or base.startswith("https://")):
            return None, "ollama_base_url_invalid_or_unset_for_llm_assisted_mode"

    raw_sce = block.get("student_controlled_execution_v1")
    if raw_sce is None and data.get("student_controlled_execution_v1") is not None:
        raw_sce = data.get("student_controlled_execution_v1")
    if isinstance(raw_sce, str):
        student_controlled_execution = raw_sce.strip().lower() in ("1", "true", "yes", "on")
    else:
        student_controlled_execution = bool(raw_sce)

    if student_controlled_execution and profile == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
        return (
            None,
            "student_controlled_execution_v1 requires memory_context_student or memory_context_llm_student, not cold baseline",
        )

    student_execution_mode = STUDENT_EXECUTION_MODE_OFF_V1
    explicit_mode: str | None = None
    if student_controlled_execution:
        raw_mode = block.get("student_execution_mode_v1")
        if raw_mode is None and data.get("student_execution_mode_v1") is not None:
            raw_mode = data.get("student_execution_mode_v1")
        if isinstance(raw_mode, str) and raw_mode.strip():
            sm = raw_mode.strip().lower()
            if sm in (
                STUDENT_EXECUTION_MODE_BASELINE_GATED_V1,
                "024c",
            ):
                explicit_mode = STUDENT_EXECUTION_MODE_BASELINE_GATED_V1
            elif sm in (
                STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1,
                "full_control",
                "024d",
            ):
                explicit_mode = STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1
            else:
                return None, f"invalid student_execution_mode_v1: {raw_mode!r}"
    if student_controlled_execution and profile in (
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    ):
        student_execution_mode = (
            explicit_mode
            if explicit_mode is not None
            else STUDENT_EXECUTION_MODE_BASELINE_GATED_V1
        )

    sfc_out = STUDENT_FULL_CONTROL_STATUS_NOT_IMPLEMENTED_V1
    if student_execution_mode == STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1:
        sfc_out = STUDENT_FULL_CONTROL_STATUS_ENABLED_V1

    raw_ctf = block.get("candle_timeframe_minutes")
    ctf_out: int | None = None
    if raw_ctf is not None:
        try:
            ctf_i = int(raw_ctf)
        except (TypeError, ValueError):
            return None, f"invalid candle_timeframe_minutes: {raw_ctf!r}"
        if not is_allowed_candle_timeframe_minutes_v1(ctf_i):
            return None, f"candle_timeframe_minutes not in supported set {{5,15,60,240}}: {raw_ctf!r}"
        ctf_out = ctf_i

    out: dict[str, Any] = {
        "schema": "exam_run_contract_request_v1",
        "contract_version": 1,
        "student_brain_profile_v1": profile,
        "student_reasoning_mode": profile,
        "student_llm_v1": slm,
        "skip_cold_baseline_if_anchor": skip_req,
        "prompt_version": pv,
        "retrieved_context_ids": rcids_out,
        "student_controlled_execution_v1": student_controlled_execution,
        "student_execution_mode_v1": student_execution_mode,
        "student_full_control_v1": sfc_out,
    }
    euid = block.get("exam_unit_id")
    if euid is None and isinstance(data.get("exam_unit_id"), str):
        euid = data.get("exam_unit_id")
    if isinstance(euid, str) and euid.strip():
        out["exam_unit_id"] = euid.strip()[:256]
    if ctf_out is not None:
        out["candle_timeframe_minutes"] = int(ctf_out)
    raw_auth = block.get("student_decision_authority_mode_v1")
    if raw_auth is None and data.get("student_decision_authority_mode_v1") is not None:
        raw_auth = data.get("student_decision_authority_mode_v1")
    if raw_auth is not None:
        am = str(raw_auth).strip().lower()
        if am not in ("shadow", "active", "off"):
            return None, f"invalid student_decision_authority_mode_v1: {raw_auth!r}"
        out["student_decision_authority_mode_v1"] = am
    if profile != STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1 and out.get("student_decision_authority_mode_v1") == "off":
        return (
            None,
            "student_decision_authority_mode_v1 off is not permitted when student_brain_profile_v1 is not "
            "cold baseline (STUDENT_DECISION_AUTHORITY_MANDATE_V1)",
        )
    lc_err = _apply_optional_026b_lifecycle_fields_v1(out, block, data)
    if lc_err:
        return None, lc_err

    raw_stm = block.get("student_test_mode_v1")
    if raw_stm is None and data.get("student_test_mode_v1") is not None:
        raw_stm = data.get("student_test_mode_v1")
    if isinstance(raw_stm, str):
        stm_ok = raw_stm.strip().lower() in ("1", "true", "yes", "on")
    else:
        stm_ok = bool(raw_stm)
    if stm_ok:
        out["student_test_mode_v1"] = True

    raw_ssp = block.get("skip_student_probe_v1")
    if isinstance(raw_ssp, str):
        ssp_ok = raw_ssp.strip().lower() in ("1", "true", "yes", "on")
    else:
        ssp_ok = bool(raw_ssp)
    if ssp_ok:
        out["skip_student_probe_v1"] = True
    return out, None


def build_exam_run_line_meta_v1(
    *,
    request: dict[str, Any] | None,
    operator_batch_audit: dict[str, Any] | None,
    fingerprint_sha256_40: str | None,
    job_id: str,
    student_seam_observability_v1: dict[str, Any] | None,
    batch_status: str,
    seam_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req = request or {}
    profile = normalize_student_reasoning_mode_v1(
        str(req.get("student_brain_profile_v1") or req.get("student_reasoning_mode") or "")
    )
    seam = student_seam_observability_v1 or {}
    oba = operator_batch_audit or {}

    llm_used = profile == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    slm_req = req.get("student_llm_v1") if isinstance(req.get("student_llm_v1"), dict) else {}
    req_model_raw: str | None = str(slm_req.get("llm_model") or "").strip() or None if llm_used else None
    llm_model: str | None = STUDENT_LLM_APPROVED_MODEL_V1 if llm_used else None
    ollama_url = default_ollama_base_url_v1() if llm_used else None
    requested_model: str | None = req_model_raw
    resolved_model: str | None = STUDENT_LLM_APPROVED_MODEL_V1 if llm_used else None
    ollama_base_url_used: str | None = ollama_url

    fp = (fingerprint_sha256_40 or "").strip()
    anchor = find_prior_baseline_job_id_for_fingerprint_v1(fp) if fp else None
    skip_req = bool(req.get("skip_cold_baseline_if_anchor"))
    skip_applicable = (
        skip_req
        and profile != STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1
        and fp
        and anchor is not None
        and batch_status == "done"
    )
    if profile == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
        skip_cold = False
        skip_reason = "mode_is_cold_baseline"
    elif not skip_req:
        skip_cold = False
        skip_reason = "skip_not_requested"
    elif not fp:
        skip_cold = False
        skip_reason = "fingerprint_unavailable"
    elif anchor is None:
        skip_cold = False
        skip_reason = "cold_required_no_prior_anchor_same_fingerprint"
    elif not skip_applicable:
        skip_cold = False
        skip_reason = "skip_not_applicable_batch_not_done" if batch_status != "done" else "skip_not_applicable"
    else:
        skip_cold = True
        skip_reason = f"prior_anchor_job_id={anchor}"

    mem_ctx = _memory_context_used_flag_v1(oba)
    if seam.get("student_retrieval_matches"):
        mem_ctx = True

    line: dict[str, Any] = {
        "student_brain_profile_v1": profile,
        "student_reasoning_mode": profile,
        "llm_used": llm_used,
        "llm_model": llm_model,
        "ollama_base_url": ollama_url,
        "requested_model": requested_model,
        "resolved_model": resolved_model,
        "ollama_base_url_used": ollama_base_url_used,
        "prompt_version": str(req.get("prompt_version") or "shadow_student_stub_v1")[:256],
        "memory_context_used": mem_ctx,
        "retrieved_context_ids": list(req.get("retrieved_context_ids") or []),
        "skip_cold_baseline": skip_cold,
        "skip_reason": skip_reason,
        "cold_baseline_anchor_job_id_v1": anchor,
        "run_config_fingerprint_sha256_40_echo_v1": fp or None,
        "system_baseline_captured_v1": bool(
            profile == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1 and batch_status == "done"
        ),
    }
    if llm_used and isinstance(req.get("student_llm_v1"), dict):
        line["student_llm_v1"] = dict(req["student_llm_v1"])
    shadow_on = bool(seam.get("shadow_student_enabled"))
    if shadow_on is not None:
        line["shadow_student_enabled_echo_v1"] = shadow_on
    _ = job_id

    sa = seam_audit if isinstance(seam_audit, dict) else {}
    lx = sa.get("student_llm_execution_v1")
    if isinstance(lx, dict) and lx.get("schema") == "student_llm_execution_v1":
        line["student_llm_execution_v1"] = lx
        if lx.get("ollama_any_attempt") is True:
            line["llm_used"] = True
        if isinstance(lx.get("model_resolved"), str) and lx["model_resolved"].strip():
            line["llm_model"] = lx["model_resolved"].strip()
        if isinstance(lx.get("base_url_resolved"), str) and lx["base_url_resolved"].strip():
            line["ollama_base_url"] = lx["base_url_resolved"].strip()
        for k in ("requested_model", "resolved_model", "ollama_base_url_used"):
            v = lx.get(k)
            if isinstance(v, str) and v.strip():
                line[k] = v.strip()
        if isinstance(lx.get("prompt_version_resolved"), str) and lx["prompt_version_resolved"].strip():
            line["prompt_version"] = lx["prompt_version_resolved"].strip()[:256]
        if isinstance(lx.get("student_brain_profile_echo_v1"), str) and lx["student_brain_profile_echo_v1"].strip():
            line["student_brain_profile_v1"] = lx["student_brain_profile_echo_v1"].strip()
            line["student_reasoning_mode"] = line["student_brain_profile_v1"]
    eid = req.get("exam_unit_id")
    if isinstance(eid, str) and eid.strip():
        line["exam_unit_id"] = eid.strip()[:256]
    ctf_req = req.get("candle_timeframe_minutes")
    if ctf_req is not None:
        try:
            line["candle_timeframe_minutes"] = int(ctf_req)
        except (TypeError, ValueError):
            pass
    elif oba.get("candle_timeframe_minutes") is not None:
        try:
            line["candle_timeframe_minutes"] = int(oba["candle_timeframe_minutes"])
        except (TypeError, ValueError):
            pass
    line["student_controlled_execution_v1"] = bool(req.get("student_controlled_execution_v1"))
    line["student_execution_mode_v1"] = str(
        req.get("student_execution_mode_v1") or STUDENT_EXECUTION_MODE_OFF_V1
    )
    sfc_req = str(req.get("student_full_control_v1") or "").strip()
    line["student_full_control_v1"] = sfc_req or STUDENT_FULL_CONTROL_STATUS_NOT_IMPLEMENTED_V1
    line["student_lane_authority_truth_v1"] = student_lane_authority_truth_v1(
        student_execution_mode_v1=line["student_execution_mode_v1"],
        student_controlled_execution=line["student_controlled_execution_v1"],
        profile=profile,
    )
    sem = line["student_execution_mode_v1"]
    if (
        line["student_controlled_execution_v1"]
        and sem == STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1
    ):
        line["execution_authority_v1"] = "student_full_control"
    elif (
        line["student_controlled_execution_v1"]
        and sem == STUDENT_EXECUTION_MODE_BASELINE_GATED_V1
    ):
        line["execution_authority_v1"] = "baseline_gated_student"
    else:
        line["execution_authority_v1"] = "baseline_control"
    return line


__all__ = [
    "STUDENT_EXECUTION_MODE_OFF_V1",
    "STUDENT_EXECUTION_MODE_BASELINE_GATED_V1",
    "STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1",
    "STUDENT_FULL_CONTROL_STATUS_NOT_IMPLEMENTED_V1",
    "STUDENT_FULL_CONTROL_STATUS_ENABLED_V1",
    "student_lane_authority_truth_v1",
    "STUDENT_REASONING_MODES_V1",
    "STUDENT_REASONING_MODE_COLD_BASELINE_V1",
    "STUDENT_REASONING_MODE_REPEAT_ANNA_V1",
    "STUDENT_REASONING_MODE_LLM_QWEN_V1",
    "STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1",
    "STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1",
    "STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1",
    "STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1",
    "STUDENT_LLM_APPROVED_MODEL_V1",
    "CANONICAL_STUDENT_BRAIN_PROFILES_V1",
    "LEGACY_STUDENT_REASONING_INPUTS_V1",
    "build_exam_run_line_meta_v1",
    "default_ollama_base_url_v1",
    "find_prior_baseline_job_id_for_fingerprint_v1",
    "normalize_student_reasoning_mode_v1",
    "parse_exam_run_contract_request_v1",
    "preview_run_config_fingerprint_sha256_40_v1",
    "resolved_llm_for_exam_contract_v1",
    "resolved_llm_model_and_url_for_student_mode_v1",
    "validate_student_reasoning_mode_v1",
]
