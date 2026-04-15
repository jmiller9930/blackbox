"""
DV-ARCH-SRA-FOUNDATION-030 — Strategy Research Agent foundation: hypotheses, manifest generation, Kitchen run, results.

Does not implement learning loops or change ingestion / evaluation logic. Uses existing
``compare-manifest`` (robustness_runner) for the full Kitchen flow.
"""

from __future__ import annotations

import argparse
import json
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
    }
    append_hypothesis_result(rec)
    return rec


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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SRA foundation — DV-ARCH-SRA-FOUNDATION-030")
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

    return p


def main() -> int:
    ns = build_parser().parse_args()
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())
