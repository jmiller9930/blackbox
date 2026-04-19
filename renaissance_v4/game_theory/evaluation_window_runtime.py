"""
Operator evaluation window — UI modes, scenario merge, and **replay bar slicing**.

``evaluation_window`` on scenarios is always echoed for audit; this module also drives the
**effective** historical span used by ``run_manifest_replay`` when ``calendar_months`` is set.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

# Approximate mean Gregorian month length (365.25/12) for bar-span cutoff without extra deps.
_DAYS_PER_CALENDAR_MONTH = 30.4375


def parse_bar_open_time_unix(row: Any) -> int:
    """Return Unix **seconds** for a SQLite row's ``open_time`` (int seconds or ms)."""
    if hasattr(row, "keys"):
        t = row["open_time"]
    else:
        t = row[1]
    if isinstance(t, float):
        ti = int(t)
    else:
        ti = int(t)
    if ti > 10**12:
        ti //= 1000
    return ti


def slice_rows_for_calendar_months(
    rows: list[Any],
    calendar_months: int,
    *,
    min_rows_required: int,
) -> tuple[list[Any], dict[str, Any]]:
    """
    Keep only bars whose ``open_time`` falls in the last ``calendar_months`` (approximate days cutoff
    from the **last** bar). If the slice would drop below ``min_rows_required``, widen to the last
    ``min_rows_required`` bars and record a clamp note.
    """
    n = len(rows)
    audit: dict[str, Any] = {
        "schema": "pattern_game_bar_window_v1",
        "dataset_bars_before_window": n,
        "bar_window_calendar_months_requested": int(calendar_months),
        "slicing_applied": False,
        "bar_window_open_time_start": None,
        "bar_window_open_time_end": None,
        "window_clamped_to_min_rows": False,
        "note": None,
    }
    if n == 0 or calendar_months <= 0:
        audit["note"] = "No slice — empty rows or non-positive months."
        return rows, audit

    last_ts = parse_bar_open_time_unix(rows[-1])
    last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
    approx_days = int(max(1, round(calendar_months * _DAYS_PER_CALENDAR_MONTH)))
    cutoff_dt = last_dt - timedelta(days=approx_days)
    cutoff_ts = int(cutoff_dt.timestamp())

    start_idx = 0
    for i, row in enumerate(rows):
        if parse_bar_open_time_unix(row) >= cutoff_ts:
            start_idx = i
            break

    sliced = rows[start_idx:]
    audit["slicing_applied"] = start_idx > 0 or len(sliced) < n

    if len(sliced) < min_rows_required:
        audit["window_clamped_to_min_rows"] = True
        audit["note"] = (
            f"Sliced window had {len(sliced)} bars (< min_rows_required={min_rows_required}); "
            "expanded to the last min_rows_required bars of the full dataset."
        )
        sliced = rows[-min_rows_required:] if n >= min_rows_required else rows
        start_idx = n - len(sliced)

    audit["dataset_bars_after_window"] = len(sliced)
    audit["bar_window_open_time_start"] = parse_bar_open_time_unix(sliced[0])
    audit["bar_window_open_time_end"] = parse_bar_open_time_unix(sliced[-1])
    audit["bar_window_span_days_approx"] = round(
        (audit["bar_window_open_time_end"] - audit["bar_window_open_time_start"]) / 86400.0,
        4,
    )
    return sliced, audit


def resolve_ui_evaluation_window(
    mode: str,
    custom_months: Any,
) -> dict[str, Any]:
    """
    Map UI mode ``12`` | ``18`` | ``24`` | ``custom`` to an integer month count.

    Returns ``effective_calendar_months`` (always int for replay slice) and labels for audit.
    """
    m = (mode or "12").strip().lower()
    if m == "custom":
        try:
            cm = int(custom_months)
        except (TypeError, ValueError):
            raise ValueError("evaluation_window_custom_months must be a positive integer when mode is custom")
        if cm < 1 or cm > 600:
            raise ValueError("evaluation_window_custom_months must be between 1 and 600")
        return {
            "evaluation_window_mode": "custom",
            "effective_calendar_months": cm,
            "custom_calendar_months": cm,
        }
    preset = {"12": 12, "18": 18, "24": 24}
    if m in preset:
        mo = preset[m]
        return {
            "evaluation_window_mode": m,
            "effective_calendar_months": mo,
            "custom_calendar_months": None,
        }
    raise ValueError("evaluation_window_mode must be one of: 12, 18, 24, custom")


def _deep_merge_evaluation_window(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any],
) -> dict[str, Any]:
    base = dict(existing or {})
    base.update(incoming)
    return base


def annotate_scenarios_with_window_and_recipe(
    scenarios: list[dict[str, Any]],
    *,
    recipe_id: str,
    recipe_label: str,
    recipe_default_calendar_months: int,
    resolved: dict[str, Any],
) -> None:
    """
    Mutates each scenario: sets ``operator_recipe_*`` and a structured ``evaluation_window`` audit
    block (merged with any existing ``evaluation_window``).
    """
    eff = int(resolved["effective_calendar_months"])
    mode = str(resolved["evaluation_window_mode"])
    overrode = eff != int(recipe_default_calendar_months)

    for s in scenarios:
        s["operator_recipe_id"] = recipe_id
        s["operator_recipe_label"] = recipe_label
        ew_prev = s.get("evaluation_window") if isinstance(s.get("evaluation_window"), dict) else {}
        json_hint = ew_prev.get("calendar_months")
        merged = _deep_merge_evaluation_window(
            ew_prev,
            {
                "calendar_months": eff,
                "operator_window_mode": mode,
                "recipe_default_calendar_months": recipe_default_calendar_months,
                "window_overrode_recipe_default": overrode,
                "json_calendar_months_before_override": json_hint,
                "referee_note": (
                    f"Replay uses the last ~{eff} calendar months of available 5m bars "
                    "(approximate day cutoff; see replay_data_audit)."
                ),
            },
        )
        s["evaluation_window"] = merged


def extract_calendar_months_for_replay(scenario: dict[str, Any]) -> int | None:
    """Integer months to pass into replay slicing, or None to use full loaded dataset."""
    ew = scenario.get("evaluation_window")
    if not isinstance(ew, dict):
        return None
    cm = ew.get("calendar_months")
    if cm is None:
        return None
    try:
        n = int(cm)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None
