"""DEV stub — post-certification trade_strategy API (HTTP smoke)."""

from __future__ import annotations

import json

from renaissance_v4.game_theory.web_app import create_app


def test_trade_strategy_stub_get_list() -> None:
    app = create_app()
    c = app.test_client()
    r = c.get("/api/trade-strategy")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data.get("ok") is True
    assert data.get("stub") is True
    assert data.get("schema") == "trade_strategy_v1_dev_stub"

    r2 = c.get("/api/v1/trade-strategy")
    assert r2.status_code == 200
    assert json.loads(r2.data).get("schema") == "trade_strategy_v1_dev_stub"


def test_trade_strategy_stub_contract() -> None:
    app = create_app()
    c = app.test_client()
    r = c.get("/api/v1/trade-strategy/contract")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data.get("schema") == "trade_strategy_api_contract_v1_dev_stub"
    assert "/api/v1/trade-strategy" in (data.get("base_paths") or [])


def test_trade_strategy_stub_get_one() -> None:
    app = create_app()
    c = app.test_client()
    r = c.get("/api/trade-strategy/stub_post_cert_default")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data.get("strategy_id") == "stub_post_cert_default"


def test_trade_strategy_stub_export_download() -> None:
    app = create_app()
    c = app.test_client()
    r = c.get("/api/trade-strategy/stub_post_cert_default/export")
    assert r.status_code == 200
    assert "attachment" in (r.headers.get("Content-Disposition") or "").lower()
    assert "trade_strategy_" in (r.headers.get("Content-Disposition") or "")
    data = json.loads(r.data.decode("utf-8"))
    assert data.get("schema") == "trade_strategy_export_v1_dev_stub"
    assert data.get("strategy_id") == "stub_post_cert_default"
    assert "strategy_document" in data

    r2 = c.get("/api/v1/trade-strategy/stub_post_cert_default/export")
    assert r2.status_code == 200
    assert json.loads(r2.data.decode("utf-8")).get("schema") == "trade_strategy_export_v1_dev_stub"


def test_trade_strategy_stub_post_patch() -> None:
    app = create_app()
    c = app.test_client()
    r = c.post("/api/trade-strategy", json={"foo": 1})
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data.get("stub") is True
    assert "foo" in (data.get("echo_keys") or [])

    r2 = c.patch("/api/trade-strategy/stub_post_cert_default", json={"bar": 2})
    assert r2.status_code == 200
    data2 = json.loads(r2.data)
    assert data2.get("stub") is True
    assert "bar" in (data2.get("echo_keys") or [])
