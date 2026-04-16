"""PolicySpecV1 + normalize_policy (DV-ARCH-CANONICAL-POLICY-SPEC-046)."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.policy_spec import normalize_policy, policy_spec_v1_validate_minimal


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    assert isinstance(data, dict)
    return data


def test_normalize_renaissance_baseline_package() -> None:
    root = Path(__file__).resolve().parents[1]
    spec_path = root / "policies" / "generated" / "renaissance_baseline_v1_stack" / "POLICY_SPEC.yaml"
    if not spec_path.is_file():
        pytest.skip("fixture POLICY_SPEC.yaml missing")
    data = _load_yaml(spec_path)
    out = normalize_policy(data)
    errs = policy_spec_v1_validate_minimal(out)
    assert not errs
    assert out["identity"]["policy_id"] == "renaissance_baseline_v1_stack"
    assert out["identity"]["policy_class"] in ("baseline", "candidate", "training", "production")


def test_normalize_pipeline_proof_loose_id() -> None:
    out = normalize_policy({"policy_id": "jup_pipeline_proof_v1", "policy_class": "training"})
    assert out["identity"]["policy_id"] == "jup_pipeline_proof_v1"
    assert out["identity"]["policy_class"] == "training"
    assert out["strategy"]["signal_type"] == "pipeline_proof"


def test_normalize_rejects_non_dict() -> None:
    with pytest.raises(TypeError):
        normalize_policy("not-a-dict")
