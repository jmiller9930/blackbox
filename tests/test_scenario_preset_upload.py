"""Tests for scenario preset upload/rename API (pattern game web UI)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest


def _minimal_valid_scenarios() -> list[dict]:
    return [
        {
            "scenario_id": "upload_test_scenario",
            "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
            "agent_explanation": {"hypothesis": "Test hypothesis for upload."},
        }
    ]


@pytest.fixture
def preset_upload_env(monkeypatch, tmp_path: Path):
    (tmp_path / "examples").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("renaissance_v4.game_theory.web_app._GAME_THEORY", tmp_path)
    from renaissance_v4.game_theory.web_app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app, tmp_path


def test_scenario_preset_upload_invalid_json(preset_upload_env):
    app, _tmp = preset_upload_env
    client = app.test_client()
    r = client.post(
        "/api/scenario-preset-upload",
        data={
            "preset_name": "My Preset",
            "file": (io.BytesIO(b"not json"), "x.json"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    body = r.get_json()
    assert body is not None
    assert body.get("ok") is False


def test_scenario_preset_upload_valid_writes_file(preset_upload_env):
    app, tmp = preset_upload_env
    client = app.test_client()
    body = json.dumps(_minimal_valid_scenarios())
    r = client.post(
        "/api/scenario-preset-upload",
        data={
            "preset_name": "My Preset",
            "file": (io.BytesIO(body.encode("utf-8")), "s.json"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j is not None
    assert j.get("ok") is True
    assert j.get("filename") == "user_my_preset.json"
    out = tmp / "examples" / "user_my_preset.json"
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    assert loaded[0]["scenario_id"] == "upload_test_scenario"


def test_scenario_preset_upload_duplicate_409(preset_upload_env):
    app, tmp = preset_upload_env
    (tmp / "examples" / "user_my_preset.json").write_text("[]\n", encoding="utf-8")
    client = app.test_client()
    body = json.dumps(_minimal_valid_scenarios())
    r = client.post(
        "/api/scenario-preset-upload",
        data={
            "preset_name": "My Preset",
            "file": (io.BytesIO(body.encode("utf-8")), "s.json"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 409


def test_scenario_preset_rename_user_file(preset_upload_env):
    app, tmp = preset_upload_env
    old = tmp / "examples" / "user_old_name.json"
    old.write_text(json.dumps(_minimal_valid_scenarios(), indent=2) + "\n", encoding="utf-8")
    client = app.test_client()
    r = client.post(
        "/api/scenario-preset-rename",
        json={"old_filename": "user_old_name.json", "new_preset_name": "New Display Name"},
        content_type="application/json",
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j is not None and j.get("ok") is True
    assert j.get("filename") == "user_new_display_name.json"
    assert not old.is_file()
    assert (tmp / "examples" / "user_new_display_name.json").is_file()
