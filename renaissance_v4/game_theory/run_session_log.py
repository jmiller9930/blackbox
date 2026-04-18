"""
run_session_log.py

Per-run filesystem artifacts: unique folder under ``logs/``, human-readable Markdown,
machine JSON copy, explicit decision/memory audit (operators review offline).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.context_memory import TIDE_METAPHOR
from renaissance_v4.game_theory.memory_paths import default_logs_root

_GAME_THEORY = Path(__file__).resolve().parent


def allocate_unique_run_directory(
    *,
    logs_root: Path | None = None,
    prefix: str = "run",
) -> Path:
    """Create ``logs_root / f\"{prefix}_<UTC>_<8 hex>\"`` and return it."""
    base = logs_root if logs_root is not None else default_logs_root()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    d = Path(base) / f"{prefix}_{ts}_{short}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_segment(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())[:120]
    return s or "scenario"


def render_human_readable_markdown(record: dict[str, Any]) -> str:
    """Operator-facing narrative from one ``build_run_memory_record`` dict."""
    da = record.get("decision_audit") or {}
    ref = record.get("referee") or {}
    pm = record.get("post_mortem") or {}
    hyp = record.get("hypothesis")
    ctx = record.get("indicator_context")
    lines: list[str] = []

    lines.append("# Pattern game — run report (human-readable)")
    lines.append("")
    lines.append(f"- **run_id:** `{record.get('run_id')}`")
    lines.append(f"- **UTC:** {record.get('utc')}")
    lines.append(f"- **source:** `{record.get('source')}`")
    lines.append("")

    lines.append("## What actually ran")
    lines.append("")
    lines.append(
        "The **Referee** is a deterministic forward replay: it does not “decide” like a learned policy. "
        "It applies **fixed rules** from your manifest and engine to historical bars. "
        "Below is exactly what was on the ticket for this run."
    )
    lines.append("")
    lines.append(f"- **Manifest path:** `{record.get('manifest_path')}`")
    sha = record.get("manifest_sha256")
    lines.append(f"- **Manifest SHA-256:** `{sha}`" if sha else "- **Manifest SHA-256:** *(file not found at record time)*")
    atr_s = record.get("atr_stop_mult")
    atr_t = record.get("atr_target_mult")
    if atr_s is not None or atr_t is not None:
        lines.append(
            f"- **ATR overrides (CLI / scenario):** stop_mult={atr_s!r}, target_mult={atr_t!r} "
            "(these override manifest values for this replay only when set)."
        )
    else:
        lines.append("- **ATR overrides:** none — values came from the manifest / catalog defaults.")
    lines.append("")

    lines.append("## Hypothesis & indicator context (what you said you were testing)")
    lines.append("")
    if hyp:
        lines.append(f"> {hyp}")
    else:
        lines.append("*(No hypothesis string was supplied for this run.)*")
    lines.append("")
    if isinstance(ctx, dict) and ctx:
        lines.append("Structured **indicator_context** (direction, regime, transitions — not raw numbers alone):")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(ctx, indent=2, ensure_ascii=False))
        lines.append("```")
    else:
        lines.append("*No structured indicator_context was supplied.*")
    lines.append("")
    iq = record.get("indicator_context_quality") or {}
    lvl = iq.get("level", "")
    lines.append("### Single-silo memory (not the universe)")
    lines.append("")
    lines.append(
        "Retrieval here is **one silo**: pattern-game replay + what you attach — **not** general RAG over "
        "the world. What must persist is **context around indicators** (regime, direction, transition, "
        "velocity). Without that, you only store **noise**."
    )
    lines.append("")
    lines.append(f"> {TIDE_METAPHOR}")
    lines.append("")
    if iq:
        lines.append(
            f"- **Context quality (raw, this run):** `{lvl}` "
            f"(signal keys matched: {iq.get('matched_signal_keys', [])})"
        )
        if iq.get("warn") and lvl in ("missing", "noise_risk", "thin"):
            lines.append("- **Warning:** Context is thin or absent — review before promoting any “memory.”")
    lines.append("")

    has_lme = "learning_memory_evidence" in record
    lme = record.get("learning_memory_evidence") or {}
    ol = lme.get("operator_labels") or {}
    lines.append("## Learning / Memory Evidence (operator drill-down)")
    lines.append("")
    if not has_lme:
        lines.append(
            "*This `run_record` predates the `learning_memory_evidence` field; re-run the scenario with "
            "a current `game_theory` runner to populate this section.*"
        )
        lines.append("")
    else:
        lines.append(
            "Quick answers: **Did training-informed memory influence this run?** "
            "**What object was used?** **Where did it come from?** **What behavior changed?** "
            "**Was that visible in the outcome?**"
        )
        lines.append("")
        lines.append("| Question | Answer |")
        lines.append("|----------|--------|")
        lines.append(
            "| Did training-informed memory influence this run? (memory merge) | "
            f"**{'Yes' if lme.get('memory_applied') else 'No'}** |"
        )
        lines.append(
            "| Training evidence (summary) | "
            f"**{ol.get('training_evidence', '—')}** (none / partial / confirmed) |"
        )
        lines.append(
            "| Memory in use | "
            f"**{ol.get('memory_in_use', '—')}** |"
        )
        lines.append(
            "| Groundhog mode (canonical bundle) | "
            f"**{ol.get('groundhog_mode', '—')}** (active / inactive) |"
        )
        lines.append(
            "| Context quality (operator label) | "
            f"**{ol.get('context_quality', '—')}** (missing / thin / rich) |"
        )
        lines.append(
            "| Training claim | "
            f"`{lme.get('training_claim', '—')}` |"
        )
        lines.append(
            "| Proof type | "
            f"**{ol.get('proof_type', '—')}** |"
        )
        lines.append(
            "| Outcome change visible vs no-memory replay? | "
            f"**{lme.get('outcome_change_visible', 'unknown')}** |"
        )
        lines.append("")
        lf = lme.get("learned_from") or {}
        lines.append("- **Learned from:**")
        lines.append(f"  - Memory bundle path: `{lf.get('bundle_path') or '—'}`")
        lines.append(f"  - Bundle `from_run_id`: `{lf.get('bundle_from_run_id') or '—'}`")
        lines.append(f"  - Scenario `prior_run_id` (metadata): `{lf.get('prior_run_id_metadata') or '—'}`")
        lines.append(f"- **What changed this run:** {lme.get('behavior_change', '—')}")
        lines.append(f"- **Outcome visibility:** {lme.get('outcome_change_note', '')}")
        lines.append("")
        gh_note = lme.get("groundhog_note")
        if gh_note:
            lines.append(f"- **Groundhog note:** {gh_note}")
            lines.append("")
        abl = lme.get("ablation") or {}
        lines.append(
            f"- **Ablation:** {'available' if abl.get('available') else 'not available'} — "
            f"{abl.get('note', '')}"
        )
        lines.append("")
    lines.append("### Memory & prior knowledge (technical decision audit)")
    lines.append("")
    loaded = da.get("prior_outcomes_or_parameters_loaded_into_replay_engine")
    lines.append(
        f"- **Parameters merged from a memory bundle before replay (changes trades):** "
        f"**{'Yes' if loaded else 'No'}** "
        f"(distinct from metadata-only links such as `prior_run_id` on the scenario)."
    )
    pr = da.get("prior_run_id_provided")
    if pr:
        lines.append(f"- **prior_run_id (metadata link):** `{pr}`")
    lines.append("")
    summary = da.get("human_readable_summary")
    if summary:
        lines.append(summary)
        lines.append("")
    extra = da.get("if_prior_run_id_is_set")
    if extra:
        lines.append(extra)
        lines.append("")

    lines.append("## Referee results (measurement — not narrative invention)")
    lines.append("")
    if record.get("error"):
        lines.append(f"- **Status:** failed — `{record['error']}`")
        lines.append("")
    elif not ref:
        lines.append("*(No referee summary attached.)*")
        lines.append("")
    else:
        lines.append("| Field | Value |")
        lines.append("|-------|--------|")
        for key in (
            "wins",
            "losses",
            "trades",
            "win_rate",
            "expectancy",
            "average_pnl",
            "max_drawdown",
            "cumulative_pnl",
            "validation_checksum",
            "dataset_bars",
        ):
            if key in ref and ref[key] is not None:
                lines.append(f"| {key} | {ref[key]} |")
        sm = ref.get("summary")
        if isinstance(sm, dict):
            lines.append("")
            lines.append("Ledger summary (full):")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(sm, indent=2, ensure_ascii=False))
            lines.append("```")
        lines.append("")

    om = record.get("outcome_measures") or {}
    lines.append("## Outcome lenses (same Referee row — not a second ledger)")
    lines.append("")
    lines.append(
        "Binary **WIN/LOSS** counts are one scorecard. Here we **interpret** the same summary row "
        "so you can answer: did money improve, was edge positive, was drawdown contained, "
        "was win rate above a coin flip — **without** mixing in a separate data source."
    )
    lines.append("")
    if not om or not om.get("from_referee_row"):
        lines.append("*(No outcome measures — referee summary missing or run failed.)*")
        lines.append("")
    else:
        pa = om.get("positive_any")
        lines.append(
            f"- **Any positive signal (under these lenses):** **{'Yes' if pa else 'No'}** "
            f"(see `positive_signals` in `run_record.json`)"
        )
        lenses = om.get("lenses") or {}
        if lenses:
            lines.append("- **Lenses:**")
            for k, v in sorted(lenses.items()):
                lines.append(f"  - `{k}` → **{v}**")
        ps = om.get("positive_signals") or []
        if ps:
            lines.append(f"- **Positive signals:** {', '.join(f'`{s}`' for s in ps)}")
        note_om = om.get("note")
        if note_om:
            lines.append(f"- _{note_om}_")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(om, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")

    lines.append("## Post-mortem (for you or Anna — optional)")
    lines.append("")
    lines.append(f"- **why:** {pm.get('why')!r}")
    lines.append(f"- **next_hypothesis:** {pm.get('next_hypothesis')!r}")
    lines.append("")
    lines.append(
        "_Nothing in this section affected the Referee. Fill in after you review the run._"
    )
    lines.append("")

    return "\n".join(lines)


def write_run_session_folder(
    record: dict[str, Any],
    *,
    logs_root: Path | None = None,
    prefix: str = "run",
) -> Path:
    """
    Create a unique directory under ``logs_root``, write ``HUMAN_READABLE.md`` and ``run_record.json``.

    Returns the directory path (print or log for the operator).
    """
    d = allocate_unique_run_directory(logs_root=logs_root, prefix=prefix)
    md = render_human_readable_markdown(record)
    (d / "HUMAN_READABLE.md").write_text(md, encoding="utf-8")
    (d / "run_record.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (d / "SESSION.txt").write_text(
        f"run_id={record.get('run_id')}\n"
        f"folder={d}\n"
        f"Open HUMAN_READABLE.md for the full narrative.\n",
        encoding="utf-8",
    )
    return d


def write_batch_index_and_scenario_logs(
    batch_dir: Path,
    records: list[tuple[str, dict[str, Any]]],
) -> None:
    """
    ``records``: list of (scenario_id_label, run_memory record dict).

    Writes ``batch_dir/BATCH_README.md`` and one subfolder per scenario.
    """
    batch_dir = Path(batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Parallel batch — session log index",
        "",
        f"**Created (UTC):** {datetime.now(timezone.utc).isoformat()}",
        "",
        "Each scenario has its own subfolder with **HUMAN_READABLE.md** and **run_record.json**.",
        "",
        "| scenario | folder | run_id |",
        "|----------|--------|--------|",
    ]
    for sid, rec in records:
        sub = batch_dir / _safe_segment(sid)
        sub.mkdir(parents=True, exist_ok=True)
        rid = rec.get("run_id", "")
        (sub / "HUMAN_READABLE.md").write_text(render_human_readable_markdown(rec), encoding="utf-8")
        (sub / "run_record.json").write_text(
            json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        lines.append(f"| `{sid}` | `{sub.name}` | `{rid}` |")
    lines.append("")
    (batch_dir / "BATCH_README.md").write_text("\n".join(lines), encoding="utf-8")
