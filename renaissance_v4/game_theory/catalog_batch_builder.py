"""
catalog_batch_builder.py — **Chef** path: build valid parallel scenario batches from the cookbook.

V1 focuses on **ATR geometry sweeps** on a fixed manifest (same tape, different exit spice).
Future: signal-subset ladders, regime swaps — each must pass ``validate_manifest_against_catalog``.

Operators and Anna call :func:`build_atr_sweep_scenarios` (or HTTP ``POST /api/catalog-batch-generate``)
instead of hand-pasting dozens of JSON objects.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.scenario_contract import resolve_scenario_manifest_path

# Sane defaults — same band as manifest validator [0.5, 6.0].
_DEFAULT_STOPS: tuple[float, ...] = (0.8, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0)
_DEFAULT_TARGETS: tuple[float, ...] = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)


def _repo_root() -> Path:
    """``renaissance_v4/game_theory`` → repo root (``blackbox``)."""
    return Path(__file__).resolve().parent.parent.parent


def _manifest_display_path(resolved_manifest: Path) -> str:
    """Prefer repo-relative strings (portable) when the file lives under the repo."""
    root = _repo_root()
    try:
        return str(resolved_manifest.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved_manifest)


def _clamp_atr(x: float) -> float:
    return max(0.5, min(6.0, float(x)))


def build_atr_sweep_scenarios(
    manifest_path: str | Path,
    *,
    stop_values: list[float] | None = None,
    target_values: list[float] | None = None,
    pairs: list[tuple[float, float]] | None = None,
    max_scenarios: int = 24,
    scenario_id_prefix: str = "chef_atr",
    game_spec_ref: str = "GAME_SPEC_INDICATOR_PATTERN_V1.md",
    tier: str = "T1",
) -> list[dict[str, Any]]:
    """
    Build scenario dicts: same ``manifest_path``, different ``atr_stop_mult`` / ``atr_target_mult``.

    Provide either ``pairs`` **or** Cartesian product of ``stop_values`` × ``target_values``
    (clamped to [0.5, 6.0]), truncated to ``max_scenarios``.
    """
    resolved_mp = resolve_scenario_manifest_path(manifest_path)
    if not resolved_mp.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    manifest_str = _manifest_display_path(resolved_mp)

    if pairs:
        combo = [(_clamp_atr(a), _clamp_atr(b)) for a, b in pairs]
    else:
        sv = list(stop_values) if stop_values is not None else list(_DEFAULT_STOPS)
        tv = list(target_values) if target_values is not None else list(_DEFAULT_TARGETS)
        sv = [_clamp_atr(x) for x in sv]
        tv = [_clamp_atr(x) for x in tv]
        combo = list(itertools.product(sv, tv))
    combo = combo[: max(1, int(max_scenarios))]

    out: list[dict[str, Any]] = []
    for i, (s, t) in enumerate(combo):
        sid = f"{scenario_id_prefix}_{i+1:02d}_{s}_{t}".replace(".", "p")
        out.append(
            {
                "scenario_id": sid,
                "tier": tier,
                "game_spec_ref": game_spec_ref,
                "manifest_path": manifest_str,
                "atr_stop_mult": s,
                "atr_target_mult": t,
                "agent_explanation": {
                    "hypothesis": (
                        f"Chef ATR sweep #{i+1}: stop_mult={s} target_mult={t} on same manifest vs same tape; "
                        "compare Referee outcomes across the grid."
                    ),
                },
            }
        )
    return out


def catalog_batch_builder_meta() -> dict[str, Any]:
    """Defaults for UI / Anna tool prompts."""
    return {
        "modes": ["atr_sweep"],
        "default_stop_values": list(_DEFAULT_STOPS),
        "default_target_values": list(_DEFAULT_TARGETS),
        "atr_bounds": {"min": 0.5, "max": 6.0},
        "default_max_scenarios": 24,
        "note": "V1 = ATR sweep on one manifest. Manifest must validate against catalog.",
    }
