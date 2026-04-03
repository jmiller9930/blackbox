"""Karpathy loop — full Anna analysis → execution_request → optional Jack paper (repeatable harness).

The supervisor daemon used to advance iterations and skill practice only; this module runs the same
path as Telegram: ``analyze_to_dict`` → ``try_create_execution_request_from_anna_analysis`` →
approve + ``run_execution`` so paper rows can append every tick when configured.

Env:
  ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK — default **1** (true): run harness each successful tick.
  ANNA_KARPATHY_AUTO_RUN_PAPER — default **1**: auto-approve + run_execution after a strategy signal.
  ANNA_KARPATHY_PAPER_APPROVER_ID — default ``karpathy-paper-harness``.
  ANNA_KARPATHY_HARNESS_PROMPT — override harness user text (iteration substituted if contains ``{iteration}``).
  ANNA_KARPATHY_HARNESS_USE_LLM — unset follows ANNA_USE_LLM; ``0``/``1`` forces off/on for harness only.

Requires for paper rows: ``BLACKBOX_JACK_EXECUTOR_CMD`` (and delegate enabled) like the E2E test.
"""

from __future__ import annotations

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
        return {
            "enabled": True,
            "iteration": iteration,
            "skipped": "analysis_preflight_blocked_body",
        }

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
        return {
            "enabled": True,
            "iteration": iteration,
            "skipped": "no_execution_request",
            "detail": "OBSERVATION_ONLY or signal policy blocked or auto-request off",
            "proposal_type": ptype,
        }

    rid = handoff.get("request_id")
    if not rid:
        return {"enabled": True, "iteration": iteration, "handoff": handoff, "skipped": "no_request_id"}

    if not _env_bool("ANNA_KARPATHY_AUTO_RUN_PAPER", True):
        return {
            "enabled": True,
            "iteration": iteration,
            "request_id": rid,
            "pending": True,
            "note": "ANNA_KARPATHY_AUTO_RUN_PAPER=0 — approve + run_execution manually",
        }

    jack = (os.environ.get("BLACKBOX_JACK_EXECUTOR_CMD") or "").strip()
    if not jack:
        return {
            "enabled": True,
            "iteration": iteration,
            "request_id": rid,
            "skipped": "BLACKBOX_JACK_EXECUTOR_CMD unset — cannot run Jack paper",
        }

    try:
        from execution_plane.approval_manager import approve_request
        from execution_plane.execution_engine import run_execution
    except Exception as e:  # noqa: BLE001
        return {"enabled": True, "request_id": rid, "error": f"import execution:{e}"}

    approver = (os.environ.get("ANNA_KARPATHY_PAPER_APPROVER_ID") or "karpathy-paper-harness").strip()
    approved = approve_request(str(rid), approver)
    if not approved:
        return {"enabled": True, "request_id": rid, "error": "approve_request returned None"}

    try:
        result = run_execution(str(rid))
    except Exception as e:  # noqa: BLE001
        return {"enabled": True, "request_id": rid, "error": f"run_execution:{e}"}

    jd = (result or {}).get("jack_delegate") or {}
    return {
        "enabled": True,
        "iteration": iteration,
        "request_id": rid,
        "execution_status": (result or {}).get("status"),
        "paper_logged": jd.get("paper_logged"),
        "jack_delegate": {"ok": jd.get("ok"), "error": jd.get("error")},
    }
