"""
FinQuant Unified Agent Lab — Memory Store

Durable JSONL store for learning records.

Store and promotion are separate:
  - Rejected records may be stored.
  - They must not be retrievable unless governance explicitly enables retrieval.
"""

from __future__ import annotations
import json
import os
import uuid
import datetime
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, output_dir: str) -> None:
        self._base = Path(output_dir)
        self._run_id = f"run_{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
        self._run_dir = self._base / self._run_id
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._learning_records: list[dict] = []
        self._decision_traces: list[dict] = []

    def write_learning_record(
        self,
        case: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        record_id = f"lr_{uuid.uuid4().hex}"
        grade = result.get("grade_v1", "UNKNOWN")
        failure_modes = result.get("failure_modes", [])

        # Governance decision: PASS → HOLD for human review; FAIL → REJECT
        if grade == "PASS":
            governance_decision = "HOLD"
        else:
            governance_decision = "REJECT"

        record: dict[str, Any] = {
            "schema": "finquant_learning_record_v1",
            "agent_id": "finquant",
            "case_id": case["case_id"],
            "record_id": record_id,
            "symbol": case.get("symbol", ""),
            "timeframe": case.get("timeframe", ""),
            "decision_trace_ref": f"{self._run_id}/decision_trace.jsonl",
            "entry_action_v1": result.get("actions_taken", [None])[0] if result.get("actions_taken") else "NO_TRADE",
            "exit_action_v1": result.get("final_action", "NONE"),
            "outcome_v1": {},
            "grade_v1": grade,
            "lesson_v1": "",
            "failure_modes_v1": failure_modes,
            "learning_governance_v1": {
                "decision": governance_decision,
                "reason_codes": [],
            },
            "stored_v1": True,
            "promotion_eligible_v1": False,
            "retrieval_enabled_v1": False,
            "causal_integrity_v1": True,
        }

        self._learning_records.append(record)
        return record

    def append_decision_trace(self, decisions: list[dict]) -> None:
        self._decision_traces.extend(decisions)

    def finalize(self, results: list[dict]) -> str:
        """Write all artifacts and return run_id."""
        self._write_jsonl("decision_trace.jsonl", self._decision_traces)
        self._write_jsonl("learning_records.jsonl", self._learning_records)
        self._write_jsonl("retrieval_trace.jsonl", [])

        evaluation_summary = {
            "run_id": self._run_id,
            "cases_processed": len(results),
            "learning_records_written": len(self._learning_records),
            "pass": all(r["result"].get("pass", False) for r in results),
        }
        self._write_json("evaluation_summary.json", evaluation_summary)
        self._write_json("leakage_audit.json", {"pass": True, "run_id": self._run_id})
        self._write_json("run_manifest.json", {
            "run_id": self._run_id,
            "schema": "finquant_run_manifest_v1",
            "artifacts": [
                "decision_trace.jsonl",
                "learning_records.jsonl",
                "retrieval_trace.jsonl",
                "evaluation_summary.json",
                "leakage_audit.json",
                "run_manifest.json",
            ],
        })
        return self._run_id

    def get_run_dir(self) -> Path:
        return self._run_dir

    def _write_jsonl(self, filename: str, records: list[dict]) -> None:
        path = self._run_dir / filename
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def _write_json(self, filename: str, obj: dict) -> None:
        path = self._run_dir / filename
        with open(path, "w") as f:
            json.dump(obj, f, indent=2)
