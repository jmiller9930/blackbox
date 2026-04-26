#!/usr/bin/env python3
"""
Print Baseline vs Student operator Markdown report to stdout.

Uses the same logic as ``GET /api/operator-report/baseline-vs-student`` on the Pattern Game host.

Examples (from repo root, same host as Flask / scorecard):

  export PYTHONPATH=.
  python3 scripts/operator_ab_report_v1.py --job-a JOB_BASELINE --job-b JOB_STUDENT

  python3 scripts/operator_ab_report_v1.py --job-a JOB_A --job-b JOB_B --run-a-job-id JOB_A \\
    --out /tmp/ab_report.md

Optional remote (HTTP GET to an already-running Pattern Game):

  python3 scripts/operator_ab_report_v1.py --base-url http://clawbot.a51.corp:8765 --job-a ... --job-b ...
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _main() -> int:
    p = argparse.ArgumentParser(description="Operator Baseline vs Student A/B Markdown report")
    p.add_argument("--job-a", required=True, help="Baseline run job_id (A)")
    p.add_argument("--job-b", required=True, help="Student run job_id (B)")
    p.add_argument("--run-a-job-id", default="", help="Optional 026C Run-A producer job_id (passed to debug trace)")
    p.add_argument(
        "--base-url",
        default="",
        help="If set, fetch GET {base}/api/operator-report/baseline-vs-student?... instead of in-process",
    )
    p.add_argument("--out", default="", help="Write Markdown to this path (default: stdout)")
    args = p.parse_args()

    if str(args.base_url or "").strip():
        base = str(args.base_url).rstrip("/")
        q = f"?job_a={urllib.parse.quote(args.job_a, safe='')}&job_b={urllib.parse.quote(args.job_b, safe='')}"
        if str(args.run_a_job_id or "").strip():
            q += f"&run_a_job_id={urllib.parse.quote(str(args.run_a_job_id).strip(), safe='')}"
        url = base + "/api/operator-report/baseline-vs-student" + q
        try:
            req = urllib.request.Request(url, method="GET", headers={"Accept": "text/markdown"})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            err_b = e.read().decode("utf-8", errors="replace")
            print(f"HTTP {e.code}: {err_b}", file=sys.stderr)
            return 1
        except OSError as e:
            print(str(e), file=sys.stderr)
            return 1
    else:
        repo = Path(__file__).resolve().parents[1]
        os.chdir(repo)
        if not os.environ.get("PYTHONPATH"):
            os.environ["PYTHONPATH"] = str(repo)
        from renaissance_v4.game_theory.operator_ab_report_v1 import (
            build_operator_baseline_vs_student_report_markdown_v1,
        )

        body = build_operator_baseline_vs_student_report_markdown_v1(
            job_id_baseline=str(args.job_a).strip(),
            job_id_student=str(args.job_b).strip(),
            run_a_job_id=str(args.run_a_job_id).strip() or None,
        )

    if str(args.out or "").strip():
        Path(args.out).write_text(body, encoding="utf-8")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
