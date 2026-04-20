"""E2E Step 5 — AC-5: UI copy does not conflate DCR/engine memory with Student Proctor; clearing paths are explicit."""

from __future__ import annotations

from renaissance_v4.game_theory.web_app import PATTERN_GAME_WEB_UI_VERSION, create_app


def test_index_html_ac5_truth_separation_strings() -> None:
    app = create_app()
    rv = app.test_client().get("/")
    assert rv.status_code == 200
    html = rv.data.decode("utf-8")

    # Primary vs engine/DCR (Step 4 overlap — still required for AC-5 context)
    assert "Not engine DCR" in html
    assert "not the student learning store" in html.lower()

    # Scorecard: Student store called out as separate from batch log
    assert "Student learning store is separate" in html
    assert "Student Proctor learning store" in html
    assert "separate file from the scorecard log" in html

    # Destructive-action confirmations (embedded in page script)
    assert "batch_scorecard.jsonl" in html
    assert "Student Proctor learning store are not cleared" in html
    assert "does NOT clear the scorecard" in html
    assert "Student Proctor learning store" in html  # reset-learning confirm
    assert "Scorecard history and engine learning files will not be changed" in html

    # Harness vs Student — scorecard summary heading (2.14.1+)
    assert "(engine / DCR; not the Student Proctor store)" in html
    assert "not Student Proctor learning" in html

    # Tooltips on the three clear/reset controls
    assert 'id="clearScorecardBtn"' in html and "Does not clear engine memory" in html
    assert 'id="resetLearningStateBtn"' in html and "Does not clear the scorecard file" in html
    assert 'id="clearStudentProctorStoreBtn"' in html and "Does not clear scorecard history" in html

    assert PATTERN_GAME_WEB_UI_VERSION in html
