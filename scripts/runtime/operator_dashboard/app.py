"""WSGI app — GET only, read-only sandbox queries. No writes, no POST."""

from __future__ import annotations

import json
import mimetypes
import re
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable
from .queries import (
    fetch_approvals,
    fetch_outcome_analyses,
    fetch_patterns,
    fetch_pipeline_runs,
    fetch_simulations,
    fetch_validation_runs,
)
from .readonly_db import open_sandbox_readonly

_STATIC = Path(__file__).resolve().parent / "static"


def _json_body(data: Any) -> bytes:
    return json.dumps(data, indent=2, default=str).encode("utf-8")


def make_app(sandbox_db: Path) -> Callable:
    sandbox_db = Path(sandbox_db).expanduser().resolve()

    def app(environ: dict, start_response: Callable) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        if method != "GET":
            start_response(
                f"{HTTPStatus.METHOD_NOT_ALLOWED.value} Method Not Allowed",
                [("Content-Type", "text/plain; charset=utf-8")],
            )
            return [b"GET only"]

        path = environ.get("PATH_INFO") or "/"

        if path == "/" or path == "/index.html":
            p = _STATIC / "index.html"
            if not p.is_file():
                start_response(f"{HTTPStatus.NOT_FOUND.value} Not Found", [("Content-Type", "text/plain")])
                return [b"missing static/index.html"]
            body = p.read_bytes()
            ctype = mimetypes.guess_type(str(p))[0] or "text/html"
            start_response(f"{HTTPStatus.OK.value} OK", [("Content-Type", f"{ctype}; charset=utf-8")])
            return [body]

        api_match = re.match(r"^/api/(pipeline-runs|validation-runs|outcome-analyses|patterns|simulations|approvals|all)$", path)
        if not api_match:
            start_response(f"{HTTPStatus.NOT_FOUND.value} Not Found", [("Content-Type", "text/plain")])
            return [b"not found"]

        conn = open_sandbox_readonly(sandbox_db)
        try:
            name = api_match.group(1)
            if name == "pipeline-runs":
                data = {"ok": True, "runs": fetch_pipeline_runs(conn)}
            elif name == "validation-runs":
                data = {"ok": True, "validation_runs": fetch_validation_runs(conn)}
            elif name == "outcome-analyses":
                data = {"ok": True, "outcome_analyses": fetch_outcome_analyses(conn)}
            elif name == "patterns":
                data = {"ok": True, "patterns": fetch_patterns(conn)}
            elif name == "simulations":
                data = {"ok": True, "simulations": fetch_simulations(conn)}
            elif name == "approvals":
                data = {"ok": True, "approvals": fetch_approvals(conn)}
            else:
                # /api/all — single round-trip for UI
                data = {
                    "ok": True,
                    "pipeline_runs": fetch_pipeline_runs(conn),
                    "validation_runs": fetch_validation_runs(conn),
                    "outcome_analyses": fetch_outcome_analyses(conn),
                    "patterns": fetch_patterns(conn),
                    "simulations": fetch_simulations(conn),
                    "approvals": fetch_approvals(conn),
                }
        finally:
            conn.close()

        body = _json_body(data)
        start_response(
            f"{HTTPStatus.OK.value} OK",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    return app
