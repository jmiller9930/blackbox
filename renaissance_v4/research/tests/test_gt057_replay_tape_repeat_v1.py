"""GT057 — tape repetition for trade-density unlock (short fixture DBs)."""

from renaissance_v4.research.replay_runner import (
    _gt057_repeat_bar_rows_v1,
    _gt057_replay_tape_repeat_factor_v1,
)


def test_gt057_repeat_bar_rows_monotonic_times() -> None:
    base = [
        {"symbol": "SOLUSDT", "open_time": 1_000_000, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100.0},
        {"symbol": "SOLUSDT", "open_time": 1_000_300_000, "open": 1.05, "high": 1.2, "low": 1.0, "close": 1.1, "volume": 110.0},
    ]
    out = _gt057_repeat_bar_rows_v1(base, 3)
    assert len(out) == 6
    times = [int(r["open_time"]) for r in out]
    assert times == sorted(times)
    assert len(set(times)) == 6


def test_gt057_repeat_factor_defaults_without_env(monkeypatch) -> None:
    monkeypatch.delenv("GT057_REPLAY_TAPE_REPEAT_V1", raising=False)
    assert _gt057_replay_tape_repeat_factor_v1() == 1


def test_gt057_repeat_factor_parses_int(monkeypatch) -> None:
    monkeypatch.setenv("GT057_REPLAY_TAPE_REPEAT_V1", "5")
    assert _gt057_replay_tape_repeat_factor_v1() == 5
