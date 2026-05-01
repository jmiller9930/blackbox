# Agent Lab — Architecture Notes

**Authority document:** `docs/architect/FINQUANT_UNIFIED_AGENT_LAB_ARCHITECTURE_001.md`

---

## Core principle

> The application is not the agent.  
> FinQuant is the agent.  
> The LLM is a governed reasoning organ inside FinQuant.

---

## Ownership boundaries

| Owner | Owns |
|-------|------|
| FinQuant | Identity, decision contract, memory, learning records, governance flags |
| LLM | May provide reasoning — does not directly write memory or policy |
| Lifecycle engine | Steps through candles one at a time; enforces no-lookahead |
| Memory store | Durable JSONL; store ≠ promotion |
| Retrieval | Only surfaces records with `retrieval_enabled_v1 == true` |

---

## Phase 0 (scaffold)

- Decision source: `rule` (stub)
- LLM: disabled
- Retrieval: disabled
- Acceptance bar: lifecycle closure, not profitability

## Future phases

- Phase 1: Wire LLM reasoning into `lifecycle_engine.py`; convert output to `finquant_decision_v1`
- Phase 2: Enable retrieval; test behavior delta with prior records
- Phase 3: Promote records via governance; test learning loop
- Integration: Only after Phase 2–3 pass does FinQuant wire back into the application

---

## No-lookahead rule

Each `step.visible_bars` contains only bars that were observable at that point in time.  
`outcome_candles` are never passed to the decision context.  
The lifecycle engine enforces this boundary.

---

## LLM integration guidance (Phase 1+)

All LLM output must be parsed into `finquant_decision_v1` before it is treated as a decision.  
Raw LLM output is not authoritative by itself.  
`decision_source_v1` must be set to `"llm"` or `"hybrid"` accordingly.
