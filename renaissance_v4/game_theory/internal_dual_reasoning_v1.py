"""
Minimal **internal dual-reasoning** helpers for Ask DATA.

**Policy:** Qwen (default ``qwen2.5:7b`` via API Gateway / role routing) remains the primary builder.
Local **DeepSeek R1** on ``172.20.2.230`` acts as an adversarial second opinion — not authority,
not execution. DATA validation stays downstream of model suggestions.

External OpenAI / GPT gateway escalation is **out of scope** for this module; Ask DATA never calls it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

InternalReasoningMode = Literal["qwen_only", "deepseek_only", "dual_review"]

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Topics that warrant dual-review (Qwen + DeepSeek) and usually DATA validation.
_DUAL_TOPIC_RE = re.compile(
    r"(?i)\b("
    r"strategy\s+logic|trading\s+policy|\bpnl\b|p&l|profit\s+and\s+loss|replay\s+determin|determinism|"
    r"\breplay\b.*\b(dw|decision|slot)|\brisk\s+(logic|math|limit|gate)|memory\s+fusion|"
    r"learning\s+behavior|execution\s+gating|policy\s+assignment|architecture\s+change|"
    r"overfitting|manifest|ledger|scorecard.*replay"
    r")\b"
)


def _token_overlap_agreement_v1(a: str, b: str) -> Literal["agree", "partial", "disagree"]:
    def _tok(s: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9]{4,}", s.lower()) if len(w) >= 4}

    sa, sb = _tok(a), _tok(b)
    if not sa and not sb:
        return "disagree"
    if not sa or not sb:
        return "partial"
    inter = len(sa & sb)
    union = len(sa | sb) or 1
    j = inter / union
    if j >= 0.11:
        return "agree"
    if j >= 0.035:
        return "partial"
    return "disagree"


def package_digest_v1(bundle: dict[str, Any], question: str) -> str:
    """Stable short id for logging (no secrets)."""
    payload = json.dumps(bundle, sort_keys=True, ensure_ascii=False)[:12000]
    h = hashlib.sha256(f"{question.strip()}\n{payload}".encode())
    return h.hexdigest()[:16]


def classify_internal_reasoning_mode_v1(
    question: str,
    *,
    ask_data_route: str,
    job_resolution: str,
) -> tuple[InternalReasoningMode, dict[str, Any]]:
    """
    ``INTERNAL_REASONING_MODE`` (optional): ``auto`` | ``qwen_only`` | ``deepseek_only`` | ``dual_review``.
    Default ``auto``: dual-review when topic hints match; ``deepseek_escalation`` route uses DeepSeek-only
    unless dual topics apply (then dual-review with Qwen builder + reviewer).
    """
    forced = (os.environ.get("INTERNAL_REASONING_MODE") or "").strip().lower()
    if forced in ("", "auto"):
        forced = ""
    meta: dict[str, Any] = {"internal_reasoning_env_override": forced or None}
    blob = f"{question}\n{job_resolution}"
    dual_hint = bool(_DUAL_TOPIC_RE.search(blob))
    meta["dual_topic_hint_v1"] = dual_hint

    if forced in ("qwen_only", "qwen", "primary"):
        return "qwen_only", meta
    if forced in ("deepseek_only", "deepseek", "reviewer"):
        return "deepseek_only", meta
    if forced in ("dual_review", "dual", "both", "parallel"):
        return "dual_review", meta

    if ask_data_route == "deepseek_escalation":
        if dual_hint:
            return "dual_review", meta
        return "deepseek_only", meta
    if dual_hint:
        return "dual_review", meta
    return "qwen_only", meta


def data_validation_sensitive_topic_v1(question: str, job_resolution: str) -> bool:
    """Trading / replay / policy / risk / PnL-shaped topics — DATA validation always required."""
    return bool(_DUAL_TOPIC_RE.search(f"{question}\n{job_resolution}"))


def resolve_qwen_target_for_internal_mode_v1(
    ask_data_route: str,
    mode: InternalReasoningMode,
) -> tuple[str, str, float]:
    """Dual-review always uses System Agent Qwen (strong builder). Otherwise use Ask DATA tier."""
    from renaissance_v4.game_theory.ask_data_router_v1 import ask_data_ollama_target_for_route_v1
    from renaissance_v4.game_theory.ollama_role_routing_v1 import (
        system_agent_ollama_base_url,
        system_agent_ollama_model_primary,
    )

    if mode == "dual_review":
        return (
            system_agent_ollama_base_url(),
            system_agent_ollama_model_primary(),
            float(os.environ.get("ASK_DATA_OLLAMA_TIMEOUT_SYSTEM_AGENT", "180") or 180),
        )
    return ask_data_ollama_target_for_route_v1(ask_data_route)  # type: ignore[arg-type]


def compare_dual_review_outputs_v1(
    qwen_text: str,
    deepseek_text: str,
    *,
    data_validation_domain: bool,
) -> dict[str, Any]:
    q = (qwen_text or "").strip()
    d = (deepseek_text or "").strip()
    agr = _token_overlap_agreement_v1(q, d)
    always_data = bool(data_validation_domain)
    need_data = always_data or agr == "disagree"
    return {
        "schema": "internal_dual_comparison_v1",
        "agreement_level_v1": agr,
        "data_validation_required_v1": need_data,
        "data_validation_note_v1": (
            "Required: verify against SQLite, logs, manifests, replay output, policy registries, and health endpoints."
            if need_data
            else "Recommended when changing behavior."
        ),
        "qwen_excerpt_v1": (q[:360] + ("…" if len(q) > 360 else "")).replace("\n", " "),
        "deepseek_excerpt_v1": (d[:360] + ("…" if len(d) > 360 else "")).replace("\n", " "),
        "conflict_summary_v1": (
            "Substantive divergence between internal models; do not treat either narrative as proof without DATA."
            if agr == "disagree"
            else ""
        ),
    }


def _ollama_generate_fn() -> Any:
    rt = str(_REPO_ROOT / "scripts" / "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    from llm.local_llm_client import ollama_generate

    return ollama_generate


def _log_dual_review_line(**parts: Any) -> None:
    msg = "[internal_dual_reasoning_v1] " + " ".join(f"{k}={parts[k]!r}" for k in sorted(parts))
    print(msg, file=sys.stderr, flush=True)


def run_ask_data_dual_review_v1(
    bundle: dict[str, Any],
    question: str,
    *,
    ask_data_route: str,
    timeout: float | None = None,
) -> tuple[str, str | None, dict[str, Any]]:
    """
    Same normalized bundle + question to **Qwen** (builder) and **DeepSeek R1** (adversarial reviewer)
    in parallel. Independent timeouts and errors; failures are surfaced explicitly.
    """
    from renaissance_v4.game_theory.ask_data_explainer import build_ask_data_llm_prompt_v1
    from renaissance_v4.game_theory.ollama_role_routing_v1 import (
        deepseek_escalation_ollama_base_url,
        deepseek_escalation_ollama_model,
    )

    gen = _ollama_generate_fn()
    pkg = package_digest_v1(bundle, question)
    qb, qm, q_def_t = resolve_qwen_target_for_internal_mode_v1(ask_data_route, "dual_review")
    db = deepseek_escalation_ollama_base_url()
    dm = deepseek_escalation_ollama_model()
    ds_timeout = float(os.environ.get("ASK_DATA_OLLAMA_TIMEOUT_DEEPSEEK", "240") or 240)
    qw_timeout = float(os.environ.get("ASK_DATA_OLLAMA_TIMEOUT_SYSTEM_AGENT", "180") or 180)
    if timeout is not None:
        qw_timeout = float(timeout)
        ds_timeout = float(timeout)

    prompt_q = build_ask_data_llm_prompt_v1(bundle, question, route=ask_data_route, role="builder")
    prompt_d = build_ask_data_llm_prompt_v1(
        bundle, question, route=ask_data_route, role="adversarial_reviewer"
    )

    q_err: str | None = None
    d_err: str | None = None
    q_text = ""
    d_text = ""
    q_lat: float | None = None
    d_lat: float | None = None
    q_rep: str | None = None
    d_rep: str | None = None

    def _run_qwen() -> tuple[str, str | None, str | None, float]:
        t0 = time.perf_counter()
        res = gen(prompt_q, base_url=qb, model=qm, timeout=qw_timeout)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        if res.error:
            return "", res.error, res.model, dt_ms
        return (res.text or "").strip(), None, res.model, dt_ms

    def _run_ds() -> tuple[str, str | None, str | None, float]:
        t0 = time.perf_counter()
        res = gen(prompt_d, base_url=db, model=dm, timeout=ds_timeout)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        if res.error:
            return "", res.error, res.model, dt_ms
        return (res.text or "").strip(), None, res.model, dt_ms

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_q = ex.submit(_run_qwen)
        f_d = ex.submit(_run_ds)
        q_text, q_err, q_rep, q_lat = f_q.result()
        d_text, d_err, d_rep, d_lat = f_d.result()

    sens = data_validation_sensitive_topic_v1(question, str((bundle or {}).get("job_resolution") or ""))
    comp = compare_dual_review_outputs_v1(q_text, d_text, data_validation_domain=sens)

    _log_dual_review_line(
        package_id=pkg,
        mode="dual_review",
        qwen_base=qb,
        qwen_requested_model=qm,
        qwen_reported_model=q_rep,
        qwen_ok=q_err is None,
        qwen_latency_ms=round(q_lat or 0.0, 2),
        qwen_error=q_err,
        deepseek_base=db,
        deepseek_requested_model=dm,
        deepseek_reported_model=d_rep,
        deepseek_ok=d_err is None,
        deepseek_latency_ms=round(d_lat or 0.0, 2),
        deepseek_error=d_err,
        comparison_agreement=comp.get("agreement_level_v1"),
        data_validation_required=comp.get("data_validation_required_v1"),
    )

    sections: list[str] = [
        "### Qwen (primary internal)",
        "",
        q_text if q_text else f"*(Qwen call failed: {q_err})*",
        "",
        "### DeepSeek R1 (adversarial reviewer — not authority)",
        "",
        d_text if d_text else f"*(DeepSeek call failed: {d_err})*",
        "",
        "---",
        "",
        "**Dual-review summary (reviewer-only; not ground truth):**",
        f"- Agreement: **{comp.get('agreement_level_v1')}**",
        f"- DATA validation: **{'required' if comp.get('data_validation_required_v1') else 'recommended'}** — "
        f"{comp.get('data_validation_note_v1', '')}",
    ]
    if comp.get("conflict_summary_v1"):
        sections.extend(["", f"- Conflicts / caution: {comp['conflict_summary_v1']}"])

    evidence = {
        "internal_reasoning_mode_v1": "dual_review",
        "prompt_package_id_v1": pkg,
        "qwen": {
            "ollama_base_url": qb,
            "requested_model": qm,
            "reported_model": q_rep,
            "latency_ms": q_lat,
            "error": q_err,
            "ok": q_err is None,
        },
        "deepseek_reviewer": {
            "ollama_base_url": db,
            "requested_model": dm,
            "reported_model": d_rep,
            "latency_ms": d_lat,
            "error": d_err,
            "ok": d_err is None,
        },
        "comparison_v1": comp,
        "external_openai_invoked_v1": False,
    }
    combined = "\n".join(sections)
    overall_err = None if (q_err is None or d_err is None) else "both_failed"
    return combined, overall_err, evidence


def run_ask_data_deepseek_only_v1(
    bundle: dict[str, Any],
    question: str,
    *,
    ask_data_route: str,
    timeout: float | None = None,
) -> tuple[str, str | None, dict[str, Any]]:
    from renaissance_v4.game_theory.ask_data_explainer import build_ask_data_llm_prompt_v1
    from renaissance_v4.game_theory.ollama_role_routing_v1 import (
        deepseek_escalation_ollama_base_url,
        deepseek_escalation_ollama_model,
    )

    gen = _ollama_generate_fn()
    pkg = package_digest_v1(bundle, question)
    prompt_d = build_ask_data_llm_prompt_v1(
        bundle, question, route=ask_data_route, role="adversarial_reviewer"
    )
    db = deepseek_escalation_ollama_base_url()
    dm = deepseek_escalation_ollama_model()
    ds_timeout = float(os.environ.get("ASK_DATA_OLLAMA_TIMEOUT_DEEPSEEK", "240") or 240)
    if timeout is not None:
        ds_timeout = float(timeout)
    t0 = time.perf_counter()
    res = gen(prompt_d, base_url=db, model=dm, timeout=ds_timeout)
    lat = (time.perf_counter() - t0) * 1000.0
    print(
        "[internal_dual_reasoning_v1] "
        f"package_id={pkg} mode=deepseek_only deepseek_base={db} requested_model={dm} "
        f"reported_model={res.model!r} ok={not res.error} latency_ms={round(lat, 2)} error={res.error!r}",
        file=sys.stderr,
        flush=True,
    )
    if res.error:
        return "", res.error, {
            "internal_reasoning_mode_v1": "deepseek_only",
            "prompt_package_id_v1": pkg,
            "deepseek_reviewer": {
                "ollama_base_url": db,
                "requested_model": dm,
                "reported_model": res.model,
                "latency_ms": lat,
                "error": res.error,
                "ok": False,
            },
            "external_openai_invoked_v1": False,
        }
    evidence = {
        "internal_reasoning_mode_v1": "deepseek_only",
        "prompt_package_id_v1": pkg,
        "deepseek_reviewer": {
            "ollama_base_url": db,
            "requested_model": dm,
            "reported_model": res.model,
            "latency_ms": lat,
            "error": None,
            "ok": True,
        },
        "external_openai_invoked_v1": False,
    }
    return (res.text or "").strip(), None, evidence


__all__ = [
    "InternalReasoningMode",
    "classify_internal_reasoning_mode_v1",
    "compare_dual_review_outputs_v1",
    "data_validation_sensitive_topic_v1",
    "package_digest_v1",
    "resolve_qwen_target_for_internal_mode_v1",
    "run_ask_data_deepseek_only_v1",
    "run_ask_data_dual_review_v1",
]
