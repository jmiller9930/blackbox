# Execution context (rehydration)

**Purpose:** Persistent reminder of **where** runtime verification runs, **what phase** the repo targets, and **what proof** is mandatory—so work does not silently fall back to local-only runs or informal proof.

---

## Why context drift happens

Without a single loaded source of truth, automation and assistants can:

- run commands only on a developer machine  
- skip SSH verification on the designated host  
- omit persistence proof (SQLite rows, staging file writes)  
- lose track of which phase is current and what was last closed  

This file, plus [`context_loader.py`](../../scripts/runtime/context_loader.py), makes **execution context** explicit before acting.

---

## 1. Phase tracking

| Field | Value |
|--------|--------|
| **current_phase** | The active roadmap phase for execution-context work (see machine-readable block below). |
| **last_completed_phase** | Last phase closed with **clawbot proof** per [`global_clawbot_proof_standard.md`](../architect/global_clawbot_proof_standard.md). |

Update **`last_completed_phase`** when the architect records a phase **CLOSED** in [`agent_verification.md`](../architect/agent_verification.md).

---

## 2. Execution environment

| Field | Value |
|--------|--------|
| **primary_host** | `clawbot.a51.corp` |
| **repo_path** | `~/blackbox` |
| **required_execution** | **SSH** to `primary_host` and run verification there. Local execution is **dev fallback only** and is **not** sufficient for phase closure. |

---

## 3. Proof standard

**Reference:** [`docs/architect/global_clawbot_proof_standard.md`](../architect/global_clawbot_proof_standard.md)

Every mandated phase proof **must** include:

1. `cd ~/blackbox` → `git pull origin main` → `git rev-parse HEAD`  
2. Required **runtime** commands on **clawbot**  
3. **Persistence proof**: DB row (`id`, `title`, `state`) and/or file content proving writes  
4. Trimmed JSON (not vague summaries)  

---

## 4. Rules (non-negotiable)

- **NEVER** treat “runs locally” as phase closure.  
- **ALWAYS** verify on **clawbot** when a directive requires it.  
- **ALWAYS** return the full **proof package** (commands, HEAD, outputs, persistence).  

---

## 5. Telegram personas (Phase 4.6.3)

| Persona | Silo | Default when |
|--------|------|----------------|
| **Anna** | Trading / market / risk / concepts / analyst | No `@`, or ambiguous question (spokesperson); natural trading questions |
| **DATA** | SQLite, execution context, reports, insights, status, infra, connectivity | `@data`, or NL cues (status, report, DB, schema, telemetry, …) |
| **Cody** | Engineering / planning / repo | `@cody`, `cody …` lead, or clear engineering NL |

**Rules:** Every reply is **persona-owned** — first line of message text is **`[Anna]`**, **`[DATA]`**, or **`[Cody]`** (optional **`[Mia]`** for reserved `@mia` only). The **Telegram bot display name** (e.g. BB Trader) is the **bot account**, not the speaker. **No** unlabeled assistant output; **`response_formatter`** enforces tags. Anna on Telegram uses **`telegram_interface`** + **`anna_analyst_v1`** — **no** separate OpenClaw process required for chat. Registry alignment: [`agents/agent_registry.json`](../../agents/agent_registry.json).

---

## Machine-readable snapshot (for `context_loader.py`)

The JSON block below is parsed by `scripts/runtime/context_loader.py`. Keep it valid JSON.

```json
{
  "current_phase": "Phase 4.6.3",
  "last_completed_phase": "4.6.3",
  "execution_environment": {
    "primary_host": "clawbot.a51.corp",
    "repo_path": "~/blackbox",
    "required_execution": "SSH to clawbot for verification; local run only as dev fallback"
  },
  "proof_standard_reference": "docs/architect/global_clawbot_proof_standard.md",
  "proof_required": true,
  "rules": [
    "NEVER stop at local execution for phase closure proof",
    "ALWAYS run mandated verification on clawbot.a51.corp",
    "ALWAYS return full proof package: git pull, git rev-parse HEAD, runtime outputs, persistence proof",
    "Telegram (Phase 4.6.3): every reply persona-tagged in message body; bot display name is not the speaker"
  ]
}
```
