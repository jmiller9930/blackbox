"""Tests for PML runtime disk layout and pre-run guards."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest


def test_check_disk_blocks_low_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from renaissance_v4.game_theory import pml_runtime_layout as prl

    monkeypatch.setenv("BLACKBOX_PML_RUNTIME_ROOT", str(tmp_path / "rt"))
    (tmp_path / "rt").mkdir()

    class U:
        def __init__(self, free: int) -> None:
            self.total = 10**12
            self.used = 10**6
            self.free = free

    def fake_usage(path: str) -> object:
        p = str(path)
        if p == "/tmp":
            return U(100 * 1024 * 1024)  # 100 MiB < 200 block
        return U(4 * 1024**3)

    with patch.object(shutil, "disk_usage", side_effect=fake_usage):
        ok, warns, block = prl.check_disk_before_run()
    assert ok is False
    assert block is not None
    assert "/tmp" in block


def test_check_disk_allows_healthy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from renaissance_v4.game_theory import pml_runtime_layout as prl

    monkeypatch.setenv("BLACKBOX_PML_RUNTIME_ROOT", str(tmp_path / "rt"))
    (tmp_path / "rt").mkdir()

    class U:
        def __init__(self, free: int) -> None:
            self.total = 10**12
            self.used = 10**6
            self.free = free

    def fake_usage(path: str) -> object:
        return U(4 * 1024**3)

    with patch.object(shutil, "disk_usage", side_effect=fake_usage):
        ok, warns, block = prl.check_disk_before_run()
    assert ok is True
    assert block is None


def test_prune_batch_dirs_removes_oldest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from renaissance_v4.game_theory import pml_runtime_layout as prl

    rt = tmp_path / "rt"
    monkeypatch.setenv("BLACKBOX_PML_RUNTIME_ROOT", str(rt))
    b = prl.pml_runtime_batches_dir()
    b.mkdir(parents=True)
    monkeypatch.setenv("PML_RUNTIME_BATCH_MAX_DIRS", "2")
    for name, t in [("batch_old", 1), ("batch_mid", 2), ("batch_new", 3)]:
        d = b / name
        d.mkdir()
        Path(d / "f.txt").write_text("x", encoding="utf-8")
        import os

        os.utime(d, (t, t))
    out = prl.prune_pml_runtime_batch_dirs()
    assert out["removed"] >= 1
    remaining = {p.name for p in b.iterdir() if p.is_dir()}
    assert "batch_new" in remaining
    assert len(remaining) <= 2
