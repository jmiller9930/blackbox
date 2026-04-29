"""GT059 — EV proxy from signal rows."""

from types import SimpleNamespace

from renaissance_v4.game_theory.gt059_precision_gate_v1 import (
    gt059_ev_best_proxy_from_signal_results_v1,
)


def test_ev_proxy_aligns_direction() -> None:
    rows = [
        SimpleNamespace(active=True, direction="long", expected_edge=0.02),
        SimpleNamespace(active=True, direction="short", expected_edge=0.99),
    ]
    assert gt059_ev_best_proxy_from_signal_results_v1(rows, entry_direction="long") == 0.02
