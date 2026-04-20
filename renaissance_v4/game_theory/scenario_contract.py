"""
Scenario batch JSON — required shape for ``parallel_runner``, ``pattern_game`` web UI, and paste-in runs.

**Top-level object (one scenario):**

**Required**

- ``manifest_path`` *(str)* — Path to a ``strategy_manifest_v1`` JSON file. Relative paths are
  resolved from the repo root (or worker cwd). This is the only key the Referee *must* have to
  load policy for replay.

**Replay inputs (optional; change execution when set)**

- ``atr_stop_mult`` / ``atr_target_mult`` *(float | null)* — Override manifest stop/target ATR
  multiples for this scenario only (applied after any memory bundle merge in ``pattern_game``).
- ``memory_bundle_path`` *(str | null)* — Optional path to a **memory bundle** JSON; whitelisted
  keys are merged into the manifest **before** replay and **do** affect trades.
- ``emit_baseline_artifacts`` *(bool)* — When true, emit extra baseline artifacts from the runner
  (see ``run_pattern_game``).

**Audit / trace only (optional; echoed into results and run_memory — do not change Referee math)**

- ``scenario_id`` *(str)* — Label for tables, logs, and batch folders; default ``unknown`` if omitted.
- ``prior_run_id`` *(str | null)* — Metadata link to a previous run UUID for **human** traceability;
  **not** loaded as simulation input unless a memory bundle is merged (see ``run_memory.build_decision_audit``).
- ``skip_groundhog_bundle`` *(bool)* — If true, do not apply the canonical Groundhog bundle when
  ``PATTERN_GAME_GROUNDHOG_BUNDLE=1`` (see ``groundhog_memory.py``).
- ``tier`` *(str)* — e.g. ``T1``; documentation / UI only.
- ``evaluation_window`` *(dict)* — Declarative intent (e.g. ``calendar_months``); replay slices the
  last N months when ``calendar_months`` is passed through ``run_manifest_replay``.
- ``context_signature_memory_mode`` / ``context_signature_memory_path`` — When ``mode`` is
  ``read`` or ``read_write``, catalog parallel workers enable Decision Context Recall on replay
  (defaults match the operator harness when mode is not ``off``).
- ``game_spec_ref`` *(str)* — Pointer to the game spec doc filename for reviewers.
- ``training_trace_id`` / ``prior_scenario_id`` *(str)* — Training pipeline correlation IDs.

**``goal_v2`` *(dict, optional)*** — Declares evaluation intent for the pattern system (e.g.
  ``pattern_outcome_quality`` with ``primary_metric`` / secondary metrics). Does not change
  engine math; surfaced in operator harness / audit. See ``pattern_outcome_quality_v1.DEFAULT_GOAL_V2_PATTERN_OUTCOME_QUALITY``.

- ``policy_framework_path`` *(str, optional)* — Repo-relative path to ``policy_framework_v1`` JSON.
  When present, prep validates the file and sets ``policy_framework_audit`` on the scenario.

- ``policy_framework_audit`` *(dict, optional)* — Framework id/version/path/sha256/tunable-surface
  summary; audit-only (see ``policy_framework.attach_policy_framework_audits``).

**``agent_explanation`` *(dict, optional)*** — Story for proctors / Anna; merged into run_memory.

- ``hypothesis`` *(str)* — One testable sentence. **May be required** when
  ``PATTERN_GAME_REQUIRE_HYPOTHESIS`` or ``validate_scenarios(..., require_hypothesis=True)``.
- ``why_this_strategy`` *(str)* — Short rationale.
- ``indicator_values`` *(object)* — Optional numeric snapshot (not a substitute for structured
  ``indicator_context``).
- ``learned`` / ``behavior_change`` *(str)* — Memory narrative fields.
- ``indicator_context`` *(object)* — Structured **context around indicators** (regime, direction,
  etc.); see ``context_memory.py`` / GAME_SPEC. Passed through to ``run_memory`` when present.

**Normative examples:** ``tier1_scenario.template.json``, ``parallel_scenarios.example.json``,
``width_depth_15.example.json`` (15 parallel ATR grid points + one memory-bundle row for depth).
Programmatic ATR grids: ``catalog_batch_builder.build_atr_sweep_scenarios`` / ``POST /api/catalog-batch-generate``.
**Rules of the game:** ``GAME_SPEC_INDICATOR_PATTERN_V1.md``.

**Pickle / multiprocessing:** Each scenario must be JSON-serializable (``str``, ``int``, ``float``,
``bool``, ``None``, ``list``, ``dict`` only). Do not embed ``Path`` objects or callables — workers
pickle scenario dicts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]

# Keys copied from each scenario dict into worker results (audit trail; not used for scoring).
SCENARIO_ECHO_KEYS: tuple[str, ...] = (
    "goal_v2",
    "agent_explanation",
    "training_trace_id",
    "prior_scenario_id",
    "prior_run_id",
    "skip_groundhog_bundle",
    "memory_bundle_path",
    "tier",
    "evaluation_window",
    "game_spec_ref",
    "operator_recipe_id",
    "operator_recipe_label",
    "context_signature_memory_mode",
    "context_signature_memory_path",
    "policy_framework_path",
    "policy_framework_audit",
)

# Backward-compatible name
AGENT_ECHO_KEYS = SCENARIO_ECHO_KEYS


def resolve_scenario_manifest_path(
    manifest_path: str | Path,
    *,
    repo_root: Path | None = None,
) -> Path:
    """
    Resolve a scenario ``manifest_path`` against the repo root when it is relative.

    The game-theory examples and curated recipes intentionally store repo-relative manifest paths so
    they stay portable across hosts; callers should not depend on the current working directory.
    """
    p = Path(str(manifest_path)).expanduser()
    if p.is_absolute():
        return p.resolve()
    root = (repo_root or _DEFAULT_REPO_ROOT).expanduser().resolve()
    return (root / p).resolve()


def extract_scenario_echo_fields(scenario: dict[str, Any]) -> dict[str, Any]:
    """Return whitelisted metadata for JSON-safe echo in parallel results."""
    out: dict[str, Any] = {}
    for k in SCENARIO_ECHO_KEYS:
        if k in scenario and scenario[k] is not None:
            out[k] = scenario[k]
    return out


def extract_agent_fields(scenario: dict[str, Any]) -> dict[str, Any]:
    """Alias for :func:`extract_scenario_echo_fields`."""
    return extract_scenario_echo_fields(scenario)


def extract_policy_contract_summary(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """
    Compact slice of the effective strategy manifest for operator UIs (signals, fusion, regime).

    Intended for tables — not a full manifest dump.
    """
    if not manifest:
        return {}
    return {
        "strategy_id": manifest.get("strategy_id"),
        "symbol": manifest.get("symbol"),
        "timeframe": manifest.get("timeframe"),
        "signal_modules": list(manifest.get("signal_modules") or []),
        "regime_module": manifest.get("regime_module"),
        "risk_model": manifest.get("risk_model"),
        "fusion_module": manifest.get("fusion_module"),
        "execution_template": manifest.get("execution_template"),
    }


def referee_session_outcome(ok: bool, summary: dict[str, Any] | None) -> str:
    """
    Session-level paper label for one replay: **WIN** if cumulative PnL is strictly positive,
    **LOSS** otherwise; **ERROR** if the run failed.
    """
    if not ok:
        return "ERROR"
    if not summary:
        return "LOSS"
    cp = summary.get("cumulative_pnl")
    try:
        v = float(cp) if cp is not None else 0.0
    except (TypeError, ValueError):
        v = 0.0
    return "WIN" if v > 0.0 else "LOSS"


def validate_scenarios(
    scenarios: list[dict[str, Any]],
    *,
    check_manifest_exists: bool = False,
    repo_root: Path | None = None,
    require_hypothesis: bool = False,
) -> tuple[bool, list[str]]:
    """
    Return ``(ok, messages)``. ``ok`` is False only for blocking errors: empty list, or
    ``manifest_path`` missing / not a string.

    **Non-blocking warnings:** undocumented top-level keys (still passed through to the worker;
    runner may ignore them), missing manifest file when ``check_manifest_exists`` is True.

    **Blocking when** ``require_hypothesis`` **is True:** each scenario needs
    ``agent_explanation.hypothesis`` as a non-empty string (web UI defaults to requiring this
    unless ``PATTERN_GAME_REQUIRE_HYPOTHESIS`` disables it).

    See the module docstring for the full field list.
    """
    messages: list[str] = []
    if not scenarios:
        return False, ["scenarios must be a non-empty JSON array of objects"]

    known = {
        "scenario_id",
        "manifest_path",
        "atr_stop_mult",
        "atr_target_mult",
        "memory_bundle_path",
        "emit_baseline_artifacts",
        "prior_run_id",
        "skip_groundhog_bundle",
        "operator_recipe_id",
        "operator_recipe_label",
        *SCENARIO_ECHO_KEYS,
    }

    for i, s in enumerate(scenarios):
        mp = s.get("manifest_path")
        if not mp or not isinstance(mp, str):
            return False, [f"scenario[{i}] missing or invalid manifest_path (required string)"]
        if check_manifest_exists and repo_root is not None:
            p = resolve_scenario_manifest_path(mp, repo_root=repo_root)
            if not p.is_file():
                messages.append(f"warning: scenario[{i}] manifest not found: {p}")

        extra = set(s.keys()) - known
        if extra:
            messages.append(
                f"scenario[{i}] has undocumented keys (ignored by runner): {sorted(extra)}"
            )

        if require_hypothesis:
            ae = s.get("agent_explanation")
            hyp_ok = False
            if isinstance(ae, dict):
                h = ae.get("hypothesis")
                hyp_ok = isinstance(h, str) and bool(h.strip())
            if not hyp_ok:
                return False, [
                    f"scenario[{i}] missing non-empty agent_explanation.hypothesis "
                    f"(PATTERN_GAME_REQUIRE_HYPOTHESIS or require_hypothesis=True)"
                ]

    return True, messages
