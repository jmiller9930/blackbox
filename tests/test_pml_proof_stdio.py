"""Tests for PML proof script stdio routing."""

from __future__ import annotations

import argparse
import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest


def test_raw_stdout_selected_flags() -> None:
    from renaissance_v4.game_theory.pml_proof_stdio import add_proof_stdio_flags, raw_stdout_selected

    p = argparse.ArgumentParser()
    add_proof_stdio_flags(p)
    assert raw_stdout_selected(p.parse_args([])) is False
    assert raw_stdout_selected(p.parse_args(["--verbose"])) is True
    assert raw_stdout_selected(p.parse_args(["--raw-stdout"])) is True
    assert raw_stdout_selected(p.parse_args(["--debug"])) is True


def test_proof_json_out_writes_real_stdout() -> None:
    from renaissance_v4.game_theory import pml_proof_stdio as ps

    buf = StringIO()
    with patch.object(ps, "_REAL_OUT", buf):
        ps.proof_json_out({"ok": True, "x": 1})
    assert json.loads(buf.getvalue()) == {"ok": True, "x": 1}


def test_begin_pml_proof_stdio_redirects_when_not_raw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from renaissance_v4.game_theory import pml_proof_stdio as ps

    monkeypatch.setenv("BLACKBOX_PML_RUNTIME_ROOT", str(tmp_path / "rt"))
    ps._stdio_locked = False
    ps._active_log_path = None
    (tmp_path / "rt" / "proofs").mkdir(parents=True)
    saved_out, saved_err = sys.stdout, sys.stderr
    try:
        path = ps.begin_pml_proof_stdio("unit_proof_stdio", raw_stdout=False)
        assert path.suffix == ".log"
        sys.stdout.write("hello proof line\n")
        sys.stdout.flush()
        assert path.is_file()
        txt = path.read_text(encoding="utf-8")
        assert "hello proof line" in txt
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
        ps._stdio_locked = False
