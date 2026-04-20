# Quantitative User Guide

**Status:** Working draft  
**Scope:** `game_theory/` folder only  
**Audience:** Operator, reviewer, or teammate who needs to understand what this system is, how to participate in it, and how to interpret its results.

## Purpose

This guide is written to do three jobs in a logical order:

1. Explain what the system is.
2. Explain how a user participates in it.
3. Explain what results the user should expect to see and how to read them.

The first goal is to let the reader understand the system on paper before touching the UI. The second goal is to explain how the major subsystems fit together. The third goal is to connect that mental model to the actual controls, runs, outputs, and decisions.

## How To Read This Guide

Read this guide in order.

- Sections 1-4 explain the system conceptually.
- Sections 5-7 explain the learning system, the operator role, and the outputs.
- Sections 8-9 explain how the subsystems fit together and how the control surface maps to them.
- Section 10 is the reference section for working vocabulary.

## Document Framework

| Section | Purpose | Status |
|---|---|---|
| 1. What This System Is | Define the project in plain language | In progress |
| 2. Core Mental Model | Explain Agent (Anna), Referee, operator, and governed learning | In progress |
| 3. Standard Game Flow | Show the lifecycle as a standard SDLC-style flow | Drafted |
| 4. How The Learning System Works | Walk through learning as a gated system | Planned |
| 5. How The User Participates | Explain what the operator does and does not do | Planned |
| 6. What Results The User Should See | Explain outputs, metrics, and expected artifacts | Planned |
| 7. Subsystems And How They Fit Together | Explain modules and their interactions | Planned |
| 8. Control Surface Guide | Map UI buttons, choices, and knobs to the lifecycle; includes **Upload Strategy** (§8.2) | In progress |
| 9. Reading Results And Choosing Next Steps | Explain how to use results to continue, compare, or reset | Planned |
| 10. Glossary | Define terms used in this folder | Planned |

## 1. What This System Is

This quantitative game theory system is a governed pattern-learning environment. It is not best understood as a live trading bot, a free-form AI strategist, or a charting dashboard. It is best understood as an experiment system with rules.

At a high level, the system allows a user to:

- define or select an experiment,
- run that experiment through deterministic replay,
- measure the outcome,
- compare alternatives where the learning lane is active,
- record evidence from the run,
- decide whether any bounded change should be carried forward.

The core discipline of the folder is simple: proposals may vary, but measured outcomes come from the Referee replay path.

## 2. Core Mental Model

The user should understand the system through four roles.

| Role | Meaning in this folder |
|---|---|
| Operator | Chooses the experiment lane, provides intent, runs the system, reviews evidence, and decides next steps |
| Agent (Anna) | The proposing side of the system; it frames candidate scenarios, interpretations, and bounded variations |
| Referee | The deterministic replay authority; it produces the measured results |
| Learning system | The governed comparison, evidence, memory, and carry-forward loop around the Referee |

This means the system should be read as a bounded loop:

- the operator provides intent,
- the agent side, represented here by Anna, frames or expands that intent inside allowed rules,
- the Referee produces truth,
- the learning layer records, compares, and prepares the next decision.

The user is not expected to hand-author every micro-step. The system is expected to fill in bounded procedural detail inside a framework with constraints. It is not expected to invent its own unrestricted rules outside that framework.

## 3. Standard Game Flow

This section expresses the system as a standard SDLC-style lifecycle so the reader can understand the game before looking at specific screens or controls.

### 3.1 SDLC Flow Chart

```text
                   RENAISSANCE GAME THEORY
                STANDARD LEARNING SYSTEM FLOW


    +--------------------+
    | 1. PLAN            |
    | Hypothesis / intent|
    +---------+----------+
              |
              v
    +--------------------+
    | 2. DESIGN          |
    | Recipe / scenario  |
    | window / behavior  |
    +---------+----------+
              |
              v
    +--------------------+
    | 3. VALIDATE        |
    | Contract / manifest|
    | governed inputs    |
    +---------+----------+
              |
              v
        +------------------+
        | INPUTS VALID ?   |
        +-----+------+-----+
              |YES   |NO
              |      |
              v      v
    +--------------------+   +--------------------+
    | 4. BUILD           |   | REVISE            |
    | Effective run      |   | Fix and resubmit  |
    | data + memory path |   +--------------------+
    +---------+----------+
              |
              v
    +--------------------+
    | 5. EXECUTE         |
    | Referee replay     |
    +---------+----------+
              |
              v
    +--------------------+
    | 6. TEST / MEASURE  |
    | Trades, PnL,       |
    | expectancy, audit  |
    +---------+----------+
              |
              v
     +--------------------------+
     | LEARNING LANE ACTIVE ?   |
     +-----------+------+-------+
                 |YES   |NO
                 |      |
                 v      v
    +--------------------+   +--------------------+
    | 7A. ANALYZE        |   | 7B. RECORD ONLY    |
    | Candidate search   |   | Execution evidence |
    | comparison / proof |   | without comparison |
    +---------+----------+   +---------+----------+
              |                        |
              +-----------+------------+
                          |
                          v
    +--------------------+
    | 8. RECORD          |
    | Memory, scorecard, |
    | logs, artifacts    |
    +---------+----------+
              |
              v
    +--------------------+
    | PROMOTE CHANGE ?   |
    +---------+------+---+
              |YES   |NO
              |      |
              v      v
    +--------------------+   +--------------------+
    | 9A. RELEASE        |   | 9B. ITERATE        |
    | Memory bundle /    |   | Keep current state |
    | Groundhog carry    |   | and try next run   |
    | forward            |   +--------------------+
    +---------+----------+
              |
              v
    +--------------------+
    | 10. NEXT RUN       |
    | Re-enter lifecycle |
    +--------------------+
```

### 3.2 What Each Phase Means In This System

| SDLC phase | Meaning in `game_theory` |
|---|---|
| Plan | The operator chooses the question to test |
| Design | The system expresses that question as a recipe, scenario, and evaluation window |
| Validate | The system checks whether the requested run is structurally allowed |
| Build | The effective run is assembled from the validated pieces |
| Execute | The Referee replay runs deterministically over the tape |
| Test / Measure | The run produces measurable outcome evidence |
| Analyze | If enabled, the learning lane compares control and candidates and builds proof |
| Record | The system stores run evidence, operator evidence, and memory artifacts |
| Release | A bounded change may be explicitly carried into a future run |
| Iterate | The next experiment begins from the current governed state |

### 3.3 Most Important Reading Of The Flow

The user should take three points from the chart above.

1. The Referee path is where truth is produced.
2. Recording evidence is not the same thing as changing future behavior.
3. A future run changes only when a bounded carry-forward step is explicitly promoted.

That last point is critical. The system may measure, compare, and remember many things, but future behavior only changes through an explicit path such as a memory bundle or Groundhog carry-forward.

## 4. How The Learning System Works

This section will explain the learning system as a gated loop rather than a single feature. It will cover:

- how learning starts from operator intent,
- which gates a run must pass through,
- when the system is only measuring,
- when comparison and candidate search are active,
- how evidence differs from carry-forward,
- where memory fits inside the larger learning system.

## 5. How The User Participates

This section will explain the operator role in plain language. It will cover:

- what the user is expected to decide,
- what the user is not expected to micromanage,
- how recipes, scenarios, and windows relate to the user,
- how to introduce a **test strategy manifest** without editing shipped baseline JSON (see **§8.2 Upload Strategy** in the web UI and `STRATEGY_IDEA_FORMAT.md`),
- how the user reviews runs and chooses next steps.

## 6. What Results The User Should See

This section will explain the expected output of the system. It will cover:

- scenario-level results,
- batch-level results,
- learning and audit signals,
- what counts as evidence,
- what does not count as proof of improvement.

## 7. Subsystems And How They Fit Together

This section will explain the major subsystems and their relationships. It will cover:

- replay and scoring,
- scenario and recipe definition,
- comparison and candidate search,
- memory and carry-forward,
- evidence and operator-facing artifacts,
- how the web control surface sits on top of these pieces.

## 8. Control Surface Guide

This section maps the lifecycle to the actual operator controls in the pattern-game web UI.

### 8.1 Core controls (planned detail)

The guide will expand on:

- **Pattern** (operator recipe / run template): PML, Reference Comparison, or Custom scenario JSON.
- **Evaluation window** and **context memory** mode.
- **Policy** line when a single catalog policy is active (execution manifest id).
- **Workers**, **Run batch**, **Score card**, and learning-related actions.

### 8.2 Upload Strategy (operator strategy idea → manifest → run)

**Update (UI v2.9.0+):** The Controls panel includes a clearly labeled **Upload Strategy** block. This is **not** the same as choosing a **Pattern**; it is how you introduce a **new strategy manifest candidate** for testing without hand-editing files under `renaissance_v4/configs/manifests/`.

**What you upload**

- A **UTF-8 text file** in the strict **`strategy_idea_v1`** format (first content line must be exactly `strategy_idea_v1`, then `key: value` lines only; unknown keys are rejected).
- **Normative spec (read this before uploading):** in-repo copy `renaissance_v4/game_theory/STRATEGY_IDEA_FORMAT.md`, also served by the web app at **`/strategy-idea-format`**.
- The format is intentionally **not** free-form English: the server does not silently interpret prose or invent catalog modules.

**What happens when you upload**

1. **Upload** — file is received (size-capped; UTF-8 only).
2. **Parse** — strict line parse; any bad key or missing required field fails with a readable error.
3. **Convert** — build a candidate **`strategy_manifest_v1`** JSON object.
4. **Validate** — run **`validate_manifest_against_catalog`** (same gate as repo manifests). Unsupported `signal_modules` ids or other unknown registry ids **fail** with explicit messages (no silent fallback).
5. **Load** — on success, the source text and generated manifest are written under the repo, and **`active.json`** points at the manifest to use for the next run when enabled.

**Where files go (repo-relative, disclosed in UI)**

| Role | Path |
|------|------|
| Uploaded source | `runtime/operator_strategy_uploads/sources/` |
| Generated manifest | `runtime/operator_strategy_uploads/manifests/` |
| Active pointer | `runtime/operator_strategy_uploads/active.json` |

These paths do **not** overwrite **`baseline_v1_recipe.json`** or other shipped baseline assets.

**Operator feedback (no guessing)**

- The UI shows staged status (upload → parse → convert → validate → load) and a checklist: uploaded / validated / loaded / strategy id / name / manifest path / ready to run.
- **GET `/api/operator-strategy-upload/state`** returns the same snapshot for tooling.
- **Clear loaded strategy** calls **`POST /api/operator-strategy-upload/clear`** (clears the active pointer; it does not delete historical source/manifest files).

**Running against your upload**

- Leave **“Use uploaded strategy for the next run”** checked (default when you want the override). The next **Run batch** applies the active uploaded manifest to **every scenario row** in that batch (curated Pattern or Custom JSON), then runs the Referee as usual.
- Uncheck it to run only what each scenario / recipe already specifies (baseline paths).

**Pattern recommendation**

- After a successful upload, the API returns a **recommended Pattern** (e.g. PML for bounded improvement search, or Reference Comparison when the idea name suggests geometry comparison). The UI may auto-select that Pattern when it matches a dropdown option.

**Important limit**

- You can only reference **catalog ids that already exist** in `renaissance_v4/registry/catalog_v1.json`. Introducing **new** signal modules or engine logic still requires engineering (code + catalog), then your idea file can reference the new ids.

## 9. Reading Results And Choosing Next Steps

This section will explain how a user should respond to what they see. It will cover:

- when to continue,
- when to compare,
- when to reset,
- when to record a retrospective,
- when a bounded change may be worth carrying forward.

## 10. Glossary

This section will define the stable vocabulary of the guide, including:

- operator,
- Agent (Anna),
- Referee,
- scenario,
- recipe,
- evaluation window,
- learning lane,
- memory bundle,
- Groundhog,
- scorecard,
- carry-forward.
