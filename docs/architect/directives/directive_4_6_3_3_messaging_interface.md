# Directive 4.6.3.3 — Messaging Interface Abstraction (Architect Approved)

## Objective

Decouple Anna from Telegram and introduce a unified messaging interface layer.

Telegram becomes an adapter, not a dependency.

---

## Core Principle

Anna is the brain.  
Messaging is the transport.

Adapters must not contain:

- reasoning logic
- context logic
- memory logic
- LLM logic

---

## Normalized Output Standard (NON-NEGOTIABLE)

All interfaces must compare against normalized Anna output.

### Required Fields

- interpretation.summary
- answer_source
- intent
- topic
- limitation_flag (if present)

### Rule

Adapters format output only.  
They do not alter meaning.

---

## Required Architecture

messaging_interface/

- base_interface.py
- telegram_adapter.py
- cli_adapter.py

---

## Data Flow

Adapter → normalized input → Anna pipeline → normalized output → adapter formatting

Anna must not be aware of:

- Telegram
- CLI
- Slack
- any transport layer

---

## Implementation Steps

1. Identify Telegram-specific logic:

   - response_formatter
   - telegram_interface
   - dispatch/router

2. Extract:

   - input handling
   - output formatting
   - transport metadata

3. Create base interface:

   - send_message()
   - receive_message()

4. Implement CLI adapter (PRIMARY VALIDATION SURFACE)

5. Wrap Telegram into telegram_adapter

---

## CLI Validation Requirement (MANDATORY)

CLI must support:

```bash
echo "test question" | python -m messaging_interface.cli_adapter
```

Phase cannot close without CLI validation.

---

## Validation Criteria

Pass only if:

- CLI produces correct Anna responses
- Telegram produces equivalent logic (not formatting)
- normalized fields match across interfaces
- no duplicated logic in adapters

---

## Out of Scope

- Slack
- OpenClaw gateway integration
- trading logic
- learning system changes

---

## Acceptance Criteria

Directive closes when:

- CLI adapter operational
- Telegram fully isolated as adapter
- Anna pipeline unchanged
- normalized outputs match across interfaces

---

## Master Plan Requirement

- Add 4.6.3.3 under 4.6.3.x
- Mark as infrastructure leaf
- dependency: after 4.6.3.1 (code closure)

---

## One-line Rule

Never bind intelligence to a transport layer.
