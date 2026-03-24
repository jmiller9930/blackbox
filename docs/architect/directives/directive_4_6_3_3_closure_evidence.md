# Directive 4.6.3.3 — closure evidence (3 prompts)

**Git HEAD (capture):** run `git rev-parse HEAD` on clawbot after `git pull origin main`.

**Env for capture:** `ANNA_USE_LLM=0` (CI-safe; no live Ollama).

---

## Adapter = formatting only (code)

- **`messaging_interface/pipeline.py`** — imports `route_message` + `dispatch` only; **no** reasoning, memory, or LLM calls.
- **`messaging_interface/telegram_adapter.py`** — imports `format_response` / `format_anna_system_message` only; **no** Anna or routing logic.

---

## Prompt 1 — `What day is it?` (Anna / factual)

### Normalized JSON (CLI)

```json
{
  "kind": "anna",
  "interpretation.summary": "Today is Tuesday, 2026-03-24 (UTC) (server UTC — check your device for local date if you're near midnight).",
  "answer_source": "rules_only",
  "intent": "QUESTION",
  "topic": "factual_datetime",
  "limitation_flag": false
}
```

### CLI command

```bash
echo "What day is it?" | python3 -m messaging_interface.cli_adapter
```

### Telegram surface (same payload via `format_telegram_reply`)

```
[Anna — Trading Analyst]

Today is Tuesday, 2026-03-24 (UTC) (server UTC — check your device for local date if you're near midnight).
```

---

## Prompt 2 — `status` (DATA)

### Normalized JSON (CLI)

```json
{
  "kind": "data",
  "interpretation.summary": null,
  "answer_source": null,
  "intent": null,
  "topic": null,
  "limitation_flag": false,
  "data_mode": "status"
}
```

### CLI command

```bash
echo "status" | python3 -m messaging_interface.cli_adapter
```

### Telegram surface (same payload via `format_telegram_reply`)

```
[DATA]
Role: DATA — system operator; read-only SQLite + execution context on this host.
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [DATA].

State
System / execution context snapshot (telemetry, read-only).

Facts
Current phase: Phase 4.6.3
Last completed phase: 4.6.3
Verification host: clawbot.a51.corp
Proof required: True
Repo path (context): ~/blackbox
Execution feedback rows (execution_feedback_v1): 9

Next check
Compare with clawbot verification when closing phases. Say insights for recent feedback rows.

Do you want me to check current conditions next?
```

*(Facts block reflects live `execution_context` on host at capture time.)*

---

## Prompt 3 — `what is a spread?` (Anna / memory or playbook)

### Normalized JSON (CLI)

```json
{
  "kind": "anna",
  "interpretation.summary": "Bid–Ask Spread — The difference between best ask and best bid (ask minus bid). Practically: Tight spread usually means cheaper to trade now; wide spread means friction. Why it matters: Direct read on liquidity and transaction cost before fees. Example: Spread is 2 cents on a 86 dollar name.",
  "answer_source": "memory_only",
  "intent": "QUESTION",
  "topic": "trading_general",
  "limitation_flag": false
}
```

### CLI command

```bash
echo "what is a spread?" | python3 -m messaging_interface.cli_adapter
```

### Telegram surface (same payload via `format_telegram_reply`)

```
[Anna — Trading Analyst]

Bid–Ask Spread — The difference between best ask and best bid (ask minus bid). Practically: Tight spread usually means cheaper to trade now; wide spread means friction. Why it matters: Direct read on liquidity and transaction cost before fees. Example: Spread is 2 cents on a 86 dollar name.
```

---

## Live Telegram (optional operator proof)

The above **Telegram** blocks are **byte-identical** to what `telegram_bot.py` sends (`format_telegram_reply` → `format_response`). **Screenshots** from a real chat with `TELEGRAM_BOT_TOKEN` can be appended by the operator for operational closure.

---

## Status

Evidence package attached; **architect review** decides whether **4.6.3.3** leaf closes.
