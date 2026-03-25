# directive_4_6_3_3_playground_output_contract.md

## METADATA
Directive ID: 4.6.3.3-playground-output
Title: Playground Output Contract & Operator Clarity
Phase: 4.x (Layer 1 – Playground)
Owner: Chief Architect
Coordinator: Chris
Status: IMPLEMENTED (presentation layer)
Depends On: 4.6.3.2
Blocks: Twig 6 (Approval System)
Risk Level: LOW (presentation-only)

> **Note:** The numeric ID here is a work-package label; canonical **4.6.3.3** in the master plan remains **Messaging interface abstraction (closed)**. This directive is scoped to **Playground output contract** only.

## OBJECTIVE
Establish deterministic Playground output so operators clearly understand DATA reasoning and cannot confuse simulation with execution or approval.

## SCOPE

ALLOWED:
- Output formatting only
- Stage visibility
- Structured summaries
- Confidence exposure
- Safety messaging

FORBIDDEN:
- No persistence changes
- No DB schema changes
- No new imports outside learning_core
- No runtime hooks
- No execution pathways
- No approval logic
- No integration with Anna / Cody / Slack / Telegram
- No pipeline logic changes

## IMPLEMENTATION REQUIREMENTS

1. GLOBAL HEADER (MANDATORY)
Print at start of EVERY run:
=== PLAYGROUND MODE (SANDBOX ONLY) ===

2. STAGE OUTPUT CONTRACT (ALL 7 STAGES)

Each stage MUST print EXACTLY:

[STAGE: <stage_name>]

Input:
<raw input>

Process:
<transformation performed>

Output:
<result>

Confidence:
<float or N/A>

Stages REQUIRED:
detect
suggest
ingest
validate
analyze
pattern
simulate

3. SIMULATION POLICY EXPOSURE (MANDATORY)

Simulation Policy:
- would_allow_real_execution: False

4. FINAL STRUCTURED SUMMARY (MANDATORY)

=== PLAYGROUND RESULT ===

Detected Signals:
- ...

Suggested Action:
- ...

Validation Result:
- PASS / FAIL
- Reason: ...

Pattern Match:
- ...

Simulation Outcome:
- ...

Confidence Score:
- ...

----------------------------------------

⚠️ PLAYGROUND MODE — NO EXECUTION PATH
⚠️ Simulation only — not approval
⚠️ No action has been taken

## REGRESSION GUARDS (NON-NEGOTIABLE)

IMPORT RESTRICTIONS:
run_data_pipeline.py MUST NOT import:
- telegram_interface
- execution modules
- dispatch/runtime handlers

ONLY allowed:
- learning_core.*

SANDBOX ENFORCEMENT:
- MUST use open_validation_sandbox()
- MUST reject production SQLite paths
- MUST NOT call default_sqlite_path() from playground (use learning_core `assert_non_production_sqlite_path`)

SIMULATION BOUNDARY:
- simulate_and_record_remediation_execution ONLY
- evaluate_simulation_policy MUST return:
  would_allow_real_execution = False

## ACCEPTANCE CRITERIA

- All 7 stages print correctly
- Header present
- Simulation policy printed
- Final summary present
- Safety warnings present
- No execution occurs
- No external calls triggered
- No non-sandbox DB writes

## PROOF REQUIREMENTS

Verifier SHOULD capture:

1. Full CLI output
2. Code diff (`run_data_pipeline.py`)
3. Import audit (learning_core only)
4. Sandbox DB path + confirmation
5. Simulation policy output showing FALSE

## FAILURE CONDITIONS

Directive FAILS if:
- Any stage missing
- Header missing
- Safety text missing
- Simulation implies execution
- Any non-learning_core import appears
- Any runtime or execution path introduced
