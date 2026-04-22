"""
Post-certification **trade_strategy** — **DEV STUB** only.

Product intent (see ``docs/STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md`` §17):
after certification, the operator loads a **tradeable strategy** document from the UI; the
Student **uses** it (paper/live tier TBD), and may **propose updates** when a better variant exists.

This module returns **deterministic placeholder payloads** so the UI and ``curl`` proofs can wire
before persistence, validation, and execution are implemented.
"""

from __future__ import annotations

from typing import Any

SCHEMA = "trade_strategy_v1_dev_stub"


def stub_trade_strategy_list_v1() -> dict[str, Any]:
    return {
        "ok": True,
        "stub": True,
        "schema": SCHEMA,
        "note": "Post-cert trade_strategy list — not persisted; replace with store + auth.",
        "strategies": [
            {
                "strategy_id": "stub_post_cert_default",
                "title": "Stub post-cert strategy (dev)",
                "certification_echo": {"exam_pack_id": None, "version": None},
                "manifest_path": None,
                "updated_at_utc": None,
            }
        ],
    }


def stub_trade_strategy_get_v1(strategy_id: str) -> dict[str, Any]:
    sid = strategy_id.strip() or "stub_post_cert_default"
    return {
        "ok": True,
        "stub": True,
        "schema": SCHEMA,
        "strategy_id": sid,
        "title": "Stub post-cert strategy (dev)",
        "body": {
            "description": "Replace with operator-uploaded trade_strategy document (versioned).",
            "indicator_plan": [],
            "risk_plan": {},
        },
        "note": "No execution wiring — Referee / paper-live seam TBD.",
    }


def stub_trade_strategy_create_v1(body: dict[str, Any] | None) -> dict[str, Any]:
    _ = body
    return {
        "ok": True,
        "stub": True,
        "schema": SCHEMA,
        "strategy_id": "stub_upload_echo",
        "note": "POST accepted — not stored; wire persistence + catalog validation next.",
        "echo_keys": sorted(body.keys()) if isinstance(body, dict) else [],
    }


def stub_trade_strategy_update_v1(strategy_id: str, body: dict[str, Any] | None) -> dict[str, Any]:
    sid = strategy_id.strip() or "stub_post_cert_default"
    return {
        "ok": True,
        "stub": True,
        "schema": SCHEMA,
        "strategy_id": sid,
        "note": "PATCH accepted — not merged; wire diff + approval + versioning next.",
        "echo_keys": sorted(body.keys()) if isinstance(body, dict) else [],
    }


__all__ = [
    "SCHEMA",
    "stub_trade_strategy_create_v1",
    "stub_trade_strategy_get_v1",
    "stub_trade_strategy_list_v1",
    "stub_trade_strategy_update_v1",
]
