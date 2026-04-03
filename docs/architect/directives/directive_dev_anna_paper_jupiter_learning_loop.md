# Directive DEV-BBX-ANNA-002 — Anna paper / Jupiter learning loop (RCS, skills, failure archive, differential)

**Status:** Issued — **developer-owned** (schemas + persistence + CLI/API hooks; no live venue).  
**Issued:** 2026-04-03  
**Governance:** [`../development_governance.md`](../development_governance.md); template alignment: [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md).

**Authorization boundary:** Implements **training-record persistence and queries** for the **paper** harness and **Jupiter-context** observation path. **Does not** enable live Jack/Billy execution, **does not** change Layer 3/4 approval semantics, **does not** replace Phase 5.3 strategy contracts — **integrates with** them.

**Architect / operator intent (canonical prose):** [`../ANNA_GOES_TO_SCHOOL.md`](../ANNA_GOES_TO_SCHOOL.md) §3.3 (RCS/RCA DNA) and §3.4 (paper / Jupiter goals, skills, failure archive, differential).

---

## Scope & objectives

**Requirement:** Deliver a **minimal, auditable learning loop** so Anna’s paper trading produces:

1. **Per-outcome lightweight reflection (`RCS`)** — every paper outcome gets structured fields (see `ANNA_GOES_TO_SCHOOL.md` §3.3): outcome, key metrics, short why, lane/guardrail check, keep/watch/drop.
2. **Qualifying-failure `RCA`** — deeper record when policy triggers (repeat pattern, qualifying loss, or explicit operator flag); fields per §3.3.
3. **Promoted skill artifact on validated wins** — durable, retrievable record (id, summary, evidence refs, optional tags) when a win passes promotion rules you define (e.g. disciplined pass + positive gate); **not** raw chat.
4. **Failure archive** — append-only or versioned store keyed by **`failure_pattern_key`** + outcome id + market context snapshot ref (Jupiter Perps context: at minimum program/pool ids or your normalized snapshot id).
5. **Differential / repeat query** — deterministic function or query: given a new failure (or pattern key + context hash), report **whether** prior archive entries match (same pattern, recurrence count, last N timestamps). No ML required for v1 — **structured compare**.
6. **Operator visibility** — extend or complement [`scripts/runtime/anna_training_cli.py`](../../../scripts/runtime/anna_training_cli.py) (or add `anna_learning_cli.py`) with **`status` / `list-rcs` / `list-failures` / `diff-check`** (names flexible) so the operator can see where training stands **from the shell** on **clawbot** (`~/blackbox`).

**Storage:** Prefer **SQLite** under `data/sqlite/` (new table(s) or dedicated `anna_learning.db` via env) with schema version + migration note; **gitignore** DB files per repo rules.

**Why:** The operator goal is **iterative, evidence-based learning** — win/loss interrogation, reusable skills, failure repetition visibility — not a dashboard promise without persistence.

**Non-negotiable for directive issuance:** Yes.

### Out of scope

- Slack/Telegram UX for this loop (CLI/API optional; messaging is follow-on).
- Automatic LLM-generated “skills” without human or gate promotion rule.
- Jupiter **live** order placement.

### Suggested artifact IDs (contractual minimum)

- `anna_rcs_v1`, `anna_rca_v1`, `anna_promoted_skill_v1`, `anna_failure_archive_v1` — or one normalized table with `kind` enum.

### Proof (closure)

- `pytest` for store + query + differential deterministic behavior.
- Document **primary-host** `git rev-parse HEAD` on clawbot when [`execution_context.md`](../../runtime/execution_context.md) applies.

---

## Documentation / Status Synchronization (Mandatory)

On **closure**: update **`docs/blackbox_master_plan.md`** and **`directive_execution_log.md`** in the **same change set** with matching status.

---

## Closeout / return summary (Mandatory)

Closeout must include:

`Plan/log status sync: PASS`

---

## Developer verification checklist (before return) (Mandatory)

- [ ] RCS persisted per paper outcome; RCA on qualifying path per rules in code + doc §3.3.
- [ ] Promoted skill + failure archive writes + **differential** / repeat query returns deterministic results.
- [ ] Operator can run CLI on clawbot and see state (document commands).
- [ ] Tests pass; no live trading.

---

## Git commit and remote sync (Mandatory for implementation closes)

Record commit SHA; **primary host** when required.

---

## Documentation mismatch failure rule (Mandatory)

Per template.

---

## Proof & evidence (Mandatory for closure)

| Criterion | Evidence |
|-----------|----------|
| Automated | `pytest` command + exit 0 for new tests. |
| Primary host | If mandated: clawbot `git rev-parse HEAD` after pull + CLI smoke. |

---

**Issuance note:** This directive **does not** require the full University Dean, curriculum JSON schema v1, or `modules/context_ledger/` completion — it is a **narrow** persistence slice aligned with §3.4.
