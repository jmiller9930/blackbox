"""
Exam decision frame schema — **GT_DIRECTIVE_005** / architecture **§11.3**, **§2**.

Parent ``exam_unit`` + ordered ``decision_frame[]`` contract, stable IDs, ordering rules,
read-through **deliberation** (§11.2 store — not duplicated), immutable timeline **commit**
after Decision A seal (dev in-memory). No downstream generator (§11.4), no grading.
"""

from __future__ import annotations

import threading
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

TIMELINE_SCHEMA = "exam_unit_timeline"
TIMELINE_SCHEMA_VERSION = "1.0.0"

FrameTypeV1 = Literal["opening", "downstream"]


class OhlcvV1(BaseModel):
    """Single-bar OHLCV (opening window default per pack)."""

    model_config = ConfigDict(extra="forbid")

    open: float
    high: float
    low: float
    close: float
    volume: float


class OpeningSnapshotV1(BaseModel):
    """Frame 0 opening snapshot shell (pack fills keys; §2 v1.8)."""

    model_config = ConfigDict(extra="forbid")

    ohlcv: OhlcvV1
    indicators: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    data_gaps: list[dict[str, Any]] = Field(default_factory=list)


class DecisionFramePayloadV1(BaseModel):
    """Per-frame payload; frame 0 carries opening + deliberation + Decision A when sealed."""

    model_config = ConfigDict(extra="forbid")

    opening_snapshot: OpeningSnapshotV1 | None = None
    deliberation: dict[str, Any] | None = Field(
        default=None,
        description="Read-through copy of §11.2 deliberation export; canonical store remains frame-0 deliberation API.",
    )
    decision_a: dict[str, Any] | None = Field(
        default=None,
        description="Sealed Decision A facts (minimal dev shape); null until sealed.",
    )
    downstream_reserved: dict[str, Any] | None = Field(
        default=None,
        description="Placeholder slot for §11.4; do not use for moment truth in this slice.",
    )


class DecisionFrameV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_frame_id: str = Field(min_length=4, max_length=256)
    exam_unit_id: str = Field(min_length=4, max_length=128)
    frame_index: int = Field(ge=0, le=4096)
    timestamp: str = Field(
        min_length=10,
        max_length=64,
        description="Bar CLOSE time (ISO-8601 string) per architecture §2 v1.8 default.",
    )
    frame_type: FrameTypeV1
    payload: DecisionFramePayloadV1


class ExamUnitTimelineDocumentV1(BaseModel):
    """Parent container + ordered frames (§11.3)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    timeline_schema: Literal["exam_unit_timeline"] = Field(
        default="exam_unit_timeline",
        validation_alias=AliasChoices("schema", "timeline_schema"),
        serialization_alias="schema",
    )
    schema_version: str = Field(default=TIMELINE_SCHEMA_VERSION, min_length=1, max_length=32)
    exam_unit_id: str = Field(min_length=4, max_length=128)
    exam_pack_id: str | None = Field(default=None, max_length=256)
    exam_pack_version: str | None = Field(default=None, max_length=64)
    decision_frames: list[DecisionFrameV1] = Field(min_length=1)


def decision_frame_id_v1(exam_unit_id: str, frame_index: int) -> str:
    """Stable id safe in URL paths: ``{exam_unit_id}__df{index}`` (exam_unit_id must not contain ``__df``)."""
    sep = "__df"
    if sep in exam_unit_id:
        raise ValueError("exam_unit_id_must_not_contain_frame_id_separator")
    return f"{exam_unit_id}{sep}{frame_index}"


def parse_decision_frame_id_v1(decision_frame_id: str) -> tuple[str, int]:
    sep = "__df"
    if sep not in decision_frame_id:
        raise ValueError("invalid_decision_frame_id")
    base, _, idx_s = decision_frame_id.rpartition(sep)
    if not base or not idx_s.isdigit():
        raise ValueError("invalid_decision_frame_id")
    return base, int(idx_s)


def default_opening_snapshot_stub_v1() -> OpeningSnapshotV1:
    """Dev placeholder OHLCV until pack-fed snapshot exists."""
    return OpeningSnapshotV1(ohlcv=OhlcvV1(open=0.0, high=0.0, low=0.0, close=0.0, volume=0.0))


def validate_decision_frames_structure_v1(doc: ExamUnitTimelineDocumentV1) -> None:
    """Ordering, parent linkage, unique ids and frame_index; frame 0 exists; no gaps."""
    if doc.exam_unit_id.strip() != doc.exam_unit_id:
        raise ValueError("exam_unit_id_whitespace")
    frames = doc.decision_frames
    if frames[0].frame_index != 0:
        raise ValueError("missing_frame_0")
    indices = [f.frame_index for f in frames]
    if sorted(indices) != list(range(len(frames))):
        raise ValueError("frame_index_not_dense_or_not_zero_based")
    if len(set(indices)) != len(indices):
        raise ValueError("duplicate_frame_index")
    ids = [f.decision_frame_id for f in frames]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate_decision_frame_id")
    for f in frames:
        if f.exam_unit_id != doc.exam_unit_id:
            raise ValueError("decision_frame_parent_mismatch")
        if f.decision_frame_id != decision_frame_id_v1(doc.exam_unit_id, f.frame_index):
            raise ValueError("decision_frame_id_must_match_canonical_pattern")
        if parse_decision_frame_id_v1(f.decision_frame_id) != (doc.exam_unit_id, f.frame_index):
            raise ValueError("decision_frame_id_parse_mismatch")


def validate_decision_frames_enter_rules_v1(doc: ExamUnitTimelineDocumentV1, *, enter: bool) -> None:
    """NO_TRADE → exactly one opening frame; ENTER → one frame in this slice (future §11.4 may add more)."""
    validate_decision_frames_structure_v1(doc)
    n = len(doc.decision_frames)
    if not enter:
        if n != 1:
            raise ValueError("no_trade_requires_exactly_one_frame")
        if doc.decision_frames[0].frame_type != "opening":
            raise ValueError("no_trade_single_frame_must_be_opening")
    else:
        if n < 1 or n > 2:
            raise ValueError("enter_requires_one_or_two_frames_in_dev")
        if doc.decision_frames[0].frame_type != "opening":
            raise ValueError("frame_0_must_be_opening")
        if n == 2 and doc.decision_frames[1].frame_type != "downstream":
            raise ValueError("second_frame_must_be_downstream_placeholder")


_TIMELINE_COMMITTED: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def get_committed_timeline_v1(exam_unit_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _TIMELINE_COMMITTED.get(exam_unit_id.strip())


def commit_timeline_immutable_v1(doc: ExamUnitTimelineDocumentV1) -> None:
    """Persist one immutable timeline per unit (raises if already committed)."""
    validate_decision_frames_structure_v1(doc)
    uid = doc.exam_unit_id.strip()
    dump = doc.model_dump(mode="json")
    with _LOCK:
        if uid in _TIMELINE_COMMITTED:
            raise ValueError("timeline_already_committed_immutable")
        _TIMELINE_COMMITTED[uid] = dump


def build_timeline_document_for_seal_v1(
    *,
    exam_unit_id: str,
    exam_pack_id: str | None,
    exam_pack_version: str | None,
    enter: bool,
    deliberation_export: dict[str, Any] | None,
    bar_close_timestamp_iso: str,
) -> ExamUnitTimelineDocumentV1:
    """Build frame 0 (+ optional downstream placeholder for ENTER dev) at Decision A seal."""
    uid = exam_unit_id.strip()
    p0 = DecisionFramePayloadV1(
        opening_snapshot=default_opening_snapshot_stub_v1(),
        deliberation=dict(deliberation_export) if deliberation_export else None,
        decision_a={"enter": enter, "schema": "decision_a_sealed_stub_v1"},
    )
    f0 = DecisionFrameV1(
        decision_frame_id=decision_frame_id_v1(uid, 0),
        exam_unit_id=uid,
        frame_index=0,
        timestamp=bar_close_timestamp_iso,
        frame_type="opening",
        payload=p0,
    )
    frames: list[DecisionFrameV1] = [f0]
    if enter:
        p1 = DecisionFramePayloadV1(
            opening_snapshot=None,
            deliberation=None,
            decision_a=None,
            downstream_reserved={"schema": "downstream_reserved_v1", "note": "§11.4 generator not implemented"},
        )
        frames.append(
            DecisionFrameV1(
                decision_frame_id=decision_frame_id_v1(uid, 1),
                exam_unit_id=uid,
                frame_index=1,
                timestamp=bar_close_timestamp_iso,
                frame_type="downstream",
                payload=p1,
            )
        )
    doc = ExamUnitTimelineDocumentV1(
        exam_unit_id=uid,
        exam_pack_id=exam_pack_id,
        exam_pack_version=exam_pack_version,
        decision_frames=frames,
    )
    validate_decision_frames_enter_rules_v1(doc, enter=enter)
    return doc


def build_timeline_document_no_trade_single_frame_v1(
    *,
    exam_unit_id: str,
    exam_pack_id: str | None,
    exam_pack_version: str | None,
    deliberation_export: dict[str, Any] | None,
    bar_close_timestamp_iso: str,
) -> ExamUnitTimelineDocumentV1:
    """NO_TRADE: exactly one opening frame."""
    return build_timeline_document_for_seal_v1(
        exam_unit_id=exam_unit_id,
        exam_pack_id=exam_pack_id,
        exam_pack_version=exam_pack_version,
        enter=False,
        deliberation_export=deliberation_export,
        bar_close_timestamp_iso=bar_close_timestamp_iso,
    )


def build_timeline_document_enter_single_frame_v1(
    *,
    exam_unit_id: str,
    exam_pack_id: str | None,
    exam_pack_version: str | None,
    deliberation_export: dict[str, Any] | None,
    bar_close_timestamp_iso: str,
) -> ExamUnitTimelineDocumentV1:
    """ENTER: single opening frame only (current product rule; no downstream row)."""
    uid = exam_unit_id.strip()
    p0 = DecisionFramePayloadV1(
        opening_snapshot=default_opening_snapshot_stub_v1(),
        deliberation=dict(deliberation_export) if deliberation_export else None,
        decision_a={"enter": True, "schema": "decision_a_sealed_stub_v1"},
    )
    f0 = DecisionFrameV1(
        decision_frame_id=decision_frame_id_v1(uid, 0),
        exam_unit_id=uid,
        frame_index=0,
        timestamp=bar_close_timestamp_iso,
        frame_type="opening",
        payload=p0,
    )
    doc = ExamUnitTimelineDocumentV1(
        exam_unit_id=uid,
        exam_pack_id=exam_pack_id,
        exam_pack_version=exam_pack_version,
        decision_frames=[f0],
    )
    validate_decision_frames_enter_rules_v1(doc, enter=True)
    return doc


def timeline_to_public_response_v1(doc: ExamUnitTimelineDocumentV1) -> dict[str, Any]:
    """HTTP envelope for GET …/decision-frames."""
    d = doc.model_dump(mode="json", by_alias=True)
    return {
        "ok": True,
        "schema": d.get("schema", TIMELINE_SCHEMA),
        "schema_version": d.get("schema_version", TIMELINE_SCHEMA_VERSION),
        "exam_unit_id": d["exam_unit_id"],
        "exam_pack_id": d.get("exam_pack_id"),
        "exam_pack_version": d.get("exam_pack_version"),
        "decision_frames": d["decision_frames"],
    }


def decision_frames_http_doc_v1() -> list[dict[str, Any]]:
    return [
        {
            "method": "GET",
            "path": "/api/v1/exam/units/{exam_unit_id}/decision-frames",
            "success": 200,
            "errors": [{"status": 404, "when": "exam_unit_not_found or timeline_not_committed_yet"}],
        },
        {
            "method": "GET",
            "path": "/api/v1/exam/frames/{decision_frame_id}",
            "success": 200,
            "errors": [{"status": 404, "when": "unknown decision_frame_id"}],
        },
    ]


def reset_exam_timelines_for_tests_v1() -> None:
    with _LOCK:
        _TIMELINE_COMMITTED.clear()


def find_frame_in_committed_timelines_v1(decision_frame_id: str) -> dict[str, Any] | None:
    """Scan committed units for a frame (dev O(n))."""
    try:
        uid, _ = parse_decision_frame_id_v1(decision_frame_id)
    except ValueError:
        return None
    doc = get_committed_timeline_v1(uid)
    if doc is None:
        return None
    for fr in doc.get("decision_frames", []):
        if fr.get("decision_frame_id") == decision_frame_id:
            return fr
    return None


__all__ = [
    "DecisionFramePayloadV1",
    "DecisionFrameV1",
    "ExamUnitTimelineDocumentV1",
    "FrameTypeV1",
    "OpeningSnapshotV1",
    "OhlcvV1",
    "TIMELINE_SCHEMA",
    "TIMELINE_SCHEMA_VERSION",
    "build_timeline_document_enter_single_frame_v1",
    "build_timeline_document_for_seal_v1",
    "build_timeline_document_no_trade_single_frame_v1",
    "commit_timeline_immutable_v1",
    "decision_frame_id_v1",
    "decision_frames_http_doc_v1",
    "default_opening_snapshot_stub_v1",
    "find_frame_in_committed_timelines_v1",
    "get_committed_timeline_v1",
    "parse_decision_frame_id_v1",
    "reset_exam_timelines_for_tests_v1",
    "timeline_to_public_response_v1",
    "validate_decision_frames_enter_rules_v1",
    "validate_decision_frames_structure_v1",
]
