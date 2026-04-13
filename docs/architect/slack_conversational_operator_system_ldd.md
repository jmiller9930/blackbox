# Slack Conversational Operator System — Low-Level Design (LDD)

**Status:** Contractual (implementation target)  
**Audience:** Engineering (implementer), Operator (acceptance), Architect (governance)  
**Scope:** Slack-native conversational interface over BlackBox / OpenClaw with **grounded** answers, **optional named-agent presentation**, **document-grounded** project Q&A, and **auditable** routing.

**Out of scope for this LDD:** Live venue order submission; full training-system integration; replacing HTTP APIs with LLM inference for factual trading data.

---

## 1. Purpose

Deliver a **single conversational system** where a human can:

1. **Ask operational / trading questions** in natural language and receive answers **grounded in tools** (ledger, policy, market ingest, dashboard bundle, wallet APIs).
2. **Optionally address a named persona** (e.g. Anna, DATA) for **tone and formatting only**, not for a different source of truth.
3. **Ask questions about the project** that are answered from **allowed documentation** (Markdown and similar under the repo), with **citations**, without requiring the operator to read code.

Move from **ambiguous intent** to a **contract**: intent labels, slots, tool calls, logging, and clarification rules are **specified** below.

---

## 2. Design Principles (Non-Negotiable)

| ID | Principle |
|----|------------|
| P1 | **Natural language first** — no required command vocabulary for the operator. |
| P2 | **Clarification over guessing** — at most 1–2 targeted follow-ups when intent or slots are ambiguous. |
| P3 | **Grounded answers only** — trading, PnL, policy outcomes, sync state, wallet balances come **only** from defined tools/APIs. |
| P4 | **Single tool layer** — default path and named path **must** call the **same** tool functions for the same intent/slots. |
| P5 | **Persona is presentation** — named agent = style/tag only; **never** a separate data-access path for factual domains. |
| P6 | **Context assists, never replaces truth** — thread memory resolves references and carries slots; it does **not** author PnL or policy results. |
| P7 | **Everything auditable** — each turn logs intent, slots, tools invoked, source refs, trace_id. |

---

## 3. High-Level Architecture

```
Slack (only operator interface for this system)
    → OpenClaw gateway / dispatch
        → BlackBox Interpreter + Router (this LDD)
            → Intent + slot extraction (+ clarification)
            → Tool layer (Python/HTTP; single registry)
            → Source systems (SQLite ledger, market DB, policy evaluators, bundle builders, wallet module)
        → Context subsystem (thread state + reference resolution + optional doc retrieval index)
            → NOT authoritative for numeric/ledger/policy facts
```

**Supporting components:**

- **`modules/context_engine/`** — operational events, health/status ticks (see existing API patterns).
- **Thread store** (new or extended) — Slack `team/channel/thread_ts` keyed; stores last resolved entities (e.g. `last_trade_id`, `last_market_event_id`, clarified filters).

---

## 4. Dual Routing Model (Contractual)

### 4.1 Default mode (primary UX)

- User does **not** name an agent.
- Router sets `presentation_route = default`.
- Intent/slots/tools execute as in Section 6–7.

### 4.2 Named mode (optional overlay)

- User message matches **named-invoke** pattern (configurable list: e.g. leading `Anna,`, `Anna:`, `DATA,`, case rules TBD).
- Router sets `presentation_route = anna | data | …` **only** after stripping the invoke prefix for intent detection.
- **Same** `intent`, **same** `slots`, **same** `tool_calls` as default for factual domains.
- Output formatter may apply persona template (opening line, emoji policy, length) — **must not** add facts not present in tool outputs.

### 4.3 Critical rule

There shall be **no** code path where:

- `presentation_route=anna` calls different SQL/APIs than `presentation_route=default` for the **same** `(intent, slots)`.

Exception (explicitly allowed, separate intents): **non-factual** “analyst narrative” or **long-form** analysis may be a distinct intent (`deep_analysis`) that **still** must ground **factual claims** via tools or cite **docs**; **must not** invent ledger rows.

---

## 5. Answer Classes (Separation of Concerns)

Implementer must implement **three** answer classes with distinct grounding rules:

| Class | Grounding | Example questions |
|-------|-----------|-------------------|
| **A — Operational / trading facts** | Tools only (ledger, bundle, policy rows, ingest, wallet) | “Last 15 closed trades”, “why no trade on this tile”, “is V3 synced to Binance”, “wallet balance” |
| **B — Project documentation** | Allowed doc corpus only (read + summarize + **mandatory citations**: file path + heading or excerpt id) | “What is the baseline policy?”, “How does JUPv3 differ from V2?”, “What is Foreman?” |
| **C — Clarification** | No external grounding; returns questions | “Baseline only or all strategies?” |

**Class B** must **not** use the LLM to invent trading numbers. If the user mixes (“what’s my PnL and what does the doc say about baseline?”), split into **tool parts** + **doc parts** with clear boundaries in the reply.

---

## 6. Internal Intent Set (Not User-Facing)

Intents are **for routing, tests, and logs** only. Operators do not memorize these names.

| Intent ID | Description | Typical slots |
|-----------|-------------|----------------|
| `explain_trade` | Why a trade / position / tile outcome | `trade_id` or `market_event_id`, optional `strategy_scope` |
| `list_trades` | List recent closed trades | `limit`, `scope` (baseline \| all), `order` (exit_time \| created) |
| `export_trades` | Export CSV or table attachment | same as `list_trades` + `format` |
| `policy_explain` | Policy / signal reason for a bar or slot | `policy_slot` (JUPv2 \| JUPv3), optional `market_event_id` |
| `ingest_status` | Pyth vs Binance / freshness | `lane` (v2 \| v3 \| both) |
| `wallet_status` | Balances / connection | none or `asset` |
| `bundle_snapshot` | Operator dashboard bundle slice | optional keys list |
| `doc_project_qa` | Answer from documentation corpus | `query`, optional `doc_glob` |
| `clarify` | Ask user for missing slots | `missing_slots[]`, `question_text` |

**Versioning:** bump `intent_schema_version` in logs when adding/removing intents.

---

## 7. Tool Layer (Single Registry)

### 7.1 Contract

- Every tool is a **pure function** with a **typed input** and **JSON-serializable output** (or error object).
- Tools **may** call:
  - HTTP: `GET/POST` to existing BlackBox APIs (e.g. `/api/v1/dashboard/bundle`, `/api/v1/wallet/status`, baseline trades report route) with `localhost` or configured base URL.
  - In-process Python: `build_dashboard_bundle`, `fetch_trade_export_rows`, `build_baseline_trades_report`, `build_context_engine_status`, etc.
- Tools **must not** call LLMs for class A facts.

### 7.2 Initial tool map (minimum Phase 1)

| Tool ID | Purpose | Primary source |
|---------|---------|----------------|
| `tool.trades.list` | Last N closed trades | `execution_trades` / `fetch_trade_export_rows` or baseline report builder |
| `tool.trades.export` | CSV bytes + filename | Same + CSV formatter |
| `tool.bundle.get` | Dashboard bundle slice | `build_dashboard_bundle` or HTTP |
| `tool.wallet.get` | Wallet status | `build_wallet_status_payload` or HTTP |
| `tool.ingest.freshness` | V2 vs V3 freshness | Bundle `five_m_ingest_freshness` + `event_axis_source` |
| `tool.policy.row` | Policy evaluation for MID | `policy_evaluations` / existing fetch helpers |
| `tool.context_engine.status` | Context engine health | `build_context_engine_status` |

### 7.3 Documentation tools (class B)

| Tool ID | Purpose | Rules |
|---------|---------|--------|
| `tool.docs.search` | Find relevant chunks | **Allowlist** roots only (e.g. `docs/`, `UIUX.Web/content/`, `agents/` — **exact list in config**). No arbitrary `../`. |
| `tool.docs.read` | Read one file under allowlist | Max size cap; binary rejected |

**Doc answering flow:** `doc_project_qa` → retrieve via `tool.docs.search` + `tool.docs.read` → LLM **summarizes only from provided excerpts** → output includes **“Sources:”** with paths.

---

## 8. Context Subsystem (Thread + Reference Resolution)

### 8.1 Stored per Slack thread (minimum keys)

- `thread_id` (Slack channel + thread_ts composite)
- `last_intent` (optional)
- `last_slots` (partial)
- `anchors`: `{ last_trade_id?, last_market_event_id?, last_export_scope?, last_doc_query? }`
- `clarification_pending`: boolean + which slots

### 8.2 Reference resolution (examples)

| User phrase | Resolution rule |
|-------------|-------------------|
| “that trade” | Use `anchors.last_trade_id` or `last_market_event_id`; if missing → **clarify** |
| “the last one” | Use most recent from **prior tool result** in thread cache |
| “baseline only” | Set `scope=baseline` in slots |

### 8.3 Explicit non-responsibilities

- Context does **not** store authoritative PnL or trade results except as **cached copies** of tool outputs for reference resolution.
- On restart, **re-fetch** facts if stale beyond TTL (configurable).

---

## 9. Clarification Protocol

**Ask** (max 2 questions) when:

- `list_trades` / `export_trades` and `scope` is ambiguous (baseline vs all).
- Reference (“that trade”) has no anchor.
- `doc_project_qa` and query is empty after strip.

**Do not ask** when:

- Safe defaults are documented (e.g. default `limit=15`, `scope=baseline` for operator reports) — **must be listed in config** so behavior is contractual.

**Output:** intent `clarify` with `question_text` + log `clarification_reason`.

---

## 10. Logging and Audit (Per Turn)

Required fields (JSON line or structured log):

- `trace_id` (UUID)
- `slack_team`, `channel`, `thread_ts` (or equivalent)
- `presentation_route` (default | anna | data | …)
- `intent` (or `clarify`)
- `slots` (object)
- `tool_calls[]` — `{ tool_id, input_hash or redacted_input, ok, duration_ms }`
- `source_refs[]` — e.g. `{ type: "api", path: "/api/v1/dashboard/bundle" }`, `{ type: "ledger", query: "execution_trades limit 15" }`, `{ type: "doc", path: "docs/architect/foo.md" }`
- `intent_schema_version`

**Retention:** per operator governance (not fixed in this LDD).

---

## 11. Slack Integration Points (Existing vs New)

**Existing (repo today):**

- `scripts/openclaw/slack_anna_ingress.py` — explicit Anna / greeting; exit 2 defers to embedded model.
- `messaging_interface/slack_adapter.py` — Bolt path with dispatch pipeline.
- `apply_openclaw_dispatch_anna_ingress.py` — patch for dispatch.

**New work (Phase 1):**

- **Router service** (or OpenClaw skill bundle) implementing Sections 6–10.
- **Thread context store** (SQLite or Redis — choose one; document in implementation PR).
- **Tool registry** package with tests.
- **Doc allowlist config** + search (start with **ripgrep** or **simple substring index**; upgrade to embeddings later without breaking contract).

---

## 12. Phased Implementation Checklist (Implementer)

### Phase 1 (MVP)

1. [ ] Tool registry + `tool.trades.list`, `tool.bundle.get`, `tool.wallet.get`, `tool.ingest.freshness` wired to real code paths.
2. [ ] Intent + slot extractor (LLM with JSON schema **or** small rules + LLM fallback) with **tests** on golden utterances.
3. [ ] Thread context store + reference resolution for “that trade” / “last one” using anchors.
4. [ ] Clarification flow for `scope` baseline vs all.
5. [ ] Named-invoke strip + `presentation_route` (style only).
6. [ ] Audit log line per Section 10.
7. [ ] `doc_project_qa` with allowlist + `tool.docs.read` + cited summaries (no numeric trading facts from docs).

### Phase 2 (optional)

- [ ] CSV attachment upload to Slack for `export_trades`.
- [ ] Richer doc search (chunking + embeddings) **same** allowlist contract.
- [ ] Additional intents (training summaries) with **same** tool-only rule for facts.

---

## 13. Acceptance Criteria (Operator / Architect)

1. Same factual question (same utterance) with **default** vs **named** route yields **identical** tool_calls and **same** numeric facts (allowing only formatting differences).
2. No answer claims wallet balance or PnL without `tool.wallet.get` or equivalent in logs.
3. Doc answers include **Sources:** with repo-relative paths under allowlist.
4. Ambiguous trade list requests produce **at most two** clarifying questions or apply safe defaults **defined in config** (defaults must be documented for operator).

---

## 14. One-Line Summary

**Slack is the surface; BlackBox/OpenClaw runs the interpreter; one tool layer grounds all factual trading and system state; context and docs assist interpretation; named agents are presentation-only overlays; documentation Q&A is allowlisted and cited — never a substitute for ledger or APIs.**

---

## 15. Document Control

- **Owner:** Engineering (with Architect approval on intent schema changes).
- **Updates:** When adding intents/tools, bump `intent_schema_version` and append a short changelog at the end of this file.
