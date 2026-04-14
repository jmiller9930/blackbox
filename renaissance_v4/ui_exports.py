"""
CSV export helpers for Quant Research Kitchen V1 — reads saved JSON artifacts only (no recompute).
"""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def csv_bytes_from_rows(rows: list[dict[str, Any]], filename: str) -> tuple[bytes, str]:
    """Return UTF-8 CSV bytes and a suggested filename."""
    buf = StringIO()
    if not rows:
        body = buf.getvalue().encode("utf-8")
        return body, filename
    keys: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in keys})
    return buf.getvalue().encode("utf-8"), filename


def trades_json_to_csv_rows(repo: Path, trades_path: Path) -> list[dict[str, Any]]:
    raw = _read_json(trades_path)
    if raw is None:
        return []
    trades = raw if isinstance(raw, list) else raw.get("trades") or []
    if not isinstance(trades, list):
        return []
    out: list[dict[str, Any]] = []
    for t in trades:
        if isinstance(t, dict):
            flat = {str(k): t[k] for k in sorted(t)}
            out.append(flat)
    return out


def deterministic_json_to_metric_rows(det: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not det or not isinstance(det, dict):
        return []
    rows = []
    for k, v in sorted(det.items()):
        rows.append({"metric": k, "value": v})
    return rows


def monte_carlo_summary_to_rows(mc: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not mc or not isinstance(mc, dict):
        return []
    rows: list[dict[str, Any]] = []
    for mode, summary in mc.items():
        if not isinstance(summary, dict):
            continue
        row: dict[str, Any] = {"mode": mode}
        for k, v in summary.items():
            row[str(k)] = v
        rows.append(row)
    return rows


def export_experiment_csv(
    repo: Path,
    experiment_id: str,
    kind: str,
    *,
    state_dir: Path,
    candidate_trades_fallback: Path | None = None,
) -> tuple[bytes, str] | None:
    """
    kind: trades | metrics | monte_carlo
    Returns (csv_bytes, filename) or None if missing.
    """
    repo = repo.resolve()
    det_path = state_dir / f"deterministic_{experiment_id}.json"
    mc_path = state_dir / f"monte_carlo_{experiment_id}_summary.json"

    if kind == "metrics":
        dj = _read_json(det_path)
        det = dj.get("deterministic") if isinstance(dj, dict) else None
        rows = deterministic_json_to_metric_rows(det if isinstance(det, dict) else None)
        b, fn = csv_bytes_from_rows(rows, f"experiment_{experiment_id}_summary_metrics.csv")
        return b, fn

    if kind == "monte_carlo":
        mj = _read_json(mc_path)
        if not isinstance(mj, dict):
            return None
        mc = mj.get("monte_carlo")
        if not isinstance(mc, dict):
            return None
        rows = monte_carlo_summary_to_rows(mc)
        b, fn = csv_bytes_from_rows(rows, f"experiment_{experiment_id}_monte_carlo.csv")
        return b, fn

    if kind == "trades":
        mj = _read_json(mc_path)
        cpath: Path | None = None
        if isinstance(mj, dict) and mj.get("candidate_trades"):
            try:
                raw_p = Path(str(mj["candidate_trades"])).resolve()
            except OSError:
                raw_p = None  # type: ignore[assignment]
            if raw_p is not None:
                try:
                    raw_p.relative_to(repo)
                    cpath = raw_p
                except ValueError:
                    cpath = None
        if (not cpath or not cpath.is_file()) and candidate_trades_fallback is not None:
            cpath = candidate_trades_fallback if candidate_trades_fallback.is_file() else None
        if not cpath or not cpath.is_file():
            return None
        rows = trades_json_to_csv_rows(repo, cpath)
        b, fn = csv_bytes_from_rows(rows, f"experiment_{experiment_id}_trades.csv")
        return b, fn

    return None


def export_baseline_csv(
    repo: Path,
    kind: str,
    *,
    reports_exp: Path,
    state_dir: Path,
) -> tuple[bytes, str] | None:
    """kind: trades | metrics | monte_carlo — baseline reference artifacts."""
    repo = repo.resolve()
    baseline_trades = reports_exp / "baseline_v1_trades.json"
    det_path = state_dir / "baseline_deterministic.json"
    mc_path = state_dir / "baseline_monte_carlo_summary.json"

    if kind == "trades":
        if not baseline_trades.is_file():
            return None
        rows = trades_json_to_csv_rows(repo, baseline_trades)
        b, fn = csv_bytes_from_rows(rows, "baseline_v1_trades.csv")
        return b, fn

    if kind == "metrics":
        dj = _read_json(det_path)
        det = dj.get("deterministic") if isinstance(dj, dict) else None
        if not det and isinstance(dj, dict):
            det = dj
        rows = deterministic_json_to_metric_rows(det if isinstance(det, dict) else None)
        b, fn = csv_bytes_from_rows(rows, "baseline_deterministic_metrics.csv")
        return b, fn

    if kind == "monte_carlo":
        mj = _read_json(mc_path)
        if not isinstance(mj, dict):
            return None
        mc = mj.get("monte_carlo")
        if not isinstance(mc, dict):
            return None
        rows = monte_carlo_summary_to_rows(mc)
        b, fn = csv_bytes_from_rows(rows, "baseline_monte_carlo_summary.csv")
        return b, fn

    return None
