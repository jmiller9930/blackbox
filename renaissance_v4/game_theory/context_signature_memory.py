"""
Context Signature Memory v1 — deterministic, append-only storage of
pattern-context signatures paired with bundle apply + outcomes.

No LLM, no embeddings. Similarity is explicit (regime/vol exact + bounded numeric tolerances).
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTEXT_SIGNATURE_SCHEMA = "context_signature_v1"
CONTEXT_SIGNATURE_MEMORY_RECORD_SCHEMA = "context_signature_memory_record_v1"

_DEFAULT_MEMORY_PATH = Path(__file__).resolve().parent / "state" / "context_signature_memory.jsonl"


class ContextSignatureMemoryError(ValueError):
    """Malformed signature, record, or store line."""


@dataclass(frozen=True)
class SignatureMatchParamsV1:
    """Explicit v1 tolerances (absolute difference on unit-interval shares)."""

    structure_share_abs_tol: float = 0.12
    conflict_share_abs_tol: float = 0.15
    directional_share_abs_tol: float = 0.15


def derive_context_signature_v1(pattern_context_v1: dict[str, Any]) -> dict[str, Any]:
    """
    Build a compact, reproducible signature from ``pattern_context_v1`` (replay output).

    Fails closed if required fields are missing or wrong types.
    """
    if not isinstance(pattern_context_v1, dict):
        raise ContextSignatureMemoryError("pattern_context_v1 must be a dict")
    if pattern_context_v1.get("schema") != "pattern_context_v1":
        raise ContextSignatureMemoryError("pattern_context_v1.schema must be 'pattern_context_v1'")

    bars = int(pattern_context_v1.get("bars_processed") or 0)
    if bars < 1:
        raise ContextSignatureMemoryError("pattern_context_v1.bars_processed must be >= 1")

    tags = pattern_context_v1.get("structure_tag_shares")
    if not isinstance(tags, dict):
        raise ContextSignatureMemoryError("pattern_context_v1.structure_tag_shares must be a dict")

    dr = pattern_context_v1.get("dominant_regime")
    dv = pattern_context_v1.get("dominant_volatility_bucket")
    if not isinstance(dr, str) or not dr:
        raise ContextSignatureMemoryError("dominant_regime must be a non-empty string")
    if not isinstance(dv, str) or not dv:
        raise ContextSignatureMemoryError("dominant_volatility_bucket must be a non-empty string")

    hc = int(pattern_context_v1.get("high_conflict_bars") or 0)
    al = int(pattern_context_v1.get("aligned_directional_bars") or 0)
    ct = int(pattern_context_v1.get("countertrend_directional_bars") or 0)

    def _f(key: str) -> float:
        return round(float(tags.get(key) or 0.0), 6)

    sig: dict[str, Any] = {
        "schema": CONTEXT_SIGNATURE_SCHEMA,
        "version": 1,
        "dominant_regime": dr,
        "dominant_volatility_bucket": dv,
        "range_like_share": _f("range_like"),
        "trend_like_share": _f("trend_like"),
        "breakout_like_share": _f("breakout_like"),
        "vol_compressed_share": _f("vol_compressed"),
        "vol_expanding_share": _f("vol_expanding"),
        "high_conflict_share": round(hc / float(bars), 6),
        "aligned_directional_share": round(al / float(bars), 6),
        "countertrend_directional_share": round(ct / float(bars), 6),
    }
    return sig


def canonical_signature_key(signature: dict[str, Any]) -> str:
    """SHA-256 of canonical JSON (sorted keys) over the signature object."""
    if not isinstance(signature, dict):
        raise ContextSignatureMemoryError("signature must be a dict")
    if signature.get("schema") != CONTEXT_SIGNATURE_SCHEMA:
        raise ContextSignatureMemoryError("signature.schema must be context_signature_v1")
    payload = json.dumps(signature, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _share_abs_delta(a: float, b: float) -> float:
    return abs(float(a) - float(b))


def signatures_match_v1(
    a: dict[str, Any],
    b: dict[str, Any],
    params: SignatureMatchParamsV1 | None = None,
) -> bool:
    """
    Rule-based v1 match: exact dominant regime + volatility bucket; bounded tolerance on shares.
    """
    p = params or SignatureMatchParamsV1()
    if a.get("schema") != CONTEXT_SIGNATURE_SCHEMA or b.get("schema") != CONTEXT_SIGNATURE_SCHEMA:
        return False
    if a.get("dominant_regime") != b.get("dominant_regime"):
        return False
    if a.get("dominant_volatility_bucket") != b.get("dominant_volatility_bucket"):
        return False

    struct_keys = (
        "range_like_share",
        "trend_like_share",
        "breakout_like_share",
        "vol_compressed_share",
        "vol_expanding_share",
    )
    for k in struct_keys:
        if _share_abs_delta(a[k], b[k]) > p.structure_share_abs_tol:
            return False

    if _share_abs_delta(a["high_conflict_share"], b["high_conflict_share"]) > p.conflict_share_abs_tol:
        return False
    if _share_abs_delta(a["aligned_directional_share"], b["aligned_directional_share"]) > p.directional_share_abs_tol:
        return False
    if _share_abs_delta(a["countertrend_directional_share"], b["countertrend_directional_share"]) > p.directional_share_abs_tol:
        return False

    return True


def _validate_outcome_summary(o: dict[str, Any]) -> dict[str, Any]:
    required = ("expectancy", "max_drawdown", "win_rate", "total_trades", "cumulative_pnl")
    for k in required:
        if k not in o:
            raise ContextSignatureMemoryError(f"outcome_summary missing {k}")
    return {
        "expectancy": float(o["expectancy"]),
        "max_drawdown": float(o["max_drawdown"]),
        "win_rate": float(o["win_rate"]),
        "total_trades": int(o["total_trades"]),
        "cumulative_pnl": float(o["cumulative_pnl"]),
    }


def _validate_effective_apply(eff: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(eff, dict):
        raise ContextSignatureMemoryError("effective_apply must be a dict")
    return dict(eff)


def validate_memory_record_v1(record: dict[str, Any]) -> dict[str, Any]:
    """Validate a full memory record; return a normalized copy. Fails closed on bad data."""
    if not isinstance(record, dict):
        raise ContextSignatureMemoryError("record must be a dict")
    if record.get("schema") != CONTEXT_SIGNATURE_MEMORY_RECORD_SCHEMA:
        raise ContextSignatureMemoryError("record.schema must be context_signature_memory_record_v1")
    rid = str(record.get("record_id") or "").strip()
    if not rid:
        raise ContextSignatureMemoryError("record_id required")
    sig = record.get("context_signature")
    if not isinstance(sig, dict):
        raise ContextSignatureMemoryError("context_signature must be a dict")
    if sig.get("schema") != CONTEXT_SIGNATURE_SCHEMA:
        raise ContextSignatureMemoryError("context_signature.schema invalid")
    sk = str(record.get("signature_key") or "").strip()
    if not sk or sk != canonical_signature_key(sig):
        raise ContextSignatureMemoryError("signature_key must match canonical hash of context_signature")
    _validate_effective_apply(record.get("effective_apply") or {})
    _validate_outcome_summary(record.get("outcome_summary") or {})
    ocs = record.get("optimizer_reason_codes")
    if not isinstance(ocs, list) or not all(isinstance(x, str) for x in ocs):
        raise ContextSignatureMemoryError("optimizer_reason_codes must be a list of strings")
    sap = record.get("source_artifact_paths")
    if not isinstance(sap, list) or not all(isinstance(x, str) for x in sap):
        raise ContextSignatureMemoryError("source_artifact_paths must be a list of strings")
    bak = record.get("bundle_apply_keys")
    if not isinstance(bak, list) or not all(isinstance(x, str) for x in bak):
        raise ContextSignatureMemoryError("bundle_apply_keys must be a list of strings")
    return record


def read_context_memory_records(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Read and validate all records from JSONL. Malformed lines raise ContextSignatureMemoryError."""
    p = Path(path or _DEFAULT_MEMORY_PATH).expanduser().resolve()
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as e:
            raise ContextSignatureMemoryError(f"line {line_no}: invalid JSON: {e}") from e
        if not isinstance(raw, dict):
            raise ContextSignatureMemoryError(f"line {line_no}: record must be an object")
        out.append(validate_memory_record_v1(raw))
    return out


def append_context_memory_record(
    *,
    pattern_context_v1: dict[str, Any],
    source_run_id: str,
    source_artifact_paths: list[str],
    effective_apply: dict[str, Any],
    outcome_summary: dict[str, Any],
    optimizer_reason_codes: list[str],
    memory_path: Path | str | None = None,
    record_id: str | None = None,
) -> dict[str, Any]:
    """
    Append one validated record to the JSONL store. Creates parent directories as needed.
    """
    sig = derive_context_signature_v1(pattern_context_v1)
    sk = canonical_signature_key(sig)
    eff = _validate_effective_apply(effective_apply)
    out_sum = _validate_outcome_summary(outcome_summary)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rid = (record_id or "").strip() or uuid.uuid4().hex
    bundle_keys = sorted(eff.keys())

    record: dict[str, Any] = {
        "schema": CONTEXT_SIGNATURE_MEMORY_RECORD_SCHEMA,
        "version": 1,
        "record_id": rid,
        "timestamp_utc": ts,
        "source_run_id": str(source_run_id),
        "source_artifact_paths": [str(x) for x in source_artifact_paths],
        "context_signature": sig,
        "signature_key": sk,
        "bundle_apply_keys": bundle_keys,
        "effective_apply": eff,
        "outcome_summary": out_sum,
        "optimizer_reason_codes": list(optimizer_reason_codes),
    }
    validate_memory_record_v1(record)

    p = Path(memory_path or _DEFAULT_MEMORY_PATH).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    fd = os.open(str(p), flags, 0o644)
    flock = None
    try:
        try:
            import fcntl

            flock = fcntl
        except ImportError:
            pass
        if flock is not None:
            try:
                flock.flock(fd, flock.LOCK_EX)
            except OSError:
                flock = None
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            if flock is not None:
                try:
                    flock.flock(fd, flock.LOCK_UN)
                except OSError:
                    pass
    finally:
        os.close(fd)
    return record


def outcome_strictly_better_for_bias(
    prior: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    """Prior run must have strictly higher expectancy and strictly lower max_drawdown."""
    pe = float(prior["expectancy"])
    ce = float(current["expectancy"])
    pd = float(prior["max_drawdown"])
    cd = float(current["max_drawdown"])
    return pe > ce + 1e-12 and pd < cd - 1e-12


def find_matching_records_v1(
    current_signature: dict[str, Any],
    records: list[dict[str, Any]],
    params: SignatureMatchParamsV1 | None = None,
) -> list[dict[str, Any]]:
    """Return records whose stored signature matches ``current_signature`` under v1 rules."""
    out: list[dict[str, Any]] = []
    for rec in records:
        sig = rec.get("context_signature")
        if not isinstance(sig, dict):
            continue
        if signatures_match_v1(current_signature, sig, params=params):
            out.append(rec)
    return sorted(out, key=lambda r: (str(r.get("record_id", ""))))


def select_best_outcome_record(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Deterministic: max expectancy, then min max_drawdown, then record_id."""
    if not candidates:
        return None

    def key(r: dict[str, Any]) -> tuple[float, float, str]:
        o = r.get("outcome_summary") or {}
        ex = float(o.get("expectancy", -1e100))
        dd = float(o.get("max_drawdown", 1e100))
        rid = str(r.get("record_id", ""))
        return (-ex, dd, rid)

    return sorted(candidates, key=key)[0]


def eligible_bias_records(
    matches: list[dict[str, Any]],
    current_outcome: dict[str, Any],
) -> list[dict[str, Any]]:
    """Subset of matches with strictly better stored outcome vs current run metrics."""
    cur = _validate_outcome_summary(current_outcome)
    eligible: list[dict[str, Any]] = []
    for rec in matches:
        prior = rec.get("outcome_summary")
        if not isinstance(prior, dict):
            raise ContextSignatureMemoryError("record outcome_summary malformed")
        po = _validate_outcome_summary(prior)
        if outcome_strictly_better_for_bias(po, cur):
            eligible.append(rec)
    return sorted(eligible, key=lambda r: str(r.get("record_id", "")))


BIAS_NUMERIC_MAX_STEP = 0.025


def apply_context_memory_bias_v1(
    apply_after_v2: dict[str, Any],
    *,
    eligible_records: list[dict[str, Any]],
    manifest_signal_modules: list[str] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """
    Deterministic bias toward the single best eligible record's numeric apply values (capped steps)
    and intersection of disabled_signal_modules across all eligible records when safe.

    Returns ``(delta_apply, bias_diff, reason_codes)``.
    """
    from renaissance_v4.game_theory.memory_bundle import BUNDLE_APPLY_WHITELIST

    mods = list(manifest_signal_modules or [])
    reason_codes: list[str] = []
    if not eligible_records:
        return {}, [], reason_codes

    best = select_best_outcome_record(eligible_records)
    if best is None:
        return {}, [], ["CM3_BIAS_SKIPPED_NO_ELIGIBLE_RECORD"]

    best_id = str(best.get("record_id", ""))
    prior_apply = dict(best.get("effective_apply") or {})
    delta: dict[str, Any] = {}
    diff: list[dict[str, Any]] = []

    numeric_keys = (
        k
        for k in BUNDLE_APPLY_WHITELIST
        if k != "disabled_signal_modules" and k in prior_apply and prior_apply[k] is not None
    )
    for k in sorted(numeric_keys):
        if k not in prior_apply:
            continue
        pv = prior_apply[k]
        cv = apply_after_v2.get(k)
        if cv is None:
            continue
        try:
            pf = float(pv)
            cf = float(cv)
        except (TypeError, ValueError):
            continue
        step = min(abs(pf - cf), BIAS_NUMERIC_MAX_STEP)
        if step <= 1e-15:
            continue
        if pf > cf:
            nv = round(cf + step, 6)
        else:
            nv = round(cf - step, 6)
        if abs(nv - cf) > 1e-12:
            delta[k] = nv
            diff.append(
                {
                    "key": k,
                    "old": cf,
                    "new": nv,
                    "from_record_id": best_id,
                    "reason": "CM3_BIAS_TOWARD_BETTER_OUTCOME_RECORD",
                }
            )
            reason_codes.append("CM3_BIAS_NUMERIC_TOWARD_PRIOR")

    # Intersection of disables across all eligible (consistent prior policy)
    dis_sets: list[set[str]] = []
    for rec in eligible_records:
        d = rec.get("effective_apply", {}).get("disabled_signal_modules")
        if isinstance(d, list) and d:
            dis_sets.append(set(str(x) for x in d))
    if dis_sets:
        inter = set.intersection(*dis_sets)
        cur_d = list(apply_after_v2.get("disabled_signal_modules") or [])
        if not isinstance(cur_d, list):
            cur_d = []
        merged = sorted(set(cur_d) | inter)
        remaining = [m for m in mods if m not in merged]
        if inter and len(remaining) >= 1:
            if merged != sorted(set(cur_d)):
                delta["disabled_signal_modules"] = merged
                diff.append(
                    {
                        "key": "disabled_signal_modules",
                        "old": sorted(set(cur_d)),
                        "new": merged,
                        "from_record_ids": sorted(str(r.get("record_id", "")) for r in eligible_records),
                        "reason": "CM3_BIAS_INTERSECTION_DISABLES_ELIGIBLE_MATCHES",
                    }
                )
                reason_codes.append("CM3_BIAS_DISABLE_INTERSECTION")

    if not delta:
        reason_codes.append("CM3_MATCHES_ELIGIBLE_NO_APPLICABLE_BIAS")

    return delta, diff, reason_codes


def default_memory_path() -> Path:
    return _DEFAULT_MEMORY_PATH
