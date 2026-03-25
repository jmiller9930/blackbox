"""Layer 2 operator dashboard — read-only proof (no writes, no banned imports)."""

from __future__ import annotations

import ast
import json
import sqlite3
import sys
from io import BytesIO
from pathlib import Path

import pytest
from wsgiref.util import setup_testing_defaults

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "scripts" / "runtime"
sys.path.insert(0, str(RUNTIME))

from operator_dashboard.app import make_app
from operator_dashboard.queries import fetch_pipeline_runs
from operator_dashboard.readonly_db import open_sandbox_readonly
from playground.run_data_pipeline import run_data_pipeline


def _wsgi_get(app, path: str, method: str = "GET") -> tuple[str, bytes]:
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "SCRIPT_NAME": "",
        "QUERY_STRING": "",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": BytesIO(b""),
        "wsgi.errors": BytesIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": True,
    }
    setup_testing_defaults(environ)
    status_holder: list[str] = []

    def start_response(status: str, _headers: list) -> None:
        status_holder.append(status)

    body = b"".join(app(environ, start_response))
    return status_holder[0], body


def _seed_sandbox(tmp_path: Path) -> Path:
    sb = tmp_path / "dash.db"
    r = run_data_pipeline(
        sandbox_db=sb,
        issue_db=None,
        replay_remediation_id=None,
        seed_demo=True,
        step_mode=False,
        quiet=True,
    )
    assert r["ok"] is True
    return sb


def test_readonly_connection_rejects_write(tmp_path: Path) -> None:
    sb = _seed_sandbox(tmp_path)
    conn = open_sandbox_readonly(sb)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO remediation_candidates (remediation_id) VALUES ('x')")
    finally:
        conn.close()


def test_queries_no_write_strings() -> None:
    path = RUNTIME / "operator_dashboard" / "queries.py"
    text = path.read_text(encoding="utf-8")
    assert "INSERT " not in text.upper()
    assert "UPDATE " not in text.upper()
    assert "DELETE " not in text.upper()
    assert "REPLACE " not in text.upper()


def test_api_get_all_json(tmp_path: Path) -> None:
    sb = _seed_sandbox(tmp_path)
    app = make_app(sb)
    status, body = _wsgi_get(app, "/api/all")
    assert status.startswith("200")
    data = json.loads(body.decode("utf-8"))
    assert data["ok"] is True
    assert len(data["pipeline_runs"]) >= 1
    assert len(data["validation_runs"]) >= 1
    assert len(data["simulations"]) >= 1


def test_wsgi_post_rejected(tmp_path: Path) -> None:
    sb = _seed_sandbox(tmp_path)
    app = make_app(sb)
    status, _body = _wsgi_get(app, "/api/all", method="POST")
    assert status.startswith("405")


def test_dashboard_forbidden_imports() -> None:
    for name in ("app.py", "readonly_db.py", "__main__.py"):
        path = RUNTIME / "operator_dashboard" / name
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


def test_pipeline_runs_seven_stages(tmp_path: Path) -> None:
    sb = _seed_sandbox(tmp_path)
    conn = open_sandbox_readonly(sb)
    try:
        runs = fetch_pipeline_runs(conn)
        assert len(runs) >= 1
        r0 = runs[0]
        assert len(r0["stages"]) == 7
        names = [s["name"] for s in r0["stages"]]
        assert names == ["DETECT", "SUGGEST", "INGEST", "VALIDATE", "ANALYZE", "PATTERN", "SIMULATE"]
    finally:
        conn.close()
