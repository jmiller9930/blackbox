from __future__ import annotations

from renaissance_v4.game_theory.module_board import compute_pattern_game_module_board


def test_promoted_bundle_module_row_has_no_groundhog_in_label() -> None:
    b = compute_pattern_game_module_board()
    mods = b.get("modules") or []
    prom = [m for m in mods if (m or {}).get("id") == "promoted_bundle"]
    assert prom, "promoted_bundle row missing"
    assert "groundhog" not in str(prom[0].get("label") or "").lower()
    assert str(prom[0].get("label") or "") == "Promoted memory bundle"
