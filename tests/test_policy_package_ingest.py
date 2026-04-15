"""DV-ARCH-POLICY-INGESTION-024-A — validation + replay ingest path."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_run_policy_package_replay_validation_failure(tmp_path: Path) -> None:
    from renaissance_v4.research.policy_package_ingest import run_policy_package_replay

    bad = tmp_path / "not_a_package"
    bad.mkdir()
    with pytest.raises(RuntimeError, match="validate_policy_package"):
        run_policy_package_replay(str(bad))


def test_run_policy_package_replay_writes_deterministic_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from renaissance_v4.research import policy_package_ingest as ingest

    pkg_src = ROOT / "policies" / "generated" / "renaissance_baseline_v1_stack"
    if not (pkg_src / "POLICY_SPEC.yaml").is_file():
        pytest.skip("policy package fixture missing")

    fake_root = tmp_path / "fake_repo"
    dst_pkg = fake_root / "policies" / "generated" / "renaissance_baseline_v1_stack"
    shutil.copytree(pkg_src, dst_pkg)
    man_dir = fake_root / "renaissance_v4" / "configs" / "manifests"
    man_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        ROOT / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json",
        man_dir / "baseline_v1_recipe.json",
    )

    fake_replay = {
        "manifest": {"strategy_id": "x"},
        "manifest_path": str(man_dir / "baseline_v1_recipe.json"),
        "dataset_bars": 99,
        "validation_checksum": "deadbeef" * 8,
        "summary": {"trades": 0},
        "cumulative_pnl": 0.0,
        "sanity": {},
    }

    def _fake_validate(_pkg: Path) -> None:
        return None

    def _fake_run_manifest_replay(*_a: object, **_k: object) -> dict:
        return fake_replay

    monkeypatch.setattr(ingest, "_repo_root", lambda: fake_root)
    monkeypatch.setattr(ingest, "_validate_policy_package_subprocess", _fake_validate)
    monkeypatch.setattr(
        "renaissance_v4.research.replay_runner.run_manifest_replay",
        _fake_run_manifest_replay,
    )

    out = ingest.run_policy_package_replay("policies/generated/renaissance_baseline_v1_stack")
    assert out["ok"] is True
    p = Path(out["output_path"])
    assert p.is_file()
    assert fake_root in p.parents
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["schema"] == "deterministic_ingested_policy_v1"
    assert data["source_type"] == "ingested_policy"
    assert data["policy_id"] == "renaissance_baseline_v1_stack"
    assert data["policy_version"] == "renaissance_baseline_v1_stack"
    assert data["policy_slug"] == "research_kitchen_generated"
    assert data["lineage"]["experiment_id"] == data["experiment_id"]
    assert data["replay"]["validation_checksum"] == fake_replay["validation_checksum"]


def test_policy_module_checksum_path_without_manifest_in_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Packages that only expose replay_manifest_policy_checksum (no parity.manifest_path)."""
    from renaissance_v4.research import policy_package_ingest as ingest

    pkg = tmp_path / "pp_test"
    pkg.mkdir()
    (pkg / "POLICY_SPEC.yaml").write_text(
        """
policy_package_version: 1
policy:
  id: test_policy_001
  display_name: Test
  baseline_policy_slot: jup_v4
  signal_mode: test_sm
  catalog_id: test_catalog_001
  timeframe: 5m
  instrument: SOL-PERP
inputs:
  canonical: ohlcv_lists
""".strip(),
        encoding="utf-8",
    )
    (pkg / "INTEGRATION_CHECKLIST.md").write_text("# checklist\n", encoding="utf-8")
    (pkg / "jupiter_9_test_policy.py").write_text(
        """
def replay_manifest_policy_checksum():
    return "abc123checksum"

def manifest_path():
    from pathlib import Path
    return Path(__file__).resolve().parent / "dummy.json"
""",
        encoding="utf-8",
    )

    def _fake_validate(_p: Path) -> None:
        return None

    monkeypatch.setattr(ingest, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ingest, "_validate_policy_package_subprocess", _fake_validate)

    out = ingest.run_policy_package_replay(str(pkg.resolve()))
    assert out["ok"] is True
    data = json.loads(Path(out["output_path"]).read_text(encoding="utf-8"))
    assert data["replay"]["validation_checksum"] == "abc123checksum"
    assert data["policy_id"] == "test_policy_001"
