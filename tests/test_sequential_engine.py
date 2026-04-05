"""sequential_engine — SPRT, manifests, MAE v1, duplicate policy."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from modules.anna_training.sequential_engine.calibration_report import CalibrationReport
from modules.anna_training.sequential_engine.decision_state import advance_sprt_after_outcome, commit_outcome
from modules.anna_training.sequential_engine.mae_v1 import MAE_PROTOCOL_ID, compute_mae_usd_v1
from modules.anna_training.sequential_engine.outcome_manifest import append_outcome_record
from modules.anna_training.sequential_engine.pair_evaluation import build_outcome_record
from modules.anna_training.sequential_engine.sequential_errors import CorruptionError
from modules.anna_training.sequential_engine.sprt import classify_sprt_decision, sprt_thresholds
from modules.anna_training.sequential_engine.patterns.pelt_regime import run_pelt_changepoints
from modules.anna_training.sequential_engine.patterns.cusum_shift import run_cusum_monitor


def _mk_market_db(tmp: Path, symbol: str = "SOL-PERP") -> Path:
    p = tmp / "m.db"
    conn = sqlite3.connect(p)
    conn.executescript(
        """
        CREATE TABLE market_bars_5m (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          canonical_symbol TEXT NOT NULL,
          tick_symbol TEXT NOT NULL,
          timeframe TEXT NOT NULL DEFAULT '5m',
          candle_open_utc TEXT NOT NULL,
          candle_close_utc TEXT NOT NULL,
          market_event_id TEXT NOT NULL UNIQUE,
          open REAL, high REAL, low REAL, close REAL,
          tick_count INTEGER NOT NULL DEFAULT 0,
          volume_base REAL,
          price_source TEXT NOT NULL DEFAULT 'pyth_primary',
          bar_schema_version TEXT NOT NULL DEFAULT 'canonical_bar_v1',
          computed_at TEXT NOT NULL
        );
        """
    )
    rows = [
        ("2025-01-01T10:00:00+00:00", "2025-01-01T10:05:00+00:00", "e1", 100.0, 102.0, 99.0, 101.0),
        ("2025-01-01T10:05:00+00:00", "2025-01-01T10:10:00+00:00", "e2", 101.0, 103.0, 100.0, 102.0),
        ("2025-01-01T10:10:00+00:00", "2025-01-01T10:15:00+00:00", "e3", 102.0, 104.0, 101.0, 103.0),
    ]
    for co, cc, meid, o, h, l, cl in rows:
        conn.execute(
            """
            INSERT INTO market_bars_5m (
              canonical_symbol, tick_symbol, candle_open_utc, candle_close_utc,
              market_event_id, open, high, low, close, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 't')
            """,
            (symbol, symbol, co, cc, meid, o, h, l, cl),
        )
    conn.commit()
    conn.close()
    return p


def test_sprt_thresholds_and_decision() -> None:
    th = sprt_thresholds(alpha=0.05, beta=0.10)
    assert th.upper == pytest.approx(18.0)
    assert th.lower == pytest.approx(0.10526, rel=1e-4)
    # Strong evidence for H1
    assert classify_sprt_decision(log_likelihood_ratio=100.0, alpha=0.05, beta=0.10) == "PROMOTE"
    assert classify_sprt_decision(log_likelihood_ratio=-100.0, alpha=0.05, beta=0.10) == "KILL"


def test_mae_v1_long(tmp_path: Path) -> None:
    db = _mk_market_db(tmp_path)
    mae, err = compute_mae_usd_v1(
        canonical_symbol="SOL-PERP",
        side="long",
        entry_price=100.0,
        size=2.0,
        entry_time="2025-01-01T10:00:00+00:00",
        exit_time="2025-01-01T10:15:00+00:00",
        market_db_path=db,
    )
    assert err is None
    # Worst low 99: adverse (100-99)*2 = 2
    assert mae == pytest.approx(2.0)


def test_duplicate_append_idempotent(tmp_path: Path) -> None:
    ad = tmp_path / "art"
    rec = {
        "market_event_id": "evt-1",
        "test_id": "t1",
        "outcome": "WIN",
        "pairing_valid": True,
        "exclusion_reason": None,
        "pnl_candidate": 1.0,
        "pnl_baseline": 0.0,
        "mae_candidate": 0.1,
        "mae_baseline": 0.2,
        "mae_protocol_id": MAE_PROTOCOL_ID,
        "candidate_passes_risk": True,
    }
    r1 = append_outcome_record(rec, test_id="t1", artifacts_dir=ad)
    assert r1["status"] == "appended"
    r2 = append_outcome_record(rec, test_id="t1", artifacts_dir=ad)
    assert r2["status"] == "duplicate_noop"
    audit = (ad / "t1" / "duplicate_audit.jsonl").read_text(encoding="utf-8").strip()
    assert "idempotent_duplicate" in audit


def test_duplicate_corruption(tmp_path: Path) -> None:
    ad = tmp_path / "art2"
    base = {
        "market_event_id": "evt-2",
        "test_id": "t2",
        "outcome": "WIN",
        "pairing_valid": True,
        "exclusion_reason": None,
        "pnl_candidate": 1.0,
        "pnl_baseline": 0.0,
        "mae_candidate": 0.1,
        "mae_baseline": 0.2,
        "mae_protocol_id": MAE_PROTOCOL_ID,
        "candidate_passes_risk": True,
    }
    append_outcome_record(dict(base), test_id="t2", artifacts_dir=ad)
    bad = dict(base)
    bad["pnl_candidate"] = 2.0
    with pytest.raises(CorruptionError):
        append_outcome_record(bad, test_id="t2", artifacts_dir=ad)


def test_commit_outcome_advances_sprt(tmp_path: Path) -> None:
    cal = CalibrationReport(
        protocol_id="p1",
        p0=0.4,
        p1=0.6,
        alpha=0.05,
        beta=0.10,
        n_min=2,
        batch_size=2,
        epsilon=0.25,
        mae_protocol_id=MAE_PROTOCOL_ID,
    )
    ad = tmp_path / "art3"
    for i, oc in enumerate(("WIN", "NOT_WIN")):
        rec = {
            "market_event_id": f"e{i}",
            "test_id": "t3",
            "outcome": oc,
            "pairing_valid": True,
            "exclusion_reason": None,
            "pnl_candidate": 1.0,
            "pnl_baseline": 0.0,
            "mae_candidate": 0.1,
            "mae_baseline": 0.2,
            "mae_protocol_id": MAE_PROTOCOL_ID,
            "candidate_passes_risk": True,
        }
        out = commit_outcome(test_id="t3", record=rec, calibration=cal, artifacts_dir=ad)
        assert out["append"]["status"] == "appended"
        adv = out["sprt_advance"]
        assert adv is not None
        if i == 1:
            assert adv["evaluated"] is True
            assert adv["wilson"] is not None


def test_patterns_cusum_monitor() -> None:
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0, 1, 40), rng.normal(2, 1, 40)])
    cus = run_cusum_monitor(x, reference_mean=0.0, sigma=1.0, k=0.5, h=5.0)
    assert "cusum_pos_max" in cus


def test_patterns_pelt_requires_ruptures() -> None:
    """PELT needs optional ``ruptures`` (see requirements.txt); skipped if not installed."""
    pytest.importorskip("ruptures")
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0, 1, 40), rng.normal(2, 1, 40)])
    pelt = run_pelt_changepoints(x, penalty=3.0)
    assert pelt["method"] == "PELT"


def test_build_outcome_pair(tmp_path: Path) -> None:
    db = _mk_market_db(tmp_path)
    b = {
        "trade_id": "b1",
        "lane": "baseline",
        "mode": "paper",
        "market_event_id": "e1",
        "symbol": "SOL-PERP",
        "side": "long",
        "entry_price": 100.0,
        "exit_price": 101.0,
        "size": 1.0,
        "entry_time": "2025-01-01T10:00:00+00:00",
        "exit_time": "2025-01-01T10:10:00+00:00",
    }
    c = dict(b)
    c["lane"] = "anna"
    c["trade_id"] = "c1"
    c["exit_price"] = 102.0
    r = build_outcome_record(
        test_id="tx",
        market_event_id="e1",
        baseline_row=b,
        candidate_row=c,
        epsilon=1.0,
        mae_protocol_id=MAE_PROTOCOL_ID,
        market_db_path=db,
    )
    assert r["outcome"] == "WIN"
