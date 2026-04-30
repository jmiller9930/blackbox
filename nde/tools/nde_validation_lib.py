"""
NDE domain contract + training dataset validation (shared by CLIs and LangGraph nodes).

Deploy: /data/NDE/tools/nde_validation_lib.py
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

# SecOps four-heading verifier (must appear in `output` when using SecOps template)
_SECOPS_HEADINGS = (
    "Claim reviewed:",
    "Math verdict:",
    "DATA evidence required:",
    "Final verifier status:",
)


def required_domain_paths(nde: Path, domain: str) -> dict[str, Path]:
    base = nde / domain
    return {
        "domain_config": base / "domain_config.yaml",
        "training_config": base / "training" / "config.yaml",
        "eval_harness": base / "eval" / "eval_v1.json",
        "final_exam": base / "eval" / "final_exam_v1.json",
        "staging_dir": base / "datasets" / "staging",
    }


def validate_domain_contract(nde: Path, domain: str) -> tuple[bool, list[str], dict[str, Any]]:
    """Return (ok, errors, detail)."""
    errs: list[str] = []
    paths = required_domain_paths(nde, domain)
    detail: dict[str, Any] = {k: str(v) for k, v in paths.items()}

    for key, p in paths.items():
        if key == "staging_dir":
            if not p.is_dir():
                errs.append(f"missing or not a directory: {p}")
        elif not p.is_file():
            errs.append(f"missing file: {p}")

    ok = not errs
    return ok, errs, detail


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _resolve_user_data_path(spec: str, domain_base: Path) -> Path:
    """Absolute path as-is; relative path resolved under domain base (…/NDE/<domain>/)."""
    s = spec.strip()
    if not s:
        return domain_base / "__invalid_empty__"
    p = Path(s)
    if p.is_absolute():
        return p.resolve()
    return (domain_base / p).resolve()


def _training_yaml_staging_candidates(domain_base: Path, tc: Path) -> list[Path]:
    """Order: explicit ``dataset`` (operator override), then ``data.staging_jsonl``."""
    out: list[Path] = []
    if not tc.is_file():
        return out
    tr = _load_yaml(tc)
    ds = tr.get("dataset")
    if isinstance(ds, str) and ds.strip():
        out.append(_resolve_user_data_path(ds, domain_base))
    rel = ((tr.get("data") or {}) or {}).get("staging_jsonl")
    if isinstance(rel, str) and rel.strip():
        out.append(_resolve_user_data_path(rel, domain_base))
    return out


# Canonical progressive baseline when no newer processed staging exists (FinQuant v0.3+).
FINQUANT_PROGRESSIVE_BASELINE = "v0.2c_combined.jsonl"
# Certified v0.2 corpus on legacy FinQuant-1 tree (single source until copied into NDE staging).
FINQUANT_LEGACY_PROGRESSIVE_BASELINE = Path("/data/finquant-1/datasets/staging/v0.2c_combined.jsonl")


def resolve_staging_jsonl(domain: str, nde: Path, domain_cfg: dict[str, Any]) -> Path | None:
    """Resolve staging JSONL: training config paths first, then domain-specific fallbacks."""
    base = nde / domain
    tc = base / "training" / "config.yaml"
    for cand in _training_yaml_staging_candidates(base, tc):
        if cand.is_file():
            return cand

    if domain == "secops":
        for name in (
            "secops_nist_v0.3_from_sources.jsonl",
            "secops_cmmc_v0.3_from_sources.jsonl",
            "secops_v0.1.jsonl",
        ):
            p = nde / "secops" / "datasets" / "staging" / name
            if p.is_file():
                return p

    if domain == "finquant":
        fb = base / "datasets" / "staging" / FINQUANT_PROGRESSIVE_BASELINE
        if fb.is_file():
            return fb
        if FINQUANT_LEGACY_PROGRESSIVE_BASELINE.is_file():
            return FINQUANT_LEGACY_PROGRESSIVE_BASELINE.resolve()
        for name in ("finquant_v0.3_from_sources.jsonl", "finquant_staging_v0.1.jsonl"):
            p = base / "datasets" / "staging" / name
            if p.is_file():
                return p

    out_fn = (domain_cfg.get("output") or {}).get("staging_filename")
    if isinstance(out_fn, str) and out_fn.strip():
        p = base / "datasets" / "staging" / out_fn
        return p if p.is_file() else None
    return None


def validate_training_dataset_for_domain(
    nde: Path,
    domain: str,
    *,
    staging_path: Path | None = None,
) -> tuple[bool, dict[str, Any], list[str]]:
    """
    Validate JSONL training data: JSONL shape, keys, source_ids, headings (SecOps), counts, adversarial ratio.
    """
    errs: list[str] = []
    detail: dict[str, Any] = {}

    dc_path = nde / domain / "domain_config.yaml"
    if not dc_path.is_file():
        return False, {}, [f"missing domain_config.yaml at {dc_path}"]

    domain_cfg = _load_yaml(dc_path)
    path = staging_path
    if path is None:
        path = resolve_staging_jsonl(domain, nde, domain_cfg)

    if path is None or not path.is_file():
        errs.append(f"staging JSONL not found (pass explicit path or fix training/config.yaml)")
        return False, {"staging_path": None}, errs

    detail["staging_path"] = str(path)

    qg = domain_cfg.get("quality_gates") or {}
    min_rows = int(qg.get("min_rows", 1))
    tgt_rows = int(domain_cfg.get("target_row_count", 0) or 0)
    if tgt_rows > 0:
        min_rows = max(min_rows, tgt_rows)

    adv_target = float(domain_cfg.get("adversarial_ratio", 0.0) or 0.0)
    check_adv = domain == "secops" and adv_target > 0

    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
    except Exception as e:
        errs.append(f"invalid JSONL: {e}")
        return False, detail, errs

    n = len(rows)
    detail["row_count"] = n
    if n < min_rows:
        errs.append(f"row_count {n} < minimum {min_rows}")

    missing_sid = 0
    bad_fields_rows = 0
    bad_heading_rows = 0
    adv_count = 0

    for i, row in enumerate(rows):
        if not row.get("source_ids"):
            missing_sid += 1
        miss_f = False
        for k in ("instruction", "input", "output"):
            v = row.get(k)
            if v is None or (isinstance(v, str) and not str(v).strip()):
                miss_f = True
                break
        if miss_f:
            bad_fields_rows += 1

        out = str(row.get("output") or "")
        if domain == "secops":
            head_ok = all(h in out for h in _SECOPS_HEADINGS)
            if not head_ok:
                bad_heading_rows += 1
        if row.get("adversarial"):
            adv_count += 1

    detail.update(
        {
            "missing_source_ids": missing_sid,
            "rows_missing_required_fields": bad_fields_rows,
            "rows_missing_verifier_headings": bad_heading_rows,
            "adversarial_count": adv_count,
            "adversarial_ratio_observed": round(adv_count / n, 4) if n else 0.0,
        }
    )

    if missing_sid:
        errs.append(f"{missing_sid} rows missing non-empty source_ids")
    if bad_fields_rows:
        errs.append(f"{bad_fields_rows} rows missing instruction/input/output")
    if domain == "secops" and bad_heading_rows:
        errs.append(
            f"{bad_heading_rows} rows: output missing one or more verifier headings "
            f"{_SECOPS_HEADINGS}"
        )

    if check_adv:
        ratio = adv_count / n if n else 0.0
        # Allow small slack
        if ratio + 1e-9 < adv_target:
            errs.append(f"adversarial_ratio {ratio:.3f} < configured {adv_target}")

    ok = not errs
    return ok, detail, errs


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
