# directive_4_6_3_3_playground_output_contract.md

## METADATA
Directive ID: 4.6.3.3-playground-output  
Title: Playground Output Contract & Operator Clarity  
Phase: 4.x (Layer 1 – Playground)  
Owner: Chief Architect  
Coordinator: Chris  
Status: CANONICAL (presentation contract; implementation alignment may trail — see §7)  
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
- Structured summaries (stage-specific fields)
- Safety messaging

FORBIDDEN:
- No persistence changes
- No DB schema changes
- No new imports outside `learning_core` (for `run_data_pipeline.py`)
- No runtime hooks
- No execution pathways
- No approval logic
- No integration with Anna / Cody / Slack / Telegram
- No pipeline logic changes

---

## 1. GLOBAL HEADER (MANDATORY)

Print at start of **every** human-readable run (non-`--json`):

```text
=== PLAYGROUND MODE (SANDBOX ONLY) ===
```

---

## 2. STAGE OUTPUT CONTRACT (ALL 7 STAGES)

Each stage **MUST** print a stage banner and operator-facing fields as below. Stages are **presentation-only**; values come from existing pipeline artifacts (no new inference or policy logic in the Playground layer).

**Common rules**
- **Stage name:** printed as `[STAGE: <stage_key>]` where `stage_key` is one of: `detect`, `suggest`, `ingest`, `validate`, `analyze`, `pattern`, `simulate`.
- **Status:** each stage record in structured output includes `status` (`pass` \| `fail` \| `blocked` as applicable). Human-readable output **SHOULD** make pass/fail/blocked obvious (e.g. in summary line or first field line).
- **Missing fields:** if a required display value is unavailable for a run, display `N/A` (do not invent values).

**Legacy note:** An older contract required fixed blocks `Input:` / `Process:` / `Output:` / `Confidence:` per stage. That shape is **replaced** by this §2 stage-specific contract for human-readable output.

### 2.1 DETECT (`detect`)
Display:
- `issue_id`
- `category`
- `severity`
- `evidence_summary` (short; from deterministic issue evidence / first supporting line, or `N/A`)

### 2.2 SUGGEST (`suggest`)
Display:
- `suggested_fix`
- `possible_causes` (optional; only if present on the suggestion artifact)
- Label: **Suggestion only** (must appear for this stage)

### 2.3 INGEST (`ingest`)
Display:
- `remediation_id`
- `source_type` (if available; else `N/A`)

### 2.4 VALIDATE (`validate`)
Display:
- `result` (`pass` / `fail`)
- `failure_class` (if `fail`; else omit or `N/A` per implementation)

### 2.5 ANALYZE (`analyze`)
Display:
- `outcome_category`
- `evidence_summary` (short; from persisted analysis evidence artifact; or `N/A`)

### 2.6 PATTERN (`pattern`)
Display:
- `pattern_id`
- `pattern_status`

### 2.7 SIMULATE (`simulate`)
Display (display-only; from existing simulation result / policy fields):
- `execution_blocked` (true/false — e.g. derived from policy `would_allow_real_execution` **not** being true in this phase)
- `blocked_reason` (from policy / simulation artifact, e.g. `execution_blocked_reason`)
- `approval_required` (from policy artifact)

---

## 3. SIMULATION POLICY EXPOSURE (MANDATORY)

After the simulate stage (human-readable), print:

```text
Simulation Policy:
- would_allow_real_execution: False
```

(`False` is required for the current phase; see regression guards.)

---

## 4. FINAL STRUCTURED SUMMARY (MANDATORY)

Human-readable footer **SHOULD** retain a compact aggregate summary, e.g.:

```text
=== PLAYGROUND RESULT ===
...
----------------------------------------

THIS RUN IS SANDBOX ONLY
NOT APPROVAL
NOT EXECUTION PERMISSION

⚠️ PLAYGROUND MODE — NO EXECUTION PATH
⚠️ Simulation only — not approval
⚠️ No action has been taken
```

Exact line text for the three-line block and warning lines **SHOULD NOT** be weakened when adjusting presentation.

---

## 5. JSON OUTPUT CONTRACT (`--json`)

When `--json` is passed, the CLI emits **one JSON object** to stdout (no stage banners). Structure:

### 5.1 Top-level keys (stable)

| Key | Meaning |
|-----|---------|
| `stages` | Array of stage objects (see §5.2). |
| `ok` | Boolean overall success of the pipeline run. |
| `remediation_id` | Sandbox remediation id when produced or replayed. |
| `pattern_id` | Pattern id when registered. |
| `simulation` | Final simulation dict from `simulate_and_record_remediation_execution` (includes `policy`, etc.). |
| `playground_mode` | `"sandbox_only"`. |
| `simulation_policy` | e.g. `{ "would_allow_real_execution": false }`. |

### 5.2 Each element of `stages`

| Key | Meaning |
|-----|---------|
| `name` | Human stage name, e.g. `DETECT`. |
| `status` | `pass` \| `fail` \| `blocked`. |
| `summary` | Short summary string. |
| `stage_key` | `detect` \| `suggest` \| … \| `simulate`. |
| `contract` | Object carrying per-stage fields for machines. |

**`contract` shape (canonical target):** align keys with §2 field names per stage (e.g. `issue_id`, `category`, `severity`, `evidence_summary` for DETECT). Optional transitional period: implementations may still emit legacy keys `input`, `process`, `output`, `confidence` until updated; new work **SHOULD** migrate `contract` to the §2 field model without changing pipeline semantics.

**JSON stability:** the **envelope** (`stages` / `ok` / `remediation_id` / `pattern_id` / `simulation` / `playground_mode` / `simulation_policy`) is stable; **`contract` inner keys** may evolve from legacy four-key form to §2 fields in a presentation-only change.

---

## 6. REGRESSION GUARDS (NON-NEGOTIABLE)

**IMPORT RESTRICTIONS:**  
`run_data_pipeline.py` MUST NOT import:
- `telegram_interface`
- execution modules
- dispatch/runtime handlers

ONLY allowed:
- `learning_core.*`

**SANDBOX ENFORCEMENT:**
- MUST use `open_validation_sandbox()`
- MUST reject production SQLite paths
- MUST NOT call `default_sqlite_path()` from playground (use `learning_core` `assert_non_production_sqlite_path`)

**SIMULATION BOUNDARY:**
- `simulate_and_record_remediation_execution` ONLY
- `evaluate_simulation_policy` MUST return `would_allow_real_execution = False` in this phase

---

## 7. IMPLEMENTATION ALIGNMENT

This file is the **canonical** operator contract for Playground **presentation**. If the checked-in CLI output differs (e.g. still using legacy `Input`/`Process`/`Output`/`Confidence` blocks), that is a **known gap** to be closed by a **presentation-only** implementation change in `scripts/runtime/playground/run_data_pipeline.py` — **not** by redefining pipeline behavior.

---

## ACCEPTANCE CRITERIA

- All 7 stages are visible with §2 field expectations (or `N/A` where applicable)
- Header present
- Simulation policy printed (human-readable path)
- Final summary + safety lines present
- No execution occurs
- No external calls triggered
- No non-sandbox DB writes

## PROOF REQUIREMENTS

Verifier SHOULD capture:

1. Full CLI output (human-readable and `--json` sample)
2. Code diff (`run_data_pipeline.py`) when aligning implementation to §2 / §5
3. Import audit (`learning_core` only)
4. Sandbox DB path + confirmation
5. Simulation policy output showing `would_allow_real_execution: False`

## FAILURE CONDITIONS

Directive FAILS if:
- Any stage missing from a successful run
- Header or safety text missing
- Simulation implies real execution permission
- Any non-`learning_core` import appears in `run_data_pipeline.py`
- Any runtime or execution path introduced
