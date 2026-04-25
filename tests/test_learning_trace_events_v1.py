"""learning_trace_events_v1 — append, read, merge into reconstructed nodes."""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.game_theory.learning_trace_events_v1 import (
    SCHEMA_EVENT,
    append_learning_trace_event_v1,
    build_learning_trace_event_v1,
    merge_learning_trace_events_into_nodes_v1,
    read_learning_trace_events_for_job_v1,
)


def test_append_and_read_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "learning_trace_events_v1.jsonl"
    ev = build_learning_trace_event_v1(
        job_id="job-a",
        fingerprint="abc",
        stage="packet_built",
        status="pass",
        summary="ok",
        producer="test",
        evidence_payload={"n": 1},
    )
    assert ev["schema"] == SCHEMA_EVENT
    append_learning_trace_event_v1(ev, path=p)
    got = read_learning_trace_events_for_job_v1("job-a", path=p)
    assert len(got) == 1
    assert got[0]["stage"] == "packet_built"


def test_merge_adds_trace_store_and_coupling_proven(tmp_path: Path) -> None:
    nodes = [
        {
            "id": "packet_build",
            "label": "Packet build",
            "node_status_v1": "pass",
            "summary_v1": "x",
            "source_fields_v1": [],
            "evidence_v1": {},
            "evidence_provenance_v1": ["scorecard"],
            "runtime_breakpoints_v1": ["not_captured_at_runtime_v1"],
        },
        {
            "id": "referee_student_output_coupling",
            "label": "Referee use of Student output",
            "node_status_v1": "unknown",
            "summary_v1": "NOT PROVEN",
            "source_fields_v1": [],
            "evidence_v1": {"verdict_v1": "NOT_PROVEN"},
            "evidence_provenance_v1": ["unknown"],
            "runtime_breakpoints_v1": ["not_captured_at_runtime_v1"],
        },
    ]
    ev = build_learning_trace_event_v1(
        job_id="j1",
        fingerprint=None,
        stage="packet_built",
        status="pass",
        summary="built",
        producer="t",
    )
    merge_learning_trace_events_into_nodes_v1(nodes, [ev])
    pb = next(n for n in nodes if n["id"] == "packet_build")
    assert "trace_store" in pb["evidence_provenance_v1"]
    assert "not_captured_at_runtime_v1" not in pb.get("runtime_breakpoints_v1", [])

    ev2 = build_learning_trace_event_v1(
        job_id="j1",
        fingerprint=None,
        stage="referee_used_student_output",
        status="pass",
        summary="Referee read student slice",
        producer="worker",
    )
    merge_learning_trace_events_into_nodes_v1(nodes, [ev2])
    cp = next(n for n in nodes if n["id"] == "referee_student_output_coupling")
    assert cp["node_status_v1"] == "pass"
    assert cp.get("evidence_v1", {}).get("verdict_v1") == "PROVEN_BY_RUNTIME_EVENT_V1"
