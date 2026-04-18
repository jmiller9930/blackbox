"""Flask web_app preset endpoints (no server bind)."""

from __future__ import annotations

from renaissance_v4.game_theory.web_app import create_app


def test_scenario_presets_and_load() -> None:
    app = create_app()
    c = app.test_client()
    r = c.get("/api/scenario-presets")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert any(row.get("filename", "").endswith(".json") for row in data)

    name = next(row["filename"] for row in data if row["filename"].endswith(".json"))
    r2 = c.get("/api/scenario-preset?name=" + name)
    assert r2.status_code == 200
    body = r2.get_json()
    assert body.get("ok") is True
    assert body.get("content")
    assert "manifest_path" in body["content"] or "[" in body["content"]
