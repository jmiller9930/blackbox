"""
FinQuant Unified Agent Lab — Memory Store.

Writes lab learning records to JSONL.
Produces all required run output artifacts.

Governance rule: store ≠ promotion.
  - promotion_eligible_v1 defaults to false.
  - retrieval_enabled_v1 defaults to false.
  - Rejected records are stored but never retrievable without explicit governance change.
"""

from __future__ import annotations
import json
import uuid
import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from learning_governance import build_learning_governance, build_lesson_text
from schemas import SCHEMA_LEARNING_RECORD, SCHEMA_RUN_SUMMARY


class MemoryStore:
    def __init__(self, config: dict[str, Any], base_output_dir: str) -> None:
        self._config = config
        self._base = Path(base_output_dir)
        self._run_id = (
            f"run_{datetime.datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            f"_{uuid.uuid4().hex[:8]}"
        )
        self._run_dir = self._base / self._run_id
        self._run_dir.mkdir(parents=True, exist_ok=True)

        # Shared store path for cross-run retrieval
        shared_path = config.get("memory_store_path", "")
        self._shared_store = Path(shared_path) if shared_path else None

        self._learning_records: list[dict] = []
        self._decision_trace: list[dict] = []
        self._retrieval_trace: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_decisions(self, decisions: list[dict]) -> None:
        self._decision_trace.extend(decisions)

    def write_learning_record(
        self,
        case: dict[str, Any],
        evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        record_id = f"lr_{uuid.uuid4().hex}"
        decisions = list(self._decision_trace)
        governance = build_learning_governance(
            evaluation=evaluation,
            decisions=decisions,
        )
        auto_promote = bool(self._config.get("auto_promote_learning_v1", False))
        promoted_now = governance["decision"] == "PROMOTE" and auto_promote
        retrieval_enabled = promoted_now
        entry_action = "NO_TRADE"
        for decision in decisions:
            action = str(decision.get("action") or "")
            if action in {"ENTER_LONG", "ENTER_SHORT"}:
                entry_action = action
                break
        exit_action = "EXIT" if any(str(d.get("action") or "") == "EXIT" for d in decisions) else "NONE"

        record: dict[str, Any] = {
            "schema": SCHEMA_LEARNING_RECORD,
            "agent_id": self._config.get("agent_id", "finquant"),
            "case_id": case["case_id"],
            "record_id": record_id,
            "symbol": case.get("symbol", ""),
            "timeframe": f"{case.get('timeframe_minutes', 0)}m",
            "timeframe_minutes": case.get("timeframe_minutes", 0),
            "decision_trace_ref": f"{self._run_id}/decision_trace.json",
            "decision_trace_ref_v1": f"{self._run_id}/decision_trace.json",
            "evaluation_ref_v1": f"{self._run_id}/evaluation.json",
            "entry_action_v1": entry_action,
            "exit_action_v1": exit_action,
            "outcome_v1": {
                "final_status_v1": evaluation.get("final_status_v1"),
                "entry_quality_v1": evaluation.get("entry_quality_v1"),
                "exit_quality_v1": evaluation.get("exit_quality_v1"),
            },
            "grade_v1": evaluation.get("final_status_v1", "UNKNOWN"),
            "lesson_v1": build_lesson_text(
                case=case,
                evaluation=evaluation,
                decisions=decisions,
            ),
            "failure_modes_v1": list(evaluation.get("learning_labels_v1", [])),
            "learning_governance_v1": governance,
            "learning_labels_v1": evaluation.get("learning_labels_v1", []),
            "stored_v1": True,
            "promotion_eligible_v1": promoted_now,
            "retrieval_enabled_v1": retrieval_enabled,
            "causal_integrity_v1": all(bool(d.get("causal_context_only_v1", True)) for d in decisions),
            "created_by_v1": "finquant_agent_lab_v1",
        }

        self._learning_records.append(record)
        return record

    def append_retrieval_trace(self, entries: list[dict]) -> None:
        self._retrieval_trace.extend(entries)

    def finalize(
        self,
        case: dict[str, Any],
        evaluation: dict[str, Any],
    ) -> str:
        """Write all run artifacts; return run_id."""
        write = self._config.get("write_outputs_v1", True)
        if not write:
            return self._run_id

        # decision_trace.json — per directive
        self._write_json("decision_trace.json", self._decision_trace)

        # learning_records.jsonl
        self._write_jsonl("learning_records.jsonl", self._learning_records)

        # retrieval_trace.json
        self._write_json(
            "retrieval_trace.json",
            {
                "schema": "finquant_retrieval_trace_v1",
                "run_id": self._run_id,
                "entries": self._retrieval_trace,
            },
        )

        # evaluation.json
        self._write_json("evaluation.json", evaluation)

        # run_summary.json
        summary = self._build_run_summary(case, evaluation)
        self._write_json("run_summary.json", summary)

        # Append to shared cross-run JSONL if configured
        if self._shared_store:
            self._shared_store.parent.mkdir(parents=True, exist_ok=True)
            with open(self._shared_store, "a") as f:
                for rec in self._learning_records:
                    f.write(json.dumps(rec) + "\n")

        # RMv2 SQLite memory index (optional dual-write)
        db_key = (self._config.get("memory_sqlite_path_v1") or "").strip()
        if db_key and self._learning_records:
            from rmv2.memory_index import upsert_learning_record

            for rec in self._learning_records:
                upsert_learning_record(db_key, rec)

        return self._run_id

    def get_run_dir(self) -> Path:
        return self._run_dir

    def get_shared_store_path(self) -> Path | None:
        return self._shared_store

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_run_summary(
        self, case: dict[str, Any], evaluation: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "schema": SCHEMA_RUN_SUMMARY,
            "run_id": self._run_id,
            "agent_id": self._config.get("agent_id", "finquant"),
            "case_id": case.get("case_id", ""),
            "symbol": case.get("symbol", ""),
            "timeframe_minutes": case.get("timeframe_minutes", 0),
            "mode": self._config.get("mode", "deterministic_stub_v1"),
            "use_llm_v1": self._config.get("use_llm_v1", False),
            "runtime_data_window_months_v1": self._config.get("runtime_data_window_months_v1"),
            "runtime_interval_v1": self._config.get("runtime_interval_v1"),
            "runtime_interval_minutes_v1": self._config.get("runtime_interval_minutes_v1"),
            "decisions_emitted": len(self._decision_trace),
            "learning_records_written": len(self._learning_records),
            "final_status_v1": evaluation.get("final_status_v1", "INFO"),
            "retrieval_records_used": len(self._retrieval_trace),
            "artifacts": [
                "decision_trace.json",
                "learning_records.jsonl",
                "retrieval_trace.json",
                "evaluation.json",
                "run_summary.json",
            ],
            "output_dir": str(self._run_dir),
        }

    def _write_json(self, filename: str, obj: Any) -> None:
        with open(self._run_dir / filename, "w") as f:
            json.dump(obj, f, indent=2)

    def _write_jsonl(self, filename: str, records: list[dict]) -> None:
        with open(self._run_dir / filename, "w") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
