"""
Staged policy intake pipeline (DV-ARCH-KITCHEN-POLICY-INTAKE-048).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.execution_targets import BASELINE_COMPARED_LABELS, LABELS, normalize_execution_target
from renaissance_v4.policy_intake.storage import ensure_submission_layout, write_json
from renaissance_v4.policy_intake.ts_validate import validate_typescript_file
from renaissance_v4.policy_spec.indicator_mechanics import mechanical_support_json_for_harness
from renaissance_v4.policy_spec.indicators_v1 import (
    coerce_indicators_section,
    indicators_section_json_for_harness,
    validate_indicators_section,
)
from renaissance_v4.policy_spec.normalize import normalize_policy
from renaissance_v4.policy_spec.policy_spec_v1 import policy_spec_v1_validate_minimal


def _finalize_intake_lifecycle(repo_root: Path, report: dict[str, Any]) -> None:
    """DV-069 — persist shared lifecycle row for this intake outcome (never raises)."""
    try:
        from renaissance_v4.kitchen_policy_lifecycle import apply_intake_report_to_lifecycle

        apply_intake_report_to_lifecycle(repo_root, report)
    except Exception:
        pass


def _reject_xml(name: str) -> bool:
    return name.lower().endswith(".xml")


def _extract_rv4_policy_indicators_json_from_ts(text: str) -> dict[str, Any] | None:
    """Parse optional /* RV4_POLICY_INDICATORS { ... } */ block (DV-064)."""
    m = re.search(r"/\*\s*RV4_POLICY_INDICATORS\s*(\{[\s\S]*?\})\s*\*/", text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _detect_kind(filename: str) -> str:
    low = filename.lower()
    if low.endswith(".ts"):
        return "typescript"
    if low.endswith(".yaml") or low.endswith(".yml"):
        return "yaml"
    if low.endswith(".json"):
        return "json"
    return "unknown"


def _static_sanity(canonical: dict[str, Any]) -> tuple[bool, list[str]]:
    errs = policy_spec_v1_validate_minimal(canonical)
    if errs:
        return False, errs
    strat = canonical.get("strategy") or {}
    if not str(strat.get("timeframe") or "").strip():
        errs.append("normalization: missing strategy.timeframe (required for test window alignment)")
    diag = canonical.get("diagnostics_contract") or {}
    req = diag.get("required_outputs")
    if isinstance(req, list) and len(req) < 4:
        errs.append("diagnostics_contract.required_outputs must list at least 4 outputs")
    dep = canonical.get("deployment_metadata") or {}
    if dep.get("promotion_eligible") is True:
        errs.append("uploaded policies cannot mark promotion_eligible true at intake")
    for sec in ("risk_sizing", "exit_model"):
        if not isinstance(canonical.get(sec), dict):
            errs.append(f"invalid_section:{sec}")
    errs.extend(validate_indicators_section(canonical.get("indicators")))
    return len(errs) == 0, errs


def _parse_harness_stdout(stdout: str) -> dict[str, Any]:
    """
    Return the harness JSON object. Prefer the last line that is a full JSON object with an ``ok`` key
    (DV-060: Node or tooling may emit warnings on stdout before the JSON line on some hosts).
    """
    lines = [ln.strip() for ln in (stdout or "").splitlines() if ln.strip()]
    for ln in reversed(lines):
        if not ln.startswith("{"):
            continue
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict) and "ok" in obj:
                return obj
        except json.JSONDecodeError:
            continue
    return {}


def _run_ts_deterministic(
    repo: Path,
    ts_path: Path,
    bar_count: int,
    *,
    execution_target: str,
    indicators_section: dict[str, Any] | None = None,
) -> dict[str, Any]:
    harness = repo / "renaissance_v4" / "policy_intake" / "run_ts_intake_eval.mjs"
    if not harness.is_file():
        return {"ok": False, "error": "missing_run_ts_intake_eval_mjs"}
    env = dict(os.environ)
    env["BLACKBOX_EXECUTION_TARGET"] = execution_target
    ind = coerce_indicators_section(indicators_section)
    env["RV4_POLICY_INDICATORS_JSON"] = indicators_section_json_for_harness(ind)
    env["RV4_MECHANICAL_REGISTRY_JSON"] = mechanical_support_json_for_harness()
    r = subprocess.run(
        ["node", str(harness), str(ts_path.resolve()), str(int(bar_count))],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    out = _parse_harness_stdout(r.stdout or "")
    if out:
        if r.stderr and r.stderr.strip():
            out = {**out, "harness_stderr_tail": (r.stderr or "")[-1500:]}
        return out
    return {
        "ok": False,
        "error": "harness_json_parse_error",
        "stdout": (r.stdout or "")[:4000],
        "stderr": (r.stderr or "")[:4000],
    }


def run_intake_pipeline(
    repo_root: Path,
    raw_bytes: bytes,
    original_filename: str,
    *,
    test_window_bars: int = 800,
    execution_target: str | None = None,
) -> dict[str, Any]:
    """
    Run stages 1–6. Returns full report dict (persisted under report/intake_report.json).
    """
    repo_root = repo_root.resolve()
    et = normalize_execution_target(execution_target)
    submission_id = uuid.uuid4().hex[:24]
    paths = ensure_submission_layout(repo_root, submission_id)
    report: dict[str, Any] = {
        "schema": "policy_intake_report_v1",
        "submission_id": submission_id,
        "execution_target": et,
        "execution_target_label": LABELS.get(et, et),
        "compared_against_baseline_label": BASELINE_COMPARED_LABELS.get(et, "Baseline"),
        "original_filename": original_filename,
        "detected_kind": _detect_kind(original_filename),
        "stages": {},
        "pass": False,
        "candidate_policy_id": None,
        "errors": [],
    }

    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", original_filename)[:180] or "upload.bin"
    if safe_name.lower().endswith(".xml") or _reject_xml(safe_name):
        report["stages"]["stage_1_intake"] = {"ok": False, "detail": "XML uploads are not supported"}
        report["errors"].append("unsupported_format: XML")
        write_json(paths["report"] / "intake_report.json", report)
        _finalize_intake_lifecycle(repo_root, report)
        return report

    # Stage 1
    raw_path = paths["raw"] / f"original_{safe_name}"
    try:
        raw_path.write_bytes(raw_bytes)
    except OSError as e:
        report["stages"]["stage_1_intake"] = {"ok": False, "detail": str(e)}
        report["errors"].append(f"intake_storage_failed:{e}")
        write_json(paths["report"] / "intake_report.json", report)
        _finalize_intake_lifecycle(repo_root, report)
        return report

    report["stages"]["stage_1_intake"] = {
        "ok": True,
        "stored_path": str(raw_path.relative_to(repo_root)),
        "bytes": len(raw_bytes),
        "content_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    kind = report["detected_kind"]
    canonical: dict[str, Any] | None = None
    norm_errs: list[str] = []

    # Stage 2 + 3 by kind
    if kind == "typescript":
        report["stages"]["stage_2_structural"] = {"status": "in_progress"}
        ok_ts, msg = validate_typescript_file(raw_path)
        report["stages"]["stage_2_structural"] = {
            "ok": ok_ts,
            "detail": msg[:8000] if not ok_ts else msg,
        }
        if not ok_ts:
            report["errors"].append(f"typescript_compile_failed:{msg[:500]}")
            write_json(paths["report"] / "intake_report.json", report)
            _finalize_intake_lifecycle(repo_root, report)
            return report

        report["stages"]["stage_3_normalization"] = {"status": "in_progress"}
        try:
            text = raw_path.read_text(encoding="utf-8", errors="replace")
            pid_m = re.search(r"policy_id\s*[:=]\s*['\"]([^'\"]+)['\"]", text)
            cid_m = re.search(r"CATALOG_ID\s*=\s*['\"]([^'\"]+)['\"]", text)
            inferred_id = (pid_m.group(1) if pid_m else None) or (cid_m.group(1) if cid_m else None)
            pid = inferred_id or f"intake_candidate_{submission_id[:12]}"
            loose = {
                "policy_id": pid,
                "policy_class": "candidate",
                "description": "Inferred from TypeScript policy upload",
                "timeframe": "5m",
                "signal_type": "other",
            }
            embedded = _extract_rv4_policy_indicators_json_from_ts(text)
            if embedded is not None:
                loose["indicators"] = embedded
            canonical = normalize_policy(loose)
            canonical.setdefault("source_submission", {})
            if isinstance(canonical["source_submission"], dict):
                canonical["source_submission"]["typescript_path"] = str(raw_path.relative_to(repo_root))
        except Exception as e:  # noqa: BLE001
            norm_errs.append(f"normalization_failed:{e}")
            report["stages"]["stage_3_normalization"] = {"ok": False, "errors": norm_errs}
            report["errors"].extend(norm_errs)
            write_json(paths["report"] / "intake_report.json", report)
            _finalize_intake_lifecycle(repo_root, report)
            return report
        report["stages"]["stage_3_normalization"] = {"ok": True, "detail": "derived_from_ts_metadata_heuristic"}

    elif kind in ("yaml", "json"):
        report["stages"]["stage_2_structural"] = {"status": "in_progress"}
        try:
            if kind == "yaml":
                try:
                    import yaml  # type: ignore
                except ImportError:
                    report["stages"]["stage_2_structural"] = {"ok": False, "detail": "PyYAML not installed on API host"}
                    report["errors"].append("missing_pyyaml")
                    write_json(paths["report"] / "intake_report.json", report)
                    _finalize_intake_lifecycle(repo_root, report)
                    return report
                data = yaml.safe_load(raw_bytes.decode("utf-8", errors="replace"))
            else:
                data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
            if not isinstance(data, dict):
                raise ValueError("top_level_must_be_object")
        except Exception as e:  # noqa: BLE001
            report["stages"]["stage_2_structural"] = {"ok": False, "detail": str(e)}
            report["errors"].append(f"parse_failed:{e}")
            write_json(paths["report"] / "intake_report.json", report)
            _finalize_intake_lifecycle(repo_root, report)
            return report
        report["stages"]["stage_2_structural"] = {"ok": True, "detail": "parsed"}

        report["stages"]["stage_3_normalization"] = {"status": "in_progress"}
        try:
            canonical = normalize_policy(data)
        except Exception as e:  # noqa: BLE001
            report["stages"]["stage_3_normalization"] = {"ok": False, "detail": str(e)}
            report["errors"].append(f"normalization_failed:{e}")
            write_json(paths["report"] / "intake_report.json", report)
            _finalize_intake_lifecycle(repo_root, report)
            return report
        report["stages"]["stage_3_normalization"] = {"ok": True}
    else:
        report["errors"].append("unsupported_file_extension")
        report["stages"]["stage_2_structural"] = {"ok": False, "detail": "Unsupported extension; use .ts, .yaml, .yml, or .json"}
        write_json(paths["report"] / "intake_report.json", report)
        _finalize_intake_lifecycle(repo_root, report)
        return report

    assert canonical is not None

    # Stage 4 — validate before persisting canonical (indicator unknown keys must fail before coerce)
    report["stages"]["stage_4_static"] = {"status": "in_progress"}
    ok_s, static_errs = _static_sanity(canonical)
    report["stages"]["stage_4_static"] = {"ok": ok_s, "errors": static_errs}
    if not ok_s:
        report["errors"].extend(static_errs)
        write_json(paths["report"] / "intake_report.json", report)
        _finalize_intake_lifecycle(repo_root, report)
        return report

    canonical["indicators"] = coerce_indicators_section(canonical.get("indicators"))
    write_json(paths["canonical"] / "policy_spec_v1.json", canonical)

    # Stage 5 — deterministic test
    report["stages"]["stage_5_deterministic"] = {
        "test_window_bars": int(test_window_bars),
        "status": "in_progress",
    }
    det: dict[str, Any] = {}
    if kind != "typescript":
        det = {
            "ok": False,
            "error": "deterministic_execution_requires_typescript_module",
            "detail": "YAML/JSON specs are normalized and validated; full signal/trade/PnL proof requires "
            "an executable TypeScript policy module (.ts) exporting generateSignalFromOhlc.",
        }
        report["stages"]["stage_5_deterministic"] = {**det, "signals_total": 0, "trades_opened": 0, "trades_closed": 0}
        report["errors"].append(det["error"])
        report["pass"] = False
        write_json(paths["report"] / "intake_report.json", report)
        _finalize_intake_lifecycle(repo_root, report)
        return report

    det = _run_ts_deterministic(
        repo_root,
        raw_path,
        test_window_bars,
        execution_target=et,
        indicators_section=canonical.get("indicators") if isinstance(canonical.get("indicators"), dict) else None,
    )
    report["stages"]["stage_5_deterministic"] = det
    if not det.get("ok"):
        report["errors"].append(str(det.get("error") or "deterministic_failed"))
        write_json(paths["report"] / "intake_report.json", report)
        _finalize_intake_lifecycle(repo_root, report)
        return report

    sig = int(det.get("signals_total") or 0)
    op = int(det.get("trades_opened") or 0)
    cl = int(det.get("trades_closed") or 0)
    pnl = det.get("pnl_summary") or {}
    realized = pnl.get("realized") if isinstance(pnl, dict) else None
    pnl_ok = isinstance(realized, (int, float)) and not (isinstance(realized, float) and (math.isnan(realized)))

    # Stage 6
    viability = (
        sig > 0
        and op >= 1
        and cl >= 1
        and pnl_ok
        and abs(float(realized)) < 1e100
    )
    report["stages"]["stage_6_viability"] = {
        "ok": viability,
        "signals_total": sig,
        "trades_opened": op,
        "trades_closed": cl,
        "pnl_valid": pnl_ok,
    }
    if not viability:
        if sig == 0:
            report["errors"].append("no_signals_generated_in_test_window")
        if op < 1:
            report["errors"].append("no_trade_opened_in_simulation")
        if cl < 1:
            report["errors"].append("no_trade_closed_in_simulation")
        if not pnl_ok:
            report["errors"].append("invalid_or_nan_pnl")
        write_json(paths["report"] / "intake_report.json", report)
        _finalize_intake_lifecycle(repo_root, report)
        return report

    cid = str(canonical.get("identity", {}).get("policy_id") or f"kitchen_candidate_{submission_id[:16]}")
    report["candidate_policy_id"] = cid
    report["pass"] = True
    report["is_active"] = True  # DV-066: soft-archive via intake report; default visible in Kitchen
    canonical.setdefault("identity", {})
    if isinstance(canonical["identity"], dict):
        canonical["identity"]["policy_id"] = cid
        canonical["identity"]["policy_class"] = "candidate"
    canonical.setdefault("deployment_metadata", {})
    if isinstance(canonical["deployment_metadata"], dict):
        canonical["deployment_metadata"]["promotion_eligible"] = False
    write_json(paths["canonical"] / "policy_spec_v1.json", canonical)
    write_json(paths["report"] / "intake_report.json", report)
    _finalize_intake_lifecycle(repo_root, report)
    return report
