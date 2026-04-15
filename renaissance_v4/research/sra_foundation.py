"""
DV-ARCH-SRA-FOUNDATION-030 / 031 / 032 / 033 / 034 — SRA hypotheses, variants, ranking, promotion readiness.

Does not implement learning loops or change ingestion / evaluation logic. Uses existing
``compare-manifest`` (robustness_runner) for the full Kitchen flow.
Promotion evaluation is readiness-only (no activation). Controlled activation after approval is in
``sra_handoff`` (DV-ARCH-SRA-HANDOFF-034).
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from renaissance_v4.manifest.validate import validate_manifest_against_catalog
from renaissance_v4.registry import load_default_catalog
from renaissance_v4.research.experiment_tracker import new_experiment_id


def _rv4_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _repo_root() -> Path:
    return _rv4_root().parent


def hypotheses_jsonl_path() -> Path:
    return _rv4_root() / "state" / "hypotheses.jsonl"


def hypothesis_results_jsonl_path() -> Path:
    return _rv4_root() / "state" / "hypothesis_results.jsonl"


def hypothesis_rankings_json_path() -> Path:
    return _rv4_root() / "state" / "hypothesis_rankings.json"


def promotion_candidates_json_path() -> Path:
    return _rv4_root() / "state" / "promotion_candidates.json"


def promotion_min_trades() -> int:
    """Minimum deterministic total_trades for promotion readiness (override: ``SRA_PROMOTION_MIN_TRADES``)."""
    raw = os.environ.get("SRA_PROMOTION_MIN_TRADES", "5").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 5


def promotion_max_drawdown_floor() -> float:
    """
    Candidate ``max_drawdown`` must be >= this value (e.g. -0.25 means not worse than -25%).
    Override: ``SRA_PROMOTION_MAX_DRAWDOWN_FLOOR`` (default ``-1.0``, very permissive).
    """
    raw = os.environ.get("SRA_PROMOTION_MAX_DRAWDOWN_FLOOR", "-1.0").strip()
    try:
        return float(raw)
    except ValueError:
        return -1.0


def baseline_manifest_template_path() -> Path:
    return _rv4_root() / "configs" / "manifests" / "baseline_v1_recipe.json"


def _slug(s: str, *, max_len: int = 64) -> str:
    t = re.sub(r"[^a-zA-Z0-9_-]+", "_", s.strip()).strip("_")
    return (t[:max_len] if t else "hypo") or "hypo"


def append_hypothesis(record: dict[str, Any]) -> None:
    """Append one hypothesis record as a JSON line (creates file if missing)."""
    p = hypotheses_jsonl_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def iter_hypotheses() -> Iterator[dict[str, Any]]:
    p = hypotheses_jsonl_path()
    if not p.is_file():
        return
    yield from _iter_jsonl(p)


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def get_hypothesis_by_id(hypothesis_id: str) -> dict[str, Any] | None:
    """Return the last occurrence of hypothesis_id in the JSONL file."""
    hid = str(hypothesis_id).strip()
    last: dict[str, Any] | None = None
    for h in iter_hypotheses():
        if str(h.get("hypothesis_id") or "").strip() == hid:
            last = h
    return last


def _effective_signal_modules(hypothesis: dict[str, Any]) -> list[str]:
    """Resolved signal_modules for a hypothesis (parameters override, else baseline template)."""
    params = hypothesis.get("parameters")
    if isinstance(params, dict) and isinstance(params.get("signal_modules"), list):
        return [str(x) for x in params["signal_modules"]]
    tpl = json.loads(baseline_manifest_template_path().read_text(encoding="utf-8"))
    sm = tpl.get("signal_modules")
    if not isinstance(sm, list):
        return []
    return [str(x) for x in sm]


def _template_monte_carlo_config() -> dict[str, Any]:
    tpl = json.loads(baseline_manifest_template_path().read_text(encoding="utf-8"))
    mc = tpl.get("monte_carlo_config")
    return copy.deepcopy(mc) if isinstance(mc, dict) else {}


def generate_variants_from_hypothesis(hypothesis_id: str, n_variants: int) -> list[str]:
    """
    DV-ARCH-SRA-VARIANTS-031 — Produce N deterministic, bounded hypotheses from a base record.

    Each variant changes **at most one** controlled aspect per record (signal set OR Monte Carlo seed offset).
    Appends rows to ``hypotheses.jsonl`` with ``parent_hypothesis_id``, ``variant_type``, ``variant_index``.

    Does not perform random search: the sequence is fixed for a given ``(base_id, n_variants)``.
    """
    if n_variants < 1:
        raise ValueError("n_variants must be >= 1")
    base = get_hypothesis_by_id(hypothesis_id)
    if base is None:
        raise LookupError(f"hypothesis_id not found: {hypothesis_id}")

    base_id = str(base.get("hypothesis_id") or "").strip()
    sm = _effective_signal_modules(base)
    if len(sm) < 1:
        raise ValueError("base hypothesis must resolve to a non-empty signal_modules list")

    new_ids: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    for i in range(n_variants):
        # Cycle variant types: single-parameter change only (no multi-stage edits).
        mode = i % 2
        variant_type: str
        params = copy.deepcopy(base.get("parameters") or {})
        if not isinstance(params, dict):
            params = {}

        if mode == 0 and len(sm) > 1:
            variant_type = "signal_toggle"
            drop_idx = i % len(sm)
            new_sm = [x for j, x in enumerate(sm) if j != drop_idx]
            params["signal_modules"] = new_sm
        else:
            variant_type = "mc_config_offset"
            mc = params.get("monte_carlo_config")
            if not isinstance(mc, dict):
                mc = _template_monte_carlo_config()
            else:
                mc = copy.deepcopy(mc)
            base_seed = int(mc.get("seed") if mc.get("seed") is not None else 42)
            mc["seed"] = base_seed + (i + 1) * 31
            params["monte_carlo_config"] = mc

        vid = f"{base_id}_var_{i + 1:03d}_{_slug(variant_type, max_len=24)}"
        strat = f"sra_{_slug(vid, max_len=80)}"
        params["strategy_id"] = strat

        record: dict[str, Any] = {
            "hypothesis_id": vid,
            "description": f"Variant {i + 1}/{n_variants} of {base_id} ({variant_type})",
            "parameters": params,
            "created_at": now,
            "created_by": "system",
            "parent_hypothesis_id": base_id,
            "variant_type": variant_type,
            "variant_index": i,
        }
        generate_manifest_from_hypothesis(record)
        append_hypothesis(record)
        new_ids.append(vid)

    return new_ids


def generate_manifest_from_hypothesis(
    hypothesis: dict[str, Any],
    *,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Map a hypothesis record to a ``strategy_manifest_v1`` dict.

    Merges ``parameters`` onto the locked baseline recipe template (deterministic for identical inputs).
    Validates against the plugin catalog.
    """
    hid = str(hypothesis.get("hypothesis_id") or "").strip()
    if not hid:
        raise ValueError("hypothesis.hypothesis_id is required")

    params = hypothesis.get("parameters")
    if params is not None and not isinstance(params, dict):
        raise ValueError("hypothesis.parameters must be a mapping when present")
    params = dict(params or {})

    tpl_path = baseline_manifest_template_path()
    if not tpl_path.is_file():
        raise FileNotFoundError(f"baseline manifest template missing: {tpl_path}")
    base: dict[str, Any] = json.loads(tpl_path.read_text(encoding="utf-8"))

    desc = str(hypothesis.get("description") or "").strip() or f"SRA hypothesis {hid}"
    strat_id = str(params.pop("strategy_id", "") or "").strip() or f"sra_{_slug(hid)}"

    out: dict[str, Any] = dict(base)
    out["strategy_id"] = strat_id[:160]
    out["strategy_name"] = desc[:240]

    merge_keys = (
        "signal_modules",
        "factor_pipeline",
        "regime_module",
        "risk_model",
        "fusion_module",
        "execution_template",
        "stop_target_template",
        "symbol",
        "timeframe",
        "experiment_type",
        "baseline_tag",
    )
    for k in merge_keys:
        if k in params:
            out[k] = params[k]

    mc = params.get("monte_carlo_config")
    if isinstance(mc, dict):
        out["monte_carlo_config"] = mc

    notes_extra = params.get("notes")
    if notes_extra is not None:
        base_notes = str(out.get("notes") or "")
        out["notes"] = (base_notes + " | " if base_notes else "") + str(notes_extra)

    errs = validate_manifest_against_catalog(out, catalog=catalog or load_default_catalog())
    if errs:
        raise ValueError("manifest validation failed: " + "; ".join(errs))
    return out


def write_manifest_for_run(manifest: dict[str, Any], hypothesis_id: str, experiment_id: str) -> Path:
    """Write candidate manifest under configs/manifests/ for compare-manifest (governed path)."""
    man_dir = _rv4_root() / "configs" / "manifests"
    man_dir.mkdir(parents=True, exist_ok=True)
    safe_h = _slug(hypothesis_id, max_len=48)
    safe_e = _slug(experiment_id, max_len=32)
    path = man_dir / f"sra_{safe_h}_{safe_e}.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def append_hypothesis_result(record: dict[str, Any]) -> None:
    p = hypothesis_results_jsonl_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _read_monte_carlo_summary(repo: Path, experiment_id: str) -> dict[str, Any] | None:
    p = repo / "renaissance_v4" / "state" / f"monte_carlo_{experiment_id}_summary.json"
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _key_metrics_from_summary(data: dict[str, Any]) -> dict[str, Any]:
    det = data.get("deterministic") if isinstance(data.get("deterministic"), dict) else {}
    mc = data.get("monte_carlo") if isinstance(data.get("monte_carlo"), dict) else {}
    primary = "shuffle"
    if primary not in mc and mc:
        primary = next(iter(mc.keys()))
    row_mc: dict[str, Any] = {}
    if isinstance(mc.get(primary), dict):
        m = mc[primary]
        row_mc = {
            "mode": primary,
            "median_terminal_pnl": m.get("median_terminal_pnl"),
            "median_max_drawdown": m.get("median_max_drawdown"),
        }
    return {
        "deterministic": {
            "total_trades": det.get("total_trades"),
            "expectancy": det.get("expectancy"),
            "max_drawdown": det.get("max_drawdown"),
        },
        "monte_carlo_primary": row_mc or None,
    }


def execute_hypothesis(
    hypothesis_id: str,
    *,
    repo_root: Path | None = None,
    n_sims: int = 5000,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Generate manifest, write under configs/manifests/, run ``compare-manifest`` subprocess,
    append one line to hypothesis_results.jsonl.

    Requires baseline Monte Carlo reference artifacts (same as other Kitchen compares).
    """
    repo = (repo_root or _repo_root()).resolve()
    hyp = get_hypothesis_by_id(hypothesis_id)
    if hyp is None:
        raise LookupError(f"hypothesis_id not found: {hypothesis_id}")

    manifest = generate_manifest_from_hypothesis(hyp)
    experiment_id = new_experiment_id()
    man_path = write_manifest_for_run(manifest, hypothesis_id, experiment_id)
    try:
        man_rel = str(man_path.relative_to(repo))
    except ValueError:
        man_rel = str(man_path)

    py = sys.executable
    cmd = [
        py,
        "-m",
        "renaissance_v4.research.robustness_runner",
        "compare-manifest",
        "--experiment-id",
        experiment_id,
        "--manifest",
        man_rel,
        "--seed",
        str(seed),
        "--n-sims",
        str(n_sims),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    env["PYTHONUNBUFFERED"] = "1"
    r = subprocess.run(cmd, cwd=str(repo), env=env, capture_output=True, text=True, timeout=7200)

    ts = datetime.now(timezone.utc).isoformat()
    strat = str(manifest.get("strategy_id") or "")

    lineage_fields = _lineage_fields_from_hypothesis(hyp)

    if r.returncode != 0:
        rec = {
            "hypothesis_id": hypothesis_id,
            "experiment_id": experiment_id,
            "strategy_id": strat,
            "classification": "inconclusive",
            "key_metrics": {
                "pipeline_ok": False,
                "exit_code": r.returncode,
                "stderr_tail": (r.stderr or "")[-2000:],
                "stdout_tail": (r.stdout or "")[-2000:],
            },
            "manifest_path_repo": man_rel,
            "timestamp": ts,
            **lineage_fields,
        }
        append_hypothesis_result(rec)
        return rec

    summary = _read_monte_carlo_summary(repo, experiment_id) or {}
    cls = str(summary.get("classification") or summary.get("recommendation") or "inconclusive")
    if cls not in ("improve", "degrade", "inconclusive"):
        cls = "inconclusive"

    rec = {
        "hypothesis_id": hypothesis_id,
        "experiment_id": experiment_id,
        "strategy_id": strat,
        "classification": cls,
        "key_metrics": {**_key_metrics_from_summary(summary), "pipeline_ok": True},
        "manifest_path_repo": man_rel,
        "timestamp": ts,
        **lineage_fields,
    }
    append_hypothesis_result(rec)
    return rec


def _lineage_fields_from_hypothesis(hyp: dict[str, Any]) -> dict[str, Any]:
    """DV-ARCH-SRA-VARIANTS-031 — trace variant → parent in results."""
    out: dict[str, Any] = {}
    pid = hyp.get("parent_hypothesis_id")
    if pid is not None and str(pid).strip():
        out["parent_hypothesis_id"] = str(pid).strip()
    vt = hyp.get("variant_type")
    if vt is not None and str(vt).strip():
        out["variant_type"] = str(vt).strip()
    if "variant_index" in hyp and hyp["variant_index"] is not None:
        out["variant_index"] = hyp["variant_index"]
    return out


# --- DV-ARCH-SRA-RESULTS-032 — aggregate results, rank variants ---


def load_hypothesis_results_latest_by_id() -> dict[str, dict[str, Any]]:
    """Last JSON line per hypothesis_id wins (traceability to latest run)."""
    p = hypothesis_results_jsonl_path()
    out: dict[str, dict[str, Any]] = {}
    if not p.is_file():
        return out
    for row in _iter_jsonl(p):
        hid = str(row.get("hypothesis_id") or "").strip()
        if hid:
            out[hid] = row
    return out


def _classification_priority(cls: str | None) -> int:
    c = str(cls or "inconclusive").strip().lower()
    if c == "improve":
        return 0
    if c == "inconclusive":
        return 1
    if c == "degrade":
        return 2
    return 1


def _rank_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """
    Deterministic ordering: class (improve < inconclusive < degrade), then higher expectancy,
    then higher max_drawdown (less negative loss), then more trades, then hypothesis_id.
    """
    cls = str(row.get("classification") or "inconclusive").strip().lower()
    prio = _classification_priority(cls)
    km = row.get("key_metrics") if isinstance(row.get("key_metrics"), dict) else {}
    det = km.get("deterministic") if isinstance(km.get("deterministic"), dict) else {}
    try:
        exp = float(det.get("expectancy")) if det.get("expectancy") is not None else float("-inf")
    except (TypeError, ValueError):
        exp = float("-inf")
    try:
        mdd = float(det.get("max_drawdown")) if det.get("max_drawdown") is not None else float("-inf")
    except (TypeError, ValueError):
        mdd = float("-inf")
    try:
        tt = int(det.get("total_trades")) if det.get("total_trades") is not None else -1
    except (TypeError, ValueError):
        tt = -1
    hid = str(row.get("hypothesis_id") or "")
    # Ascending sort: lower prio first; then higher exp (negate); then higher mdd; then higher tt; then hid
    return (prio, -exp, -mdd, -tt, hid)


def results_for_parent(
    parent_hypothesis_id: str,
    *,
    latest_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Rows whose parent matches, or base hypothesis row (hypothesis_id == parent)."""
    pid = str(parent_hypothesis_id).strip()
    pool = latest_by_id if latest_by_id is not None else load_hypothesis_results_latest_by_id()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in pool.values():
        ph = str(row.get("parent_hypothesis_id") or "").strip()
        hid = str(row.get("hypothesis_id") or "").strip()
        if ph == pid and hid:
            if hid not in seen:
                seen.add(hid)
                out.append(row)
        elif hid == pid:
            if hid not in seen:
                seen.add(hid)
                out.append(row)
    return out


def rank_hypothesis_variants(parent_hypothesis_id: str) -> dict[str, Any]:
    """
    DV-ARCH-SRA-RESULTS-032 — Rank variants for one parent (improve > inconclusive > degrade;
    within class: deterministic expectancy / drawdown / trades / id).
    """
    rows = results_for_parent(parent_hypothesis_id)
    sorted_rows = sorted(rows, key=_rank_sort_key)
    ordered_ids = [str(r.get("hypothesis_id") or "").strip() for r in sorted_rows if r.get("hypothesis_id")]
    best = ordered_ids[0] if ordered_ids else None
    return {
        "parent_hypothesis_id": str(parent_hypothesis_id).strip(),
        "best_variant": best,
        "ordered_variants": ordered_ids,
    }


def load_hypothesis_rankings_file() -> dict[str, Any]:
    p = hypothesis_rankings_json_path()
    if not p.is_file():
        return {
            "schema": "renaissance_v4_hypothesis_rankings_v1",
            "generated_at": None,
            "rankings": [],
        }
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("rankings"), list):
            return raw
    except (json.JSONDecodeError, OSError):
        pass
    return {
        "schema": "renaissance_v4_hypothesis_rankings_v1",
        "generated_at": None,
        "rankings": [],
    }


def upsert_parent_ranking(entry: dict[str, Any]) -> dict[str, Any]:
    """Merge one parent block into hypothesis_rankings.json (deterministic ordering of file by parent id)."""
    data = load_hypothesis_rankings_file()
    rankings: list[dict[str, Any]] = list(data.get("rankings") or [])
    pid = str(entry.get("parent_hypothesis_id") or "").strip()
    replaced = False
    for i, r in enumerate(rankings):
        if str(r.get("parent_hypothesis_id") or "").strip() == pid:
            rankings[i] = entry
            replaced = True
            break
    if not replaced:
        rankings.append(entry)
    rankings.sort(key=lambda x: str(x.get("parent_hypothesis_id") or ""))
    data["rankings"] = rankings
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    p = hypothesis_rankings_json_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return data


def run_rank_cli(parent_hypothesis_id: str) -> dict[str, Any]:
    """Compute ranking, persist hypothesis_rankings.json, return entry."""
    entry = rank_hypothesis_variants(parent_hypothesis_id)
    upsert_parent_ranking(entry)
    return entry


def _cmd_rank(args: argparse.Namespace) -> int:
    try:
        out = run_rank_cli(args.parent_hypothesis_id)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "ranking": out}, indent=2))
    return 0


# --- DV-ARCH-SRA-PROMOTION-033 — promotion readiness (no activation) ---


def _best_variant_from_rankings_file(parent_hypothesis_id: str) -> str | None:
    pid = str(parent_hypothesis_id).strip()
    data = load_hypothesis_rankings_file()
    for r in data.get("rankings") or []:
        if str(r.get("parent_hypothesis_id") or "").strip() != pid:
            continue
        bv = r.get("best_variant")
        if bv is None:
            return None
        s = str(bv).strip()
        return s or None
    return None


def evaluate_promotion_candidate(parent_hypothesis_id: str) -> dict[str, Any]:
    """
    Qualify the top-ranked variant for promotion **readiness** only (deterministic rules).

    Reads ``hypothesis_rankings.json`` when present; otherwise uses in-memory
    ``rank_hypothesis_variants`` for ``best_variant``.
    """
    pid = str(parent_hypothesis_id).strip()
    evaluated_at = datetime.now(timezone.utc).isoformat()
    min_tt = promotion_min_trades()
    mdd_floor = promotion_max_drawdown_floor()

    selected = _best_variant_from_rankings_file(pid)
    if selected is None:
        selected = rank_hypothesis_variants(pid).get("best_variant")

    base: dict[str, Any] = {
        "parent_hypothesis_id": pid,
        "selected_hypothesis_id": selected,
        "experiment_id": None,
        "classification": None,
        "key_metrics": None,
        "eligible": False,
        "reason": None,
        "evaluated_at": evaluated_at,
    }

    if not selected:
        base["reason"] = "no_ranked_variant_for_parent"
        return base

    latest = load_hypothesis_results_latest_by_id()
    row = latest.get(selected)
    if row is None:
        base["reason"] = "no_result_row_for_selected_hypothesis"
        return base

    base["experiment_id"] = row.get("experiment_id")
    cls = str(row.get("classification") or "").strip().lower()
    base["classification"] = row.get("classification")
    km = row.get("key_metrics") if isinstance(row.get("key_metrics"), dict) else {}
    base["key_metrics"] = copy.deepcopy(km)

    if km.get("pipeline_ok") is not True:
        base["reason"] = "pipeline_not_ok_or_incomplete"
        return base

    if cls != "improve":
        base["reason"] = "classification_not_improve"
        return base

    det = km.get("deterministic") if isinstance(km.get("deterministic"), dict) else {}
    exp = det.get("expectancy")
    if exp is None:
        base["reason"] = "expectancy_missing"
        return base
    try:
        exp_f = float(exp)
    except (TypeError, ValueError):
        base["reason"] = "expectancy_not_numeric"
        return base
    if not math.isfinite(exp_f):
        base["reason"] = "expectancy_not_finite"
        return base

    try:
        tt = int(det.get("total_trades")) if det.get("total_trades") is not None else None
    except (TypeError, ValueError):
        tt = None
    if tt is None:
        base["reason"] = "total_trades_missing"
        return base
    if tt < min_tt:
        base["reason"] = f"total_trades_below_minimum (need>={min_tt}, got={tt})"
        return base

    try:
        mdd = float(det.get("max_drawdown")) if det.get("max_drawdown") is not None else None
    except (TypeError, ValueError):
        mdd = None
    if mdd is None:
        base["reason"] = "max_drawdown_missing"
        return base
    if not math.isfinite(mdd):
        base["reason"] = "max_drawdown_not_finite"
        return base
    if mdd < mdd_floor:
        base["reason"] = (
            f"max_drawdown_below_floor (need>={mdd_floor}, got={mdd})"
        )
        return base

    base["eligible"] = True
    base["reason"] = None
    return base


def load_promotion_candidates_file() -> dict[str, Any]:
    p = promotion_candidates_json_path()
    if not p.is_file():
        return {
            "schema": "renaissance_v4_promotion_candidates_v1",
            "generated_at": None,
            "candidates": [],
        }
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("candidates"), list):
            return raw
    except (json.JSONDecodeError, OSError):
        pass
    return {
        "schema": "renaissance_v4_promotion_candidates_v1",
        "generated_at": None,
        "candidates": [],
    }


def get_promotion_ready_candidates() -> list[dict[str, Any]]:
    """
    DV-ARCH-SRA-HANDOFF-034 — candidates from ``promotion_candidates.json`` with ``eligible == True``.

    Does not re-evaluate; returns stored rows only.
    """
    out: list[dict[str, Any]] = []
    for c in load_promotion_candidates_file().get("candidates") or []:
        if isinstance(c, dict) and c.get("eligible") is True:
            out.append(c)
    return out


def upsert_promotion_candidate(entry: dict[str, Any]) -> dict[str, Any]:
    data = load_promotion_candidates_file()
    cands: list[dict[str, Any]] = list(data.get("candidates") or [])
    pid = str(entry.get("parent_hypothesis_id") or "").strip()
    replaced = False
    for i, r in enumerate(cands):
        if str(r.get("parent_hypothesis_id") or "").strip() == pid:
            cands[i] = entry
            replaced = True
            break
    if not replaced:
        cands.append(entry)
    cands.sort(key=lambda x: str(x.get("parent_hypothesis_id") or ""))
    data["candidates"] = cands
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    p = promotion_candidates_json_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return data


def run_promote_cli(parent_hypothesis_id: str) -> dict[str, Any]:
    entry = evaluate_promotion_candidate(parent_hypothesis_id)
    upsert_promotion_candidate(entry)
    return entry


def _cmd_promote(args: argparse.Namespace) -> int:
    try:
        out = run_promote_cli(args.parent_hypothesis_id)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "promotion": out}, indent=2, default=str))
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    raw = Path(args.file).read_text(encoding="utf-8")
    record = json.loads(raw)
    if not isinstance(record, dict):
        print("JSON root must be an object", file=sys.stderr)
        return 1
    append_hypothesis(record)
    print(json.dumps({"ok": True, "appended": record.get("hypothesis_id")}, indent=2))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        out = execute_hypothesis(args.hypothesis_id, n_sims=args.n_sims, seed=args.seed)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "result": out}, indent=2, default=str))
    return 0 if out.get("key_metrics", {}).get("pipeline_ok") else 2


def _cmd_dry_run(args: argparse.Namespace) -> int:
    hyp = get_hypothesis_by_id(args.hypothesis_id)
    if hyp is None:
        print(f"hypothesis not found: {args.hypothesis_id}", file=sys.stderr)
        return 1
    m = generate_manifest_from_hypothesis(hyp)
    print(json.dumps(m, indent=2, sort_keys=True))
    return 0


def _cmd_variants(args: argparse.Namespace) -> int:
    try:
        ids = generate_variants_from_hypothesis(args.hypothesis_id, int(args.n_variants))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "hypothesis_ids": ids}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SRA foundation — 030 / 031 / 032 / 033 (hypotheses, variants, rank, promotion readiness)"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Append a hypothesis record from a JSON file")
    a.add_argument("file", type=str, help="Path to JSON object (hypothesis_id, description, parameters, …)")
    a.set_defaults(func=_cmd_add)

    r = sub.add_parser("run", help="Execute hypothesis via compare-manifest + store result")
    r.add_argument("hypothesis_id", type=str)
    r.add_argument("--n-sims", type=int, default=5000)
    r.add_argument("--seed", type=int, default=42)
    r.set_defaults(func=_cmd_run)

    d = sub.add_parser("dry-run", help="Print generated manifest JSON for a hypothesis_id")
    d.add_argument("hypothesis_id", type=str)
    d.set_defaults(func=_cmd_dry_run)

    v = sub.add_parser(
        "variants",
        help="DV-ARCH-SRA-VARIANTS-031 — generate N controlled variants (append hypotheses.jsonl)",
    )
    v.add_argument("hypothesis_id", type=str)
    v.add_argument("n_variants", type=int)
    v.set_defaults(func=_cmd_variants)

    rk = sub.add_parser(
        "rank",
        help="DV-ARCH-SRA-RESULTS-032 — rank variants for a parent, write hypothesis_rankings.json",
    )
    rk.add_argument("parent_hypothesis_id", type=str)
    rk.set_defaults(func=_cmd_rank)

    pr = sub.add_parser(
        "promote",
        help="DV-ARCH-SRA-PROMOTION-033 — evaluate top variant for promotion readiness, write promotion_candidates.json",
    )
    pr.add_argument("parent_hypothesis_id", type=str)
    pr.set_defaults(func=_cmd_promote)

    return p


def main() -> int:
    ns = build_parser().parse_args()
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())
