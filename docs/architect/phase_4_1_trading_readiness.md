# Phase 4.1 — Real Trading Integration Readiness Map

**Date:** 2026-03-23  
**Status:** Planning blueprint — **does not** enable trading, venues, or secrets in code.

**Aligns with:** [`docs/blackbox_master_plan.md`](../blackbox_master_plan.md) (Phase 4), [`docs/runtime/execution_context.md`](../runtime/execution_context.md).

---

## Purpose

Define the **operational blueprint** for how real trading integration would be approached: accounts, wallets, authority, modes, approvals, separation of chat from execution, safety, and audit — **without** implementing execution logic or storing credentials.

---

## 1. Account model

### Individual accounts

- Each **trading or funding relationship** maps to a **named account context** with a **single clear human owner** (or documented legal entity) responsible for risk and approvals.
- **Separation of funds:** Strategies or purposes that must not commingle use **distinct** account identifiers and documented allocation rules.
- **Human → account mapping:** Every venue account is **attributed** to an owner and (where applicable) operators; **no anonymous “system” accounts** without documented control.

### Shared / pooled / hedge-style accounts

- **Shared or pooled** exposure requires **explicit** written rules: who contributes capital, how P&L and risk are allocated, and who may approve actions.
- **Hedge-style** or offsetting positions across accounts must be **documented** (which legs, which approval path) to avoid accidental net exposure mistakes.
- **Multi-user** access uses **role-based** rules (see §3); no implicit “everyone can trade.”

---

## 2. Wallet / connection model

### Wallet types (conceptual)

| Class | Role |
|-------|------|
| **Hot** | Online convenience; **highest** compromise risk — limited scope and limits if used at all for system-related flows. |
| **Warm / semi-custodial** | Intermediate — policy-defined. |
| **Hardware / cold** | Stronger custody for material funds — preferred for production-sized exposure when architect approves. |
| **Delegated signing** | Only under **explicit** policy (which key, which venue, which limits); not a default. |

### Connection methods

- **Venue API keys** (where used): stored only in **approved secret stores**, never in Git or chat.
- **Wallet adapters** (browser, mobile, hardware): connect through **documented** flows; **no** ad hoc script key paste.
- **Read-only** data feeds remain separable from **signing** paths.

### Custody & secrets (must match Phase 4 master plan)

- **No private keys or seed phrases in Git or chat.**
- Integration uses **vault / secret-manager** patterns approved by technical leadership.
- Recovery material: **offline**, **split** where required, **no** single-person chat copy.

---

## 3. Authority model

| Role | Authority (conceptual) |
|------|-------------------------|
| **Anna** | **Proposes** analysis, structured recommendations, and **paper-level** intents — **no** unsupervised live execution. |
| **Human approvers** (e.g. Sean + designated officers) | **Approve or reject** live-affecting actions per policy; **multi-party** where required. |
| **Billy** (execution agent, future) | **Executes** only **after** policy gate and human approval path — **no** self-directed live trading. |
| **Technical / risk authority** (e.g. John, CTO) | **Revokes** keys, **disables** integration, **freezes** paths without full redeploy. |
| **DATA** | **Evidence / health / integrity** — monitoring and logging; **not** trade approval by default. |

### Role-based permissions & multi-user

- Permissions are **least privilege**: propose vs approve vs execute vs revoke are **separate** concerns.
- **Multi-user** support means **documented** approvers and substitutes — not informal shared passwords.

---

## 4. Execution modes

| Mode | Definition |
|------|------------|
| **Read-only** | Market data, quotes, public feeds — **no** signing, **no** orders. |
| **Paper** | Simulated pipeline (Phase 2 / guardrail / policy-gated action) — **no** venue keys required for core path. |
| **Live (gated)** | Real orders or signed transactions — **only** after Phase 4 gates, human approval, and enabled policy. |

### Transitions

- **Read-only → paper:** Operational / config only; **no** keys.
- **Paper → live:** Requires **explicit** go-live approval, custody readiness, venue onboarding, and kill-switch readiness — **not** a single toggle.
- **Live → read-only / disabled:** **Revocation** path (keys off, integration frozen) must work without panic redeploy.

---

## 5. Approval & signing flow

**Target end-to-end shape (conceptual):**

1. **Chat / UI** — human or Anna-mediated **intent** and context (Telegram, future portals).
2. **Proposal** — structured artifact (e.g. `anna_proposal_v1`-class or venue-specific order intent) with **risk and policy** visibility.
3. **Approval** — **human** (initially **every** live action) via **secure approval plane** — not chat-only for high-risk moves.
4. **Signing** — **isolated** from chat; **wallet / key** or venue API **only** in approved paths.
5. **Execution** — Billy or equivalent **executes** only what was approved.
6. **Audit** — immutable or append-only record of proposal → approval → signature → result.

### Manual vs future automated approval

- **Initial:** **Manual approval** for every live execution.
- **Future:** **Automated** approval only after **validated** policy, **audits**, and **rollback** drills — **architect-approved**, not default.

---

## 6. Chat vs secure execution plane

| Plane | Allowed |
|-------|---------|
| **Chat (Telegram / conversational)** | Discussion, alerts, **proposals** in human-readable form, links to **approval** — **not** raw secrets, **not** final signing. |
| **Secure execution layer** | Wallets, signing, **API keys**, venue calls — **isolated** from chat; **policy-gated**. |

**Explicit rule:** **Chat NEVER directly executes trades** or holds **keys**. Any message that looks like “execute now” in chat must **route** through proposal + approval + signing — not a direct venue call from chat.

---

## 7. Safety & kill switches

- **Kill switch** — global or per-account **halt** of execution (software + venue disable where possible).
- **Trade limits** — size, notional, daily loss, rate limits — **policy-defined** before live scale-up.
- **Account disable** — per-venue or per-wallet **off** without deleting audit history.
- **Emergency revoke** — keys rotated / pulled; integration **frozen**; humans notified.

---

## 8. Audit & traceability

- **Every** live trade (when enabled) must be **traceable**: who approved, what was signed, venue response, timestamp, policy version.
- **Approvals** and **actions** stored in **durable** stores (DB / event log) — **not** only chat scrollback.
- **Link to Phase 2/3 learning:** outcomes feed **episodes**, **insights**, **reflections** — same **evidence-first** doctrine (wins/losses both analyzed).

---

## 9. Non-goals (this phase)

- **No live trading** enabled by this document.
- **No API keys, seeds, or secrets** in repository code or chat.
- **No execution logic** implemented as part of Phase 4.1 **readiness mapping** (no new trading scripts).
- **No exchange connection** work in this phase.
- **No wallet creation** or custody operations in-repo.

---

## Related

- [`docs/blackbox_master_plan.md`](../blackbox_master_plan.md) — Phase 4 summary sections.
- [`docs/architect/global_clawbot_proof_standard.md`](global_clawbot_proof_standard.md) — verification standard for phase closure.
