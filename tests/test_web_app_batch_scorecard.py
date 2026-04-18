"""Pattern game web: batch scorecard API."""

from __future__ import annotations

from renaissance_v4.game_theory.web_app import create_app


def test_batch_scorecard_get_empty() -> None:
    app = create_app()
    c = app.test_client()
    r = c.get("/api/batch-scorecard?limit=5")
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("ok") is True
    assert "path" in j
    assert "entries" in j
    assert isinstance(j["entries"], list)
