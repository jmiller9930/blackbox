"""Layer 3 approval interface — decision POST only; no execution_plane / messaging."""

from __future__ import annotations

import ast
import json
import sys
from io import BytesIO
from pathlib import Path

import pytest
from wsgiref.util import setup_testing_defaults

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "scripts" / "runtime"
sys.path.insert(0, str(RUNTIME))

from approval_interface.app import make_app
from learning_core.approval_model import STATUS_DEFERRED, create_approval_request, get_approval
from learning_core.remediation_validation import open_validation_sandbox
from playground.run_data_pipeline import run_data_pipeline


def _seed(tmp_path: Path) -> tuple[Path, str, str]:
    sb = tmp_path / "l3.db"
    r = run_data_pipeline(
        sandbox_db=sb,
        issue_db=None,
        replay_remediation_id=None,
        seed_demo=True,
        step_mode=False,
        quiet=True,
    )
    assert r["ok"] is True
    rid = str(r["remediation_id"])
    conn = open_validation_sandbox(sb)
    try:
        row = create_approval_request(conn, source_remediation_id=rid, requested_by="pytest")
        aid = str(row["approval_id"])
    finally:
        conn.close()
    return sb, rid, aid


def _call(
    app,
    path: str,
    method: str = "GET",
    body: bytes = b"",
    *,
    token: str | None = None,
) -> tuple[str, bytes]:
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "SCRIPT_NAME": "",
        "QUERY_STRING": "",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": BytesIO(body),
        "wsgi.errors": BytesIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": True,
        "CONTENT_LENGTH": str(len(body)),
    }
    if token:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    setup_testing_defaults(environ)
    status_holder: list[str] = []

    def start_response(status: str, _headers: list) -> None:
        status_holder.append(status)

    out = b"".join(app(environ, start_response))
    return status_holder[0], out


def test_post_defer_with_token(tmp_path: Path) -> None:
    sb, _rid, aid = _seed(tmp_path)
    tok = "test-secret-token"
    app = make_app(sb, decision_token=tok)
    body = json.dumps({"action": "defer", "actor": "op1", "reason": "review later"}).encode()
    status, resp = _call(app, f"/api/approvals/{aid}/decision", method="POST", body=body, token=tok)
    assert status.startswith("200")
    data = json.loads(resp.decode())
    assert data["ok"] is True
    assert data["approval"]["status"] == STATUS_DEFERRED

    conn = open_validation_sandbox(sb)
    try:
        row = get_approval(conn, aid)
        assert row is not None
        assert row["status"] == STATUS_DEFERRED
    finally:
        conn.close()


def test_post_without_token_401(tmp_path: Path) -> None:
    sb, _rid, aid = _seed(tmp_path)
    app = make_app(sb, decision_token="secret")
    body = json.dumps({"action": "reject", "actor": "x"}).encode()
    status, _resp = _call(app, f"/api/approvals/{aid}/decision", method="POST", body=body, token=None)
    assert status.startswith("401")


def test_approval_interface_forbidden_imports() -> None:
    path = RUNTIME / "approval_interface" / "app.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    banned = {"telegram_interface", "messaging_interface", "execution_plane", "data_status"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.add(a.name.split(".")[0])
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    assert banned.isdisjoint(found)
