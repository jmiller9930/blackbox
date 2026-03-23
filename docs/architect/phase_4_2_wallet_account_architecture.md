# Phase 4.2 — Wallet / Account Integration Architecture (Stub)

**Date:** 2026-03-23  
**Status:** Architecture stub — **planning and boundaries only**. **Does not** implement wallets, signing, exchanges, vaults, or live trading.

**Builds on:** [`phase_4_1_trading_readiness.md`](phase_4_1_trading_readiness.md), [`blackbox_master_plan.md`](../blackbox_master_plan.md) (Phase 4).

---

## Purpose

Translate the Phase **4.1** readiness blueprint into a **concrete technical shape**: how accounts and wallets are represented, how identity maps to access, where approval and signing split from analysis, and how chat hands off to a **secure execution plane** — so later implementation phases can proceed without ambiguity.

---

## 1. Account entity model

### Conceptual entities

| Entity | Role |
|--------|------|
| **Human user** | A natural person (or documented legal principal) with identity, roles, and contact channels; **not** interchangeable with a software agent. |
| **Trading account** | A **logical** container for venue exposure: strategy, limits, policy binding, and audit. **Not** the same as a single wallet — one account may use one or more wallets/connections per venue rules. |
| **Wallet** | A **key custody / signing interface** (browser extension, mobile, hardware, or venue-derived). Holds or references **public** addresses; **keys** stay in vault/custody boundary, not in app source. |
| **Venue connection** | Read-only or trading-capable **link** to an exchange/chain API, scoped by account, mode, and policy. |
| **Approval role** | Permission to **authorize** a specific class of action (e.g. size limits, venue list). |
| **Execution authority** | Permission to **cause** a signed action to occur **after** approval — typically **Billy** (agent) bounded by policy, not unbounded. |

### Relationships

- **One human** may **own or operate** **multiple** trading accounts (different strategies, risk buckets).
- **Multiple humans** may **govern** one **shared / pooled / team** account via **roles** (approvers, operators) — **documented** in advance.
- **Account ≠ wallet:** A **trading account** is policy + venue + exposure context; a **wallet** is a signing/custody tool. Linking them is **explicit** and **auditable**.
- **Venue connection** attaches to **account** with a **mode** (read-only / paper / live gated).

---

## 2. Wallet integration models

### Patterns (conceptual)

| Pattern | Who holds keys | Who signs | System visibility | System capability |
|---------|----------------|-----------|-------------------|-------------------|
| **Direct user wallet (e.g. connect in browser/mobile)** | User (or user-controlled wallet app) | **User** at signing time; system may receive **signed** payloads or session proofs | **Public** addresses, **approved** tx intents (not raw secrets) | **Request** signature via wallet; **never** embed seed |
| **Delegated / service-assisted** | Split: **Vault** or **HSM** holds material; user or policy authorizes | **Policy** + **human** or **approved automation** triggers signing path | **No** raw keys in app; **metadata** only in runtime | **Enqueue** approved operations; **connector** talks to vault |
| **Hardware / stronger custody (future)** | **User** or **custodian**; device-bound | **User** or **policy** on device | Same as direct — **no** key material in repo | **Prepare** unsigned tx; **hand off** to device flow |

### Rules

- **Raw seed phrases** and **private keys** must **never** be embedded in application code, **repo**, or **chat**.
- **Connection** (identity, address, permissions) and **signing** (authorization to produce a signature) are **separate** concerns: design APIs and flows so signing is **explicit** and **after** approval.

---

## 3. Account access modes

| Mode | Allows | Forbids |
|------|--------|---------|
| **Read-only market / account visibility** | Quotes, balances (if API permits read), positions view — **no** orders | Signing, transfers, order placement |
| **Paper / simulated** | Current paper pipeline (`anna_*`, guardrails, episodes) — **no** venue keys required for core path | Any **live** venue write |
| **Approval-required live** | **After** human approval + policy gate: **signed** actions per scope | **Silent** or **chat-only** execution |
| **Future automated (gated)** | **Not active now** — policy-defined auto-approval **only** after architect approval, audits, drills | Default automation without governance |

**Transitions** are **explicit** (config + approval record), not implicit from chat tone.

---

## 4. Identity, permissions, and authority mapping

### Roles (conceptual)

| Role | Function |
|------|----------|
| **Strategist / analyst** | Interprets context, proposes — **Anna**-class outputs; **no** live execution authority. |
| **Operator** | Runs day-to-day workflows within **approved** limits; **no** override of policy without approver role. |
| **Approver** | **Grants** or **denies** specific live actions (human or delegated policy). |
| **Signer** | **Cryptographic** signing actor (human wallet, hardware, or vault) — **never** chat. |
| **Executor** | **Billy** (future): carries out **approved** execution steps **within** boundaries; **cannot** expand scope. |
| **Revoker / admin** | Disables **keys**, **accounts**, or **modes** — **John** / CTO path + risk owner. |

### Roster alignment

| Actor | Boundary |
|-------|----------|
| **Sean** | Risk owner, business approver class; **grants** authority; **not** a signing implementation. |
| **John** | Technical **revocation**, architecture, security sign-off. |
| **Future users** | Same role model — **least privilege**, **documented** approvers. |
| **Anna** | **Recommends**; **never** irreversible financial execution from chat. |
| **Billy** | **Executes** only **within** approved, policy-bound envelopes. |

**Explicit:** **Humans** grant and revoke **authority**; **Anna** recommends; **Billy** executes **only** inside approved boundaries.

---

## 5. Signing boundary

### Layers (strict order)

1. **Analysis / recommendation** — Anna, paper tools, guardrails — **no** chain keys.  
2. **Approval** — human or **future** gated automation — **recorded** intent.  
3. **Signing** — **secure plane only**; produces **signatures** or **signed** API calls.  
4. **Execution** — venue/chain receives **signed** action; **Billy** or equivalent **orchestrates** only **after** 2–3.

### Rules

- **Chat** never **directly** executes **irreversible** financial actions.  
- **Sensitive** approval and signing **must** move to a **secure plane** (portal, wallet, vault connector).  
- **Recommendation** in chat may **link** to a **pending approval** in the secure plane — **not** substitute for it.

---

## 6. Chat-to-portal / secure plane handoff

### Pattern

**Chat (Telegram / conversational)** → **intent + context** → **secure portal / signing plane** → **execution path** (policy-gated).

### Why chat is the command surface

- **Fast** human coordination, alerts, and **discussion** of proposals.

### Why chat is not the authority surface

- **No** key material, **no** final signing, **no** bypass of approval — **prevents** social-engineering and accidental execution.

### What requires handoff

- **Any** live order, transfer, or key-bearing operation.  
- **High-risk** config changes (e.g. enable live mode, add new venue).

### Mobile-first

- Approvals and **time-sensitive** decisions should be **reachable** on **mobile** (portal, push, wallet app) — **not** only desktop chat.

---

## 7. Secrets / vault responsibility boundary

| Zone | Responsibility |
|------|------------------|
| **Vault / secret manager** (future concrete choice) | **Stores** API keys, signing service credentials, **not** in Git. |
| **Runtime application** | **Consumes** **references** (IDs, env indirection) **only**; **no** raw secrets in repo. |
| **Connectors** | **Abstract** vault vs cloud; **rotate** and **scope** per policy. |

**Must never** appear in **chat**, **repo**, or **ad hoc scripts:** seeds, private keys, raw API secrets.

**This document does not** select a specific vault product — **architect** decision later.

---

## 8. Event / audit model (conceptual)

Minimum **event types** later implementation should emit (not a DB schema here):

- **wallet_connected** / **wallet_disconnected**  
- **account_linked** / **account_unlinked**  
- **approval_granted** / **approval_revoked** / **approval_expired**  
- **signing_requested** / **signing_completed** / **signing_rejected**  
- **execution_requested** / **execution_completed** / **execution_blocked**  

Each ties to **actor**, **account**, **policy version**, and **timestamp** for traceability and Phase 2/3 **learning** linkage.

---

## 9. Failure / safety cases

| Case | Expected behavior (architecture) |
|------|----------------------------------|
| **Revoked authority** | **No** new signing; **pending** intents **cancel** or **block**; **notify** operators. |
| **Disconnected wallet** | **Execution** blocked; **read-only** may continue; **no** silent retry with keys. |
| **Approval expired** | **Requires** new approval; **no** stale approval reuse. |
| **Signer unavailable** | **Queue** or **fail** visibly; **no** fallback to chat signing. |
| **Policy mode = FROZEN** | **Block** live execution; **paper** may continue per policy. |
| **Kill switch** | **Halt** outbound execution paths; **preserve** audit trail. |

---

## 10. Explicit non-goals (Phase 4.2)

Phase **4.2** does **not**:

- Implement **wallet** connection or UI.  
- Implement **signing** or **exchange** APIs.  
- **Store** secrets in-repo or in this document.  
- **Enable** live trading.  
- Define **final** SQLite schema or event store — only **conceptual** audit expectations.

---

## Related

- [`phase_4_1_trading_readiness.md`](phase_4_1_trading_readiness.md)  
- [`../blackbox_master_plan.md`](../blackbox_master_plan.md) — Phase 4  
- [`global_clawbot_proof_standard.md`](global_clawbot_proof_standard.md)
