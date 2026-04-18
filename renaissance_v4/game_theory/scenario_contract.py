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
- ``evaluation_window`` *(dict)* — Declarative intent (e.g. ``calendar_months``); slicing may be
  wired later; replay today uses whatever bar range the SQLite DB provides unless the manifest
  specifies dates.
- ``game_spec_ref`` *(str)* — Pointer to the game spec doc filename for reviewers.
- ``training_trace_id`` / ``prior_scenario_id`` *(str)* — Training pipeline correlation IDs.

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

# Keys copied from each scenario dict into worker results (audit trail; not used for scoring).
SCENARIO_ECHO_KEYS: tuple[str, ...] = (
    "agent_explanation",
    "training_trace_id",
    "prior_scenario_id",
    "tier",
    "evaluation_window",
    "game_spec_ref",
)

# Backward-compatible name
AGENT_ECHO_KEYS = SCENARIO_ECHO_KEYS


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
        *SCENARIO_ECHO_KEYS,
    }

    for i, s in enumerate(scenarios):
        mp = s.get("manifest_path")
        if not mp or not isinstance(mp, str):
            return False, [f"scenario[{i}] missing or invalid manifest_path (required string)"]
        if check_manifest_exists and repo_root is not None:
            p = Path(mp).expanduser()
            if not p.is_absolute():
                p = (repo_root / p).resolve()
            else:
                p = p.resolve()
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
