"""
GT_DIRECTIVE_016 — L1 **road** aggregation: brain-profile split, A/B vs fingerprint baseline, single-pass scorecard read.

**Truth rules:** Only scorecard-native fields are used. ``expectancy_per_trade`` is the **E** scalar
(mean across runs in a group). **P** uses optional ``student_l1_process_score_v1`` (0..1) when
present on a line — reserved for future batch denorm; when absent, ``avg_p`` is null and banding
falls back to **E vs anchor** only with ``process_leg: "data_gap"``.

**No cross-fingerprint mixing:** Groups are keyed by ``(fingerprint, brain_profile, llm_model)``.

**GT_DIRECTIVE_020:** Per-job ``road_by_job_id_v1`` carries denormalized exam E/P and value sources;
group objects expose optional ``group_avg_exam_*`` aggregates for operator comparison (same scalars as band logic).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    CANONICAL_STUDENT_BRAIN_PROFILES_V1,
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    normalize_student_reasoning_mode_v1,
)

SCHEMA_L1_ROAD = "student_panel_l1_road_v1"

# Reserved optional scorecard field (0..1). Not written by batch_scorecard v1 — tests may set it.
_PROCESS_SCORE_KEY = "student_l1_process_score_v1"
# GT_DIRECTIVE_019 — exam-pack grading denorm on scorecard (from ``compute_exam_grade_v1`` only).
_EXAM_E_SCORE_KEY = "exam_e_score_v1"
_EXAM_P_SCORE_KEY = "exam_p_score_v1"


def scorecard_line_fingerprint_sha256_40_v1(row: dict[str, Any]) -> str | None:
    """Same fingerprint recipe as L1 D11 anchor chain (MCI first, else operator_batch_audit hash)."""
    mci = row.get("memory_context_impact_audit_v1")
    if isinstance(mci, dict):
        fp = mci.get("run_config_fingerprint_sha256_40")
        if fp:
            return str(fp).strip()
    oba = row.get("operator_batch_audit")
    if isinstance(oba, dict):
        parts = [
            str(oba.get("operator_recipe_id") or ""),
            str(oba.get("evaluation_window_effective_calendar_months") or ""),
            str(oba.get("manifest_path_primary") or ""),
            str(oba.get("policy_framework_id") or ""),
        ]
        blob = "\n".join(parts)
        if blob.strip():
            return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]
    return None


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def line_e_value_for_l1_v1(row: dict[str, Any]) -> float | None:
    """Prefer ``exam_e_score_v1``; else ``expectancy_per_trade`` (Referee batch proxy E)."""
    e = _float(row.get(_EXAM_E_SCORE_KEY))
    if e is not None:
        return e
    return _float(row.get("expectancy_per_trade"))


def line_p_value_for_l1_v1(row: dict[str, Any]) -> float | None:
    """Prefer ``exam_p_score_v1``; else optional ``student_l1_process_score_v1``."""
    p = _float(row.get(_EXAM_P_SCORE_KEY))
    if p is not None:
        return p
    return _float(row.get(_PROCESS_SCORE_KEY))


def _started_ts(row: dict[str, Any]) -> str:
    return str(row.get("started_at_utc") or row.get("ended_at_utc") or "")


def resolved_brain_profile_v1(row: dict[str, Any]) -> str | None:
    raw = row.get("student_brain_profile_v1")
    if isinstance(raw, str) and raw.strip() in CANONICAL_STUDENT_BRAIN_PROFILES_V1:
        return raw.strip()
    leg = row.get("student_reasoning_mode")
    if isinstance(leg, str) and leg.strip():
        return normalize_student_reasoning_mode_v1(leg.strip())
    return None


def resolved_llm_model_tag_v1(row: dict[str, Any], profile: str | None) -> str | None:
    if profile != STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        return None
    m = row.get("llm_model")
    if isinstance(m, str) and m.strip():
        return m.strip()
    block = row.get("student_llm_v1")
    if isinstance(block, dict):
        lm = block.get("llm_model")
        if isinstance(lm, str) and lm.strip():
            return lm.strip()
    return None


def read_batch_scorecard_file_order_v1(*, path: Path | None = None, max_lines: int = 20_000) -> list[dict[str, Any]]:
    """
    Parse ``batch_scorecard.jsonl`` in **file order** (oldest line first). Streams the file and stops
    after ``max_lines`` physical lines (same cap as the historical ``read_text`` + slice behavior) so
    huge logs do not allocate one giant string.
    """
    from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl

    p = (path or default_batch_scorecard_jsonl()).expanduser().resolve()
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    n_read = 0
    with p.open(encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            if n_read >= max_lines:
                break
            n_read += 1
            line = raw_line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def newest_done_rows_by_brain_profile_for_fingerprint_v1(
    fingerprint_sha256_40: str,
    *,
    accepted_profiles: frozenset[str],
    path: Path | None = None,
    max_scan_lines: int | None = 500_000,
) -> dict[str, dict[str, Any]]:
    """
    One forward streaming pass of ``batch_scorecard.jsonl``: for each ``done`` line whose
    fingerprint matches ``fingerprint_sha256_40``, record the row under ``resolved_brain_profile_v1``
    when that profile is in ``accepted_profiles``. On append-only JSONL, the **last** seen row per
    profile is the newest — no full-file ``read_text``.
    """
    from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl

    fp_need = str(fingerprint_sha256_40 or "").strip()
    if not fp_need:
        return {}
    p = (path or default_batch_scorecard_jsonl()).expanduser().resolve()
    if not p.is_file():
        return {}
    out: dict[str, dict[str, Any]] = {}
    n = 0
    with p.open(encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            if max_scan_lines is not None and n >= max_scan_lines:
                break
            n += 1
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("status") or "").strip().lower() != "done":
                continue
            if scorecard_line_fingerprint_sha256_40_v1(row) != fp_need:
                continue
            pr = resolved_brain_profile_v1(row)
            if not pr or pr not in accepted_profiles:
                continue
            out[pr] = row
    return out


def l1_road_legend_v1() -> dict[str, Any]:
    """API-delivered legend (no UI hardcoding required)."""
    return {
        "schema": "student_panel_l1_road_legend_v1",
        "brain_profiles": {
            STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1: (
                "Operator **Baseline** (control): deterministic Referee replay; Student seam off; "
                "no cross-run memory or 026C cumulative learning on this run."
            ),
            STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1: (
                "Internal profile (debug): memory + context with stub / deterministic Student emitter — "
                "not the primary operator Run mode; use **Student** for the full unified path."
            ),
            STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1: (
                "Operator **Student**: unified path — entry/lifecycle reasoning, 026C retrieval, 026AI router, "
                "governed Ollama (``qwen2.5:7b``; ``STUDENT_OLLAMA_BASE_URL``)."
            ),
        },
        "band_a": (
            "Band **A** — improved vs the **same-fingerprint** baseline anchor: group mean **E** uses "
            "``exam_e_score_v1`` when present on scorecard lines (**GT_DIRECTIVE_019**), else "
            "``expectancy_per_trade``; strictly greater than anchor **E**. When **P** is available on "
            "both sides, group mean **P** uses ``exam_p_score_v1`` when present, else "
            "``student_l1_process_score_v1``, compared ≥ anchor **P** (within float tolerance)."
        ),
        "band_b": (
            "Band **B** — not improved or degraded vs that anchor under the same E/P rules as Band A "
            "(exam E/P when present on lines, else batch proxies), or E-only tie when P is unavailable."
        ),
        "band_baseline_ruler": (
            "Rows whose brain profile is the baseline ruler for the fingerprint — not scored A vs B "
            "against themselves."
        ),
        "pass_rate_percent": (
            "Mean of ``referee_win_pct`` over runs in the group where that field is non-null. "
            "This is **session** Referee win rate as recorded on the scorecard line, not an invented pass bit."
        ),
        "avg_e_expectancy_per_trade": (
            "Mean of **E** scalars per line: ``exam_e_score_v1`` when set (**019**), else "
            "``expectancy_per_trade`` proxy."
        ),
        "avg_p_process_score": (
            "Mean of **P** scalars per line: ``exam_p_score_v1`` when set (**019**), else optional "
            "``student_l1_process_score_v1``; else null with ``process_leg: data_gap`` for A/B when P "
            "cannot be compared."
        ),
        "fingerprint": (
            "``run_config_fingerprint_sha256_40`` from ``memory_context_impact_audit_v1``, else a "
            "deterministic 40-char hash from ``operator_batch_audit`` recipe/window/manifest keys — "
            "same as Student panel L1 anchor logic."
        ),
        "llm_model": (
            "Student Ollama model tag (fixed: ``qwen2.5:7b``) for ``memory_context_llm_student`` "
            "only; null for other profiles."
        ),
        "group_avg_exam_e_score_v1": (
            "GT_DIRECTIVE_020 — mean of ``exam_e_score_v1`` over group members that have exam economic grade; "
            "null when no line in the group is graded."
        ),
        "group_avg_exam_p_score_v1": (
            "GT_DIRECTIVE_020 — mean of ``exam_p_score_v1`` over members with exam process score; null when none."
        ),
        "group_exam_graded_run_count_v1": (
            "Count of runs in the group with ``exam_e_score_v1`` present (exam-pack grading denormalized)."
        ),
        "group_exam_pass_count_v1": (
            "Count of runs in the group with ``exam_pass_v1`` true (subset of graded lines only)."
        ),
        "road_exam_ep_per_job_v1": (
            "Per ``job_id``, ``road_by_job_id_v1`` includes ``exam_*``, ``l1_*_value_source_v1``, and "
            "``l1_e_scalar_v1`` / ``l1_p_scalar_v1`` (same scalars used for banding)."
        ),
    }


def _line_ok_for_agg(row: dict[str, Any]) -> bool:
    st = str(row.get("status") or "").strip().lower()
    if st in ("running", "error"):
        return False
    if str(row.get("_inflight", "")).lower() == "true" or row.get("scorecard_inflight"):
        return False
    return True


def _group_sort_key(g: dict[str, Any]) -> tuple[str, str, str]:
    gk = g.get("group_key") or {}
    fp = str(gk.get("fingerprint_sha256_40") or "")
    pr = str(gk.get("student_brain_profile_v1") or "")
    lm = str(gk.get("llm_model") or "")
    return (fp, pr, lm)


def build_l1_road_payload_v1(
    *,
    lines: list[dict[str, Any]] | None = None,
    scorecard_path: Path | None = None,
    max_scorecard_lines: int = 20_000,
) -> dict[str, Any]:
    """
    Build the ``GET /api/student-panel/l1-road`` JSON body.

    Either pass ``lines`` (tests) or ``scorecard_path`` / default file (production).
    """
    if lines is None:
        lines = read_batch_scorecard_file_order_v1(path=scorecard_path, max_lines=max_scorecard_lines)
    top_gaps: list[str] = []
    fp_missing_any = False
    usable = [r for r in lines if isinstance(r, dict) and _line_ok_for_agg(r)]
    if not usable:
        leg = l1_road_legend_v1()
        return {
            "ok": True,
            "schema": SCHEMA_L1_ROAD,
            "groups": [],
            "legend": leg,
            "road_by_job_id_v1": {},
            "data_gaps": ["no_completed_scorecard_lines_v1"],
            "note": "Single-pass scorecard aggregation; no Student learning JSONL scan.",
        }

    job_id_to_line: dict[str, dict[str, Any]] = {}
    for row in usable:
        jid = str(row.get("job_id") or "").strip()
        if jid:
            job_id_to_line[jid] = row

    by_fp: dict[str, list[dict[str, Any]]] = {}
    unknown_profile = 0
    for row in usable:
        fp = scorecard_line_fingerprint_sha256_40_v1(row)
        if not fp:
            fp_missing_any = True
            continue
        prof = resolved_brain_profile_v1(row)
        if not prof:
            unknown_profile += 1
            continue
        by_fp.setdefault(fp, []).append(row)
    if unknown_profile:
        top_gaps.append("scorecard_lines_missing_brain_profile_v1")
    if fp_missing_any:
        top_gaps.append("scorecard_line_missing_fingerprint_v1")

    groups_out: list[dict[str, Any]] = []

    for fp, fp_rows in sorted(by_fp.items(), key=lambda x: x[0]):
        fp_rows_sorted = sorted(fp_rows, key=_started_ts)
        anchor_row: dict[str, Any] | None = None
        for r in fp_rows_sorted:
            if resolved_brain_profile_v1(r) == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
                anchor_row = r
                break
        anchor_e = line_e_value_for_l1_v1(anchor_row) if anchor_row else None
        anchor_p = line_p_value_for_l1_v1(anchor_row) if anchor_row else None
        anchor_job = str(anchor_row.get("job_id") or "") if anchor_row else ""

        # Partition into (profile, llm_model) buckets — LLM profile splits by model tag (including None).
        buckets: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
        for r in fp_rows:
            prof = resolved_brain_profile_v1(r)
            if not prof:
                continue
            lm = resolved_llm_model_tag_v1(r, prof)
            key = (prof, lm)
            buckets.setdefault(key, []).append(r)

        for (prof, lm_tag), rs in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
            e_vals = [x for x in (line_e_value_for_l1_v1(x) for x in rs) if x is not None]
            p_vals = [x for x in (line_p_value_for_l1_v1(x) for x in rs) if x is not None]
            e_sources = sorted(
                {str(x.get("l1_e_value_source_v1") or "expectancy_per_trade_proxy_v1") for x in rs}
            )
            p_sources = sorted({str(x.get("l1_p_value_source_v1") or "data_gap") for x in rs})
            rw_vals = [x for x in (_float(x.get("referee_win_pct")) for x in rs) if x is not None]

            avg_e = round(sum(e_vals) / len(e_vals), 6) if e_vals else None
            avg_p = round(sum(p_vals) / len(p_vals), 6) if p_vals else None
            pass_rate = round(sum(rw_vals) / len(rw_vals), 4) if rw_vals else None

            exam_e_only = [_float(x.get(_EXAM_E_SCORE_KEY)) for x in rs]
            exam_e_only = [x for x in exam_e_only if x is not None]
            exam_p_only = [_float(x.get(_EXAM_P_SCORE_KEY)) for x in rs]
            exam_p_only = [x for x in exam_p_only if x is not None]
            graded_n = sum(1 for x in rs if x.get(_EXAM_E_SCORE_KEY) is not None)
            pass_n = sum(1 for x in rs if x.get("exam_pass_v1") is True)
            group_avg_exam_e = (
                round(sum(exam_e_only) / len(exam_e_only), 6) if exam_e_only else None
            )
            group_avg_exam_p = (
                round(sum(exam_p_only) / len(exam_p_only), 6) if exam_p_only else None
            )

            g_gaps: list[str] = []
            band: str
            process_leg: str

            if prof == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
                band = "baseline_ruler"
                process_leg = "n_a"
            elif anchor_row is None:
                band = "data_gap"
                process_leg = "data_gap"
                g_gaps.append("no_baseline_anchor_in_fingerprint_v1")
            else:
                ae = anchor_e
                ap = anchor_p
                if avg_e is None:
                    band = "data_gap"
                    process_leg = "data_gap"
                    g_gaps.append("group_missing_expectancy_per_trade_v1")
                elif ae is None:
                    band = "data_gap"
                    process_leg = "data_gap"
                    g_gaps.append("anchor_missing_expectancy_per_trade_v1")
                else:
                    eps = 1e-9
                    e_improved = avg_e > ae + eps
                    e_degraded = avg_e < ae - eps
                    if avg_p is not None and ap is not None:
                        process_leg = "compared"
                        p_ok = avg_p >= ap - eps
                        if e_improved and p_ok:
                            band = "A"
                        else:
                            band = "B"
                    else:
                        process_leg = "data_gap"
                        if e_improved:
                            band = "A"
                        elif e_degraded:
                            band = "B"
                        else:
                            band = "B"

            member_ids = [str(x.get("job_id") or "").strip() for x in rs if str(x.get("job_id") or "").strip()]
            groups_out.append(
                {
                    "schema": "student_panel_l1_road_group_v1",
                    "group_key": {
                        "fingerprint_sha256_40": fp,
                        "student_brain_profile_v1": prof,
                        "llm_model": lm_tag,
                    },
                    "run_count": len(rs),
                    "member_job_ids": member_ids,
                    "job_ids_sample": member_ids[-5:],
                    "pass_rate_percent": pass_rate,
                    "avg_e_expectancy_per_trade": avg_e,
                    "avg_p_process_score": avg_p,
                    "band": band,
                    "process_leg": process_leg,
                    "anchor_job_id": anchor_job or None,
                    "anchor_expectancy_per_trade": anchor_e,
                    "anchor_process_score": anchor_p,
                    "l1_e_value_sources_v1": e_sources,
                    "l1_p_value_sources_v1": p_sources,
                    "group_avg_exam_e_score_v1": group_avg_exam_e,
                    "group_avg_exam_p_score_v1": group_avg_exam_p,
                    "group_exam_graded_run_count_v1": graded_n,
                    "group_exam_pass_count_v1": pass_n,
                    "data_gaps": g_gaps,
                }
            )

    groups_out.sort(key=_group_sort_key)

    road_by_job_id_v1: dict[str, dict[str, Any]] = {}
    for g in groups_out:
        gk = g.get("group_key") or {}
        band = str(g.get("band") or "")
        anchor_j = str(g.get("anchor_job_id") or "").strip() or None
        g_gaps = list(g.get("data_gaps") or [])
        for jid in g.get("member_job_ids") or []:
            if not jid:
                continue
            role = "compare"
            if band == "baseline_ruler":
                role = "ruler"
            elif anchor_j and jid == anchor_j:
                role = "baseline_anchor"
            line = job_id_to_line.get(jid) or {}
            road_by_job_id_v1[jid] = {
                "band": band,
                "process_leg": str(g.get("process_leg") or ""),
                "anchor_job_id": anchor_j,
                "row_anchor_role_v1": role,
                "group_data_gaps": g_gaps,
                "student_brain_profile_v1": gk.get("student_brain_profile_v1"),
                "llm_model": gk.get("llm_model"),
                "fingerprint_sha256_40": gk.get("fingerprint_sha256_40"),
                "exam_e_score_v1": line.get(_EXAM_E_SCORE_KEY),
                "exam_p_score_v1": line.get(_EXAM_P_SCORE_KEY),
                "exam_pass_v1": line.get("exam_pass_v1"),
                "l1_e_value_source_v1": line.get("l1_e_value_source_v1"),
                "l1_p_value_source_v1": line.get("l1_p_value_source_v1"),
                "l1_execution_authority_v1": line.get("l1_execution_authority_v1"),
                "l1_student_full_control_v1": line.get("l1_student_full_control_v1"),
                "execution_authority_v1": line.get("execution_authority_v1"),
                "student_lane_authority_truth_v1": line.get("student_lane_authority_truth_v1"),
                "l1_e_scalar_v1": line_e_value_for_l1_v1(line) if line else None,
                "l1_p_scalar_v1": line_p_value_for_l1_v1(line) if line else None,
                "external_api_status_v1": line.get("external_api_status_v1"),
                "external_api_block_reason_v1": line.get("external_api_block_reason_v1"),
                "external_api_action_url_v1": line.get("external_api_action_url_v1"),
            }
    # De-dupe top_gaps order-stable
    seen: set[str] = set()
    dg = [x for x in top_gaps if not (x in seen or seen.add(x))]

    legend = l1_road_legend_v1()
    return {
        "ok": True,
        "schema": SCHEMA_L1_ROAD,
        "groups": groups_out,
        "legend": legend,
        "road_by_job_id_v1": road_by_job_id_v1,
        "data_gaps": dg,
        "note": (
            "Aggregated in one scorecard read; keyed by fingerprint + brain profile + llm_model. "
            "A/B vs oldest baseline row in the same fingerprint only."
        ),
    }


__all__ = [
    "SCHEMA_L1_ROAD",
    "build_l1_road_payload_v1",
    "l1_road_legend_v1",
    "line_e_value_for_l1_v1",
    "line_p_value_for_l1_v1",
    "newest_done_rows_by_brain_profile_for_fingerprint_v1",
    "read_batch_scorecard_file_order_v1",
    "resolved_brain_profile_v1",
    "resolved_llm_model_tag_v1",
    "scorecard_line_fingerprint_sha256_40_v1",
]
