"""Ensure pattern-game PAGE_HTML inline script is valid JavaScript (no Python \\n bleed-through)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from renaissance_v4.game_theory.web_app import _render_page_html


def test_inline_script_has_no_join_with_literal_newline_in_quotes() -> None:
    html = _render_page_html()
    assert not re.search(
        r"lines\.join\(\s*'\s*\n\s*'\s*\)",
        html,
    ), "telemetry join() must emit JS '\\n' (backslash+n), not a literal newline inside quotes"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_inline_script_passes_node_syntax_check() -> None:
    html = _render_page_html()
    m = re.search(r"<script>\s*(.*?)\s*</script>", html, re.DOTALL)
    assert m, "expected single inline <script> block"
    js = m.group(1)
    tmp = Path("/tmp/pattern_game_inline_script_check.js")
    tmp.write_text(js, encoding="utf-8")
    r = subprocess.run(
        ["node", "--check", str(tmp)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, f"node --check failed:\n{r.stderr or r.stdout}"
