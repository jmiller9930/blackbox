"""DV-078 — unified Kitchen policy inventory payload (stable first paint vs refresh)."""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.kitchen_policy_inventory import build_kitchen_policy_inventory_payload


def _copy_registry(tmp: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json"
    dst = tmp / "renaissance_v4" / "config" / "kitchen_policy_registry_v1.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def test_inventory_matches_registry_allowlist_and_runtime_nested(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    p = build_kitchen_policy_inventory_payload(
        tmp_path,
        execution_target="jupiter",
        include_archived=False,
        collapse_duplicate_policy_ids=True,
    )
    assert p["schema"] == "kitchen_policy_inventory_v1"
    assert p["execution_target"] == "jupiter"
    allow = p["registry_allowlist"]["runtime_policy_ids"]
    assert isinstance(allow, list) and "jup_v4" in allow
    kr = p["kitchen_runtime"]
    assert kr.get("schema") == "kitchen_runtime_assignment_read_v5"
    assert "runtime" in kr and "drift" in kr
    # Default repo manifest is empty — every allowlist id is "legacy" (no manifest binding).
    leg = set(p["legacy_registry_only"]["runtime_policy_ids"])
    assert leg == set(allow)


def test_manifest_entry_removes_id_from_legacy_only(tmp_path: Path) -> None:
    _copy_registry(tmp_path)
    man = tmp_path / "renaissance_v4" / "config" / "kitchen_policy_deployment_manifest_v1.json"
    man.parent.mkdir(parents=True, exist_ok=True)
    man.write_text(
        """{
  "schema": "kitchen_policy_deployment_manifest_v1",
  "entries": [
    {
      "execution_target": "jupiter",
      "submission_id": "sub_x",
      "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "deployed_runtime_policy_id": "jup_v4"
    }
  ]
}
""",
        encoding="utf-8",
    )
    p = build_kitchen_policy_inventory_payload(tmp_path, execution_target="jupiter")
    leg = p["legacy_registry_only"]["runtime_policy_ids"]
    assert "jup_v4" not in leg
    mids = [e.get("deployed_runtime_policy_id") for e in p["manifest_entries"]]
    assert "jup_v4" in mids
