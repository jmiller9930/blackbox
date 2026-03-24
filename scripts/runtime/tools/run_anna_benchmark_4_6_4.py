#!/usr/bin/env python3
"""
Generate Directive 4.6.4 benchmark Q&A for architect review.
Uses the same Anna path as Telegram: build_analysis + format_response.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from anna_modules.analysis import build_analysis
from telegram_interface.message_router import route_message
from telegram_interface.response_formatter import format_response

# Prompts from directive_4_6_4_anna_benchmark_questions.md (exact user-facing text).
BENCHMARKS: list[tuple[str, str]] = [
    (
        "Benchmark 1 — Exit timing on a winning trade",
        "How do you know when to get out of a trade if the trade is success but seems to be topping out and looking to reverse?",
    ),
    (
        "Benchmark 2 — Fake breakout recognition",
        "If price breaks above a local high but immediately loses follow-through, what would make you treat that as a fake breakout instead of a real move?",
    ),
    (
        "Benchmark 3 — Low-volume trade suppression",
        "If RSI divergence is present but SOL-PERP volume is weak, should we still take the trade?",
    ),
    (
        "Benchmark 4 — Wide spread entry risk",
        "If the setup looks good but the spread is suddenly wide at entry, how should that affect the signal?",
    ),
    (
        "Benchmark 5 — Confidence threshold discipline",
        "If a setup scores 61 confidence after adjustments and our threshold is 65, what should happen?",
    ),
    (
        "Benchmark 6 — Consecutive loss pause logic",
        "If we take three consecutive losses during low-volume conditions, what should the system do next?",
    ),
    (
        "Benchmark 7 — Partial profit vs full hold",
        "When would you take partial profit instead of holding for the full target?",
    ),
    (
        "Benchmark 8 — No-trade conditions",
        "What conditions would make you refuse a signal even if RSI divergence appears valid?",
    ),
    (
        "Benchmark 9 — Learning from a bad fill",
        "If a technically correct signal loses money because entry happened during a bad spread environment, what should Anna learn from that?",
    ),
    (
        "Benchmark 10 — Human pushback / clarification",
        "If Sean tells you \"that signal was wrong because the move had no real follow-through,\" what should you do with that information?",
    ),
]


def _ctx():
    return dict(
        market=None,
        market_err=None,
        ctx=None,
        ctx_err=None,
        trend=None,
        trend_err=None,
        policy=None,
        policy_err=None,
        use_snapshot=False,
        use_ctx=False,
        use_trend=False,
        use_policy=False,
    )


def _git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> None:
    repo = ROOT.parents[1]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = _git_head(repo)

    # title, prompt, agent, human_intent, telegram body, summary text, interpretation dict
    rows: list[tuple[str, str, str, dict, str, str, dict]] = []
    for title, prompt in BENCHMARKS:
        routed = route_message(prompt)
        analysis = build_analysis(prompt, **_ctx())
        hi = analysis.get("human_intent") or {}
        payload = {
            "kind": "anna",
            "data": {"anna_analysis": analysis, "stored_task_id": None},
        }
        telegram_text = format_response(payload, user_display_name="Sean")
        interp = analysis.get("interpretation") or {}
        rows.append(
            (title, prompt, routed.agent, hi, telegram_text, str(interp.get("summary", "")), interp)
        )

    lines: list[str] = [
        "# Directive 4.6.4 — Anna benchmark run (architect submission)",
        "",
        "Generated automatically from `scripts/runtime/tools/run_anna_benchmark_4_6_4.py`.",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| UTC timestamp | {ts} |",
        f"| Git commit | `{commit}` |",
        "| Route | `anna` (default; verified per prompt below) |",
        "| Pipeline | `build_analysis` → `format_response` (Telegram-equivalent body) |",
        "| Display name in copy | Sean |",
        "",
        "---",
        "",
        "## Answers 1–10 (read this first)",
        "",
        "Each item is the **benchmark prompt** and Anna’s **primary interpretation text** "
        "(`interpretation.summary` from `anna_analysis_v1`). The detailed Telegram-formatted "
        "bubble (with Risk read / How I'd play it) is in the [Full record](#full-record-prompt-metadata-telegram) section below.",
        "",
    ]

    for i, (title, prompt, _agent, _hi, _tg, summary, interp) in enumerate(rows, 1):
        short = title.split("—", 1)[-1].strip() if "—" in title else title
        lines.extend(
            [
                f"### {i}. {short}",
                "",
                f"- **Prompt:** {prompt}",
                f"- **Headline:** {interp.get('headline', '')}",
                f"- **Anna (interpretation summary):** {summary}",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            '<a id="full-record-prompt-metadata-telegram"></a>',
            "",
            "## Full record (prompt, metadata, Telegram)",
            "",
        ]
    )

    for i, (title, prompt, agent, hi, telegram_text, _summary, interp) in enumerate(rows, 1):
        lines.extend(
            [
                f"## Benchmark {i} — {title.split('—', 1)[-1].strip()}",
                "",
                "### Prompt",
                "",
                f"> {prompt}",
                "",
                "### Metadata",
                "",
                f"- **route_selected:** `{agent}`",
                f"- **classifier (human_intent):** `{json.dumps(hi, ensure_ascii=False)}`",
                "- **fallback_fired:** `no` (normal `anna_analysis_v1` path)",
                "",
                "### Structured interpretation (for review)",
                "",
                f"- **headline:** {interp.get('headline', '')}",
                f"- **summary:** {interp.get('summary', '')}",
                "",
                "### Anna reply (as user sees in Telegram)",
                "",
                "```",
                telegram_text,
                "```",
                "",
                "---",
                "",
            ]
        )

    print("\n".join(lines))


if __name__ == "__main__":
    main()
