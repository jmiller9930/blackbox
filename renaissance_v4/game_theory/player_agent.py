"""
Player agent (orchestrator) — proposes scenario rows, fills *audit* narrative, runs Referee batch, emits report.

The Referee remains deterministic; this layer does **not** change scores. It exists so runs **explain themselves**
(operator-facing text tied to manifest, tier, and outcomes).

**Anna (LLM):** When enabled, reuses the same Ollama stack as Anna — ``scripts/runtime/_ollama.py`` +
``llm/local_llm_client.ollama_generate``. She writes **advisory** text: run summaries from Referee facts, and can
answer **operator questions** doc-grounded via ``agent_context_bundle`` (game spec, QUANT design, context_memory).
She does **not** judge WIN/LOSS or change scores. Enable with ``PLAYER_AGENT_USE_ANNA=1`` (default: follow
``ANNA_USE_LLM``). If ``ANNA_CONTEXT_PROFILE`` is unset/``none``, pattern-game calls default it to ``pattern_game``
so factual repo docs are loaded. CLI: ``--ask "…"`` for a standalone factual answer (no batch).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from renaissance_v4.game_theory.memory_paths import default_experience_log_jsonl, default_run_memory_jsonl
from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel
from renaissance_v4.game_theory.scenario_contract import extract_scenario_echo_fields, validate_scenarios

_GAME_THEORY = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _runtime_imports() -> tuple[Any, Any]:
    """Load Anna's Ollama helpers from ``scripts/runtime`` (same process as Anna)."""
    rt = str(_REPO_ROOT / "scripts" / "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    from _ollama import ollama_base_url
    from llm.local_llm_client import ollama_generate

    return ollama_base_url, ollama_generate


@contextlib.contextmanager
def _ensure_anna_pattern_game_context() -> Iterator[None]:
    """If ANNA_CONTEXT_PROFILE is empty/none, load ``pattern_game`` docs for factual answers."""
    key = "ANNA_CONTEXT_PROFILE"
    old = os.environ.get(key)
    v = (old or "").strip().lower()
    if v in ("", "none", "0", "false", "no"):
        os.environ[key] = "pattern_game"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old


def player_agent_use_anna_llm() -> bool:
    """Respect explicit PLAYER_AGENT_USE_ANNA; else mirror ANNA_USE_LLM (off in CI)."""
    v = os.environ.get("PLAYER_AGENT_USE_ANNA")
    if v is not None and str(v).strip() != "":
        return str(v).strip().lower() not in ("0", "false", "no")
    return os.environ.get("ANNA_USE_LLM", "1").strip().lower() not in ("0", "false", "no")


def anna_narrate_pattern_report(report_markdown: str, *, timeout: float = 180.0) -> tuple[str | None, str | None]:
    """
    Anna-style prose from **Referee facts** + **repo docs** (when context is enabled). Returns (text, error).

    Uses ``agent_context_bundle`` so indicator/game rules and context-vs-value guidance are available for
    **factual** explanations. Referee numbers must still come only from the facts block.
    """
    _scripts = str(_REPO_ROOT / "scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from agent_context_bundle import build_context_prefix

    with _ensure_anna_pattern_game_context():
        prefix = build_context_prefix(_REPO_ROOT)
    ollama_base_url, ollama_generate = _runtime_imports()
    base = ollama_base_url()
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    prompt = (
        prefix
        + "You are Anna — Trading Analyst (advisory).\n\n"
        + "**AUTHORITATIVE RULES**\n"
        + "- **REPOSITORY CONTEXT** (above): use for game rules, indicator *context* (regime/direction/transitions) vs raw values, single-silo scope, and the tide metaphor. Ground explanations there when possible.\n"
        + "- **REFEREE FACTS** (below): the **only** source for numeric outcomes (wins, losses, PnL, trades, checksums). Never invent or alter those numbers.\n"
        + "- If something is not in REPOSITORY CONTEXT, say it is not in the checked-in docs and avoid fabricating exchange-specific or broker-specific behavior.\n"
        + "- Do not claim live execution or production trading.\n\n"
        + "Write a short operator summary: what was tested, what outcomes suggest, sensible next hypotheses. "
        + "If the block shows failures, say so.\n\n"
        + "--- REFEREE FACTS ---\n"
        + report_markdown
    )
    res = ollama_generate(prompt, base_url=base, model=model, timeout=timeout)
    if res.error:
        return None, res.error
    return (res.text or None), None


def anna_answer_operator_question(question: str, *, timeout: float = 180.0) -> tuple[str | None, str | None]:
    """
    Standalone factual / conceptual answer for the operator (e.g. what an indicator *means* in this silo).

    Doc-grounded via ``agent_context_bundle``; does not run the Referee. Returns (text, error).
    """
    q = (question or "").strip()
    if not q:
        return None, "empty question"

    _scripts = str(_REPO_ROOT / "scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from agent_context_bundle import build_context_prefix

    with _ensure_anna_pattern_game_context():
        prefix = build_context_prefix(_REPO_ROOT)
    ollama_base_url, ollama_generate = _runtime_imports()
    base = ollama_base_url()
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    prompt = (
        prefix
        + "You are Anna — Trading Analyst (advisory). The operator asked a question about indicators, "
        + "context, or pattern-game rules.\n\n"
        + "**RULES**\n"
        + "- Answer from **REPOSITORY CONTEXT** when possible. Prefer definitions and metaphors that appear there (e.g. context around indicators vs raw numbers).\n"
        + "- If the answer is **not** in context, say clearly that it is not in the checked-in docs and do **not** invent firm-specific or market guarantees.\n"
        + "- Keep the answer concise and factual. No live-trading or execution claims.\n\n"
        + "--- OPERATOR QUESTION ---\n"
        + q
    )
    res = ollama_generate(prompt, base_url=base, model=model, timeout=timeout)
    if res.error:
        return None, res.error
    return (res.text or None), None


def propose_tier1_scenario(
    manifest_path: str | Path,
    *,
    scenario_id: str = "tier1_agent_default",
    partner_note: str = "",
) -> dict[str, Any]:
    """
    Build one Tier-1-shaped scenario dict (12-month *historical* window intent, not wall-clock runtime).
    """
    mp = str(manifest_path).strip()
    note = partner_note.strip()
    return {
        "scenario_id": scenario_id,
        "tier": "T1",
        "evaluation_window": {
            "calendar_months": 12,
            "referee_note": (
                "Historical bar window intent (simulation-time), not 12 months of real-world waiting."
            ),
        },
        "game_spec_ref": "GAME_SPEC_INDICATOR_PATTERN_V1.md",
        "manifest_path": mp,
        "training_trace_id": f"player_agent_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "agent_explanation": {
            "why_this_strategy": (
                note
                if note
                else "Tier-1 candidate: manifest defines entries/exits; Referee replays stored bars forward."
            ),
            "hypothesis": note if note else "",
            "indicator_context": {},
            "indicator_values": {},
            "learned": "(pending — compare to other trials in this trace)",
            "behavior_change": "(pending — link prior_scenario_id when curating)",
        },
    }


def ensure_agent_explanations(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure each scenario has an ``agent_explanation`` block (template if missing)."""
    out: list[dict[str, Any]] = []
    defaults = ("hypothesis", "indicator_context", "indicator_values", "learned", "behavior_change")
    for s in scenarios:
        n = dict(s)
        if not n.get("agent_explanation"):
            sid = n.get("scenario_id", "unknown")
            n["agent_explanation"] = {
                "why_this_strategy": (
                    f"Scenario {sid!r}: Referee will run one deterministic replay for manifest_path; "
                    "scores come only from replay outcomes."
                ),
                "hypothesis": "",
                "indicator_context": {},
                "indicator_values": {},
                "learned": "",
                "behavior_change": "",
            }
        else:
            ae = dict(n["agent_explanation"]) if isinstance(n["agent_explanation"], dict) else {}
            for key in defaults:
                if key == "indicator_context" and key not in ae:
                    ae[key] = {}
                elif key != "indicator_context" and key not in ae:
                    ae[key] = ""
            n["agent_explanation"] = ae
        out.append(n)
    return out


def markdown_operator_report(results: list[dict[str, Any]]) -> str:
    """Human-readable batch summary: scenario id, ok, key Referee stats, echoed agent fields."""
    lines: list[str] = [
        "# Player agent batch report",
        "",
        f"Generated (UTC): {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    for r in sorted(results, key=lambda x: str(x.get("scenario_id", ""))):
        sid = r.get("scenario_id", "?")
        lines.append(f"## {sid}")
        lines.append("")
        if not r.get("ok"):
            lines.append(f"- **Status:** failed — `{r.get('error', 'unknown')}`")
            lines.append("")
            continue
        summ = r.get("summary") or {}
        b = {k: summ.get(k) for k in ("wins", "losses", "trades", "win_rate", "cumulative_pnl")}
        lines.append(f"- **Referee:** wins={b.get('wins')} losses={b.get('losses')} trades={b.get('trades')} "
                       f"win_rate={b.get('win_rate')} pnl={b.get('cumulative_pnl')}")
        lines.append(f"- **Manifest:** `{r.get('manifest_path', '')}`")
        ae = r.get("agent_explanation")
        if isinstance(ae, dict):
            for key in ("hypothesis", "why_this_strategy", "learned", "behavior_change"):
                if ae.get(key):
                    lines.append(f"- **{key}:** {ae[key]}")
            ic = ae.get("indicator_context")
            if isinstance(ic, dict) and ic:
                lines.append(f"- **indicator_context:** `{json.dumps(ic, ensure_ascii=False)}`")
        echo = extract_scenario_echo_fields(r)
        if echo.get("training_trace_id"):
            lines.append(f"- **training_trace_id:** `{echo['training_trace_id']}`")
        lines.append("")
    lines.append(
        "_Referee scores are deterministic replays; this report echoes them next to agent/story fields._"
    )
    return "\n".join(lines)


def _resolve_run_memory_log_path(
    explicit: Path | str | None,
) -> Path | None:
    if explicit is not None:
        s = str(explicit).strip()
        if not s:
            return None
        if s in ("default", "1"):
            return default_run_memory_jsonl()
        return Path(s).expanduser()
    env = os.environ.get("RUN_MEMORY_LOG")
    if not env or not str(env).strip():
        return None
    return _resolve_run_memory_log_path(env)


def run_player_batch(
    scenarios: list[dict[str, Any]],
    *,
    max_workers: int | None = None,
    experience_log_path: Path | str | None = None,
    run_memory_log_path: Path | str | None = None,
    write_session_logs: bool = True,
    session_logs_base: Path | str | None = None,
    fill_missing_explanations: bool = True,
    with_anna: bool | None = None,
) -> dict[str, Any]:
    """
    Run parallel batch; optionally fill missing ``agent_explanation``; return results + markdown report.

    ``with_anna``: ``None`` = use env (``PLAYER_AGENT_USE_ANNA`` / ``ANNA_USE_LLM``); ``True``/``False`` = force.
    When on, appends Anna's Ollama narrative (same stack as ``scripts/runtime`` Anna) — **advisory text only**.
    """
    if fill_missing_explanations:
        scenarios = ensure_agent_explanations(scenarios)
    req_hyp = os.environ.get("PATTERN_GAME_REQUIRE_HYPOTHESIS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if req_hyp:
        ok, msgs = validate_scenarios(scenarios, require_hypothesis=True)
        if not ok:
            raise ValueError(msgs[0] if msgs else "scenario validation failed")
    rmem = _resolve_run_memory_log_path(run_memory_log_path)
    results = run_scenarios_parallel(
        scenarios,
        max_workers=max_workers,
        experience_log_path=experience_log_path,
        run_memory_log_path=rmem,
        write_session_logs=write_session_logs,
        session_logs_base=session_logs_base,
    )
    md = markdown_operator_report(results)
    anna_text: str | None = None
    anna_err: str | None = None
    do_anna = with_anna if with_anna is not None else player_agent_use_anna_llm()
    if do_anna:
        anna_text, anna_err = anna_narrate_pattern_report(md)
        if anna_text:
            md += "\n\n## Anna — operator narrative\n" + anna_text + "\n"
        elif anna_err:
            md += "\n\n## Anna — LLM unavailable\n`" + anna_err + "`\n"
    return {
        "results": results,
        "report_markdown": md,
        "anna_narrative": anna_text,
        "anna_error": anna_err,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Player agent: run scenario batch + print markdown report")
    p.add_argument(
        "scenarios_json",
        nargs="?",
        help="JSON file (array of scenarios); required unless --proposal-only",
    )
    p.add_argument("-j", "--jobs", type=int, default=None, help="Parallel workers")
    p.add_argument(
        "--log",
        type=str,
        default=None,
        help="Append JSONL (use 'default' for game_theory/experience_log.jsonl)",
    )
    p.add_argument(
        "--run-memory",
        type=str,
        default=None,
        nargs="?",
        const="default",
        help="Append structured run_memory JSONL (default path: game_theory/run_memory.jsonl); or set RUN_MEMORY_LOG",
    )
    p.add_argument(
        "--proposal-only",
        action="store_true",
        help="Print one Tier-1 proposal JSON and exit (no run)",
    )
    p.add_argument(
        "--manifest",
        type=str,
        default="renaissance_v4/configs/manifests/baseline_v1_recipe.json",
        help="With --proposal-only: manifest path",
    )
    p.add_argument(
        "--anna",
        action="store_true",
        help="After batch, call Anna (Ollama) for operator narrative from Referee facts",
    )
    p.add_argument(
        "--no-anna",
        action="store_true",
        help="Skip Anna narrative even if env would enable it",
    )
    p.add_argument(
        "--no-session-log",
        action="store_true",
        help="Skip logs/batch_<UTC>_<id>/ per-scenario HUMAN_READABLE.md (default: session logs ON)",
    )
    p.add_argument(
        "--session-logs-root",
        type=str,
        default=None,
        help="Base directory for batch session folders (default: game_theory/logs)",
    )
    p.add_argument(
        "--ask",
        type=str,
        default=None,
        metavar="QUESTION",
        help="Ask Anna a doc-grounded question (Ollama); no scenario batch. Sets repo context to pattern_game.",
    )
    args = p.parse_args()

    if args.ask:
        if args.scenarios_json:
            raise SystemExit("Use either --ask or scenarios_json, not both")
        if args.proposal_only:
            raise SystemExit("Use either --ask or --proposal-only, not both")
        os.environ.setdefault("REPO_ROOT", str(_REPO_ROOT.resolve()))
        text, err = anna_answer_operator_question(args.ask)
        if err:
            raise SystemExit(err)
        print(text or "")
        return

    if args.proposal_only:
        prop = propose_tier1_scenario(args.manifest)
        print(json.dumps(prop, indent=2))
        return

    if not args.scenarios_json:
        p.error("scenarios_json required (or use --proposal-only)")

    path = Path(args.scenarios_json)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "scenarios" in raw:
        scenarios = raw["scenarios"]
    else:
        scenarios = raw
    if not isinstance(scenarios, list):
        raise SystemExit("JSON must be an array of scenarios")
    scenarios = [x for x in scenarios if isinstance(x, dict)]

    log_path: Path | None = None
    if args.log == "1" or args.log == "default":
        log_path = default_experience_log_jsonl()
    elif args.log:
        log_path = Path(args.log)

    run_mem: Path | str | None = args.run_memory

    if args.anna and args.no_anna:
        raise SystemExit("Use only one of --anna / --no-anna")
    with_anna: bool | None = None
    if args.anna:
        with_anna = True
    elif args.no_anna:
        with_anna = False

    sl_root = Path(args.session_logs_root).expanduser() if args.session_logs_root else None
    out = run_player_batch(
        scenarios,
        max_workers=args.jobs,
        experience_log_path=log_path,
        run_memory_log_path=run_mem,
        write_session_logs=not args.no_session_log,
        session_logs_base=sl_root,
        with_anna=with_anna,
    )
    print(out["report_markdown"])
    print()
    print("--- raw JSON summary ---")
    print(json.dumps({"ok_count": sum(1 for r in out["results"] if r.get("ok")), "results": out["results"]}, indent=2))


if __name__ == "__main__":
    main()
