"""E2E Step 4 — SR-4 / AC-3: Student primary, engine/DCR surfaces labeled secondary (HTML contract)."""

from __future__ import annotations

from renaissance_v4.game_theory.web_app import PATTERN_GAME_WEB_UI_VERSION, create_app


def test_index_html_student_primary_terminal_secondary_labeled() -> None:
    app = create_app()
    rv = app.test_client().get("/")
    assert rv.status_code == 200
    html = rv.data.decode("utf-8")
    assert "Student → learning → outcome" in html
    assert "Primary surface" in html
    assert "pg-secondary-surface-label" in html
    assert "Secondary" in html
    assert "Terminal" in html
    assert "Decision Context Recall" in html or "DCR" in html
    assert "Score card" in html
    assert "batch history" in html.lower()
    assert PATTERN_GAME_WEB_UI_VERSION in html


def test_capabilities_includes_ui_version() -> None:
    app = create_app()
    rv = app.test_client().get("/api/capabilities")
    assert rv.status_code == 200
    j = rv.get_json()
    assert j.get("pattern_game_web_ui_version") == PATTERN_GAME_WEB_UI_VERSION
