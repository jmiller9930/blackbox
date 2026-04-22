"""
Exam deliberation capture — **GT_DIRECTIVE_004** / architecture **§11.2**.

Versioned H1–H4 payload validation, non-placeholder enforcement, pack-aware ``data_gap``,
and in-memory attachment for **decision frame index 0** (dev; not durable persistence).
"""

from __future__ import annotations

import threading
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

# Supported deliberation contract versions (bump when fields change).
SUPPORTED_DELIBERATION_SCHEMA_VERSIONS = frozenset({"1.0.0"})

_PLACEHOLDER_FRAGMENTS = (
    "todo",
    "tbd",
    "fixme",
    "placeholder",
    "lorem ipsum",
    "<fill",
    "xxx",
    "n/a",
)


class PackDeliberationPolicyV1(BaseModel):
    """Per-pack rules carried on submit (until pack registry exists)."""

    model_config = ConfigDict(extra="forbid")

    k_min: int = Field(default=3, ge=1, le=12)
    data_gap_allowed_paths: list[str] = Field(default_factory=list)
    allow_no_trade_primary: bool = Field(
        default=True,
        description="If false, H4 primary_selection may not be NO_TRADE (pack disallows that outcome).",
    )


class DataGapEntryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=512)
    reason: str = Field(min_length=8, max_length=2048)


class HypothesisDeliberationV1(BaseModel):
    """H1–H3 (or H1..HK) — one row per hypothesis before H4."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str = Field(pattern=r"^H[1-9][0-9]*$")
    market_interpretation: str = Field(min_length=20, max_length=8000)
    indicator_support: str = Field(min_length=20, max_length=8000)
    resulting_action: Literal["ENTER_LONG", "ENTER_SHORT", "NO_TRADE"]
    falsification_condition: str = Field(min_length=20, max_length=8000)


class H4DeliberationV1(BaseModel):
    """Comparative evaluation + selection + bounded reasoning (§1.2 / §11.2)."""

    model_config = ConfigDict(extra="forbid")

    comparative_evaluation: str = Field(min_length=40, max_length=12000)
    primary_selection: str = Field(
        description="Hypothesis id (e.g. H2) or NO_TRADE when no arm wins on merit.",
        pattern=r"^(H[1-9][0-9]*|NO_TRADE)$",
    )
    bounded_reasoning: str = Field(min_length=40, max_length=12000)


class ExamDeliberationPayloadV1(BaseModel):
    """
    Exported deliberation artifact (frame 0 moment truth — deliberation slice only).

    JSON uses key ``schema`` (``exam_deliberation``); ``schema_version`` gates compatibility.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    deliberation_schema: Literal["exam_deliberation"] = Field(
        default="exam_deliberation",
        validation_alias=AliasChoices("schema", "deliberation_schema"),
        serialization_alias="schema",
    )
    schema_version: str = Field(min_length=1, max_length=32)
    exam_unit_id: str = Field(min_length=4, max_length=128)
    exam_pack_id: str | None = Field(default=None, max_length=256)
    exam_pack_version: str | None = Field(default=None, max_length=64)
    hypotheses: list[HypothesisDeliberationV1] = Field(min_length=1, max_length=12)
    h4: H4DeliberationV1
    data_gaps: list[DataGapEntryV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _schema_version_gate(self) -> ExamDeliberationPayloadV1:
        if self.schema_version not in SUPPORTED_DELIBERATION_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported_schema_version:{self.schema_version!r}")
        return self

    @model_validator(mode="after")
    def _primary_selection_consistent(self) -> ExamDeliberationPayloadV1:
        ids = {h.hypothesis_id for h in self.hypotheses}
        if self.h4.primary_selection != "NO_TRADE" and self.h4.primary_selection not in ids:
            raise ValueError("h4.primary_selection_must_reference_declared_hypothesis")
        return self


class ExamDeliberationSubmitEnvelopeV1(BaseModel):
    """HTTP submit body: optional pack policy + deliberation payload."""

    model_config = ConfigDict(extra="forbid")

    pack_deliberation_policy: PackDeliberationPolicyV1 = Field(default_factory=PackDeliberationPolicyV1)
    deliberation: ExamDeliberationPayloadV1


def assert_non_placeholder_deliberation_v1(payload: ExamDeliberationPayloadV1) -> None:
    """
    Reject stub / placeholder “complete” exports (§11.2 regression guard).

    Raises ``ValueError`` with a stable prefix so HTTP layer maps to 422.
    """
    texts: list[str] = []
    for h in payload.hypotheses:
        texts.extend(
            [
                h.market_interpretation,
                h.indicator_support,
                h.falsification_condition,
            ]
        )
    texts.extend(
        [
            payload.h4.comparative_evaluation,
            payload.h4.bounded_reasoning,
        ]
    )
    for t in texts:
        low = t.lower().strip()
        for frag in _PLACEHOLDER_FRAGMENTS:
            if frag in low:
                raise ValueError(f"placeholder_text_forbidden:{frag}")
        if len(low.strip()) < 10:
            raise ValueError("placeholder_text_forbidden:too_short")


def validate_h4_primary_selection_integrity_v1(
    payload: ExamDeliberationPayloadV1,
    policy: PackDeliberationPolicyV1,
) -> None:
    """
    H4 ``primary_selection`` must reference a declared ``hypothesis_id``, or ``NO_TRADE`` when the pack allows it.

    Also rejects duplicate ``hypothesis_id`` rows (ambiguous winner reference).
    """
    ids_list = [h.hypothesis_id for h in payload.hypotheses]
    if len(ids_list) != len(frozenset(ids_list)):
        raise ValueError("duplicate_hypothesis_id")
    uid_set = frozenset(ids_list)
    ps = payload.h4.primary_selection
    if ps == "NO_TRADE":
        if not policy.allow_no_trade_primary:
            raise ValueError("no_trade_primary_not_allowed_by_pack")
        return
    if ps not in uid_set:
        raise ValueError("h4.primary_selection_must_reference_declared_hypothesis")


def validate_deliberation_against_policy_v1(
    payload: ExamDeliberationPayloadV1,
    policy: PackDeliberationPolicyV1,
) -> None:
    """Hypothesis count, H4 selection integrity, ``data_gap`` allowlist."""
    validate_h4_primary_selection_integrity_v1(payload, policy)
    if len(payload.hypotheses) < policy.k_min:
        raise ValueError(f"hypothesis_count_below_k_min:{len(payload.hypotheses)}<{policy.k_min}")
    allowed = frozenset(policy.data_gap_allowed_paths)
    for g in payload.data_gaps:
        if g.path not in allowed:
            raise ValueError(f"data_gap_path_not_allowed_by_pack:{g.path!r}")


def parse_submit_envelope_v1(raw: Any) -> ExamDeliberationSubmitEnvelopeV1:
    """Parse JSON object; raises ``ValueError`` on bad shape (map to 400)."""
    if not isinstance(raw, dict):
        raise ValueError("body_must_be_json_object")
    return ExamDeliberationSubmitEnvelopeV1.model_validate(raw)


def deliberation_payload_to_export_dict_v1(payload: ExamDeliberationPayloadV1) -> dict[str, Any]:
    """Stable JSON-ready dict for storage and GET responses (``schema`` key via alias)."""
    return payload.model_dump(mode="json", by_alias=True)


_FRAME0_DELIBERATIONS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def put_frame0_deliberation_v1(exam_unit_id: str, export_dict: dict[str, Any]) -> None:
    with _LOCK:
        _FRAME0_DELIBERATIONS[exam_unit_id.strip()] = dict(export_dict)


def get_frame0_deliberation_v1(exam_unit_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _FRAME0_DELIBERATIONS.get(exam_unit_id.strip())


def reset_exam_deliberations_for_tests_v1() -> None:
    with _LOCK:
        _FRAME0_DELIBERATIONS.clear()


def deliberation_http_route_matrix_v1() -> list[dict[str, Any]]:
    """Operator / PR documentation for new §11.2 routes."""
    return [
        {
            "method": "PUT",
            "path": "/api/v1/exam/units/{exam_unit_id}/frames/0/deliberation",
            "success": 200,
            "errors": [
                {"status": 400, "when": "malformed JSON or envelope validation failure"},
                {"status": 404, "when": "exam_unit_id not found"},
                {
                    "status": 422,
                    "when": (
                        "semantic failure: policy, placeholder, unsupported schema_version, "
                        "H4 primary_selection integrity (unknown hypothesis id, duplicate ids, NO_TRADE disallowed)"
                    ),
                },
            ],
        },
        {
            "method": "GET",
            "path": "/api/v1/exam/units/{exam_unit_id}/frames/0/deliberation",
            "success": 200,
            "errors": [{"status": 404, "when": "no deliberation stored for frame 0"}],
        },
    ]


__all__ = [
    "DataGapEntryV1",
    "ExamDeliberationPayloadV1",
    "ExamDeliberationSubmitEnvelopeV1",
    "H4DeliberationV1",
    "HypothesisDeliberationV1",
    "PackDeliberationPolicyV1",
    "SUPPORTED_DELIBERATION_SCHEMA_VERSIONS",
    "assert_non_placeholder_deliberation_v1",
    "deliberation_http_route_matrix_v1",
    "deliberation_payload_to_export_dict_v1",
    "get_frame0_deliberation_v1",
    "parse_submit_envelope_v1",
    "put_frame0_deliberation_v1",
    "reset_exam_deliberations_for_tests_v1",
    "validate_deliberation_against_policy_v1",
    "validate_h4_primary_selection_integrity_v1",
]
