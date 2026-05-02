"""
FinQuant Unified Agent Lab — runtime flag normalization and config overlays.

These flags are intentionally small and script-friendly so the isolated project can be run as:

  --data-window-months 12 --interval 15
  --data-window-months 18 --interval 45m
  --data-window-months 25 --interval 1hour

The current lab persists these selections into the run config and artifacts so future
data-contract work can consume them deterministically.
"""

from __future__ import annotations

from typing import Any


_INTERVAL_ALIASES = {
    "5": "5m",
    "5m": "5m",
    "15": "15m",
    "15m": "15m",
    "45": "45m",
    "45m": "45m",
    "60": "1h",
    "60m": "1h",
    "1h": "1h",
    "1hour": "1h",
}

_INTERVAL_TO_MINUTES = {
    "5m": 5,
    "15m": 15,
    "45m": 45,
    "1h": 60,
}


def normalize_interval_v1(value: str | int | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    out = _INTERVAL_ALIASES.get(raw)
    if out is None:
        raise ValueError(
            "interval must be one of: 5, 5m, 15, 15m, 45, 45m, 1h, 1hour"
        )
    return out


def interval_minutes_v1(value: str | int | None) -> int | None:
    norm = normalize_interval_v1(value)
    if norm is None:
        return None
    return _INTERVAL_TO_MINUTES[norm]


def validate_data_window_months_v1(value: int | str | None) -> int | None:
    if value is None:
        return None
    try:
        months = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("data-window-months must be an integer") from exc
    if months <= 0:
        raise ValueError("data-window-months must be > 0")
    return months


def apply_runtime_overrides_v1(
    config: dict[str, Any],
    *,
    data_window_months: int | str | None = None,
    interval: str | int | None = None,
) -> dict[str, Any]:
    out = dict(config)
    months = validate_data_window_months_v1(data_window_months)
    interval_norm = normalize_interval_v1(interval)
    interval_minutes = interval_minutes_v1(interval)

    if months is not None:
        out["runtime_data_window_months_v1"] = months
    if interval_norm is not None:
        out["runtime_interval_v1"] = interval_norm
    if interval_minutes is not None:
        out["runtime_interval_minutes_v1"] = interval_minutes

    out["runtime_request_v1"] = {
        "data_window_months_v1": months,
        "interval_v1": interval_norm,
        "interval_minutes_v1": interval_minutes,
    }
    return out

