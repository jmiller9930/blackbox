"""
Read-only + governed job payloads for RenaissanceV4 dashboard API.

Paths are resolved under the repo root (BLACKBOX_REPO_ROOT / api mount).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from renaissance_v4.execution_targets import (
    BASELINE_COMPARED_LABELS,
    BASELINE_TAGS,
    LABELS,
    baseline_artifacts_present,
    normalize_execution_target,
    paths_for_execution_target,
)

BASELINE_TAG = "RenaissanceV4_baseline_v1"


def _repo_root(repo: Path) -> Path:
    return repo.resolve()


def rv4_paths(repo: Path) -> dict[str, Path]:
    r = _repo_root(repo)
    rv4 = r / "renaissance_v4"
    return {
        "root": rv4,
        "reports": rv4 / "reports",
        "state": rv4 / "state",
        "baseline_md": rv4 / "reports" / "baseline_v1.md",
        "baseline_mc_md": rv4 / "reports" / "monte_carlo" / "monte_carlo_baseline_v1_reference.md",
        "diag_post": rv4 / "reports" / "diagnostic_quality_post_DV013.md",
        "correction_q": rv4 / "reports" / "correction_quality_v1.md",
        "baseline_det": rv4 / "state" / "baseline_deterministic.json",
        "baseline_mc": rv4 / "state" / "baseline_monte_carlo_summary.json",
        "experiment_index": rv4 / "state" / "experiment_index.json",
        "job_queue": rv4 / "state" / "ui_job_queue.json",
        "experiments_dir": rv4 / "reports" / "experiments",
    }


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _git_rev_parse(repo: Path) -> str | None:
    import subprocess

    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (p.stdout or "").strip() or None
    except OSError:
        return None


def _file_query_url(rel: str) -> str:
    return f"/api/v1/renaissance/file?rel={quote(rel, safe='')}"


def resolve_safe_artifact_path(repo: Path, rel: str) -> Path | None:
    """Read-only files under renaissance_v4/reports or renaissance_v4/state."""
    repo = repo.resolve()
    rel = rel.strip().replace("\\", "/")
    if not rel or ".." in rel or rel.startswith("/"):
        return None
    p = (repo / rel).resolve()
    try:
        p.relative_to(repo)
    except ValueError:
        return None
    allowed_roots = (
        repo / "renaissance_v4" / "reports",
        repo / "renaissance_v4" / "state",
    )
    ok = False
    for root in allowed_roots:
        try:
            p.relative_to(root)
            ok = True
            break
        except ValueError:
            continue
    if not ok or not p.is_file():
        return None
    return p


def build_baseline_payload(repo: Path, *, execution_target: str | None = None) -> dict[str, Any]:
    """Baseline snapshot for the selected execution target (Jupiter vs BlackBox). No cross-target fallback."""
    repo = repo.resolve()
    et = normalize_execution_target(execution_target)
    tag = BASELINE_TAGS.get(et, BASELINE_TAG)
    p = paths_for_execution_target(repo, et)
    ready, baseline_err = baseline_artifacts_present(repo, et)

    det = _read_json(p["baseline_det"]) or {}
    mc = _read_json(p["baseline_mc"]) or {}
    deterministic = det.get("deterministic") if isinstance(det, dict) else {}
    if not deterministic and isinstance(mc, dict):
        deterministic = mc.get("deterministic") or {}

    git_head = _git_rev_parse(repo)
    md_exists = p["baseline_md"].is_file()
    mc_md_exists = p["baseline_mc_md"].is_file()

    reports_map = {
        "baseline_v1_md": str(p["baseline_md"].relative_to(repo)) if md_exists else None,
        "monte_carlo_baseline_reference_md": str(p["baseline_mc_md"].relative_to(repo)) if mc_md_exists else None,
        "diagnostic_post_dv013": str(p["diag_post"].relative_to(repo)) if p["diag_post"].is_file() else None,
        "correction_quality_v1": str(p["correction_q"].relative_to(repo)) if p["correction_q"].is_file() else None,
    }
    report_links: list[dict[str, str]] = []
    for label, key, title in (
        ("Baseline markdown report", "baseline_v1_md", "Deterministic baseline narrative"),
        ("Baseline Monte Carlo markdown report", "monte_carlo_baseline_reference_md", "Monte Carlo reference run"),
        ("Diagnostic quality (post DV013)", "diagnostic_post_dv013", None),
        ("Correction quality v1", "correction_quality_v1", None),
    ):
        rel = reports_map.get(key)
        if rel:
            report_links.append(
                {
                    "label": label,
                    "rel_path": rel,
                    "download_url": _file_query_url(rel),
                    "title": title or "",
                }
            )

    qet = quote(et, safe="")
    export_base = f"/api/v1/renaissance/baseline/export?execution_target={qet}"
    csv_names = (
        ("blackbox_baseline_v1_trades.csv", "blackbox_baseline_metrics.csv", "blackbox_baseline_monte_carlo.csv")
        if et == "blackbox"
        else ("baseline_v1_trades.csv", "baseline_deterministic_metrics.csv", "baseline_monte_carlo_summary.csv")
    )

    return {
        "schema": "renaissance_v4_ui_baseline_v3",
        "execution_target": et,
        "execution_target_label": LABELS.get(et, et),
        "compared_against_baseline_label": BASELINE_COMPARED_LABELS.get(et, "Baseline"),
        "baseline_ready": ready,
        "baseline_error": None if ready else baseline_err,
        "baseline_tag": tag,
        "strategy_id": tag,
        "commit_hint": git_head,
        "reports": reports_map,
        "report_links": report_links,
        "export_urls": {
            "trades_csv": f"{export_base}&kind=trades",
            "metrics_csv": f"{export_base}&kind=metrics",
            "monte_carlo_csv": f"{export_base}&kind=monte_carlo",
        },
        "export_csv_filenames": {
            "trades_csv": csv_names[0],
            "metrics_csv": csv_names[1],
            "monte_carlo_csv": csv_names[2],
        },
        "deterministic": deterministic if isinstance(deterministic, dict) else {},
        "monte_carlo_reference_present": bool(mc) and isinstance(mc.get("monte_carlo"), dict),
        "monte_carlo_summary_keys": list(mc.get("monte_carlo", {}).keys()) if isinstance(mc, dict) else [],
        "raw_monte_carlo_meta": {
            "generated_at": mc.get("generated_at") if isinstance(mc, dict) else None,
            "git_head": mc.get("git_head") if isinstance(mc, dict) else None,
        }
        if isinstance(mc, dict)
        else {},
    }


def build_experiments_list_payload(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    p = rv4_paths(repo)
    idx = _read_json(p["experiment_index"])
    jobs = _read_json(p["job_queue"])
    experiments: list[dict[str, Any]] = []
    if isinstance(idx, dict) and isinstance(idx.get("experiments"), list):
        experiments = list(idx["experiments"])

    # Merge queue status by experiment_id
    job_by_exp: dict[str, dict[str, Any]] = {}
    if isinstance(jobs, dict) and isinstance(jobs.get("jobs"), list):
        for j in jobs["jobs"]:
            if isinstance(j, dict) and j.get("experiment_id"):
                job_by_exp[str(j["experiment_id"])] = j

    rows: list[dict[str, Any]] = []
    for e in experiments:
        if not isinstance(e, dict):
            continue
        eid = str(e.get("experiment_id", ""))
        jq = job_by_exp.get(eid, {})
        extra = e.get("extra") if isinstance(e.get("extra"), dict) else {}
        etype = str(extra.get("experiment_type") or e.get("subsystem") or "")
        completed_at = str(e.get("completed_at") or "") or (
            e.get("created_at", "") if e.get("status") == "complete" else ""
        )
        strat = extra.get("strategy_id") if isinstance(extra.get("strategy_id"), str) else None
        rows.append(
            {
                "experiment_id": eid,
                "experiment_type": etype,
                "status": e.get("status", "unknown"),
                "stage": jq.get("stage") or ("complete" if e.get("status") == "complete" else "—"),
                "subsystem": e.get("subsystem", ""),
                "recommendation": e.get("recommendation", ""),
                "strategy_id": strat or str(e.get("baseline_tag") or BASELINE_TAG),
                "baseline_reference": extra.get("baseline_reference") or e.get("baseline_tag") or BASELINE_TAG,
                "manifest_path": extra.get("manifest_path_repo") or extra.get("manifest_path"),
                "created_at": e.get("created_at", ""),
                "completed_at": completed_at,
                "branch": e.get("branch", ""),
                "commit_hash": e.get("commit_hash", ""),
            }
        )

    # Synthetic queue rows for jobs not in index
    seen = {r["experiment_id"] for r in rows}
    for eid, j in job_by_exp.items():
        if eid not in seen:
            rows.append(
                {
                    "experiment_id": eid,
                    "experiment_type": str(j.get("action") or ""),
                    "status": j.get("status", "pending"),
                    "stage": j.get("stage", "queued"),
                    "subsystem": j.get("action", ""),
                    "recommendation": "",
                    "strategy_id": BASELINE_TAG,
                    "baseline_reference": BASELINE_TAG,
                    "manifest_path": j.get("manifest_rel"),
                    "created_at": j.get("created_at", ""),
                    "completed_at": "",
                    "branch": "",
                    "commit_hash": "",
                }
            )

    return {
        "schema": "renaissance_v4_ui_experiments_v2",
        "baseline_tag": BASELINE_TAG,
        "experiments": rows,
        "jobs": jobs.get("jobs", []) if isinstance(jobs, dict) else [],
    }


def _f_metric(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _comparison_vs_baseline(
    repo: Path,
    det_c: dict[str, Any] | None,
    mc_c: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Structured delta vs locked baseline artifacts (read-only JSON)."""
    if not det_c:
        return None
    p = rv4_paths(repo.resolve())
    bd = _read_json(p["baseline_det"]) or {}
    bm = _read_json(p["baseline_mc"]) or {}
    det_b = bd.get("deterministic") if isinstance(bd, dict) else {}
    if not det_b and isinstance(bm, dict):
        det_b = bm.get("deterministic") or {}
    if not isinstance(det_b, dict):
        return None
    mc_b = bm.get("monte_carlo") if isinstance(bm, dict) else None
    tb, tc = int(det_b.get("total_trades", 0)), int(det_c.get("total_trades", 0))
    primary = "shuffle"
    row_mc: dict[str, Any] | None = None
    if isinstance(mc_b, dict) and isinstance(mc_c, dict):
        if primary not in mc_b and mc_b:
            primary = next(iter(mc_b.keys()))
        mb = mc_b.get(primary) if isinstance(mc_b.get(primary), dict) else {}
        mc = mc_c.get(primary) if isinstance(mc_c.get(primary), dict) else {}
        row_mc = {
            "mode": primary,
            "median_terminal_pnl_baseline": mb.get("median_terminal_pnl"),
            "median_terminal_pnl_candidate": mc.get("median_terminal_pnl"),
            "median_max_drawdown_baseline": mb.get("median_max_drawdown"),
            "median_max_drawdown_candidate": mc.get("median_max_drawdown"),
        }
    return {
        "baseline_tag": BASELINE_TAG,
        "deterministic": {
            "baseline": {
                "total_trades": tb,
                "expectancy": det_b.get("expectancy"),
                "max_drawdown": det_b.get("max_drawdown"),
            },
            "candidate": {
                "total_trades": tc,
                "expectancy": det_c.get("expectancy"),
                "max_drawdown": det_c.get("max_drawdown"),
            },
            "delta_expectancy": _f_metric(det_c.get("expectancy")) - _f_metric(det_b.get("expectancy")),
            "delta_max_drawdown": _f_metric(det_c.get("max_drawdown")) - _f_metric(det_b.get("max_drawdown")),
            "delta_total_trades": tc - tb,
        },
        "monte_carlo_primary_mode": row_mc,
        "notes": [],
    }


def get_candidate_trades_fallback(repo: Path, experiment_id: str) -> Path | None:
    """Resolve candidate trades path from experiment index ``extra`` (legacy runs)."""
    repo = repo.resolve()
    p = rv4_paths(repo)
    idx = _read_json(p["experiment_index"])
    if not isinstance(idx, dict):
        return None
    for e in idx.get("experiments") or []:
        if not isinstance(e, dict) or str(e.get("experiment_id")) != experiment_id:
            continue
        extra = e.get("extra") if isinstance(e.get("extra"), dict) else {}
        ct = extra.get("candidate_trades")
        if not ct:
            return None
        try:
            path = Path(str(ct)).resolve()
            path.relative_to(repo)
        except ValueError:
            return None
        except OSError:
            return None
        return path if path.is_file() else None
    return None


def build_experiment_detail_payload(repo: Path, experiment_id: str) -> dict[str, Any]:
    repo = repo.resolve()
    p = rv4_paths(repo)
    idx = _read_json(p["experiment_index"])
    hit: dict[str, Any] | None = None
    if isinstance(idx, dict) and isinstance(idx.get("experiments"), list):
        for e in idx["experiments"]:
            if isinstance(e, dict) and str(e.get("experiment_id")) == experiment_id:
                hit = dict(e)
                break

    det_path = p["state"] / f"deterministic_{experiment_id}.json"
    mc_path = p["state"] / f"monte_carlo_{experiment_id}_summary.json"
    exp_md = p["experiments_dir"] / f"experiment_{experiment_id}.md"
    rob_md = p["reports"] / "robustness" / f"robustness_{experiment_id}.md"
    mc_md = p["reports"] / "monte_carlo" / f"monte_carlo_{experiment_id}.md"

    det_j = _read_json(det_path) if det_path.is_file() else None
    mc_j = _read_json(mc_path) if mc_path.is_file() else None

    det_c = det_j.get("deterministic") if isinstance(det_j, dict) else None
    mc_c = mc_j.get("monte_carlo") if isinstance(mc_j, dict) else None
    rec = (mc_j.get("recommendation") if isinstance(mc_j, dict) else None) or (
        (hit or {}).get("recommendation") if hit else None
    )

    report_paths = {
        "experiment_md": str(exp_md.relative_to(repo)) if exp_md.is_file() else None,
        "robustness_md": str(rob_md.relative_to(repo)) if rob_md.is_file() else None,
        "monte_carlo_md": str(mc_md.relative_to(repo)) if mc_md.is_file() else None,
    }
    report_links: list[dict[str, str]] = []
    for label, rp_key, title in (
        ("Experiment summary (markdown)", "experiment_md", None),
        ("Robustness comparison (markdown)", "robustness_md", None),
        ("Monte Carlo report (markdown)", "monte_carlo_md", None),
    ):
        rel = report_paths.get(rp_key)
        if rel:
            report_links.append(
                {
                    "label": label,
                    "rel_path": rel,
                    "download_url": _file_query_url(rel),
                    "title": title or "",
                }
            )

    comparison_vs_baseline = _comparison_vs_baseline(repo, det_c, mc_c)

    mc_j_full = mc_j if isinstance(mc_j, dict) else {}
    ix_extra = (hit.get("extra") if isinstance(hit, dict) else None) or {}
    if not isinstance(ix_extra, dict):
        ix_extra = {}
    strategy_id = ix_extra.get("strategy_id") or mc_j_full.get("strategy_id")
    manifest_path = ix_extra.get("manifest_path_repo") or ix_extra.get("manifest_path") or mc_j_full.get(
        "manifest_path_repo"
    ) or mc_j_full.get("manifest_path")
    baseline_reference = ix_extra.get("baseline_reference") or mc_j_full.get("baseline_reference") or BASELINE_TAG

    return {
        "schema": "renaissance_v4_ui_experiment_detail_v2",
        "experiment_id": experiment_id,
        "strategy_id": strategy_id,
        "manifest_path": manifest_path,
        "baseline_reference": baseline_reference,
        "index": hit,
        "deterministic": det_c,
        "monte_carlo": mc_c,
        "recommendation": rec,
        "report_paths": report_paths,
        "report_links": report_links,
        "comparison_vs_baseline": comparison_vs_baseline,
        "export_urls": {
            "trades_csv": f"/api/v1/renaissance/experiments/{quote(experiment_id, safe='')}/export?kind=trades",
            "metrics_csv": f"/api/v1/renaissance/experiments/{quote(experiment_id, safe='')}/export?kind=metrics",
            "monte_carlo_csv": f"/api/v1/renaissance/experiments/{quote(experiment_id, safe='')}/export?kind=monte_carlo",
        },
    }


def build_workbench_meta_payload() -> dict[str, Any]:
    """Approved launcher actions (governed subprocesses only — no freeform code)."""
    return {
        "schema": "renaissance_v4_ui_workbench_meta_v1",
        "product": "Quant Research Kitchen V1",
        "baseline_reference": BASELINE_TAG,
        "governance_notes": [
            "Baseline logic is immutable; experiments run as separate harness jobs.",
            "Promotion to production is not available from the UI.",
            "Monte Carlo supplements deterministic replay; it does not replace it.",
            "Policy intake (DV-048): POST /api/v1/renaissance/policy-intake — evaluation only; not deployment or activation.",
        ],
        "policy_intake": {
            "post_url": "/api/v1/renaissance/policy-intake",
            "status_url_template": "/api/v1/renaissance/policy-intake/{submission_id}",
            "archive_url_template": "/api/v1/renaissance/policy-intake/{submission_id}/archive",
            "multipart_field": "policy_file",
            "execution_target_field": "execution_target",
            "execution_target_values": ["jupiter", "blackbox"],
            "doc": "renaissance_v4/policy_intake/README.md",
            "note": "DV-055: All intake requests must include execution_target; evaluation and baseline are scoped to that target only.",
            "dv_066": "Soft-archive: POST archive_url with JSON {\"is_active\":false}; restore with {\"is_active\":true}.",
        },
        "approved_job_actions": [
            {
                "id": "baseline_mc",
                "label": "Generate baseline Monte Carlo reference",
                "description": "Replay, export baseline trades, run Monte Carlo, write baseline reports (long-running).",
            },
            {
                "id": "example_flow",
                "label": "Example robustness pipeline check",
                "description": "Compare baseline trade export to itself (sanity / pipeline validation).",
            },
            {
                "id": "compare",
                "label": "Candidate robustness experiment",
                "description": "Requires a candidate trades JSON under renaissance_v4/reports/experiments/ and an experiment id.",
            },
            {
                "id": "compare_manifest",
                "label": "Manifest-driven compare (replay + baseline)",
                "description": "Replay using a manifest under renaissance_v4/configs/manifests/, export namespaced trades, compare vs frozen baseline.",
            },
            {
                "id": "ingest_policy",
                "label": "Ingest policy package (full Kitchen pipeline)",
                "description": "DV-ARCH-POLICY-INGESTION-024-C — validate package, replay via parity.manifest_path, Monte Carlo + baseline compare; appears as a normal experiment.",
            },
        ],
        "roadmap_experiment_types": [
            "Date-range replay slice",
            "Stop / target sensitivity",
            "Regime gating sweep",
            "Risk-threshold sweep",
        ],
    }


def validate_job_action(action: str) -> bool:
    return action in {"baseline_mc", "compare", "compare_manifest", "example_flow", "ingest_policy"}


def validate_experiment_id(eid: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_.-]{4,64}$", eid))


def validate_candidate_trades_path(repo: Path, rel: str) -> Path | None:
    """Only allow paths under renaissance_v4/reports/experiments/."""
    repo = repo.resolve()
    rel = rel.strip().replace("\\", "/")
    if ".." in rel or rel.startswith("/"):
        return None
    p = (repo / rel).resolve()
    exp_root = (repo / "renaissance_v4" / "reports" / "experiments").resolve()
    try:
        p.relative_to(exp_root)
    except ValueError:
        return None
    if not p.is_file() or p.suffix.lower() != ".json":
        return None
    return p


def validate_manifest_path(repo: Path, rel: str) -> Path | None:
    """Only allow strategy manifests under renaissance_v4/configs/manifests/."""
    repo = repo.resolve()
    rel = rel.strip().replace("\\", "/")
    if ".." in rel or rel.startswith("/"):
        return None
    p = (repo / rel).resolve()
    man_root = (repo / "renaissance_v4" / "configs" / "manifests").resolve()
    try:
        p.relative_to(man_root)
    except ValueError:
        return None
    if not p.is_file() or p.suffix.lower() != ".json":
        return None
    return p


def validate_policy_package_path(repo: Path, rel: str) -> Path | None:
    """Policy package directory under policies/ with POLICY_SPEC.yaml (DV-ARCH-POLICY-INGESTION-024-C)."""
    repo = repo.resolve()
    rel = rel.strip().replace("\\", "/")
    if not rel or ".." in rel or rel.startswith("/"):
        return None
    p = (repo / rel).resolve()
    try:
        p.relative_to(repo)
    except ValueError:
        return None
    policies_root = (repo / "policies").resolve()
    try:
        p.relative_to(policies_root)
    except ValueError:
        return None
    if not p.is_dir():
        return None
    spec = p / "POLICY_SPEC.yaml"
    if not spec.is_file():
        return None
    return p
