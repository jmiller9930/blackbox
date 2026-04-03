# Slack and hashtag operator language

**Audience:** operators and backend/UI engineers wiring the workspace.  
**Primary chat surface:** Slack (Socket Mode); the same routing code is shared with CLI and optional Telegram (`messaging_interface` → `telegram_interface`).

This document lists **hashtag-style commands**, **@-mentions**, **bare keywords**, **human confirmation phrases**, and **Slack environment names**. It separates what is **implemented in the repo today** from what is **specified for future / training v1** in architecture docs.

---

## 1. Implemented today (routing code)

**Source of truth:** `scripts/runtime/telegram_interface/message_router.py` (`route_message`, `_hashtag_command`).

### 1.1 Composable operator hashtags (pure `#` lines → DATA)

**Rule:** The message must be **only** hashtags and whitespace (so normal sentences are not hijacked). Case-insensitive. Tokens may repeat normalized forms (`#context-engine` ≡ `#context_engine`).

**Implementation:** `message_router._extract_hashtag_tokens` → `data_mode=hashtag_composed` → `data_status.compose_operator_hashtag_message`.

| Pattern | Meaning |
|---------|---------|
| `#status` | **Legacy slice:** context engine (🟢/🟡/🔴) **+** execution/phase snapshot (`build_status_text`). |
| `#status #system` | **Full stack:** system rollup (runtime + Pyth + agents from `modules/operator_snapshot`) **+** context engine **+** execution phase — “everything” for ops. |
| `#status #context_engine` | **Narrow:** context-engine health **only**. |
| `#status #runtime` \| `#agents` \| `#pyth` \| `#execution` | **Single slice** (only that plane). |
| `#runtime #agents` | **Union** of slices (no `#status` prefix). |
| `#system` or `#rollup` | Rollup only (UI-parity planes). |
| `#context_engine` alone | Context engine only. |
| `#billy_checkin` | Drift-doctor check-in probe (same gate as API). |
| `#ops_help` \| `#help_ops` \| `#operations` | Index + restart **instructions** (no auto-exec). |
| `#op_restart` | Restart runbook text only. |
| `#anna` `#report_card` \| `#report_card` | Anna **training report card** (same signal as `anna watch` TUI): preflight; curriculum/method; **four curriculum tools** + checklist %; **measurable progress** (tool %, paper numeric %, combined, bottleneck); paper cohort; Grade-12 **gate** (tools + numeric); next focus; carry-forward. `#anna` alone hints to add `#report_card`. |

**Unknown tokens** are listed as ignored; **unrecognized-only** messages return a short error line.

**Training-style multi-tags** (`#train #simulate`, …) are **not** parsed here yet — see §2 — unless the line is still “pure hashtag” and those tokens are added to `_KNOWN_TAGS` in code.

### 1.2 @-mentions and leading forms (multi-persona)

| Form | Agent | Notes |
|------|--------|--------|
| `@anna …` | Anna | Rest of line after `@anna`. |
| `@data …` | DATA | Optional modes: `report`, `insights`, `status`, `infra` as first word after `@data`, or general text. |
| `@cody …` | Cody | Engineering stub. |
| `@mia …` | Mia | Reserved / placeholder. |
| `Anna, …` | Anna | Leading `Anna,` (see Slack Anna routing in `messaging_interface/anna_slack_route.py`). |
| `cody …` | Cody | Leading `cody` + space. |

**Bare keywords (no @):** `report`, `insights`, `status`, `infra` alone → DATA with that mode. Unprefixed NL routes by conservative regex (system/execution status, DB/SQLite cues → DATA; engineering cues → Cody; else **Anna** default).

**Identity intents:** `help`, `who are you`, `what can you do`, `how do i use this` (and `@anna`/`@data` variants) → identity/help flow.

### 1.3 Reply labels (not commands)

Outbound messages are prefixed for humans: **`[Anna — Trading Analyst]`** (Anna), **`[DATA]`**, **`[Cody]`** per `response_formatter.py` and Slack persona enforcement (`slack_persona_enforcement.py`).

---

## 2. Training / operator contract (documented — not all wired in `message_router`)

**Sources:** `docs/architect/ANNA_GOES_TO_SCHOOL.md`, `docs/architect/development_plan.md` (§5.8.2 and related).  
These define **deterministic tags** for governed training and operator control. **They are not necessarily parsed as separate commands** in `message_router.py` until implemented per phase.

### 2.1 Training tags (governed lane)

| Tag / pattern | Intent (contract) |
|---------------|-------------------|
| `#train #simulate` | Enter simulation training path (Bachelor lane rules apply). |
| `#train #trade` | Training fork toward trade path (safety-sensitive, degree-bound). |
| `#train` | Explicit marker that a suggestion should enter staging (with human confirmation). |

**Rule (contract):** Plain-language training suggestions stay **conversation** until explicit confirmation or `#train` / staging flow (`ANNA_GOES_TO_SCHOOL.md` §8).

### 2.2 Inspection and review tags (contract surface)

| Tag | Intent (contract) |
|-----|-------------------|
| `#why` | Ask for rationale / trace of a prior answer. |
| `#status` | **Implemented** as DATA hashtag (see §1.1); contract also discussed broader “operating state” in school doc. |
| `#review` | Request review / exam-board style check (future wiring). |
| `#exchange_status` | Billy-owned exchange connectivity summary (contract: payload from Billy path). |

### 2.3 Anna runtime control (contract — `v1`)

| Command | Required effect (development plan) |
|---------|-------------------------------------|
| `Anna #pause` | Pause Anna runtime participation (not permanent shutdown). |
| `Anna #stop` | Stop participation; runtime marked stopped. |
| `Anna #start` | Start when conditions satisfied. |
| `Anna #restart` | Controlled stop + start. |

**Rule:** Each must emit structured control artifacts (operator id, command, timestamps, state, reason, trace_id) per plan.

### 2.4 Human confirmation grammar (not hashtags)

Used after Anna’s training classification packet:

| Phrase | Meaning |
|--------|---------|
| `stage it` | Promote to staging. |
| `revise it` | One revised candidate only (`v1`). |
| `leave it` | Keep as conversation only. |

---

## 3. Slack environment (channel names — not user “commands”)

| Name | Role |
|------|------|
| `#blackbox_lab` | Lab workspace channel used in directives for live Anna/ingress proofs (`directive_4_6_3_4_c_slack_anna_closure.md`, OpenClaw listen config). |
| `blackbox_lab` / `blackbox-lab` | Alternate keys in `scripts/openclaw/configure_slack_lab_channel_listen.py`. |

These are **where** the bot listens, not messages users type as hashtags.

---

## 4. Machine-readable status (for UI parity with hashtags)

| Resource | Purpose |
|----------|---------|
| `GET /api/v1/context-engine/status` | JSON: `status` (`healthy` \| `degraded` \| `error` \| `unknown`), `reason_code`, paths, heartbeat — same model as `#context_engine` text. **Code:** `modules/context_engine/status.py`, `UIUX.Web/api_server.py`. |

UI can map **green / yellow / red** to `healthy` / `degraded` / (`error` \| `unknown`) consistently with chat.

---

## 5. Canonical pointers

| Topic | Path |
|-------|------|
| Hashtag routing (code) | `scripts/runtime/telegram_interface/message_router.py` |
| Composable hashtag composer | `scripts/runtime/telegram_interface/data_status.py` (`compose_operator_hashtag_message`) |
| Repo-relative system rollup (Slack + API parity) | `modules/operator_snapshot.py` |
| Operator README (Slack + hashtags) | `scripts/runtime/README.md` |
| Training / school contract | `docs/architect/ANNA_GOES_TO_SCHOOL.md` |
| Development plan operator / training v1 | `docs/architect/development_plan.md` (search “Operator control”, “#exchange_status”) |
| Portal “natural language” copy | `UIUX.Web/docs-anna-language.html`, `UIUX.Web/guide.html` |

---

## 6. Change control

When adding a **new** hashtag that must be deterministic for operators:

1. Implement in `message_router._hashtag_command()` (or agreed parser).  
2. Document the row in **§1** of this file.  
3. Optionally extend `scripts/runtime/README.md` Slack section.  
4. Add or extend a test (e.g. `tests/test_context_engine.py` for isolated router load, or full `telegram_interface` tests when imports allow).

---

## 7. Gaps (what the dictionary / chat do not cover yet)

These are **not omissions by accident** — they are **next-wave** items to align chat with APIs and ops reality.

| Gap | Why it matters | Existing source (today) |
|-----|----------------|-------------------------|
| **Aggregated “system” status** | `#status` in §1 is **context engine + execution_context MD**, not the same object as the UI **system rollup**. | `GET /api/v1/system/status` → `build_system_status()` in `UIUX.Web/api_server.py` (control plane, data plane / Pyth, UI API, agent workers, per-agent nodes + fix hints). |
| **Runtime vs agents vs market** | Operators think in **planes**; hashtags only expose one slice. | `GET /api/v1/runtime/status`, `/api/v1/agents/status`, `/api/v1/market/pyth/status`. |
| **Ollama / LLM path** | Anna “brain off” is a common failure mode. | Env + `tools/check_ollama_runtime.py`; not a first-class hashtag. |
| **Messaging process** | Slack Socket Mode app **is** the bot process — distinct from context engine. | `python3 -m messaging_interface`; no GET probe in §4. |
| **Sentinel / Hermes / Foreman** | Stack supervision exists outside DM routing. | `python3 sentinel.py --status`; `foreman_v2`; not exposed as hashtags. |
| **Execution / approval / kill switch** | Strong safety boundaries — historically **no** control from chat. | `execution_cli.py`, `approval_cli.py`; API `run_control` mostly **not_wired** for agents. |

**Naming collision:** the word **`#status`** is overloaded — **school doc** (§2.2), **bare `status`** to DATA, and **§1.1 hashtag** mean different things. Future option: split into **`#status_system`** (rollup / API parity) vs **`#status_context`** (context engine + execution file) vs plain `@data status` (legacy DATA mode).

---

## 8. Proposed status hashtags (read-only) — align with API

**Intent:** “Ask for virtually any **status**” by **deterministic tags** that mirror GET routes (same facts as the portal pills). Implementation would call shared helpers or HTTP to localhost **from the bot host** (not from a developer laptop unless proxied).

| Proposed token | Parity endpoint / fact | Notes |
|----------------|-------------------------|--------|
| `#system_status` | `/api/v1/system/status` | Top-level rollup + `nodes` + embedded `fix` hints (docker, drift doctor, etc.). |
| `#runtime_status` | `/api/v1/runtime/status` | Control / runtime plane. |
| `#agents_status` | `/api/v1/agents/status` | Anna, Billy, DATA, … as configured. |
| `#pyth_status` | `/api/v1/market/pyth/status` | Data plane / stream health. |
| `#ollama_status` | (new small probe or wrap `check_ollama_runtime`) | LLM reachability for Anna. |
| `#messaging_status` | (new: process heartbeat or “last Bolt connect”) | Answers “is Slack bridge up?” |

**Optional conjunction pattern (single message):** allow **two tokens** on one line for deterministic routing, e.g. `#status #pyth` → combined DATA reply (parser extension). Avoid free-form English for the machine half — keep **closed vocabulary**.

---

## 9. Restart / control from chat — not “any service” without governance

**Design principle:** Read-only status hashtags are **low risk**. **Restarting arbitrary services from Slack** is high risk (wrong host, confused environments, no audit). The repo already states **no execution / kill switch from Telegram**; Slack should inherit the same default.

**Safer patterns:**

| Pattern | Role |
|---------|------|
| **Fix hints only** | `#system_status` text includes the same **commands/docs** already embedded in `build_system_status()` `fix` blocks — operator copies to shell. |
| **Portal / systemd** | Restarts run from **approved** automation (internal UI button, systemd unit, clawbot runbook) — not an open-ended `#restart_postgres`. |
| **Gated control POST** | Extend `POST /api/v1/.../control` with **explicit** allowlist (today Billy check-in is partially wired) — hashtags map to **requests** that return **accepted/rejected + reason**, not silent fork. |
| **Two-step confirmation** | e.g. `#restart_messaging` requires a **second message** `CONFIRM restart_messaging` from same user within TTL — document in governance. |

**Contract commands** (`Anna #restart`, etc. — §2.3) still require **structured artifacts** (operator id, trace_id) before implementation.

**What not to add** as raw hashtags: unlimited `#restart_*` for every subprocess — that becomes undebuggable and unsafe.

---

## 10. Summary — should we add to the dictionary?

**Yes — as §7–9 above:** (1) acknowledge **system/runtime/agent/Pyth** status vs current `#status`; (2) list **proposed read-only** hashtags aligned with **existing JSON APIs**; (3) state clearly that **full “restart any service”** belongs behind **governance + allowlist**, not a growing hashtag soup.

---

*Last consolidated from runtime, architect school doc, development plan, messaging README, and `UIUX.Web/api_server.py` routes.*
