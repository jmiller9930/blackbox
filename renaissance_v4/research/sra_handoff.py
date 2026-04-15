"""
DV-ARCH-SRA-HANDOFF-034 — Operator-controlled promotion approval → baseline Jupiter activation queue.

Reads eligible rows from ``promotion_candidates.json``; approval enqueues pending activation via
``enqueue_baseline_jupiter_policy_activation`` (same boundary rules as POST …/baseline-jupiter-policy).
Does not auto-approve or auto-activate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from renaissance_v4.research.sra_foundation import (
    get_hypothesis_by_id,
    get_promotion_ready_candidates,
    load_promotion_candidates_file,
)


def _blackbox_repo_root() -> Path:
    """``renaissance_v4/research/`` → repository root."""
    return Path(__file__).resolve().parent.parent.parent


def merge_handoff_parameters(
    parent: dict[str, Any] | None, selected: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge ``parameters`` objects: parent base, then selected overrides."""
    out: dict[str, Any] = {}
    if isinstance(parent, dict):
        p = parent.get("parameters")
        if isinstance(p, dict):
            out.update(p)
    if isinstance(selected, dict):
        p = selected.get("parameters")
        if isinstance(p, dict):
            out.update(p)
    return out


def build_promotion_candidates_api_payload() -> dict[str, Any]:
    """Shape for GET ``/api/v1/renaissance/promotion-candidates``."""
    rows = get_promotion_ready_candidates()
    candidates: list[dict[str, Any]] = []
    for c in rows:
        if not isinstance(c, dict):
            continue
        hid = c.get("selected_hypothesis_id")
        candidates.append(
            {
                "parent_hypothesis_id": c.get("parent_hypothesis_id"),
                "hypothesis_id": hid,
                "experiment_id": c.get("experiment_id"),
                "key_metrics": c.get("key_metrics"),
                "selected_hypothesis_id": hid,
                "eligible": True,
            }
        )
    return {
        "schema": "renaissance_v4_promotion_candidates_handoff_v1",
        "candidates": candidates,
    }


def approve_promotion(
    parent_hypothesis_id: str,
    *,
    repo_root: Path | None = None,
    assigned_by: str = "sra_handoff_034",
) -> dict[str, Any]:
    """
    Enqueue pending baseline Jupiter activation for an **eligible** promotion candidate.

    Safety (all required):
    - Row exists in ``promotion_candidates.json`` for ``parent_hypothesis_id``
    - ``eligible is True``
    - ``experiment_id`` present
    - ``selected_hypothesis_id`` resolves to a hypothesis record
    - ``parameters.handoff_jupiter_slot`` or ``policy_slot`` (or ``baseline_jupiter_slot``) maps to
      ``jup_v2`` / ``jup_v3`` / ``jup_v4`` (merged from parent then selected hypothesis)
    - If ``policy_package_repo_path`` or ``policy_package_path`` is set, it must resolve under
      ``policies/`` with ``POLICY_SPEC.yaml`` (proves materialized package on disk)

    Does not HTTP-call the dashboard; uses the same ledger enqueue as the activation API.
    """
    from modules.anna_training.execution_ledger import (
        baseline_jupiter_policy_activation_api_snapshot,
        baseline_jupiter_policy_lineage,
        connect_ledger,
        default_execution_ledger_path,
        enqueue_baseline_jupiter_policy_activation,
        ensure_execution_ledger_schema,
        normalize_baseline_jupiter_policy_slot,
        POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
    )

    pid = str(parent_hypothesis_id).strip()
    if not pid:
        raise ValueError("parent_hypothesis_id is required")

    cand: dict[str, Any] | None = None
    for c in load_promotion_candidates_file().get("candidates") or []:
        if isinstance(c, dict) and str(c.get("parent_hypothesis_id") or "").strip() == pid:
            cand = c
            break
    if cand is None:
        raise ValueError("promotion candidate not found for this parent_hypothesis_id")
    if cand.get("eligible") is not True:
        raise ValueError("candidate is not eligible for approval")
    exp = cand.get("experiment_id")
    if exp is None or str(exp).strip() == "":
        raise ValueError("experiment_id is required on the promotion candidate")

    sel = str(cand.get("selected_hypothesis_id") or "").strip()
    if not sel:
        raise ValueError("selected_hypothesis_id is missing on the promotion candidate")

    h_sel = get_hypothesis_by_id(sel)
    h_par = get_hypothesis_by_id(pid)
    if h_sel is None:
        raise ValueError("selected hypothesis record not found in hypotheses.jsonl")

    merged = merge_handoff_parameters(h_par, h_sel)

    raw_slot = (
        merged.get("handoff_jupiter_slot")
        or merged.get("policy_slot")
        or merged.get("baseline_jupiter_slot")
    )
    ps = normalize_baseline_jupiter_policy_slot(str(raw_slot or "").strip())
    if ps is None:
        raise ValueError(
            "set parameters.handoff_jupiter_slot (or policy_slot) to jup_v2, jup_v3, or jup_v4 "
            "on the parent or selected hypothesis"
        )

    pkg_rel = merged.get("policy_package_repo_path") or merged.get("policy_package_path")
    repo = (repo_root if repo_root is not None else _blackbox_repo_root()).resolve()
    if pkg_rel is not None and str(pkg_rel).strip():
        from renaissance_v4.ui_api import validate_policy_package_path

        if validate_policy_package_path(repo, str(pkg_rel).strip()) is None:
            raise ValueError(
                "policy_package_repo_path does not resolve to a valid policy package under policies/"
            )

    pid_l, pver_l = baseline_jupiter_policy_lineage(ps)

    ldb = default_execution_ledger_path()
    conn = connect_ledger(ldb)
    try:
        ensure_execution_ledger_schema(conn)
        enqueue_baseline_jupiter_policy_activation(
            conn,
            policy_id=pid_l,
            policy_version=pver_l,
            slot=POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
            assigned_by=assigned_by,
        )
        conn.commit()
        snap = baseline_jupiter_policy_activation_api_snapshot(conn)
    finally:
        conn.close()

    return {
        "ok": True,
        "schema": "renaissance_v4_promotion_approve_v1",
        "parent_hypothesis_id": pid,
        "selected_hypothesis_id": sel,
        "experiment_id": str(exp).strip(),
        "target_jupiter_slot": ps,
        "policy_id": pid_l,
        "policy_version": pver_l,
        "activation_slot": POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
        "activation_snapshot": snap,
    }
