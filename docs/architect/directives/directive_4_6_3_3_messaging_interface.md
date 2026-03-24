# Directive 4.6.3.3 — Messaging Interface Abstraction

## Objective

Decouple Anna from Telegram and introduce a unified messaging interface layer.

Telegram must become an adapter, not a dependency.

---

## Core Principle

Anna is the brain. Messaging is a transport layer.

No reasoning, context handling, or learning logic may live inside any messaging adapter.

---

## Scope

This directive introduces an infrastructure layer and does NOT modify:

- Anna reasoning logic
- context / memory system
- LLM usage flow
- learning loop behavior

---

## Required Architecture

Create:

```
messaging_interface/
- base_interface.py
- telegram_adapter.py
- cli_adapter.py
```

---

## Data Flow

Adapter → normalized input → Anna pipeline → normalized output → adapter formatting

Anna must remain unaware of:

- Telegram
- CLI
- any transport-specific behavior

---

## Implementation Steps

1. Identify all Telegram-specific logic in:
   - response_formatter
   - telegram_interface
   - dispatch/router entry points

2. Extract:
   - input handling
   - output formatting
   - transport metadata

3. Create base interface:
   - send_message()
   - receive_message()

4. Implement CLI adapter:
   - simple stdin/stdout loop
   - becomes primary validation surface

5. Wrap existing Telegram logic into telegram_adapter

---

## Validation

Pass criteria:

- CLI interface runs Anna end-to-end
- Telegram still functions (if stable)
- Outputs from CLI and Telegram are identical (logic, not formatting)
- No duplicated logic across adapters

---

## Out of Scope

- No new agent behavior
- No learning system changes
- No trading logic
- No external integrations

---

## Acceptance Criteria

Directive closes when:

- CLI adapter operational
- Telegram isolated as adapter
- Anna pipeline unchanged
- identical responses across interfaces

---

## One-line Rule

Never bind intelligence to a transport layer.
