"""DV-ARCH-POLICY-INGESTION-024-C — policy package path validation for jobs API."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_validate_policy_package_path_accepts_policies_subdir(tmp_path: Path) -> None:
    from renaissance_v4.ui_api import validate_policy_package_path

    pkg = tmp_path / "policies" / "demo_pkg"
    pkg.mkdir(parents=True)
    (pkg / "POLICY_SPEC.yaml").write_text("policy:\n  id: x\n", encoding="utf-8")
    got = validate_policy_package_path(tmp_path, "policies/demo_pkg")
    assert got == pkg.resolve()


def test_validate_policy_package_path_rejects_outside_policies(tmp_path: Path) -> None:
    from renaissance_v4.ui_api import validate_policy_package_path

    other = tmp_path / "other" / "pkg"
    other.mkdir(parents=True)
    (other / "POLICY_SPEC.yaml").write_text("policy:\n  id: x\n", encoding="utf-8")
    assert validate_policy_package_path(tmp_path, "other/pkg") is None


def test_robustness_runner_has_ingest_policy_subcommand() -> None:
    from renaissance_v4.research.robustness_runner import build_parser

    p = build_parser()
    ns = p.parse_args(["ingest-policy", "--experiment-id", "exp_test_001", "--policy-path", "policies/x"])
    assert ns.cmd == "ingest-policy"
    assert ns.experiment_id == "exp_test_001"
