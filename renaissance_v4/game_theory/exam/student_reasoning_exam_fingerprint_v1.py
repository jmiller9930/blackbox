"""GT038 — Markdown appendix: Exam Result Summary (per scenario)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_exam_fingerprint_summary_md_v1(results: dict[str, Any], out_dir: Path) -> Path:
    """Writes ``exam_fingerprint_summary_v1.md`` under the exam runtime folder."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Exam Result Summary — Student Reasoning Quality Exam\n")
    lines.append(f"- **exam_id:** `{results.get('exam_id')}`")
    lines.append(f"- **schema:** `{results.get('schema')}`")
    lines.append("")
    lines.append("## Per scenario\n")
    for row in results.get("scenarios_v1") or []:
        sid = row.get("scenario_id")
        lines.append(f"### `{sid}`\n")
        g = row.get("grading_v1") or {}
        lines.append(
            f"- **final sealed action:** `{row.get('final_sealed_action_v1')}` · "
            f"**action_correct:** {g.get('action_correct')} · **hallucination:** {g.get('hallucination')}"
        )
        lines.append(
            f"- **state / memory / EV / risk / reasoning_quality:** "
            f"{g.get('state_alignment')} / {g.get('memory_alignment')} / {g.get('ev_alignment')} / "
            f"{g.get('risk_awareness')} / {g.get('reasoning_quality')}"
        )
        lines.append(f"- **no_trade_correct:** {g.get('no_trade_correct')}")
        lines.append(f"- **sealed_ok_v1:** {row.get('sealed_ok_v1')}")
        gp = row.get("gt041_proof_v1")
        if isinstance(gp, dict):
            lines.append(
                f"- **GT041 proof:** matched=`{gp.get('matched_count_v1')}` · "
                f"pattern_effect=`{gp.get('pattern_effect_to_score_v1')}` · "
                f"EV avail=`{gp.get('expected_value_available_v1')}` · "
                f"sample_count=`{gp.get('sample_count_v1')}` · "
                f"ev_adj=`{gp.get('ev_score_adjustment_v1')}` · "
                f"lane=`{gp.get('gt041_lane_v1')}`"
            )
        lines.append("")
    ga = results.get("gt041_acceptance_v1")
    if isinstance(ga, dict):
        lines.append("## GT_DIRECTIVE_041 acceptance\n")
        for k, v in ga.items():
            lines.append(f"- **{k}:** `{v}`")
        lines.append("")
    lines.append("## Raw scenario blob (embedded)\n")
    try:
        blob = json.dumps(results.get("scenarios_v1"), indent=2, ensure_ascii=False, default=str)
    except TypeError:
        blob = str(results.get("scenarios_v1"))
    lines.append("```json")
    lines.append(blob[:120000])
    lines.append("```\n")
    out = out_dir / "exam_fingerprint_summary_v1.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


__all__ = ["write_exam_fingerprint_summary_md_v1"]
