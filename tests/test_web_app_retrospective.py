"""Pattern game web: retrospective log API."""

from __future__ import annotations

from renaissance_v4.game_theory.web_app import create_app


def test_retrospective_log_get_empty() -> None:
    app = create_app()
    c = app.test_client()
    r = c.get("/api/retrospective-log?limit=5")
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("ok") is True
    assert isinstance(j.get("entries"), list)
