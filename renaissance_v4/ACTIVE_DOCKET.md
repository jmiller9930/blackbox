# BLACKBOX / JUPITER / KITCHEN — ACTIVE DOCKET

Living work queue for Renaissance / Jupiter / Quant Research Kitchen. **Priority order at bottom — do not reorder without architect approval.**

---

## PHASE 1 — PIPELINE PROOF (CURRENT BLOCKER)

**DV-ARCH-JUPITER-LIVE-PROOF-047**

**Goal:** Prove the system can produce real closed trades.

- Deploy latest build to clawbot
- Activate `jup_pipeline_proof_v1`
- Confirm:
  - trades open
  - trades close
  - `sean_paper_trades` populated
  - PnL exists

**This unblocks everything downstream.**

---

## PHASE 2 — OPERATOR POLICY INTAKE

**DV-ARCH-KITCHEN-POLICY-INTAKE-048**

**Goal:** Operator can upload policy → system validates + tests.

- File upload (TS primary)
- Validation (compile + structure)
- Normalization → PolicySpecV1
- Deterministic test pipeline: signals, trades, closes, PnL
- Candidate policy creation

**Removes engineering dependency for policy onboarding.**

---

## PHASE 3 — KITCHEN UI CLEANUP

**DV-ARCH-KITCHEN-UI-CLEANUP-045**

**Goal:** Make Kitchen usable for operators.

- Fix layout issues
- Clarify operator flow
- Separate: submit policy → evaluate policy → (future) deploy policy
- Remove clutter / debug feel

**Prevents confusion and misuse.**

---

## PHASE 4 — POLICY DEPLOYMENT CONTROL

**DV-ARCH-POLICY-DEPLOYMENT-BROKER-049**

**Goal:** Controlled deployment of validated policies.

- Explicit deploy step (NOT upload)
- Target selection: Jupiter | BlackBox
- Enforce: only validated candidates deployable; API-driven deployment

**Separates testing from production.**

---

## PHASE 5 — MONTE CARLO UNBLOCK

**DV-ARCH-MC-UNBLOCK-050**

**Goal:** Enable real MC runs on actual trade data.

- Require non-empty trade series
- Run MC on: pipeline-proof policy, baseline policies
- Produce stability metrics

**Turns system from “running” → “learning”.**

---

## PHASE 6 — SRA (AI AGENT V1)

**DV-ARCH-SRA-V1-051**

**Goal:** Autonomous policy generation loop.

- Generate policy variants
- Submit via intake (048)
- Run test pipeline
- Analyze results
- Iterate improvements

**Introduces self-improving system.**

---

## PHASE 7 — KITCHEN COMPARISON VIEW

**DV-ARCH-KITCHEN-COMPARISON-052**

**Goal:** Move Anna-style comparisons into Kitchen.

- Policy vs policy comparison
- Baseline vs candidate
- Structured metrics (not visual clutter)

**Replaces old Anna parallel concept cleanly.**

---

## PHASE 8 — BLACKBOX CLEAN SEPARATION

**DV-ARCH-BLACKBOX-GOVERNANCE-053**

**Goal:** Remove experimental noise from production.

- BlackBox = production only
- Kitchen = experimentation only
- No parallel lanes in BlackBox

**Enforces system integrity.**

---

## PRIORITY ORDER (DO NOT CHANGE)

1. **047** — Live trade proof  
2. **048** — Policy upload + testing  
3. **045** — UI cleanup  
4. **049** — Deployment control  
5. **050** — Monte Carlo  
6. **051** — AI agent (SRA)  
7. **052** — Comparison view  
8. **053** — Governance cleanup  

---

## ONE-LINE SUMMARY

Prove trades → allow policy upload → clean UI → control deployment → enable Monte Carlo → turn on AI → cleanly separate research vs production.

---

## Related

- Policy spec / normalization: `renaissance_v4/policy_spec/README.md`  
- Policy intake: `renaissance_v4/policy_intake/README.md`  
- Kitchen checklist: `renaissance_v4/QUANT_KITCHEN_COMPLETED_CHECKLIST.md`  
