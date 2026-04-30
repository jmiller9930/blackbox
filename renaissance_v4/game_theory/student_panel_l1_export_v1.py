"""
L1 row export — single-run bundle for engineering handoff.

Bundles the raw scorecard line (when present), the enriched ``student_panel_run_row_v2`` row
(same shape as ``GET /api/student-panel/runs``), and the per-job L1 road overlay slice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from renaissance_v4.game_theory.batch_scorecard import read_batch_scorecard_recent
from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl
from renaissance_v4.game_theory.scorecard_drill import find_scorecard_entry_by_job_id
from renaissance_v4.game_theory.student_panel_d11 import build_d11_run_rows_v1
from renaissance_v4.game_theory.student_panel_d14 import enrich_student_panel_run_rows_d14
from renaissance_v4.game_theory.student_panel_l1_road_v1 import build_l1_road_payload_v1

SCHEMA_STUDENT_PANEL_L1_ROW_EXPORT_V1 = "student_panel_l1_row_export_v1"


def build_student_panel_l1_row_export_v1(
    job_id: str,
    *,
    merged_entries_newest_first: list[dict[str, Any]] | None = None,
    scorecard_read_limit: int = 500,
) -> dict[str, Any]:
    """
    Build one JSON object suitable for clipboard or file share.

    When ``merged_entries_newest_first`` is omitted, reads recent lines from
    ``default_batch_scorecard_jsonl()`` (newest first). Callers that merge in-flight jobs
    (same as ``GET /api/student-panel/runs``) should pass that merged list for parity.
    """
    jid = str(job_id or "").strip()
    if not jid:
        return {"ok": False, "error": "job_id_required", "schema": SCHEMA_STUDENT_PANEL_L1_ROW_EXPORT_V1}

    lim = max(1, min(2000, int(scorecard_read_limit)))
    merged = merged_entries_newest_first
    if merged is None:
        merged = read_batch_scorecard_recent(lim, path=default_batch_scorecard_jsonl())

    scorecard_line = find_scorecard_entry_by_job_id(jid)
    if scorecard_line is None:
        scorecard_line = next(
            (e for e in merged if str(e.get("job_id") or "").strip() == jid),
            None,
        )

    rows = enrich_student_panel_run_rows_d14(build_d11_run_rows_v1(merged))
    panel_row = next((r for r in rows if str(r.get("run_id") or "").strip() == jid), None)

    if panel_row is None:
        return {
            "ok": False,
            "error": "run_row_not_found_v1",
            "schema": SCHEMA_STUDENT_PANEL_L1_ROW_EXPORT_V1,
            "job_id": jid,
            "hint_v1": (
                "Unknown job_id, or line outside the merged scorecard slice "
                "(raise limit or pass merged_entries_newest_first including this job)."
            ),
        }

    road = build_l1_road_payload_v1()
    road_by_jid = road.get("road_by_job_id_v1") or {}
    road_row = road_by_jid.get(jid)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "ok": True,
        "schema": SCHEMA_STUDENT_PANEL_L1_ROW_EXPORT_V1,
        "job_id": jid,
        "exported_at_utc_v1": now,
        "scorecard_line_v1": scorecard_line,
        "student_panel_run_row_v2": panel_row,
        "l1_road_row_overlay_v1": road_row,
        "l1_road_global_v1": {
            "legend": road.get("legend"),
            "data_gaps": road.get("data_gaps"),
            "note": road.get("note"),
        },
        "export_note_v1": (
            "scorecard_line_v1 is the persisted batch_scorecard object when available; "
            "in-flight-only rows may be synthetic until JSONL append. "
            "student_panel_run_row_v2 matches the L1 table row from GET /api/student-panel/runs."
        ),
    }


__all__ = [
    "SCHEMA_STUDENT_PANEL_L1_ROW_EXPORT_V1",
    "build_student_panel_l1_row_export_v1",
]
