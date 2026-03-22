# ARCHITECT UPDATE — CONSULTATION & LEARNING SYSTEM INTEGRATION

Date: 2026-03-22

---

## PURPOSE

This document formalizes the next phase of the BLACK BOX / Cody system.

Core objective:
> Build a system that becomes smarter over time through learning and controlled escalation — not just larger models.

**Real trading / venue integration prerequisites (governance, wallet, signing, gates):** see **Phase 4** in [`docs/blackbox_master_plan.md`](../blackbox_master_plan.md).

---

## FINAL ARCHITECTURE (LOCKED)

### 1. Analyst Agent (Decision Layer)

Responsibilities:

- Market analysis
- Signal generation (long / short / no-trade)
- Confidence scoring
- Structured reasoning output

Required Output:

```json
{
  "action": "long | short | none",
  "confidence": 0.0-1.0,
  "reasoning": "...",
  "context": {}
}
```

---

### 2. Executor Agent (Execution Layer)

Responsibilities:

- Order placement
- Risk management (TP / SL / trailing)
- Slippage + liquidity handling
- Exchange reconciliation

RULE:

Executor NEVER generates signals.

It can:

- Accept
- Reject
- Modify (within risk constraints)

---

### 3. Consultant Layer (Controlled Escalation)

Purpose:

Provide second-opinion intelligence ONLY when required.

This is NOT default behavior.

---

## ESCALATION RULES (MANDATORY)

Escalation is triggered ONLY if:

1. Confidence is below threshold
   - Example: confidence < 0.65

2. Signal conflict detected
   - Multiple indicators disagree

3. High-risk conditions
   - High leverage
   - Low liquidity
   - Volatility spikes

4. Execution uncertainty
   - Orderbook instability
   - Price gaps

---

## ESCALATION FLOW

1. Analyst produces signal
2. System evaluates confidence + conditions
3. If escalation triggered:
   → Call external model (API)
4. Consultant returns:
   - agreement / disagreement
   - reasoning
5. System merges result:
   - approve
   - downgrade confidence
   - reject trade

---

## GOVERNANCE (HARD RULES)

- Escalation must be:
  - Metered (cost-controlled)
  - Logged (full audit trail)
  - Explicitly triggered (not automatic looping)

- API keys:
  - NEVER stored in repo
  - Stored server-side only

- No infinite loops:
  - Max 1 consultation per decision

---

## ROUTER / MODEL SELECTION (FUTURE)

Introduce routing layer:

Inputs:

- task type
- latency tolerance
- cost budget
- confidence level

Output:

- selected model

Examples:

- Local model → default
- External model → escalation only

---

## LEARNING LOOP (CRITICAL)

Every trade must be recorded:

- signal
- confidence
- execution details
- outcome (win/loss)
- reasoning snapshot

This enables:

- strategy improvement
- confidence calibration
- future model tuning

---

## PRIORITY IMPLEMENTATION ORDER

### Phase 1 (Immediate)

- Stabilize execution bot
- Remove unsafe logic
- Add logging

### Phase 2

- Split analyst vs executor

### Phase 3

- Add learning storage
- Track outcomes

### Phase 4

- Implement consultant escalation

### Phase 5

- Add routing / scoring system

---

## FINAL DIRECTIVE

The system must evolve toward:

- Local-first intelligence
- Controlled external escalation
- Continuous learning from outcomes

NOT:

- Blind reliance on larger models
- Uncontrolled API usage
- Single-agent decision making

---

END OF DOCUMENT
