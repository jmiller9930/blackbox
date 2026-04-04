"""Karpathy loop — full Anna analysis → execution_request → optional Jack paper (repeatable harness).

The supervisor daemon used to advance iterations and skill practice only; this module runs the same
path as Telegram: ``analyze_to_dict`` → ``try_create_execution_request_from_anna_analysis`` →
approve + ``run_execution`` so paper rows can append every tick when configured.

Env:
  ANNA_KARPATHY_DISABLE_LAB_WIRE_JACK — if ``1``/true: keep ``OBSERVATION_ONLY`` (no execution_request from
    observational classification). **Default is off** — thin analyses map to ``CONDITION_TIGHTENING`` so the
    base harness can create a pending request. ``ANNA_KARPATHY_LAB_WIRE_JACK=0`` is an alias for the same opt-out.
    Still need ``BLACKBOX_JACK_EXECUTOR_CMD`` **or** ``ANNA_KARPATHY_JACK_STUB=1`` for ``run_execution`` → Jack paper.
  ANNA_KARPATHY_JACK_STUB — if ``1``/true and ``BLACKBOX_JACK_EXECUTOR_CMD`` is unset, use
    ``scripts/runtime/jack_paper_bump_stub.py`` (deterministic paper row; lab / agents without a real Jupiter Jack).
  ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK — default **1** (true): run harness each successful tick.
  ANNA_KARPATHY_AUTO_RUN_PAPER — default **1**: auto-approve + run_execution after a strategy signal.
  ANNA_KARPATHY_PAPER_APPROVER_ID — default ``karpathy-paper-harness``.
  ANNA_KARPATHY_HARNESS_PROMPT — override harness user text (iteration substituted if contains ``{iteration}``).
  ANNA_KARPATHY_HARNESS_USE_LLM — unset follows ANNA_USE_LLM; ``0``/``1`` forces off/on for harness only.

Requires for paper rows: ``BLACKBOX_JACK_EXECUTOR_CMD`` **or** ``ANNA_KARPATHY_JACK_STUB=1`` (and delegate enabled).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def _runtime_scripts() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "runtime"


def _ensure_runtime_path() -> None:
    rt = _runtime_scripts()
    if str(rt) not in sys.path:
        sys.path.insert(0, str(rt))


def analysis_snapshot_for_dashboard(analysis: dict[str, Any]) -> dict[str, Any]:
    """Compact, JSON-safe slice of ``anna_analysis_v1`` for operator dashboards (data, not prose)."""
    interp = analysis.get("interpretation") if isinstance(analysis.get("interpretation"), dict) else {}
    pipe = analysis.get("pipeline") if isinstance(analysis.get("pipeline"), dict) else {}
    mc = analysis.get("market_context") if isinstance(analysis.get("market_context"), dict) else {}
    risk = analysis.get("risk_assessment") if isinstance(analysis.get("risk_assessment"), dict) else {}
    sug = analysis.get("suggested_action") if isinstance(analysis.get("suggested_action"), dict) else {}
    hi = analysis.get("human_intent") if isinstance(analysis.get("human_intent"), dict) else {}
    cum = analysis.get("cumulative_learning") if isinstance(analysis.get("cumulative_learning"), dict) else {}

    summary = str(interp.get("summary") or "")
    if len(summary) > 800:
        summary = summary[:797] + "..."

    factors = risk.get("factors") or []
    if isinstance(factors, list):
        factors_out = [str(x)[:160] for x in factors[:10]]
    else:
        factors_out = []

    notes = analysis.get("notes")
    if isinstance(notes, list):
        note_lines = [str(x)[:240] for x in notes[:6]]
    else:
        note_lines = []

    sig = interp.get("signals") if isinstance(interp.get("signals"), list) else []
    sig_out = [str(x) for x in sig[:12]]

    steps = pipe.get("steps")
    if not isinstance(steps, list):
        steps = []

    pol = analysis.get("policy_alignment") if isinstance(analysis.get("policy_alignment"), dict) else {}
    concepts = analysis.get("concepts_used")
    if isinstance(concepts, list):
        concepts_out = [str(c) for c in concepts[:16]]
    else:
        concepts_out = []

    sa = analysis.get("strategy_awareness")
    sa_detected: list[str] = []
    sa_expl = ""
    sa_risks: list[str] = []
    if isinstance(sa, dict):
        det = sa.get("detected")
        if isinstance(det, list):
            sa_detected = [str(x) for x in det[:12]]
        sa_expl = str(sa.get("explanation") or "")[:700]
        rs = sa.get("risks")
        if isinstance(rs, list):
            sa_risks = [str(x) for x in rs[:8]]

    sig_snap = analysis.get("signal_snapshot")
    sig_line = ""
    if isinstance(sig_snap, dict):
        sig_line = json.dumps(sig_snap, ensure_ascii=False)[:900]
    elif sig_snap is not None:
        sig_line = str(sig_snap)[:500]

    me = analysis.get("math_engine")
    me_line = ""
    if isinstance(me, dict):
        me_line = json.dumps(me, ensure_ascii=False)[:600]
    elif me is not None:
        me_line = str(me)[:400]

    return {
        "generated_at": analysis.get("generated_at"),
        "answer_source": pipe.get("answer_source"),
        "pipeline_steps": [str(s) for s in steps],
        "interpretation_headline": interp.get("headline"),
        "interpretation_summary": summary,
        "risk_level": risk.get("level"),
        "risk_factors": factors_out,
        "suggested_intent": sug.get("intent"),
        "suggested_rationale": (str(sug.get("rationale") or ""))[:500],
        "market_price": mc.get("price"),
        "market_spread": mc.get("spread"),
        "market_notes_count": len(mc.get("notes") or []) if isinstance(mc.get("notes"), list) else 0,
        "regime": analysis.get("regime"),
        "human_intent": {k: hi.get(k) for k in ("kind", "label", "confidence") if hi.get(k) is not None},
        "curriculum_stage": cum.get("stage"),
        "cumulative_log_entries": cum.get("cumulative_log_entries"),
        "interpretation_signals": sig_out,
        "analysis_notes_tail": note_lines,
        "concepts_used": concepts_out,
        "policy_guardrail_mode": pol.get("guardrail_mode") or pol.get("mode"),
        "policy_alignment": pol.get("alignment"),
        "strategy_playbook_applied": bool(analysis.get("strategy_playbook_applied")),
        "strategy_concepts_detected": sa_detected,
        "strategy_explanation": sa_expl,
        "strategy_risks": sa_risks,
        "trading_core_signal_snapshot": sig_line,
        "math_engine_snapshot": me_line,
    }


def _with_analysis_snapshot(analysis: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    snap = analysis_snapshot_for_dashboard(analysis)
    if snap:
        out["analysis_snapshot"] = snap
    return out


def run_karpathy_paper_harness_tick(*, iteration: int) -> dict[str, Any]:
    """
    One full paper harness attempt. Safe to call when preflight already passed for the daemon tick.

    Returns a JSON-serializable dict stored on state as ``karpathy_last_paper_harness``.
    """
    if not _env_bool("ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK", True):
        return {"enabled": False, "reason": "ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK=0"}

    _ensure_runtime_path()

    from _paths import default_sqlite_path
    from anna_analyst_v1 import analyze_to_dict
    from execution_plane.anna_signal_execution import try_create_execution_request_from_anna_analysis

    tmpl = (os.environ.get("ANNA_KARPATHY_HARNESS_PROMPT") or "").strip()
    if tmpl:
        try:
            prompt = tmpl.format(iteration=iteration)
        except (KeyError, IndexError):
            prompt = tmpl
    else:
        prompt = (
            f"[Karpathy paper harness tick {iteration}] SOL-PERP Grade-12 paper: "
            "Use live market tick + FACTs. State risk (low/medium/high), guardrail mode, and whether "
            "a paper-trade evaluation is warranted. If data supports a directional or risk-reduction "
            "posture, say so clearly — we need a non-observation strategy signal when justified."
        )

    use_llm: bool | None = None
    raw_llm = (os.environ.get("ANNA_KARPATHY_HARNESS_USE_LLM") or "").strip().lower()
    if raw_llm in ("0", "false", "no"):
        use_llm = False
    elif raw_llm in ("1", "true", "yes"):
        use_llm = True

    db_path = default_sqlite_path()
    try:
        out = analyze_to_dict(
            db_path,
            prompt,
            use_snapshot=True,
            use_ctx=True,
            use_trend=False,
            use_policy=True,
            store=False,
            use_llm=use_llm,
            skip_preflight=True,
        )
    except Exception as e:  # noqa: BLE001
        return {"enabled": True, "error": f"analyze_to_dict:{e}", "iteration": iteration}

    analysis = out.get("anna_analysis") or {}
    pipe = analysis.get("pipeline") or {}
    if pipe.get("answer_source") == "preflight_blocked":
        return _with_analysis_snapshot(
            analysis,
            {
                "enabled": True,
                "iteration": iteration,
                "skipped": "analysis_preflight_blocked_body",
            },
        )

    handoff = try_create_execution_request_from_anna_analysis(
        analysis,
        source_task_id=None,
        extra_notes=[f"karpathy_paper_harness iteration={iteration}"],
    )

    if not handoff:
        from anna_modules.proposal import assemble_anna_proposal_v1

        try:
            prop = assemble_anna_proposal_v1(analysis, source_task_id=None, extra_notes=[])
            ptype = prop.get("proposal_type")
        except Exception:
            ptype = None
        return _with_analysis_snapshot(
            analysis,
            {
                "enabled": True,
                "iteration": iteration,
                "skipped": "no_execution_request",
                "detail": "OBSERVATION_ONLY or signal policy blocked or auto-request off",
                "proposal_type": ptype,
            },
        )

    rid = handoff.get("request_id")
    if not rid:
        return _with_analysis_snapshot(
            analysis,
            {"enabled": True, "iteration": iteration, "handoff": handoff, "skipped": "no_request_id"},
        )

    if not _env_bool("ANNA_KARPATHY_AUTO_RUN_PAPER", True):
        return _with_analysis_snapshot(
            analysis,
            {
                "enabled": True,
                "iteration": iteration,
                "request_id": rid,
                "pending": True,
                "note": "ANNA_KARPATHY_AUTO_RUN_PAPER=0 — approve + run_execution manually",
            },
        )

    jack = (os.environ.get("BLACKBOX_JACK_EXECUTOR_CMD") or "").strip()
    if not jack and _env_bool("ANNA_KARPATHY_JACK_STUB", False):
        stub = _runtime_scripts() / "jack_paper_bump_stub.py"
        if stub.is_file():
            jack = f"{sys.executable} {stub}"
    if not jack:
        return _with_analysis_snapshot(
            analysis,
            {
                "enabled": True,
                "iteration": iteration,
                "request_id": rid,
                "skipped": "BLACKBOX_JACK_EXECUTOR_CMD unset — set it or ANNA_KARPATHY_JACK_STUB=1 (lab bump stub)",
            },
        )

    try:
        from execution_plane.approval_manager import approve_request
        from execution_plane.execution_engine import run_execution
    except Exception as e:  # noqa: BLE001
        return _with_analysis_snapshot(
            analysis,
            {"enabled": True, "request_id": rid, "error": f"import execution:{e}"},
        )

    approver = (os.environ.get("ANNA_KARPATHY_PAPER_APPROVER_ID") or "karpathy-paper-harness").strip()
    approved = approve_request(str(rid), approver)
    if not approved:
        return _with_analysis_snapshot(
            analysis,
            {"enabled": True, "request_id": rid, "error": "approve_request returned None"},
        )

    prev_jack = os.environ.get("BLACKBOX_JACK_EXECUTOR_CMD")
    try:
        # ``maybe_delegate_to_jack`` reads ``BLACKBOX_JACK_EXECUTOR_CMD`` from the environment.
        if jack:
            os.environ["BLACKBOX_JACK_EXECUTOR_CMD"] = jack
        try:
            result = run_execution(str(rid))
        except Exception as e:  # noqa: BLE001
            return _with_analysis_snapshot(
                analysis,
                {"enabled": True, "request_id": rid, "error": f"run_execution:{e}"},
            )
    finally:
        if prev_jack is None:
            os.environ.pop("BLACKBOX_JACK_EXECUTOR_CMD", None)
        else:
            os.environ["BLACKBOX_JACK_EXECUTOR_CMD"] = prev_jack

    jd = (result or {}).get("jack_delegate") or {}
    return _with_analysis_snapshot(
        analysis,
        {
            "enabled": True,
            "iteration": iteration,
            "request_id": rid,
            "execution_status": (result or {}).get("status"),
            "paper_logged": jd.get("paper_logged"),
            "jack_delegate": {"ok": jd.get("ok"), "error": jd.get("error")},
        },
    )
