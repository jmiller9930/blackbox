"""
Deterministic **hunter batch suggestions** from pattern-game **memory** (scorecard + retrospective).

This is not Referee ground truth and not an LLM oracle. It builds **distinct** parallel scenarios
(ATR geometry on the same manifest) so the next run is not an accidental repeat of the last paste.
Retrospective text steers **tight** vs **wide** grids; scorecard/history length rotates the ladder
so repeated clicks do not emit identical JSON forever.

Schema: ``hunter_suggestion_v1`` on the top-level response when used from the web API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.batch_scorecard import read_batch_scorecard_recent
from renaissance_v4.game_theory.memory_paths import (
    default_batch_scorecard_jsonl,
    default_retrospective_log_jsonl,
)
from renaissance_v4.game_theory.retrospective_log import read_retrospective_recent

SCHEMA_V1 = "hunter_suggestion_v1"
DEFAULT_MANIFEST_REL = "renaissance_v4/configs/manifests/baseline_v1_recipe.json"


def resolve_repo_root(candidate: Path | None = None) -> Path:
    """Repository root (contains ``renaissance_v4/``)."""
    if candidate is not None:
        return candidate.expanduser().resolve()
    env = os.environ.get("PATTERN_GAME_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    # renaissance_v4/game_theory -> blackbox
    return Path(__file__).resolve().parent.parent.parent


def _bias_from_retrospective(rows: list[dict[str, Any]]) -> str:
    """Return ``tight``, ``wide``, or ``neutral`` from latest operator notes."""
    if not rows:
        return "neutral"
    r0 = rows[0]
    blob = f"{r0.get('what_to_try_next', '')} {r0.get('what_observed', '')}".lower()
    tight_hits = (
        "tight",
        "narrow",
        "smaller stop",
        "cut loss",
        "tighter",
        "reduce risk",
    )
    wide_hits = ("wide", "loose", "let run", "bigger target", "trail", "wider", "give room")
    if any(h in blob for h in tight_hits) and not any(h in blob for h in wide_hits):
        return "tight"
    if any(h in blob for h in wide_hits) and not any(h in blob for h in tight_hits):
        return "wide"
    return "neutral"


def _round_index(
    *,
    score_rows: list[dict[str, Any]],
    retro_rows: list[dict[str, Any]],
) -> int:
    """Rotate ladder so successive batches get different scenario_id sets."""
    n = len(score_rows) + len(retro_rows)
    return int(n % 3)


# (scenario_id_suffix, atr_stop, atr_target, hypothesis one-liner) — None,None = baseline only
_ROUND_PRESETS: tuple[tuple[tuple[str, float | None, float | None, str], ...], ...] = (
    (
        ("baseline_default", None, None, "Reference recipe ATR from manifest (baseline for this ladder)."),
        ("ladder_tight", 1.5, 2.5, "Tighter multiples 1.5 / 2.5 vs baseline on this tape."),
        ("ladder_wide", 2.5, 4.0, "Wider multiples 2.5 / 4.0 to let winners run vs ladder_tight."),
        ("ladder_mid", 2.0, 3.5, "Mid ladder 2.0 / 3.5 between tight and wide."),
    ),
    (
        ("baseline_default", None, None, "Reference recipe ATR from manifest (baseline for this ladder)."),
        ("ladder_xs", 1.25, 2.0, "Aggressive tight 1.25 / 2.0 — explore stop sensitivity."),
        ("ladder_xl", 3.0, 5.0, "Loose 3.0 / 5.0 — explore tail behavior vs xs."),
        ("ladder_bridge", 2.25, 3.75, "Bridge 2.25 / 3.75 between xs and xl."),
    ),
    (
        ("baseline_default", None, None, "Reference recipe ATR from manifest (baseline for this ladder)."),
        ("ladder_scalp", 1.75, 2.75, "Scalp-leaning 1.75 / 2.75."),
        ("ladder_swing", 2.75, 4.25, "Swing-leaning 2.75 / 4.25."),
        ("ladder_asym", 1.5, 3.5, "Asymmetric 1.5 stop / 3.5 target vs symmetric ladders."),
    ),
)


def _adjust_round_for_bias(round_idx: int, bias: str) -> int:
    if bias == "tight":
        return 1  # round 1 has the smallest stops on average
    if bias == "wide":
        return 2  # round 2 emphasizes wider geometry
    return round_idx


def _single_scenario_streak(cards: list[dict[str, Any]], depth: int = 6) -> bool:
    """True if recent successful batches only ran one scenario each."""
    chunk = cards[:depth]
    if len(chunk) < 3:
        return False
    for c in chunk:
        if c.get("status") != "done":
            continue
        ts = c.get("total_scenarios")
        if ts != 1:
            return False
    return len([c for c in chunk if c.get("status") == "done"]) >= 3


def _build_scenario_dict(
    manifest_rel: str,
    suffix: str,
    atr_stop: float | None,
    atr_target: float | None,
    hyp_line: str,
    *,
    ladder_round: int,
    memory_tag: str,
) -> dict[str, Any]:
    hyp = f"[{memory_tag}] {hyp_line}"
    base: dict[str, Any] = {
        "scenario_id": f"hunt_r{ladder_round}_{suffix}",
        "manifest_path": manifest_rel,
        "agent_explanation": {
            "hypothesis": hyp,
            "why_this_strategy": "Suggested by hunter planner from memory + bounded ATR ladder (not Referee truth).",
            "indicator_values": {},
            "learned": "",
            "behavior_change": "",
        },
    }
    if atr_stop is not None and atr_target is not None:
        base["atr_stop_mult"] = atr_stop
        base["atr_target_mult"] = atr_target
    return base


def build_hunter_suggestion(
    *,
    repo_root: Path | None = None,
    scorecard_path: Path | None = None,
    retrospective_path: Path | None = None,
    manifest_rel: str | None = None,
) -> dict[str, Any]:
    """
    Build parallel-scenario JSON (list of dicts) plus rationale and warnings.

    ``repo_root`` defaults to parent of ``renaissance_v4`` containing this package.
    """
    root = resolve_repo_root(repo_root)
    mrel = manifest_rel or DEFAULT_MANIFEST_REL
    mp = root / mrel
    if not mp.is_file():
        return {
            "schema": SCHEMA_V1,
            "ok": False,
            "error": f"Manifest not found under repo: {mrel}",
            "repo_root": str(root),
        }

    sp = scorecard_path or default_batch_scorecard_jsonl()
    rp = retrospective_path or default_retrospective_log_jsonl()
    cards = read_batch_scorecard_recent(120, path=sp)
    retro = read_retrospective_recent(80, path=rp)

    bias = _bias_from_retrospective(retro)
    base_round = _round_index(score_rows=cards, retro_rows=retro)
    eff_round = _adjust_round_for_bias(base_round, bias)
    presets = _ROUND_PRESETS[eff_round % len(_ROUND_PRESETS)]

    mem_tag = "memory"
    if retro:
        mem_tag = "memory+retro"
    elif cards:
        mem_tag = "memory+scorecard"

    scenarios: list[dict[str, Any]] = []
    for suffix, ast, att, hyp in presets:
        scenarios.append(
            _build_scenario_dict(
                mrel,
                suffix,
                ast,
                att,
                hyp,
                ladder_round=eff_round,
                memory_tag=mem_tag,
            )
        )

    warnings: list[str] = []
    if not retro:
        warnings.append(
            "No retrospective lines yet — steering is scorecard rotation + keyword pass only; "
            "append retrospective after runs for tighter/wider hints."
        )
    if _single_scenario_streak(cards):
        warnings.append(
            "Recent batches look like single-scenario streaks — this suggestion uses four distinct "
            "geometries to explore the ladder in one parallel batch."
        )

    rationale_lines = [
        "### Hunter suggestion (deterministic)",
        "",
        f"- **Repo**: `{root}`",
        f"- **Manifest**: `{mrel}`",
        f"- **Ladder round**: {eff_round} (base rotation {base_round}, retrospective bias **{bias}**).",
        f"- **Scorecard lines read**: {len(cards)} · **Retrospective lines read**: {len(retro)}.",
        "",
    ]
    if retro:
        r0 = retro[0]
        rationale_lines.append(
            f"- Latest retrospective ({r0.get('utc', '?')}): "
            f"observed “{(str(r0.get('what_observed', ''))[:200])}…” → "
            f"try “{(str(r0.get('what_to_try_next', ''))[:200])}…”"
        )
    if cards:
        c0 = cards[0]
        rationale_lines.append(
            f"- Latest batch scorecard: status={c0.get('status')} "
            f"processed={c0.get('total_processed')}/{c0.get('total_scenarios')} "
            f"ok={c0.get('ok_count')} fail={c0.get('failed_count')}."
        )
    rationale_lines.append("")
    rationale_lines.append(
        "Referee replay remains the ground truth for outcomes; this planner only diversifies "
        "the next experiment from **memory**, not predictions."
    )
    rationale = "\n".join(rationale_lines)

    return {
        "schema": SCHEMA_V1,
        "ok": True,
        "repo_root": str(root),
        "manifest_path": mrel,
        "bias": bias,
        "ladder_round": eff_round,
        "ladder_round_base": base_round,
        "scenarios": scenarios,
        "rationale_markdown": rationale,
        "warnings": warnings,
        "memory": {
            "scorecard_path": str(sp.resolve()),
            "retrospective_path": str(rp.resolve()),
            "scorecard_entries_used": len(cards),
            "retrospective_entries_used": len(retro),
        },
    }


def main() -> None:
    import argparse
    import json as json_mod

    ap = argparse.ArgumentParser(description="Print hunter suggestion JSON from memory.")
    ap.add_argument("--repo", type=Path, default=None, help="Repo root (default: auto)")
    args = ap.parse_args()
    out = build_hunter_suggestion(repo_root=args.repo)
    print(json_mod.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
