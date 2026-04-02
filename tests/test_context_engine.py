"""Context engine — storage guards, append store, status, consumer policy, API wiring."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.context_engine.consumer import validate_bundle_for_agent  # noqa: E402
from modules.context_engine.paths import ContextPathError, resolve_context_root, safe_relative_file, validate_path_under_root  # noqa: E402
from modules.context_engine.status import build_context_engine_status, record_api_probe  # noqa: E402
from modules.context_engine.store import append_event, read_recent_events  # noqa: E402


def test_path_guard_rejects_escape_outside_mount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ctx"
    root.mkdir()
    monkeypatch.setenv("BLACKBOX_CONTEXT_ROOT", str(root))
    evil = Path("/etc/passwd")
    with pytest.raises(ContextPathError):
        validate_path_under_root(root, evil)
    with pytest.raises(ContextPathError):
        safe_relative_file(root, "..", "x")


def test_append_and_status_healthy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ce"
    monkeypatch.setenv("BLACKBOX_CONTEXT_ROOT", str(root))
    monkeypatch.delenv("BLACKBOX_CONTEXT_ENGINE_DISABLE", raising=False)
    append_event(None, "test_event", {"k": "v"}, repo_root=tmp_path)
    record_api_probe(tmp_path)
    st = build_context_engine_status(tmp_path)
    assert st["status"] == "healthy"
    assert st["reason_code"] == "CTX-ENGINE-OK"
    assert st.get("freshness_seconds") is not None
    rows, corr = read_recent_events(resolve_context_root(tmp_path), limit=10)
    assert corr is None
    assert len(rows) >= 1
    kinds = {r.get("kind") for r in rows}
    assert "test_event" in kinds or "runtime_api_probe" in kinds


def test_corrupt_jsonl_surfaces_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ce2"
    root.mkdir(parents=True)
    monkeypatch.setenv("BLACKBOX_CONTEXT_ROOT", str(root))
    (root / "events.jsonl").write_text('{"seq":1,"bad":}\n', encoding="utf-8")
    (root / "heartbeat.json").write_text('{"last_seq":1,"last_heartbeat_at":"2026-01-01T00:00:00+00:00"}\n', encoding="utf-8")
    st = build_context_engine_status(tmp_path)
    assert st["status"] == "error"
    assert st["reason_code"] == "CTX-STORE-CORRUPT"


def test_consumer_bundle_engaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg = json.loads((REPO / "agents" / "agent_registry.json").read_text(encoding="utf-8"))
    bundle = {
        "kind": "context_bundle_v1",
        "validation_state": "approved",
        "record_class": "registry_identity_slice",
        "issued_at_utc": "2099-01-01T00:00:00+00:00",
        "sections": {},
    }
    ok, reason = validate_bundle_for_agent(bundle, agent_id="anna", registry=reg)
    assert ok and reason == ""


def test_consumer_rejects_wrong_class(tmp_path: Path) -> None:
    reg = json.loads((REPO / "agents" / "agent_registry.json").read_text(encoding="utf-8"))
    bundle = {
        "kind": "context_bundle_v1",
        "validation_state": "approved",
        "record_class": "definitely_not_allowed_class",
        "issued_at_utc": "2099-01-01T00:00:00+00:00",
    }
    ok, reason = validate_bundle_for_agent(bundle, agent_id="anna", registry=reg)
    assert not ok
    assert "record_class" in reason


def _load_context_ledger_consumer():
    import importlib.util

    path = REPO / "scripts" / "runtime" / "anna_modules" / "context_ledger_consumer.py"
    spec = importlib.util.spec_from_file_location("context_ledger_consumer_standalone", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_context_bundle_attachment_path_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_context_ledger_consumer()

    root = tmp_path / "mount"
    root.mkdir()
    monkeypatch.setenv("BLACKBOX_CONTEXT_ROOT", str(root))
    bad = tmp_path / "secret.json"
    bad.write_text("{}", encoding="utf-8")
    att = mod.resolve_context_bundle_attachment(None, bad, "anna", registry_path=REPO / "agents" / "agent_registry.json")
    assert att is not None
    assert att.get("consumption") == "rejected"
    assert "CTX-GUARD-REJECT" in str(att.get("reason", ""))


def test_resolve_context_bundle_attachment_ok_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_context_ledger_consumer()

    root = tmp_path / "mount"
    root.mkdir()
    monkeypatch.setenv("BLACKBOX_CONTEXT_ROOT", str(root))
    bdir = root / "bundles"
    bdir.mkdir()
    p = bdir / "b.json"
    p.write_text(
        json.dumps(
            {
                "kind": "context_bundle_v1",
                "validation_state": "approved",
                "record_class": "registry_identity_slice",
                "issued_at_utc": "2099-06-01T00:00:00+00:00",
                "sections": {"x": 1},
            }
        ),
        encoding="utf-8",
    )
    att = mod.resolve_context_bundle_attachment(None, p, "anna", registry_path=REPO / "agents" / "agent_registry.json")
    assert att is not None
    assert att.get("consumption") == "engaged"


def test_api_server_defines_context_engine_route() -> None:
    text = (REPO / "UIUX.Web" / "api_server.py").read_text(encoding="utf-8")
    assert 'path == "/api/v1/context-engine/status"' in text
    assert "build_context_engine_status" in text


def test_internal_html_context_engine_pill() -> None:
    text = (REPO / "UIUX.Web" / "internal.html").read_text(encoding="utf-8")
    assert "context-engine-pill" in text
    assert "/api/v1/context-engine/status" in text


def test_status_disabled_unknown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BLACKBOX_CONTEXT_ENGINE_DISABLE", "1")
    st = build_context_engine_status(tmp_path)
    assert st["status"] == "unknown"
    assert st["reason_code"] == "CTX-ENGINE-DISABLED"
