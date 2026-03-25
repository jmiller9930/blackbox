"""Layer 3 WSGI — GET list/detail; POST decision only. No execution_plane, messaging, or pipeline calls."""

from __future__ import annotations

import json
import mimetypes
import re
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from learning_core.approval_model import (
    approve_pending,
    defer_pending,
    get_approval,
    list_approvals,
    reject_pending,
)
from learning_core.remediation_validation import assert_non_production_sqlite_path, open_validation_sandbox

from .context import fetch_approval_context

_STATIC = Path(__file__).resolve().parent / "static"


def _json(data: Any) -> bytes:
    return json.dumps(data, indent=2, default=str).encode("utf-8")


def _read_body(environ: dict) -> bytes:
    try:
        n = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        n = 0
    if n <= 0:
        return b""
    return environ["wsgi.input"].read(n)


def _token_ok(environ: dict, token: str) -> bool:
    if not token:
        return False
    auth = (environ.get("HTTP_AUTHORIZATION") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() == token
    return (environ.get("HTTP_X_APPROVAL_TOKEN") or "").strip() == token


def make_app(sandbox_db: Path, *, decision_token: str) -> Callable:
    sandbox_db = Path(sandbox_db).expanduser().resolve()
    token = (decision_token or "").strip()

    def app(environ: dict, start_response: Callable) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO") or "/"

        if path == "/" or path == "/index.html":
            p = _STATIC / "index.html"
            if not p.is_file():
                start_response(f"{HTTPStatus.NOT_FOUND.value} Not Found", [("Content-Type", "text/plain")])
                return [b"missing static/index.html"]
            body = p.read_bytes()
            ct = mimetypes.guess_type(str(p))[0] or "text/html"
            start_response(f"{HTTPStatus.OK.value} OK", [(f"Content-Type", f"{ct}; charset=utf-8")])
            return [body]

        assert_non_production_sqlite_path(sandbox_db)
        conn = open_validation_sandbox(sandbox_db)
        try:
            if method == "GET" and path == "/api/approvals":
                rows = list_approvals(conn)
                body = _json({"ok": True, "approvals": rows})
                start_response(
                    f"{HTTPStatus.OK.value} OK",
                    [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))],
                )
                return [body]

            m = re.match(r"^/api/approvals/([^/]+)$", path)
            if method == "GET" and m:
                aid = m.group(1)
                ctx = fetch_approval_context(conn, aid)
                if not ctx:
                    start_response(f"{HTTPStatus.NOT_FOUND.value} Not Found", [("Content-Type", "application/json")])
                    return [_json({"ok": False, "error": "approval not found"})]
                body = _json({"ok": True, **ctx})
                start_response(
                    f"{HTTPStatus.OK.value} OK",
                    [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))],
                )
                return [body]

            m2 = re.match(r"^/api/approvals/([^/]+)/decision$", path)
            if method == "POST" and m2:
                if not _token_ok(environ, token):
                    start_response(
                        f"{HTTPStatus.UNAUTHORIZED.value} Unauthorized",
                        [("Content-Type", "application/json; charset=utf-8")],
                    )
                    return [_json({"ok": False, "error": "missing or invalid decision token"})]
                aid = m2.group(1)
                if not get_approval(conn, aid):
                    start_response(f"{HTTPStatus.NOT_FOUND.value} Not Found", [("Content-Type", "application/json")])
                    return [_json({"ok": False, "error": "approval not found"})]
                raw = _read_body(environ)
                try:
                    payload = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    start_response(f"{HTTPStatus.BAD_REQUEST.value} Bad Request", [("Content-Type", "application/json")])
                    return [_json({"ok": False, "error": "invalid JSON"})]
                action = str(payload.get("action") or "").strip().lower()
                actor = str(payload.get("actor") or payload.get("approved_by") or "").strip()
                reason = payload.get("reason")
                reason_s = str(reason).strip() if reason is not None else None
                if not actor:
                    start_response(f"{HTTPStatus.BAD_REQUEST.value} Bad Request", [("Content-Type", "application/json")])
                    return [_json({"ok": False, "error": "actor required"})]
                try:
                    if action == "approve":
                        ttl = int(payload.get("ttl_hours") or 168)
                        out = approve_pending(
                            conn,
                            approval_id=aid,
                            approved_by=actor,
                            ttl_hours=ttl,
                            decision_note=reason_s,
                        )
                    elif action == "reject":
                        out = reject_pending(conn, approval_id=aid, approved_by=actor, decision_note=reason_s)
                    elif action == "defer":
                        out = defer_pending(conn, approval_id=aid, approved_by=actor, decision_note=reason_s)
                    else:
                        start_response(
                            f"{HTTPStatus.BAD_REQUEST.value} Bad Request",
                            [("Content-Type", "application/json; charset=utf-8")],
                        )
                        return [_json({"ok": False, "error": "action must be approve, reject, or defer"})]
                except ValueError as e:
                    start_response(f"{HTTPStatus.BAD_REQUEST.value} Bad Request", [("Content-Type", "application/json")])
                    return [_json({"ok": False, "error": str(e)})]
                body = _json({"ok": True, "approval": out})
                start_response(
                    f"{HTTPStatus.OK.value} OK",
                    [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))],
                )
                return [body]

            start_response(f"{HTTPStatus.NOT_FOUND.value} Not Found", [("Content-Type", "text/plain")])
            return [b"not found"]
        finally:
            conn.close()

    return app
