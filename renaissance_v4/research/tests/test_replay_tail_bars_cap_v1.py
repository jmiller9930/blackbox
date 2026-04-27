"""replay_max_bars_v1 / load_replay_pre_loop_bars_v1 tail cap (RM preflight bounded tape)."""

from __future__ import annotations

from renaissance_v4.research.replay_runner import MIN_ROWS_REQUIRED, load_replay_pre_loop_bars_v1


def test_load_replay_pre_loop_bars_tail_cap_trims_leading() -> None:
    rows300 = [("SYM", i * 300_000, 1.0, 1.0, 1.0, 1.0, 1.0) for i in range(300)]

    class Conn:
        def execute(self, *_a: object, **_k: object) -> Conn:
            return self

        def fetchall(self) -> list[tuple[object, ...]]:
            return rows300

    out, audit, ctf = load_replay_pre_loop_bars_v1(
        Conn(),
        bar_window_calendar_months=None,
        candle_timeframe_minutes=None,
        verbose=False,
        replay_max_bars_v1=120,
    )
    assert len(out) == 120
    trim = audit.get("replay_tail_bars_trim_v1") or {}
    assert trim.get("dropped_leading_bars_v1") == 180
    assert trim.get("replay_max_bars_effective_v1") == 120
    assert ctf is None


def test_load_replay_pre_loop_bars_tail_cap_respects_min_rows() -> None:
    rows200 = [("SYM", i * 300_000, 1.0, 1.0, 1.0, 1.0, 1.0) for i in range(200)]

    class Conn:
        def execute(self, *_a: object, **_k: object) -> Conn:
            return self

        def fetchall(self) -> list[tuple[object, ...]]:
            return rows200

    out, audit, _ctf = load_replay_pre_loop_bars_v1(
        Conn(),
        bar_window_calendar_months=None,
        candle_timeframe_minutes=None,
        verbose=False,
        replay_max_bars_v1=30,
    )
    assert len(out) == MIN_ROWS_REQUIRED
    trim = audit.get("replay_tail_bars_trim_v1") or {}
    assert trim.get("replay_max_bars_effective_v1") == MIN_ROWS_REQUIRED
