# Directive 4.6.3.4 — Messenger Configuration + Slack Adapter Bring-Up

## Objective

Add a single-runtime messenger configuration layer and bring up Slack as the next usable operator interface for Anna.

This directive follows **4.6.3.3 (closed)** and assumes messaging abstraction is now in place.

---

## Core Principle

One messenger backend active at a time.

We are not building multi-active fan-out in this leaf.

The system must support multiple messenger definitions in configuration, but runtime must select **one** active backend only.

---

## Primary Goal

Enable Anna to run through Slack as a usable human interface for testing and operation, without binding intelligence to Slack-specific logic.

---

## Scope

This directive includes:

- messenger configuration file
- runtime backend selection
- Slack adapter implementation
- Slack bring-up and proof
- keeping Telegram/CLI intact as adapters

This directive does **not** include:

- multi-backend simultaneous output
- OpenClaw gateway integration
- Discord
- new trading logic
- learning-core extraction
- live trading / keys / venue work

---

## Required Architecture

## 1. Messenger Configuration

Create or extend a JSON config file for messenger selection.

Suggested location:

```text
config/messaging_config.json
```

**Secrets:** Do not commit real tokens. Prefer env overrides, `config/messaging_config.local.json` (gitignored), or operator vault — same discipline as `TELEGRAM_BOT_TOKEN`.

### Required shape

```json
{
  "messaging": {
    "backend": "slack",
    "telegram": {
      "token": "",
      "chat_id": ""
    },
    "cli": {
      "enabled": true
    },
    "slack": {
      "bot_token": "",
      "app_token": "",
      "channel": "",
      "mode": "socket"
    }
  }
}
```

### Rules

- `backend` is the only runtime selector
- only one backend may be active at a time
- other backend blocks remain present as configuration definitions only
- no scattered `enabled=true` logic should override `backend`

---

## 2. Runtime Adapter Selection

At startup, the system must:

1. load `messaging_config.json`
2. read `messaging.backend`
3. instantiate the corresponding adapter
4. fail clearly if backend is unknown or required config is missing

### Required behavior

If backend = `slack`, only Slack adapter should start.

If backend = `cli`, only CLI adapter should start.

If backend = `telegram`, only Telegram adapter should start.

---

## 3. Slack Adapter

Implement a dedicated Slack adapter that uses the existing normalized Anna pipeline.

Suggested location:

```text
messaging_interface/slack_adapter.py
```

### Slack adapter responsibilities

- receive Slack messages
- normalize inbound user text
- call the existing messaging pipeline / Anna boundary
- render outbound response for Slack
- keep transport-specific logic in adapter only

### Slack adapter must NOT contain

- Anna reasoning
- context logic
- memory logic
- LLM logic
- trading decision logic

---

## 4. Formatter Boundary

Slack formatting must begin **after** normalized Anna output exists.

The adapter may handle:

- Slack markdown / mrkdwn
- message envelope
- channel / thread behavior
- Slack-specific identity display

It must not alter Anna’s reasoning content.

---

## 5. CLI Must Remain Available

CLI remains the primary validation surface and fallback testing interface.

Slack does not replace CLI as the proof surface.
Slack becomes the next operator surface.

---

## Slack Bring-Up Requirements

Cursor must determine and document what is required in this repo/environment to run Slack successfully.

If anything is unknown, Cursor must answer it explicitly before or during implementation.

### Cursor must confirm:

1. required Slack tokens / app mode
2. where those secrets/config values live
3. startup command for Slack mode
4. how inbound messages map into the existing pipeline
5. how outbound replies are rendered
6. how to test locally and on clawbot

---

## Required Proof

This directive does not close on “adapter code exists.”

It closes only with proof.

### Proof requirements

#### A. Config proof

- show `messaging_config.json`
- show backend selection works
- prove only one backend starts

#### B. Slack proof

Provide at least 3 prompt examples through Slack adapter:

1. direct Anna question
2. ambiguous question requiring clarification
3. correction / pushback scenario

For each, return:

- input prompt
- normalized output
- Slack-rendered output
- answer source
- evidence the Slack adapter called the shared pipeline

#### C. Boundary proof

Show that Slack adapter contains only transport logic and no intelligence logic.

#### D. No-regression proof

- CLI still works
- Telegram adapter still exists and remains selectable
- existing tests continue to pass

---

## Acceptance Criteria

Directive 4.6.3.4 closes only if:

1. messenger config JSON exists
2. backend selection works with one active backend
3. Slack adapter runs through the shared Anna pipeline
4. Slack can be used as a real interface for Anna
5. CLI remains operational
6. no intelligence logic is embedded in Slack adapter
7. proof artifacts are returned

---

## Operational Notes

Slack is the preferred target surface for this leaf because Telegram is currently a poor operator experience.

That is a valid reason to prioritize Slack now.

---

## One-line Rule

Define many messengers in config, run one at a time, and keep intelligence out of the transport.
