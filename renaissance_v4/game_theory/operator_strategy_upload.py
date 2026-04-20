"""
Operator strategy upload — parse strategy_idea_v1 text, build manifest, validate, persist.

Paths (repo-relative, under blackbox root):

* ``runtime/operator_strategy_uploads/sources/`` — original uploaded ``.txt``
* ``runtime/operator_strategy_uploads/manifests/`` — generated ``strategy_manifest_v1`` JSON
* ``runtime/operator_strategy_uploads/active.json`` — last successful load + recommendation

Does not overwrite ``renaissance_v4/configs/manifests/baseline_v1_recipe.json`` or other shipped assets.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.manifest.validate import validate_manifest_against_catalog

STRATEGY_IDEA_MAGIC = "strategy_idea_v1"

# Repo-relative roots (resolved under repo root).
UPLOAD_SOURCES_REL = Path("runtime/operator_strategy_uploads/sources")
UPLOAD_MANIFESTS_REL = Path("runtime/operator_strategy_uploads/manifests")
ACTIVE_STATE_REL = Path("runtime/operator_strategy_uploads/active.json")

REQUIRED_IDEA_KEYS: tuple[str, ...] = (
    "strategy_id",
    "strategy_name",
    "symbol",
    "timeframe",
    "factor_pipeline",
    "signal_modules",
    "regime_module",
    "risk_model",
    "fusion_module",
    "execution_template",
    "stop_target_template",
    "experiment_type",
)

OPTIONAL_IDEA_KEYS: frozenset[str] = frozenset(
    {
        "baseline_tag",
        "notes",
        "start_date",
        "end_date",
        "atr_stop_mult",
        "atr_target_mult",
        "fusion_min_score",
        "fusion_max_conflict_score",
        "fusion_overlap_penalty_per_extra_signal",
        "mean_reversion_fade_min_confidence",
        "trend_continuation_min_confidence",
        "trend_continuation_min_regime_fit",
        "pullback_continuation_min_confidence",
        "pullback_continuation_volatility_threshold",
        "breakout_expansion_min_confidence",
        "mean_reversion_fade_stretch_threshold",
        "disabled_signal_modules",
    }
)

ALLOWED_IDEA_KEYS: frozenset[str] = frozenset(REQUIRED_IDEA_KEYS) | OPTIONAL_IDEA_KEYS

# Baseline template fields copied when absent from idea (deterministic replay defaults).
_BASELINE_MONTE_CARLO: dict[str, Any] = {
    "seed": 42,
    "modes": ["shuffle", "bootstrap"],
    "n_simulations": 10000,
}


def default_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def upload_paths(repo_root: Path | None = None) -> tuple[Path, Path, Path]:
    root = (repo_root or default_repo_root()).resolve()
    return (
        (root / UPLOAD_SOURCES_REL).resolve(),
        (root / UPLOAD_MANIFESTS_REL).resolve(),
        (root / ACTIVE_STATE_REL).resolve(),
    )


def ensure_upload_dirs(repo_root: Path | None = None) -> tuple[Path, Path, Path]:
    root = (repo_root or default_repo_root()).resolve()
    src, man, act = upload_paths(root)
    src.mkdir(parents=True, exist_ok=True)
    man.mkdir(parents=True, exist_ok=True)
    return src, man, act


def _sanitize_strategy_id(raw: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw.strip())[:64].strip("_")
    return s or "strategy"


def parse_strategy_idea_v1(text: str) -> tuple[dict[str, Any], list[str]]:
    """
    Parse strict line-oriented strategy idea file.

    First non-empty, non-comment line must be exactly ``strategy_idea_v1``.
    Remaining lines: ``key: value`` (one key per line). ``signal_modules`` and
    ``disabled_signal_modules`` use comma-separated tokens.
    """
    errors: list[str] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    found_header = False
    data: dict[str, Any] = {}
    for i, line in enumerate(lines, start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if not found_header:
            if raw != STRATEGY_IDEA_MAGIC:
                errors.append(
                    f"Line {i}: first content line must be exactly '{STRATEGY_IDEA_MAGIC}' "
                    f"(optional leading comments/blank lines allowed)."
                )
                return {}, errors
            found_header = True
            continue
        if ":" not in raw:
            errors.append(f"Line {i}: expected 'key: value', got {raw[:80]!r}")
            continue
        key, _, rest = raw.partition(":")
        key = key.strip().lower()
        val = rest.strip()
        if not key:
            errors.append(f"Line {i}: empty key")
            continue
        if key not in ALLOWED_IDEA_KEYS:
            errors.append(
                f"Line {i}: unsupported key {key!r}. Allowed keys: "
                f"{', '.join(sorted(ALLOWED_IDEA_KEYS))}."
            )
            continue
        if key in data:
            errors.append(f"Line {i}: duplicate key {key!r}")
            continue
        if key in ("signal_modules", "disabled_signal_modules"):
            parts = [p.strip() for p in val.split(",") if p.strip()]
            if not parts and key == "signal_modules":
                errors.append(f"Line {i}: signal_modules must list at least one catalog signal id")
                continue
            data[key] = parts
        else:
            data[key] = val

    if not found_header:
        errors.append(f"Missing format header '{STRATEGY_IDEA_MAGIC}'.")
        return {}, errors

    for rk in REQUIRED_IDEA_KEYS:
        if rk not in data or data[rk] in (None, "", []):
            errors.append(f"Missing or empty required field: {rk}")

    return data, errors


def build_manifest_v1_from_idea(fields: dict[str, Any]) -> dict[str, Any]:
    """Build ``strategy_manifest_v1`` dict (not yet written to disk)."""
    sigs = fields["signal_modules"]
    if not isinstance(sigs, list):
        raise ValueError("signal_modules must be a list")
    manifest: dict[str, Any] = {
        "schema": "strategy_manifest_v1",
        "manifest_version": "1.0",
        "strategy_id": str(fields["strategy_id"]).strip(),
        "strategy_name": str(fields["strategy_name"]).strip(),
        "baseline_tag": str(fields.get("baseline_tag") or "operator_upload_v1"),
        "symbol": str(fields["symbol"]).strip(),
        "timeframe": str(fields["timeframe"]).strip(),
        "start_date": fields.get("start_date"),
        "end_date": fields.get("end_date"),
        "factor_pipeline": str(fields["factor_pipeline"]).strip(),
        "signal_modules": list(sigs),
        "regime_module": str(fields["regime_module"]).strip(),
        "risk_model": str(fields["risk_model"]).strip(),
        "fusion_module": str(fields["fusion_module"]).strip(),
        "execution_template": str(fields["execution_template"]).strip(),
        "stop_target_template": str(fields["stop_target_template"]).strip(),
        "monte_carlo_config": json.loads(json.dumps(_BASELINE_MONTE_CARLO)),
        "experiment_type": str(fields["experiment_type"]).strip(),
        "notes": str(fields.get("notes") or "Generated from operator strategy upload (strategy_idea_v1)."),
    }
    if manifest.get("start_date") == "":
        manifest["start_date"] = None
    if manifest.get("end_date") == "":
        manifest["end_date"] = None

    numeric_optional = (
        "atr_stop_mult",
        "atr_target_mult",
        "fusion_min_score",
        "fusion_max_conflict_score",
        "fusion_overlap_penalty_per_extra_signal",
        "mean_reversion_fade_min_confidence",
        "trend_continuation_min_confidence",
        "trend_continuation_min_regime_fit",
        "pullback_continuation_min_confidence",
        "pullback_continuation_volatility_threshold",
        "breakout_expansion_min_confidence",
        "mean_reversion_fade_stretch_threshold",
    )
    for k in numeric_optional:
        if k not in fields:
            continue
        v = fields[k]
        if v is None or v == "":
            continue
        try:
            manifest[k] = float(v) if "." in str(v) else int(v)
        except (TypeError, ValueError):
            manifest[k] = float(str(v).strip())

    if fields.get("disabled_signal_modules"):
        dm = fields["disabled_signal_modules"]
        if isinstance(dm, list) and dm:
            manifest["disabled_signal_modules"] = list(dm)

    return manifest


def recommend_pattern_template(fields: dict[str, Any]) -> dict[str, Any]:
    """Heuristic recommendation for operator after upload."""
    sid = str(fields.get("strategy_id") or "").lower()
    sname = str(fields.get("strategy_name") or "").lower()
    et = str(fields.get("experiment_type") or "").lower()
    blob = f"{sid} {sname}"
    if "comparison" in blob or "tight" in blob and "wide" in blob:
        return {
            "primary_recipe_id": "reference_comparison",
            "label": "Reference Comparison Run",
            "reason": (
                "Your name or id suggests comparing geometries or variants — Reference Comparison "
                "runs default vs tighter vs wider risk settings side-by-side on the same tape."
            ),
        }
    if et == "robustness_compare":
        return {
            "primary_recipe_id": "reference_comparison",
            "label": "Reference Comparison Run",
            "reason": "experiment_type is robustness_compare — use Reference Comparison for structured multi-arm geometry tests.",
        }
    return {
        "primary_recipe_id": "pattern_learning",
        "label": "Pattern Machine Learning (PML)",
        "reason": (
            "Default: use PML to run the operator harness (control vs bounded candidates) on this "
            "manifest and surface improvement / learning scorecard fields."
        ),
    }


@dataclass
class StrategyUploadResult:
    ok: bool
    strategy_uploaded: bool
    strategy_validated: bool
    strategy_loaded: bool
    strategy_id: str | None = None
    strategy_name: str | None = None
    manifest_repo_relative: str | None = None
    source_repo_relative: str | None = None
    human_errors: list[str] = field(default_factory=list)
    stages: list[dict[str, Any]] = field(default_factory=list)
    pattern_recommendation: dict[str, Any] | None = None

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "strategy_uploaded": self.strategy_uploaded,
            "strategy_validated": self.strategy_validated,
            "strategy_loaded": self.strategy_loaded,
            "ready_to_run": self.ok and self.strategy_loaded,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "manifest_repo_relative": self.manifest_repo_relative,
            "source_repo_relative": self.source_repo_relative,
            "errors": list(self.human_errors),
            "stages": list(self.stages),
            "pattern_recommendation": self.pattern_recommendation,
        }


def process_strategy_idea_upload(
    raw_bytes: bytes,
    original_filename: str,
    *,
    repo_root: Path | None = None,
    max_bytes: int = 256_000,
) -> StrategyUploadResult:
    """
    Full pipeline: decode → parse → build → validate → write sources + manifest → active.json.
    """
    root = (repo_root or default_repo_root()).resolve()
    stages: list[dict[str, Any]] = []
    out = StrategyUploadResult(
        ok=False,
        strategy_uploaded=False,
        strategy_validated=False,
        strategy_loaded=False,
    )

    def add_stage(name: str, ok: bool, detail: str) -> None:
        stages.append({"name": name, "ok": ok, "detail": detail})

    if len(raw_bytes) > max_bytes:
        out.human_errors.append(f"File too large (max {max_bytes} bytes).")
        add_stage("upload", False, out.human_errors[0])
        out.stages = stages
        return out

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        out.human_errors.append("File must be UTF-8 text.")
        add_stage("upload", False, out.human_errors[0])
        out.stages = stages
        return out

    out.strategy_uploaded = True
    add_stage("upload", True, f"Received {len(raw_bytes)} bytes ({original_filename!r}).")

    fields, parse_errs = parse_strategy_idea_v1(text)
    if parse_errs:
        out.human_errors.extend(parse_errs)
        add_stage("parse", False, parse_errs[0])
        out.stages = stages
        return out
    add_stage("parse", True, "strategy_idea_v1 header and keys accepted.")

    try:
        manifest = build_manifest_v1_from_idea(fields)
    except (ValueError, KeyError, TypeError) as e:
        out.human_errors.append(f"Build manifest failed: {e}")
        add_stage("convert", False, str(e))
        out.stages = stages
        return out
    add_stage("convert", True, "Built strategy_manifest_v1 candidate.")

    v_errs = validate_manifest_against_catalog(manifest)
    if v_errs:
        out.human_errors.extend(v_errs)
        add_stage("validate", False, v_errs[0])
        out.stages = stages
        return out
    out.strategy_validated = True
    add_stage("validate", True, "Manifest passed catalog checks.")

    src_dir, man_dir, active_path = ensure_upload_dirs(root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = _sanitize_strategy_id(str(fields["strategy_id"]))
    uq = uuid.uuid4().hex[:8]
    base = f"{stamp}_{slug}_{uq}"
    src_name = f"{base}.txt"
    man_name = f"{base}.json"
    src_rel = str(UPLOAD_SOURCES_REL / src_name)
    man_rel = str(UPLOAD_MANIFESTS_REL / man_name)
    src_abs = root / src_rel
    man_abs = root / man_rel
    try:
        src_abs.write_bytes(raw_bytes)
        man_abs.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as e:
        out.human_errors.append(f"Could not save files: {e}")
        add_stage("load", False, str(e))
        out.stages = stages
        return out

    rec = recommend_pattern_template(fields)
    active_doc = {
        "status": "loaded",
        "strategy_id": manifest.get("strategy_id"),
        "strategy_name": manifest.get("strategy_name"),
        "manifest_repo_relative": man_rel.replace("\\", "/"),
        "source_repo_relative": src_rel.replace("\\", "/"),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "original_filename": original_filename,
        "pattern_recommendation": rec,
    }
    try:
        active_path.write_text(json.dumps(active_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as e:
        out.human_errors.append(f"Could not write active state: {e}")
        add_stage("load", False, str(e))
        out.stages = stages
        return out

    out.strategy_loaded = True
    out.ok = True
    out.strategy_id = str(manifest.get("strategy_id"))
    out.strategy_name = str(manifest.get("strategy_name"))
    out.manifest_repo_relative = man_rel.replace("\\", "/")
    out.source_repo_relative = src_rel.replace("\\", "/")
    out.pattern_recommendation = rec
    add_stage("load", True, f"Saved manifest; active state at {ACTIVE_STATE_REL.as_posix()}.")
    out.stages = stages
    return out


def read_active_operator_strategy(repo_root: Path | None = None) -> dict[str, Any] | None:
    """Return active.json dict or None if missing/invalid."""
    root = (repo_root or default_repo_root()).resolve()
    p = root / ACTIVE_STATE_REL
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def clear_active_operator_strategy(repo_root: Path | None = None) -> None:
    root = (repo_root or default_repo_root()).resolve()
    p = root / ACTIVE_STATE_REL
    if p.is_file():
        p.unlink()


def active_manifest_repo_relative(repo_root: Path | None = None) -> str | None:
    doc = read_active_operator_strategy(repo_root)
    if not doc or doc.get("status") != "loaded":
        return None
    mp = doc.get("manifest_repo_relative")
    return str(mp).strip() if isinstance(mp, str) and mp.strip() else None


def public_state(repo_root: Path | None = None) -> dict[str, Any]:
    """UI-facing snapshot including explicit YES/NO style flags."""
    root = (repo_root or default_repo_root()).resolve()
    baseline = "renaissance_v4/configs/manifests/baseline_v1_recipe.json"
    doc = read_active_operator_strategy(root)
    if not doc or doc.get("status") != "loaded":
        return {
            "has_active_upload": False,
            "strategy_uploaded": False,
            "strategy_validated": False,
            "strategy_loaded": False,
            "ready_to_run": False,
            "active_source": "builtin",
            "default_baseline_manifest": baseline,
            "strategy_id": None,
            "strategy_name": None,
            "manifest_repo_relative": None,
            "pattern_recommendation": None,
            "disclosure": {
                "sources_dir": UPLOAD_SOURCES_REL.as_posix(),
                "manifests_dir": UPLOAD_MANIFESTS_REL.as_posix(),
                "active_state_file": ACTIVE_STATE_REL.as_posix(),
            },
        }
    mp = doc.get("manifest_repo_relative")
    mp = str(mp).replace("\\", "/") if mp else None
    rec = doc.get("pattern_recommendation") if isinstance(doc.get("pattern_recommendation"), dict) else None
    return {
        "has_active_upload": True,
        "strategy_uploaded": True,
        "strategy_validated": True,
        "strategy_loaded": True,
        "ready_to_run": True,
        "active_source": "operator_upload",
        "default_baseline_manifest": baseline,
        "strategy_id": doc.get("strategy_id"),
        "strategy_name": doc.get("strategy_name"),
        "manifest_repo_relative": mp,
        "uploaded_at": doc.get("uploaded_at"),
        "source_repo_relative": doc.get("source_repo_relative"),
        "pattern_recommendation": rec,
        "disclosure": {
            "sources_dir": UPLOAD_SOURCES_REL.as_posix(),
            "manifests_dir": UPLOAD_MANIFESTS_REL.as_posix(),
            "active_state_file": ACTIVE_STATE_REL.as_posix(),
        },
    }
