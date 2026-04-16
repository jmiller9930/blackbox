"""
Deprecated shim (DV-068): use :mod:`renaissance_v4.kitchen_runtime_assignment`.

Kept so older imports continue to work.
"""

from renaissance_v4.kitchen_runtime_assignment import (  # noqa: F401
    APPROVED_MECHANICAL_BY_TARGET,
    MECHANICAL_CANDIDATE_POLICY_ID,
    assign_mechanical_candidate,
    assign_mechanical_candidate_to_jupiter,
    assignment_json_path,
    get_assignment,
    legacy_jupiter_assignment_path,
    read_assignment,
    read_store,
    runtime_assignment_store_path,
)

JUPITER_MECHANICAL_SLOT = APPROVED_MECHANICAL_BY_TARGET["jupiter"]["approved_runtime_slot_id"]
