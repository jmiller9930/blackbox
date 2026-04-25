"""
GT_DIRECTIVE_024B — ``student_execution_intent_v1``.

Validated contract bridging sealed ``student_output_v1`` to a future Student-controlled
replay lane. **No replay wiring** — schema, validation, digests, and builder only.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Final

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    CANONICAL_STUDENT_BRAIN_PROFILES_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    normalize_student_reasoning_mode_v1,
    validate_student_reasoning_mode_v1,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    SCHEMA_STUDENT_OUTPUT_V1,
    validate_student_output_directional_thesis_required_for_llm_profile_v1,
    validate_student_output_v1,
)

# --- Schema identity ---

SCHEMA_STUDENT_EXECUTION_INTENT_V1: Final[str] = "student_execution_intent_v1"
STUDENT_EXECUTION_INTENT_SCHEMA_VERSION_V1: Final[int] = 1

STUDENT_EXECUTION_INTENT_ACTIONS_V1: Final[frozenset[str]] = frozenset(
    {"enter_long", "enter_short", "no_trade"}
)
STUDENT_EXECUTION_INTENT_DIRECTIONS_V1: Final[frozenset[str]] = frozenset({"long", "short", "flat"})

STUDENT_EXECUTION_INTENT_CONFIDENCE_BANDS_V1: Final[frozenset[str]] = frozenset({"low", "medium", "high"})

_DIGEST_EXCLUDE_KEYS: Final[frozenset[str]] = frozenset({"created_at_utc", "student_execution_intent_digest_v1"})


def _err(msg: str) -> list[str]:
    return [msg]


def canonical_json_sha256_v1(obj: Any) -> str:
    """
    Deterministic JSON → UTF-8 → SHA-256 hex. Used for sealed Student output and intent digests.
    """
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def digest_sealed_student_output_v1(student_output: dict[str, Any]) -> str:
    """
    ``source_student_output_digest_v1`` — stable for byte-identical semantic content
    (canonical JSON, sorted keys; identical dicts always yield the same digest).
    """
    if not isinstance(student_output, dict):
        raise TypeError("student_output must be a dict")
    return canonical_json_sha256_v1(student_output)


def _intent_payload_for_digest_v1(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k not in _DIGEST_EXCLUDE_KEYS}


def compute_student_execution_intent_digest_v1(intent_doc: dict[str, Any]) -> str:
    """
    ``student_execution_intent_digest_v1`` — **excludes** ``created_at_utc`` and the digest field itself.
    """
    if not isinstance(intent_doc, dict):
        raise TypeError("intent must be a dict")
    return canonical_json_sha256_v1(_intent_payload_for_digest_v1(intent_doc))


def student_execution_intent_trace_created_fields_v1(intent: dict[str, Any]) -> dict[str, Any]:
    """
    Data required for a future ``student_execution_intent_created`` trace (no I/O, no emit).
    """
    return {
        "job_id": intent.get("job_id"),
        "fingerprint": intent.get("fingerprint"),
        "student_execution_intent_digest_v1": intent.get("student_execution_intent_digest_v1"),
        "source_student_output_digest_v1": intent.get("source_student_output_digest_v1"),
        "action": intent.get("action"),
        "direction": intent.get("direction"),
        "confidence_01": intent.get("confidence_01"),
        "student_brain_profile_v1": intent.get("student_brain_profile_v1"),
        "llm_model": intent.get("llm_model"),
    }


def _action_direction_consistent_v1(action: str, direction: str) -> bool:
    if action == "enter_long" and direction == "long":
        return True
    if action == "enter_short" and direction == "short":
        return True
    if action == "no_trade" and direction == "flat":
        return True
    return False


def _map_intent_action_direction_from_student_v1(
    so: dict[str, Any], *, student_brain_profile_v1: str
) -> tuple[str, str, list[str]]:
    errs: list[str] = []
    sa = so.get("student_action_v1")
    llm = student_brain_profile_v1 == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1

    if isinstance(sa, str) and sa.strip():
        sa_l = sa.strip().lower()
        if sa_l in STUDENT_EXECUTION_INTENT_ACTIONS_V1:
            if sa_l == "enter_long":
                return "enter_long", "long", errs
            if sa_l == "enter_short":
                return "enter_short", "short", errs
            if sa_l == "no_trade":
                return "no_trade", "flat", errs
        errs.append("student_action_v1 must be enter_long|enter_short|no_trade when present")
        if llm:
            return "no_trade", "flat", errs

    if llm and not (isinstance(sa, str) and sa.strip()):
        errs.append("student_action_v1 is required for memory_context_llm_student")
        return "no_trade", "flat", errs

    act = so.get("act")
    d = so.get("direction")
    d_l = d.lower().strip() if isinstance(d, str) and d.strip() else None
    if act is not True or d_l is None or d_l == "flat":
        return "no_trade", "flat", errs
    if d_l == "long":
        return "enter_long", "long", errs
    if d_l == "short":
        return "enter_short", "short", errs
    return "no_trade", "flat", errs


def _thesis_basics_present_for_intent_v1(so: dict[str, Any], *, for_llm: bool) -> list[str]:
    if for_llm:
        return validate_student_output_directional_thesis_required_for_llm_profile_v1(so)
    errs: list[str] = []
    for k in ("context_fit", "invalidation_text"):
        v = so.get(k)
        if not isinstance(v, str) or not v.strip():
            errs.append(f"intent_build_requires_{k}_on_student_output")
    cb = so.get("confidence_band")
    if not isinstance(cb, str) or not str(cb).strip():
        errs.append("intent_build_requires_confidence_band_on_student_output")
    elif str(cb).strip().lower() not in STUDENT_EXECUTION_INTENT_CONFIDENCE_BANDS_V1:
        errs.append("confidence_band must be low|medium|high")
    for name in ("supporting_indicators", "conflicting_indicators"):
        v = so.get(name)
        if v is not None and not isinstance(v, list):
            errs.append(f"{name} must be a list or absent")
    for name in ("supporting_indicators", "conflicting_indicators"):
        v = so.get(name) or []
        if isinstance(v, list):
            for i, x in enumerate(v):
                if not isinstance(x, str):
                    errs.append(f"{name}[{i}] must be str")
    return errs


def validate_student_execution_intent_v1(doc: Any) -> list[str]:
    """
    Full validation of ``student_execution_intent_v1`` (rejects malformed payloads and bad pairings).
    """
    errs: list[str] = []
    if not isinstance(doc, dict):
        return _err("student_execution_intent_v1 must be a dict")
    if doc.get("schema") != SCHEMA_STUDENT_EXECUTION_INTENT_V1:
        errs.append(f"schema must be {SCHEMA_STUDENT_EXECUTION_INTENT_V1!r}")
    if doc.get("schema_version") != STUDENT_EXECUTION_INTENT_SCHEMA_VERSION_V1:
        errs.append("schema_version must be 1")
    for k in (
        "job_id",
        "fingerprint",
        "source_student_output_digest_v1",
        "action",
        "direction",
        "confidence_01",
        "confidence_band",
        "context_fit",
        "invalidation_text",
        "created_at_utc",
    ):
        v = doc.get(k)
        if v is None or (isinstance(v, str) and not str(v).strip()):
            errs.append(f"{k} is required and must be non-empty (when string)")

    if doc.get("llm_model") is not None and not isinstance(doc.get("llm_model"), str):
        errs.append("llm_model must be string or null")

    s_sc = doc.get("scenario_id")
    s_tr = doc.get("trade_id")
    has_s = isinstance(s_sc, str) and s_sc.strip()
    has_t = isinstance(s_tr, str) and s_tr.strip()
    if not has_s and not has_t:
        errs.append("at least one of scenario_id or trade_id must be a non-empty string")

    raw_profile = (doc.get("student_brain_profile_v1") or "")
    if not str(raw_profile).strip():
        errs.append("student_brain_profile_v1 is required")
    else:
        perr = validate_student_reasoning_mode_v1(str(raw_profile).strip() or None)
        if perr:
            errs.append(perr)
        else:
            pn = normalize_student_reasoning_mode_v1(str(raw_profile).strip() or None)
            if pn not in CANONICAL_STUDENT_BRAIN_PROFILES_V1:
                errs.append("student_brain_profile_v1 must resolve to a canonical profile")

    dprog = str(doc.get("student_execution_intent_digest_v1") or "")
    if not isinstance(doc.get("student_execution_intent_digest_v1"), str) or len(dprog) != 64:
        errs.append("student_execution_intent_digest_v1 must be 64 hex chars")

    action = str(doc.get("action") or "")
    if action not in STUDENT_EXECUTION_INTENT_ACTIONS_V1:
        errs.append("action must be enter_long|enter_short|no_trade")
    direction = str(doc.get("direction") or "")
    if direction not in STUDENT_EXECUTION_INTENT_DIRECTIONS_V1:
        errs.append("direction must be long|short|flat")
    if not _action_direction_consistent_v1(action, direction):
        errs.append("action/direction mismatch (enter_long→long, enter_short→short, no_trade→flat)")

    c01 = doc.get("confidence_01")
    if not isinstance(c01, (int, float)) or not 0.0 <= float(c01) <= 1.0:
        errs.append("confidence_01 must be a number in [0, 1]")

    cb = str(doc.get("confidence_band") or "").strip().lower()
    if cb not in STUDENT_EXECUTION_INTENT_CONFIDENCE_BANDS_V1:
        errs.append("confidence_band must be low, medium, or high")

    for name in ("supporting_indicators", "conflicting_indicators"):
        v = doc.get(name)
        if not isinstance(v, list):
            errs.append(f"{name} must be a list")
        else:
            for i, x in enumerate(v):
                if not isinstance(x, str):
                    errs.append(f"{name}[{i}] must be a string")
    cf = doc.get("context_fit")
    if not isinstance(cf, str) or not cf.strip():
        errs.append("context_fit must be a non-empty string")
    inv = doc.get("invalidation_text")
    if not isinstance(inv, str) or not inv.strip():
        errs.append("invalidation_text must be a non-empty string")

    ssrc = str(doc.get("source_student_output_digest_v1") or "")
    if not isinstance(doc.get("source_student_output_digest_v1"), str) or len(ssrc) != 64:
        errs.append("source_student_output_digest_v1 must be 64 hex chars")

    if errs:
        return errs
    recompute = compute_student_execution_intent_digest_v1(
        {k: v for k, v in doc.items() if k != "student_execution_intent_digest_v1"},
    )
    if dprog != recompute:
        errs.append(
            "student_execution_intent_digest_v1 does not match canonical payload (excluding created_at_utc)"
        )
    return errs


def build_student_execution_intent_from_sealed_output_v1(
    *,
    student_output_v1: dict[str, Any],
    job_id: str,
    fingerprint: str,
    student_brain_profile_v1: str,
    scenario_id: str | None = None,
    trade_id: str | None = None,
    llm_model: str | None = None,
    created_at_utc: str | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """
    From **validated** sealed ``student_output_v1`` and run identity, build ``student_execution_intent_v1``.

    * ``no_trade`` / ``flat`` = no entry intent for a future Student lane consumer (024A); object is still
      fully validated and digest-stable.
    * LLM profile: §1.0 thesis via ``validate_student_output_directional_thesis_required_for_llm_profile_v1``.
    * Non-LLM: requires ``context_fit``, ``invalidation_text``, ``confidence_band`` on the sealed output, and
      well-typed optional indicator lists.
    """
    if not isinstance(student_output_v1, dict):
        return None, _err("student_output_v1 must be a dict")
    if student_output_v1.get("schema") != SCHEMA_STUDENT_OUTPUT_V1:
        return None, _err("sealed object must be schema student_output_v1")

    if not str(student_brain_profile_v1 or "").strip():
        return None, _err("student_brain_profile_v1 is required")
    perr = validate_student_reasoning_mode_v1(str(student_brain_profile_v1 or "").strip() or None)
    if perr:
        return None, [perr]
    prof_n = normalize_student_reasoning_mode_v1(str(student_brain_profile_v1 or "").strip() or None)
    if prof_n not in CANONICAL_STUDENT_BRAIN_PROFILES_V1:
        return None, _err("invalid student_brain_profile_v1")
    for_llm = prof_n == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1

    core = validate_student_output_v1(student_output_v1)
    if core:
        return None, core

    if for_llm:
        thesis_errs = validate_student_output_directional_thesis_required_for_llm_profile_v1(
            student_output_v1
        )
        if thesis_errs:
            return None, thesis_errs
    else:
        thesis_errs = _thesis_basics_present_for_intent_v1(student_output_v1, for_llm=False)
        if thesis_errs:
            return None, thesis_errs

    action, direction, map_errs = _map_intent_action_direction_from_student_v1(
        student_output_v1, student_brain_profile_v1=prof_n
    )
    if map_errs:
        return None, map_errs
    if not _action_direction_consistent_v1(action, direction):
        return None, _err("action/direction mapping inconsistent with student_output_v1")

    sid = (scenario_id or "").strip() or None
    tid = (trade_id or "").strip() or None
    if not tid and isinstance(student_output_v1.get("graded_unit_id"), str):
        tid = str(student_output_v1["graded_unit_id"]).strip() or None
    if not sid and not tid:
        return None, _err("provide scenario_id and/or trade_id, or sealed graded_unit_id for trade_id")

    c01 = float(student_output_v1.get("confidence_01"))
    cb = str(student_output_v1.get("confidence_band", "")).strip().lower()
    if cb not in STUDENT_EXECUTION_INTENT_CONFIDENCE_BANDS_V1:
        return None, _err("confidence_band on student output must be low|medium|high for intent build")

    sup = list(student_output_v1.get("supporting_indicators") or [])
    con = list(student_output_v1.get("conflicting_indicators") or [])
    if for_llm:
        if not all(isinstance(x, str) for x in sup) or not all(isinstance(x, str) for x in con):
            return None, _err("supporting_indicators and conflicting_indicators must be list[str] for LLM profile")

    ctx = str(student_output_v1.get("context_fit") or "")
    inv = str(student_output_v1.get("invalidation_text") or "")

    source_d = digest_sealed_student_output_v1(student_output_v1)

    ts = created_at_utc
    if not ts:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    j = (job_id or "").strip()
    fp = (fingerprint or "").strip()
    if not j or not fp:
        return None, _err("job_id and fingerprint must be non-empty")

    out: dict[str, Any] = {
        "schema": SCHEMA_STUDENT_EXECUTION_INTENT_V1,
        "schema_version": STUDENT_EXECUTION_INTENT_SCHEMA_VERSION_V1,
        "job_id": j,
        "fingerprint": fp,
        "student_brain_profile_v1": prof_n,
        "llm_model": llm_model,
        "source_student_output_digest_v1": source_d,
        "action": action,
        "direction": direction,
        "confidence_01": c01,
        "confidence_band": cb,
        "supporting_indicators": sup,
        "conflicting_indicators": con,
        "context_fit": ctx.strip(),
        "invalidation_text": inv.strip(),
        "created_at_utc": ts,
    }
    if sid:
        out["scenario_id"] = sid
    if tid:
        out["trade_id"] = tid

    out["student_execution_intent_digest_v1"] = compute_student_execution_intent_digest_v1(out)
    v = validate_student_execution_intent_v1(out)
    if v:
        return None, v
    return out, []
