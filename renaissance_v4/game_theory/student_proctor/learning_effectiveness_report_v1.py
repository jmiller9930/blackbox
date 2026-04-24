"""
GT_DIRECTIVE_023 — Learning **effectiveness** proof (read-only audit).

Uses persisted ``batch_scorecard.jsonl``, ``student_learning_records_v1.jsonl``, and optionally
``training_dataset_v1.jsonl`` line count only. Does **not** mutate stores, re-run grading, or re-run L3.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
)
from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl
from renaissance_v4.game_theory.pml_runtime_layout import pml_runtime_root
from renaissance_v4.game_theory.student_panel_l1_road_v1 import (
    line_e_value_for_l1_v1,
    line_p_value_for_l1_v1,
    read_batch_scorecard_file_order_v1,
    resolved_brain_profile_v1,
    scorecard_line_fingerprint_sha256_40_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    load_student_learning_records_v1,
)
from renaissance_v4.game_theory.student_proctor.training_export_v1 import (
    default_training_dataset_jsonl_path_v1,
)

SCHEMA_LEARNING_EFFECTIVENESS_REPORT_V1 = "learning_effectiveness_report_v1"
CONTRACT_VERSION_LEARNING_EFFECTIVENESS_V1 = 1

MATERIALIZE_LEARNING_EFFECTIVENESS_CONFIRM_V1 = "MATERIALIZE_LEARNING_EFFECTIVENESS_REPORT_V1"


def default_learning_effectiveness_report_path_v1() -> Path:
    """
    Default: ``<pml_runtime_root>/student_learning/learning_effectiveness_report_v1.json``.

    Override: ``PATTERN_GAME_LEARNING_EFFECTIVENESS_REPORT_V1`` — path to a ``.json`` file.
    """
    override = (os.environ.get("PATTERN_GAME_LEARNING_EFFECTIVENESS_REPORT_V1") or "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    root = pml_runtime_root() / "student_learning"
    root.mkdir(parents=True, exist_ok=True)
    return root / "learning_effectiveness_report_v1.json"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _started_ts(row: dict[str, Any]) -> str:
    return str(row.get("started_at_utc") or row.get("ended_at_utc") or "")


def _run_done_v1(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "").strip().lower() == "done"


def _pass_float_v1(row: dict[str, Any]) -> float | None:
    v = row.get("exam_pass_v1")
    if v is True:
        return 1.0
    if v is False:
        return 0.0
    return None


def _linear_slope_y_over_index_v1(ys: list[float]) -> float | None:
    """Slope of ``y`` vs ``x = 0..n-1`` (least squares). ``None`` if ``n < 2``."""
    n = len(ys)
    if n < 2:
        return None
    xs = list(range(n))
    sx = float(sum(xs))
    sy = float(sum(ys))
    sxx = float(sum(x * x for x in xs))
    sxy = float(sum(xs[i] * ys[i] for i in range(n)))
    den = n * sxx - sx * sx
    if abs(den) < 1e-18:
        return None
    return (n * sxy - sx * sy) / den


def _variance_population_v1(vals: list[float]) -> float | None:
    if not vals:
        return None
    m = sum(vals) / len(vals)
    if len(vals) == 1:
        return 0.0
    return sum((v - m) ** 2 for v in vals) / len(vals)


def _trend_label_v1(slope: float | None, *, eps: float = 1e-9) -> str:
    if slope is None:
        return "insufficient_data"
    if slope > eps:
        return "increasing"
    if slope < -eps:
        return "decreasing"
    return "flat"


def _mean_or_none(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _aggregate_learning_by_run_v1(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        jid = str(row.get("run_id") or "").strip()
        if not jid:
            continue
        b = out.setdefault(jid, {"promote": 0, "hold": 0, "reject": 0, "ungoverned": 0})
        lg = row.get("learning_governance_v1")
        if not isinstance(lg, dict):
            b["ungoverned"] += 1
            continue
        d = str(lg.get("decision") or "").strip().lower()
        if d == "promote":
            b["promote"] += 1
        elif d == "hold":
            b["hold"] += 1
        elif d == "reject":
            b["reject"] += 1
        else:
            b["ungoverned"] += 1
    return out


def _training_dataset_line_count_v1() -> tuple[str | None, int]:
    p = default_training_dataset_jsonl_path_v1()
    if not p.is_file():
        return None, 0
    n = sum(1 for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip())
    return str(p.resolve()), n


def build_learning_effectiveness_report_v1(
    *,
    scorecard_path: Path | None = None,
    store_path: Path | str,
    max_scorecard_lines: int = 20_000,
) -> dict[str, Any]:
    """
    Build ``learning_effectiveness_report_v1`` (pure function — caller may persist).

    Deterministic: fingerprints sorted lexicographically; runs within each fingerprint sorted by
    ``(started_at_utc, job_id)``; JSON serialization uses ``sort_keys=True`` when materializing.
    """
    sc_path = scorecard_path or default_batch_scorecard_jsonl()
    raw_rows = read_batch_scorecard_file_order_v1(path=sc_path, max_lines=max_scorecard_lines)
    done_rows = [r for r in raw_rows if isinstance(r, dict) and _run_done_v1(r)]
    learn_rows = load_student_learning_records_v1(store_path)
    learn_by_run = _aggregate_learning_by_run_v1(learn_rows)
    train_path, train_n = _training_dataset_line_count_v1()

    by_fp: dict[str, list[dict[str, Any]]] = {}
    for row in done_rows:
        fp = scorecard_line_fingerprint_sha256_40_v1(row)
        if not fp:
            fp = "__missing_fingerprint_v1__"
        by_fp.setdefault(fp, []).append(row)

    fp_keys = sorted(by_fp.keys())
    per_fp: list[dict[str, Any]] = []

    for fp in fp_keys:
        runs = by_fp[fp]
        runs.sort(key=lambda r: (_started_ts(r), str(r.get("job_id") or "")))

        series_e: list[float] = []
        series_p: list[float] = []
        series_pass: list[float] = []
        run_summaries: list[dict[str, Any]] = []
        for i, r in enumerate(runs):
            jid = str(r.get("job_id") or "").strip()
            e = line_e_value_for_l1_v1(r)
            p = line_p_value_for_l1_v1(r)
            pv = _pass_float_v1(r)
            prof = resolved_brain_profile_v1(r) or ""
            lg = learn_by_run.get(jid, {"promote": 0, "hold": 0, "reject": 0, "ungoverned": 0})
            if e is not None:
                series_e.append(float(e))
            if p is not None:
                series_p.append(float(p))
            if pv is not None:
                series_pass.append(float(pv))
            run_summaries.append(
                {
                    "job_id": jid,
                    "started_at_utc": _started_ts(r),
                    "student_brain_profile_v1": prof,
                    "e_scalar_v1": e,
                    "p_scalar_v1": p,
                    "exam_pass_v1": r.get("exam_pass_v1"),
                    "learning_rows_promote_v1": int(lg.get("promote") or 0),
                    "learning_rows_hold_v1": int(lg.get("hold") or 0),
                    "ordinal_in_fingerprint_v1": i,
                }
            )

        slope_e = _linear_slope_y_over_index_v1(series_e) if len(series_e) >= 2 else None
        slope_p = _linear_slope_y_over_index_v1(series_p) if len(series_p) >= 2 else None
        slope_pass = _linear_slope_y_over_index_v1(series_pass) if len(series_pass) >= 2 else None

        def _collect_profile(measure: str) -> dict[str, Any]:
            buckets: dict[str, list[float]] = {
                STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1: [],
                STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1: [],
                STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1: [],
            }
            pass_buckets: dict[str, list[float]] = {
                STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1: [],
                STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1: [],
                STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1: [],
            }
            for r in runs:
                prof = resolved_brain_profile_v1(r) or ""
                if prof not in buckets:
                    continue
                if measure == "e":
                    v = line_e_value_for_l1_v1(r)
                    if v is not None:
                        buckets[prof].append(float(v))
                elif measure == "p":
                    v = line_p_value_for_l1_v1(r)
                    if v is not None:
                        buckets[prof].append(float(v))
                else:
                    pv = _pass_float_v1(r)
                    if pv is not None:
                        pass_buckets[prof].append(pv)
            out_m: dict[str, Any] = {}
            for pk, vals in buckets.items():
                out_m[pk] = {
                    "n": len(vals),
                    "mean": _mean_or_none(vals),
                }
            if measure == "pass":
                for pk, vals in pass_buckets.items():
                    out_m[pk] = {
                        "n": len(vals),
                        "mean_pass_rate_v1": _mean_or_none(vals),
                    }
            return out_m

        e_by_prof = _collect_profile("e")
        p_by_prof = _collect_profile("p")
        pass_by_prof = _collect_profile("pass")

        def _delta(mean_a: float | None, mean_b: float | None) -> float | None:
            if mean_a is None or mean_b is None:
                return None
            return float(mean_a - mean_b)

        base_e = e_by_prof[STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1]["mean"]
        mem_e = e_by_prof[STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1]["mean"]
        llm_e = e_by_prof[STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1]["mean"]
        base_p = p_by_prof[STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1]["mean"]
        mem_p = p_by_prof[STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1]["mean"]
        llm_p = p_by_prof[STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1]["mean"]
        base_pass = pass_by_prof[STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1]["mean_pass_rate_v1"]
        mem_pass = pass_by_prof[STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1]["mean_pass_rate_v1"]
        llm_pass = pass_by_prof[STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1]["mean_pass_rate_v1"]

        next_e_prom: list[float] = []
        next_e_not: list[float] = []
        next_p_prom: list[float] = []
        next_p_not: list[float] = []
        next_pass_prom: list[float] = []
        next_pass_not: list[float] = []
        for i in range(len(runs) - 1):
            cur = runs[i]
            nxt = runs[i + 1]
            jid = str(cur.get("job_id") or "").strip()
            lg = learn_by_run.get(jid, {"promote": 0})
            promoted = int(lg.get("promote") or 0) > 0
            e_n = line_e_value_for_l1_v1(nxt)
            p_n = line_p_value_for_l1_v1(nxt)
            pass_n = _pass_float_v1(nxt)
            if promoted:
                if e_n is not None:
                    next_e_prom.append(float(e_n))
                if p_n is not None:
                    next_p_prom.append(float(p_n))
                if pass_n is not None:
                    next_pass_prom.append(float(pass_n))
            else:
                if e_n is not None:
                    next_e_not.append(float(e_n))
                if p_n is not None:
                    next_p_not.append(float(p_n))
                if pass_n is not None:
                    next_pass_not.append(float(pass_n))

        all_e_vals = [float(line_e_value_for_l1_v1(r)) for r in runs if line_e_value_for_l1_v1(r) is not None]
        all_p_vals = [float(line_p_value_for_l1_v1(r)) for r in runs if line_p_value_for_l1_v1(r) is not None]

        per_fp.append(
            {
                "fingerprint_sha256_40": fp,
                "n_runs_done_v1": len(runs),
                "runs_ordered_v1": run_summaries,
                "time_trends_v1": {
                    "slope_e_over_ordinal_v1": slope_e,
                    "slope_p_over_ordinal_v1": slope_p,
                    "slope_pass_over_ordinal_v1": slope_pass,
                    "pass_trend_label_v1": _trend_label_v1(slope_pass),
                    "e_trend_label_v1": _trend_label_v1(slope_e),
                    "p_trend_label_v1": _trend_label_v1(slope_p),
                    "n_points_e_v1": len(series_e),
                    "n_points_p_v1": len(series_p),
                    "n_points_pass_v1": len(series_pass),
                },
                "profile_means_v1": {
                    "e_by_profile_v1": e_by_prof,
                    "p_by_profile_v1": p_by_prof,
                    "pass_rate_by_profile_v1": pass_by_prof,
                },
                "deltas_v1": {
                    "delta_mean_e_memory_student_vs_baseline_v1": _delta(mem_e, base_e),
                    "delta_mean_p_memory_student_vs_baseline_v1": _delta(mem_p, base_p),
                    "delta_mean_pass_memory_student_vs_baseline_v1": _delta(mem_pass, base_pass),
                    "delta_mean_e_llm_vs_memory_student_v1": _delta(llm_e, mem_e),
                    "delta_mean_p_llm_vs_memory_student_v1": _delta(llm_p, mem_p),
                    "delta_mean_pass_llm_vs_memory_student_v1": _delta(llm_pass, mem_pass),
                },
                "promotion_next_run_v1": {
                    "n_pairs_next_after_promoted_source_v1": len(next_e_prom),
                    "mean_e_next_run_after_promoted_source_v1": _mean_or_none(next_e_prom),
                    "mean_p_next_run_after_promoted_source_v1": _mean_or_none(next_p_prom),
                    "mean_pass_next_run_after_promoted_source_v1": _mean_or_none(next_pass_prom),
                    "n_pairs_next_after_non_promoted_source_v1": len(next_e_not),
                    "mean_e_next_run_after_non_promoted_source_v1": _mean_or_none(next_e_not),
                    "mean_p_next_run_after_non_promoted_source_v1": _mean_or_none(next_p_not),
                    "mean_pass_next_run_after_non_promoted_source_v1": _mean_or_none(next_pass_not),
                },
                "stability_v1": {
                    "variance_e_across_runs_v1": _variance_population_v1(all_e_vals),
                    "variance_p_across_runs_v1": _variance_population_v1(all_p_vals),
                },
            }
        )

    n_fp = len(per_fp)
    n_runs = sum(x["n_runs_done_v1"] for x in per_fp)
    slopes_e = [x["time_trends_v1"]["slope_e_over_ordinal_v1"] for x in per_fp]
    slopes_e_f = [s for s in slopes_e if s is not None]
    pos_e_fp = sum(1 for s in slopes_e_f if s > 1e-9)
    neg_e_fp = sum(1 for s in slopes_e_f if s < -1e-9)

    def _collect_global_deltas(key: str) -> list[float]:
        out: list[float] = []
        for x in per_fp:
            v = (x.get("deltas_v1") or {}).get(key)
            if isinstance(v, (int, float)):
                out.append(float(v))
        return out

    d_mem_e = _collect_global_deltas("delta_mean_e_memory_student_vs_baseline_v1")
    d_llm_e = _collect_global_deltas("delta_mean_e_llm_vs_memory_student_v1")

    verdict_improving = False
    if slopes_e_f and pos_e_fp > neg_e_fp:
        verdict_improving = True
    if d_mem_e:
        need = (len(d_mem_e) // 2) + 1
        if sum(1 for x in d_mem_e if x > 1e-9) >= need:
            verdict_improving = True
    if d_llm_e and sum(d_llm_e) / len(d_llm_e) > 1e-9:
        verdict_improving = True

    verdict_statement = (
        "system_improving_v1: positive E time-slopes dominate negative ones across fingerprints, "
        "and/or memory-context Student mean E exceeds baseline on a majority of fingerprints, "
        "and/or LLM profile mean E exceeds memory-stub on average (read-only audit)."
        if verdict_improving
        else "not_improving_or_inconclusive_v1: fingerprints do not jointly show the above signals — "
        "do not proceed to training on this evidence alone."
    )

    report: dict[str, Any] = {
        "schema": SCHEMA_LEARNING_EFFECTIVENESS_REPORT_V1,
        "contract_version": CONTRACT_VERSION_LEARNING_EFFECTIVENESS_V1,
        "generated_at_utc": _utc_iso(),
        "sources_v1": {
            "batch_scorecard_path": str(Path(sc_path).resolve()),
            "student_learning_store_path": str(Path(store_path).resolve()),
            "training_dataset_v1_path": train_path,
            "training_dataset_v1_line_count": train_n,
        },
        "global_v1": {
            "fingerprints_analyzed_v1": n_fp,
            "runs_done_analyzed_v1": n_runs,
            "fingerprints_with_positive_e_slope_v1": pos_e_fp,
            "fingerprints_with_negative_e_slope_v1": neg_e_fp,
            "fingerprints_with_computable_e_slope_v1": len(slopes_e_f),
            "verdict_improving_flag_v1": verdict_improving,
        },
        "fingerprints_v1": per_fp,
        "verdict_v1": {
            "statement_v1": verdict_statement,
            "verdict_class_v1": "improving" if verdict_improving else "not_improving_or_inconclusive",
        },
    }
    return report


def summarize_learning_effectiveness_report_v1(report: dict[str, Any]) -> dict[str, Any]:
    """Strip heavy per-run arrays for ``summary=1`` API responses."""
    fps = report.get("fingerprints_v1") or []
    slim: list[dict[str, Any]] = []
    for x in fps:
        if not isinstance(x, dict):
            continue
        d = {k: v for k, v in x.items() if k != "runs_ordered_v1"}
        d["n_runs_in_series_v1"] = len(x.get("runs_ordered_v1") or [])
        slim.append(d)
    return {
        "schema": "learning_effectiveness_report_summary_v1",
        "contract_version": report.get("contract_version"),
        "generated_at_utc": report.get("generated_at_utc"),
        "sources_v1": report.get("sources_v1"),
        "global_v1": report.get("global_v1"),
        "verdict_v1": report.get("verdict_v1"),
        "fingerprints_v1": slim,
    }


def materialize_learning_effectiveness_report_v1(
    *,
    scorecard_path: Path | None,
    store_path: Path | str,
    output_path: Path | str | None,
    confirm: str | None,
) -> dict[str, Any]:
    if str(confirm or "").strip() != MATERIALIZE_LEARNING_EFFECTIVENESS_CONFIRM_V1:
        return {
            "ok": False,
            "error": "confirm must match MATERIALIZE_LEARNING_EFFECTIVENESS_REPORT_V1",
        }
    out_p = Path(str(output_path)) if output_path else default_learning_effectiveness_report_path_v1()
    doc = build_learning_effectiveness_report_v1(scorecard_path=scorecard_path, store_path=store_path)
    body = json.dumps(doc, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_p.with_suffix(out_p.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(out_p)
    return {"ok": True, "path": str(out_p.resolve()), "bytes_written": len(body.encode("utf-8"))}


__all__ = [
    "CONTRACT_VERSION_LEARNING_EFFECTIVENESS_V1",
    "MATERIALIZE_LEARNING_EFFECTIVENESS_CONFIRM_V1",
    "SCHEMA_LEARNING_EFFECTIVENESS_REPORT_V1",
    "build_learning_effectiveness_report_v1",
    "default_learning_effectiveness_report_path_v1",
    "materialize_learning_effectiveness_report_v1",
    "summarize_learning_effectiveness_report_v1",
]
