# Agent artifacts (reserved)

**Location:** Artifact files live under `renaissance_v4/state/agent_artifacts/` (runtime directory). This file is the **documentation** for that folder (kept in `game_theory/` with other agent / training notes).

**Strategy Research Agent (SRA)** durable artifacts under Quant Research Kitchen V1.

**Types (see [`docs/architect/strategy_research_agent_v1.md`](../../docs/architect/strategy_research_agent_v1.md)):**

- `agent_manifest_request`
- `agent_experiment_submission`
- `agent_result_summary`
- `agent_promotion_recommendation`

Files are written here by future agent tooling — not by baseline harness by default. Naming convention TBD; include `trace_id` / timestamps in payloads for auditability.

Example JSON: [`../configs/agent_artifacts/example_agent_promotion_recommendation.json`](../configs/agent_artifacts/example_agent_promotion_recommendation.json).
