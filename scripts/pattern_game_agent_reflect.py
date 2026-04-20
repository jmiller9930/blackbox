#!/usr/bin/env python3
"""
Pattern game — **reflect bundle** for Anna / operators: scorecard + hunter next batch.

Prints JSON (default) or ``--prompt`` markdown for pasting into an LLM. Optionally **POST** a parallel
run to the local web UI — **disabled by default**; requires explicit env (see below).

**Does not** implement an autonomous loop. Use for: review → decide → run again (or gate submit).

Env for HTTP submit (all required):
  ANNA_PATTERN_GAME_SUBMIT=1
  PATTERN_GAME_BASE_URL   — e.g. http://127.0.0.1:8765 (no trailing slash)
  Optional: PATTERN_GAME_SUBMIT_WORKERS — max_workers (default: min(8, scenario count))
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from renaissance_v4.game_theory.agent_reflect_bundle import build_agent_reflect_bundle  # noqa: E402
from renaissance_v4.game_theory.pml_proof_stdio import (  # noqa: E402
    add_proof_stdio_flags,
    begin_pml_proof_stdio,
    proof_json_out,
    raw_stdout_selected,
)


def _maybe_post_parallel(base_url: str, bundle: dict[str, Any], max_workers: int | None) -> dict[str, Any]:
    hunter = bundle.get("hunter_suggestion") or {}
    if not hunter.get("ok") or not hunter.get("scenarios"):
        return {"ok": False, "error": "No scenarios to submit — fix hunter suggestion or manifest path."}
    scenarios = hunter["scenarios"]
    mw = max_workers if max_workers is not None else min(len(scenarios), 8)
    mw = max(1, min(mw, 64))
    body_obj: dict[str, Any] = {
        "scenarios_json": json.dumps(scenarios, ensure_ascii=False),
        "max_workers": mw,
        "log_path": True,
    }
    url = base_url.rstrip("/") + "/api/run-parallel/start"
    data = json.dumps(body_obj).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {"ok": False, "error": "empty response"}
    except HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {"ok": False, "error": f"HTTP {e.code}: {err_body[:2000]}"}
    except URLError as e:
        return {"ok": False, "error": f"URL error: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Pattern game reflect bundle (scorecard + hunter).")
    ap.add_argument("--repo", type=Path, default=None, help="Repo root (default: auto)")
    ap.add_argument("--prompt", action="store_true", help="Print prompt_block markdown only (stdout)")
    ap.add_argument(
        "--submit",
        action="store_true",
        help="POST /api/run-parallel/start using hunter scenarios (requires ANNA_PATTERN_GAME_SUBMIT=1 and PATTERN_GAME_BASE_URL)",
    )
    ap.add_argument("--workers", type=int, default=None, help="max_workers for submit (optional)")
    add_proof_stdio_flags(ap)
    args = ap.parse_args()
    begin_pml_proof_stdio("pattern_game_agent_reflect", raw_stdout=raw_stdout_selected(args))

    bundle = build_agent_reflect_bundle(repo_root=args.repo)
    raw = raw_stdout_selected(args)
    if args.prompt:
        if raw:
            print(bundle.get("prompt_block", ""), end="")
        else:
            from renaissance_v4.game_theory.pml_runtime_layout import proof_rotating_log_path

            pb = str(bundle.get("prompt_block", "") or "")
            cap = 6 * 1024 * 1024
            b = pb.encode("utf-8")
            if len(b) > cap:
                pb = b[:cap].decode("utf-8", errors="replace") + "\n[truncated]\n"
            p = proof_rotating_log_path("pattern_game_agent_reflect_prompt")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(pb, encoding="utf-8")
            proof_json_out({"ok": True, "prompt_saved_to": str(p), "chars": len(pb)})
        return 0

    if args.submit:
        if os.environ.get("ANNA_PATTERN_GAME_SUBMIT", "").strip() not in ("1", "true", "yes", "on"):
            print(
                "Refusing submit: set ANNA_PATTERN_GAME_SUBMIT=1 and PATTERN_GAME_BASE_URL.",
                file=sys.stderr,
            )
            return 2
        base = os.environ.get("PATTERN_GAME_BASE_URL", "").strip()
        if not base:
            print("Refusing submit: PATTERN_GAME_BASE_URL is empty.", file=sys.stderr)
            return 2
        out = _maybe_post_parallel(base, bundle, args.workers)
        proof_json_out(out)
        return 0 if out.get("ok") else 1

    proof_json_out(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
