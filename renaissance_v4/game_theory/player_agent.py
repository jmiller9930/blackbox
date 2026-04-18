"""
Player agent (orchestrator) — proposes scenario rows, fills *audit* narrative, runs Referee batch, emits report.

The Referee remains deterministic; this layer does **not** change scores. It exists so runs **explain themselves**
(operator-facing text tied to manifest, tier, and outcomes).

Optional future: plug ``narrative_llm_hook`` to rewrite ``agent_explanation`` prose (must still cite Referee facts).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel
from renaissance_v4.game_theory.scenario_contract import extract_scenario_echo_fields

_GAME_THEORY = Path(__file__).resolve().parent


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
            "indicator_values": {},
            "learned": "(pending — compare to other trials in this trace)",
            "behavior_change": "(pending — link prior_scenario_id when curating)",
        },
    }


def ensure_agent_explanations(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure each scenario has an ``agent_explanation`` block (template if missing)."""
    out: list[dict[str, Any]] = []
    for s in scenarios:
        n = dict(s)
        if not n.get("agent_explanation"):
            sid = n.get("scenario_id", "unknown")
            n["agent_explanation"] = {
                "why_this_strategy": (
                    f"Scenario {sid!r}: Referee will run one deterministic replay for manifest_path; "
                    "scores come only from replay outcomes."
                ),
                "indicator_values": {},
                "learned": "",
                "behavior_change": "",
            }
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
            for key in ("why_this_strategy", "learned", "behavior_change"):
                if ae.get(key):
                    lines.append(f"- **{key}:** {ae[key]}")
        echo = extract_scenario_echo_fields(r)
        if echo.get("training_trace_id"):
            lines.append(f"- **training_trace_id:** `{echo['training_trace_id']}`")
        lines.append("")
    lines.append(
        "_Referee scores are deterministic replays; this report echoes them next to agent/story fields._"
    )
    return "\n".join(lines)


def run_player_batch(
    scenarios: list[dict[str, Any]],
    *,
    max_workers: int | None = None,
    experience_log_path: Path | str | None = None,
    fill_missing_explanations: bool = True,
) -> dict[str, Any]:
    """
    Run parallel batch; optionally fill missing ``agent_explanation``; return results + markdown report.
    """
    if fill_missing_explanations:
        scenarios = ensure_agent_explanations(scenarios)
    results = run_scenarios_parallel(
        scenarios,
        max_workers=max_workers,
        experience_log_path=experience_log_path,
    )
    return {
        "results": results,
        "report_markdown": markdown_operator_report(results),
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
    args = p.parse_args()

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
        log_path = _GAME_THEORY / "experience_log.jsonl"
    elif args.log:
        log_path = Path(args.log)

    out = run_player_batch(scenarios, max_workers=args.jobs, experience_log_path=log_path)
    print(out["report_markdown"])
    print()
    print("--- raw JSON summary ---")
    print(json.dumps({"ok_count": sum(1 for r in out["results"] if r.get("ok")), "results": out["results"]}, indent=2))


if __name__ == "__main__":
    main()
