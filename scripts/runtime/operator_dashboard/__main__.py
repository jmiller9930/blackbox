"""Run Layer 2 read-only dashboard: python -m operator_dashboard --sandbox-db PATH"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1]
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from wsgiref.simple_server import make_server

from operator_dashboard.app import make_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BLACKBOX Layer 2 — read-only operator dashboard (sandbox SQLite only).",
    )
    parser.add_argument(
        "--sandbox-db",
        type=Path,
        required=True,
        help="Path to sandbox SQLite (same validation sandbox as Playground).",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    app = make_app(args.sandbox_db)
    server = make_server(args.host, args.port, app)
    print(
        f"Layer 2 dashboard (READ ONLY) — http://{args.host}:{args.port}/\n"
        f"sandbox-db: {args.sandbox_db.resolve()}\n"
        "GET only — no writes, no approval, no execution.",
        file=sys.stderr,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
