# Directive 4.6.4 — Anna benchmark run (architect submission)

Generated automatically from `scripts/runtime/tools/run_anna_benchmark_4_6_4.py`.

| Field | Value |
| --- | --- |
| UTC timestamp | 2026-03-24T01:49:28Z |
| Git commit | `f06da23955b163b48100e67a5d6bb645d253e21a` |
| Route | `anna` (default; verified per prompt below) |
| Pipeline | `build_analysis` → `format_response` (Telegram-equivalent body) |
| Display name in copy | Sean |

---

## Answers 1–10 (read this first)

Each item is the **benchmark prompt** and Anna’s **primary interpretation text** (`interpretation.summary` from `anna_analysis_v1`). The detailed Telegram-formatted bubble (with Risk read / How I'd play it) is in the [Full record](#full-record-prompt-metadata-telegram) section below.

### 1. Exit timing on a winning trade

- **Prompt:** How do you know when to get out of a trade if the trade is success but seems to be topping out and looking to reverse?
- **Headline:** Exit timing
- **Anna (interpretation summary):** Step down when momentum stalls: weaker candle bodies, upper wicks, volume thins, or lower highs / reversal structure form. Consider tightening the stop, scaling out, or taking partial profit to protect open PnL instead of hoping for full take-profit into a rollover.

### 2. Fake breakout recognition

- **Prompt:** If price breaks above a local high but immediately loses follow-through, what would make you treat that as a fake breakout instead of a real move?
- **Headline:** Breakout failure
- **Anna (interpretation summary):** Treat it as a likely fake if price breaks a local high then immediately fails: no continuation, wick-heavy rejection, failure to hold above the level, and volume that does not confirm. A reclaim back inside the prior range reinforces trap behavior over a real trend leg.

### 3. Low-volume trade suppression

- **Prompt:** If RSI divergence is present but SOL-PERP volume is weak, should we still take the trade?
- **Headline:** Signal quality vs volume
- **Anna (interpretation summary):** RSI divergence alone is not enough if SOL-PERP volume is weak: signal quality drops. Default stance is to reduce confidence, size down, or skip unless structure and volume confirm — divergence without participation is easy to fade.

### 4. Wide spread entry risk

- **Prompt:** If the setup looks good but the spread is suddenly wide at entry, how should that affect the signal?
- **Headline:** Spread vs setup quality
- **Anna (interpretation summary):** A wide spread at entry hurts fill quality and raises slippage risk even when the chart setup looks good. The signal should be downgraded or you should wait until the spread normalizes — good pattern ≠ good trade if execution is toxic.

### 5. Confidence threshold discipline

- **Prompt:** If a setup scores 61 confidence after adjustments and our threshold is 65, what should happen?
- **Headline:** Threshold discipline
- **Anna (interpretation summary):** With a hard threshold at 65 and an adjusted score of 61, the setup should not be forwarded for execution — it fails the gate. Treat it as no-go for automated forwarding; you can still log, watch, or refine inputs until it clears 65. This is rule-driven: no emotional override.

### 6. Consecutive loss pause logic

- **Prompt:** If we take three consecutive losses during low-volume conditions, what should the system do next?
- **Headline:** Loss streak + thin conditions
- **Anna (interpretation summary):** After three consecutive losses in a low-volume regime, the system should pause new signals (cooldown), require a regime reset or revalidation, and avoid firing blindly — edge is likely degraded until volume and structure improve.

### 7. Partial profit vs full hold

- **Prompt:** When would you take partial profit instead of holding for the full target?
- **Headline:** Partial vs full
- **Anna (interpretation summary):** Take partial profit when momentum fades before the target, structure shows lower highs or reversal risk, you approach resistance, spread widens, or volume dries up — lock some gain and manage the rest with a trail or clearer invalidation.

### 8. No-trade conditions

- **Prompt:** What conditions would make you refuse a signal even if RSI divergence appears valid?
- **Headline:** Veto conditions
- **Anna (interpretation summary):** Even with valid RSI divergence you can refuse the trade: dead or weak volume, wide spread, conflicting structure, bad follow-through, or post-adjustment confidence below gate. Divergence is a filter input, not a blank check.

### 9. Learning from a bad fill

- **Prompt:** If a technically correct signal loses money because entry happened during a bad spread environment, what should Anna learn from that?
- **Headline:** Execution vs idea
- **Anna (interpretation summary):** If the idea was sound but you lost due to a bad spread environment, separate signal quality from fill quality: track spread at entry, tighten confidence or filter when spreads are wide, and learn execution conditions — not just win/loss.

### 10. Human pushback / clarification

- **Prompt:** If Sean tells you "that signal was wrong because the move had no real follow-through," what should you do with that information?
- **Headline:** Human feedback
- **Anna (interpretation summary):** Treat that as correction: log it, classify as analytical feedback, ask a clarifying question if needed, and validate against trade evidence before changing rules — do not mutate strategy from one comment alone.

---

<a id="full-record-prompt-metadata-telegram"></a>

## Full record (prompt, metadata, Telegram)

## Benchmark 1 — Exit timing on a winning trade

### Prompt

> How do you know when to get out of a trade if the trade is success but seems to be topping out and looking to reverse?

### Metadata

- **route_selected:** `anna`
- **classifier (human_intent):** `{"intent": "QUESTION", "topic": "exit_logic", "requires_reasoning": true, "bypass": null}`
- **fallback_fired:** `no` (normal `anna_analysis_v1` path)

### Structured interpretation (for review)

- **headline:** Exit timing
- **summary:** Step down when momentum stalls: weaker candle bodies, upper wicks, volume thins, or lower highs / reversal structure form. Consider tightening the stop, scaling out, or taking partial profit to protect open PnL instead of hoping for full take-profit into a rollover.

### Anna reply (as user sees in Telegram)

```
[Anna]
Role: Anna — trading analyst (markets, risk, concepts; advisory only).
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [Anna].

Quick take
Sean, Step down when momentum stalls: weaker candle bodies, upper wicks, volume thins, or lower highs / reversal structure form. Consider tightening the stop, scaling out, or taking partial profit to protect open PnL instead of hoping for full take-profit into a rollover.
Exit timing

Risk read
I'm seeing risk around low here.
What's in the mix: No strong risk amplifiers detected from text and available context..

How I'd play it
WATCH.
No live guardrail policy is attached in this session; stay cautious and paper-only — no execution implied.

Want to go deeper? Throw me a scenario, or ping @data for system readouts / @cody for code.

Do you want me to check current conditions next?
```

---

## Benchmark 2 — Fake breakout recognition

### Prompt

> If price breaks above a local high but immediately loses follow-through, what would make you treat that as a fake breakout instead of a real move?

### Metadata

- **route_selected:** `anna`
- **classifier (human_intent):** `{"intent": "QUESTION", "topic": "trading_general", "requires_reasoning": true, "bypass": null}`
- **fallback_fired:** `no` (normal `anna_analysis_v1` path)

### Structured interpretation (for review)

- **headline:** Breakout failure
- **summary:** Treat it as a likely fake if price breaks a local high then immediately fails: no continuation, wick-heavy rejection, failure to hold above the level, and volume that does not confirm. A reclaim back inside the prior range reinforces trap behavior over a real trend leg.

### Anna reply (as user sees in Telegram)

```
[Anna]
Role: Anna — trading analyst (markets, risk, concepts; advisory only).
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [Anna].

Quick take
Sean, Treat it as a likely fake if price breaks a local high then immediately fails: no continuation, wick-heavy rejection, failure to hold above the level, and volume that does not confirm. A reclaim back inside the prior range reinforces trap behavior over a real trend leg.
Breakout failure

Risk read
I'm seeing risk around low here.
What's in the mix: No strong risk amplifiers detected from text and available context..

How I'd play it
WATCH.
No live guardrail policy is attached in this session; stay cautious and paper-only — no execution implied.

Want to go deeper? Throw me a scenario, or ping @data for system readouts / @cody for code.

Want me to go deeper on any part?
```

---

## Benchmark 3 — Low-volume trade suppression

### Prompt

> If RSI divergence is present but SOL-PERP volume is weak, should we still take the trade?

### Metadata

- **route_selected:** `anna`
- **classifier (human_intent):** `{"intent": "QUESTION", "topic": "trading_general", "requires_reasoning": true, "bypass": null}`
- **fallback_fired:** `no` (normal `anna_analysis_v1` path)

### Structured interpretation (for review)

- **headline:** Signal quality vs volume
- **summary:** RSI divergence alone is not enough if SOL-PERP volume is weak: signal quality drops. Default stance is to reduce confidence, size down, or skip unless structure and volume confirm — divergence without participation is easy to fade.

### Anna reply (as user sees in Telegram)

```
[Anna]
Role: Anna — trading analyst (markets, risk, concepts; advisory only).
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [Anna].

Quick take
Sean, RSI divergence alone is not enough if SOL-PERP volume is weak: signal quality drops. Default stance is to reduce confidence, size down, or skip unless structure and volume confirm — divergence without participation is easy to fade.
Signal quality vs volume

Risk read
I'm seeing risk around low here.
What's in the mix: No strong risk amplifiers detected from text and available context..

How I'd play it
WATCH.
No live guardrail policy is attached in this session; stay cautious and paper-only — no execution implied.

Want to go deeper? Throw me a scenario, or ping @data for system readouts / @cody for code.

Want me to go deeper on any part?
```

---

## Benchmark 4 — Wide spread entry risk

### Prompt

> If the setup looks good but the spread is suddenly wide at entry, how should that affect the signal?

### Metadata

- **route_selected:** `anna`
- **classifier (human_intent):** `{"intent": "QUESTION", "topic": "trading_general", "requires_reasoning": true, "bypass": null}`
- **fallback_fired:** `no` (normal `anna_analysis_v1` path)

### Structured interpretation (for review)

- **headline:** Spread vs setup quality
- **summary:** A wide spread at entry hurts fill quality and raises slippage risk even when the chart setup looks good. The signal should be downgraded or you should wait until the spread normalizes — good pattern ≠ good trade if execution is toxic.

### Anna reply (as user sees in Telegram)

```
[Anna]
Role: Anna — trading analyst (markets, risk, concepts; advisory only).
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [Anna].

Quick take
Sean, A wide spread at entry hurts fill quality and raises slippage risk even when the chart setup looks good. The signal should be downgraded or you should wait until the spread normalizes — good pattern ≠ good trade if execution is toxic.
Spread vs setup quality

Risk read
I'm seeing risk around low here.
What's in the mix: No strong risk amplifiers detected from text and available context..

How I'd play it
WATCH.
No live guardrail policy is attached in this session; stay cautious and paper-only — no execution implied.

Want to go deeper? Throw me a scenario, or ping @data for system readouts / @cody for code.

Do you want me to check current conditions next?
```

---

## Benchmark 5 — Confidence threshold discipline

### Prompt

> If a setup scores 61 confidence after adjustments and our threshold is 65, what should happen?

### Metadata

- **route_selected:** `anna`
- **classifier (human_intent):** `{"intent": "QUESTION", "topic": "trading_general", "requires_reasoning": true, "bypass": null}`
- **fallback_fired:** `no` (normal `anna_analysis_v1` path)

### Structured interpretation (for review)

- **headline:** Threshold discipline
- **summary:** With a hard threshold at 65 and an adjusted score of 61, the setup should not be forwarded for execution — it fails the gate. Treat it as no-go for automated forwarding; you can still log, watch, or refine inputs until it clears 65. This is rule-driven: no emotional override.

### Anna reply (as user sees in Telegram)

```
[Anna]
Role: Anna — trading analyst (markets, risk, concepts; advisory only).
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [Anna].

Quick take
Sean, With a hard threshold at 65 and an adjusted score of 61, the setup should not be forwarded for execution — it fails the gate. Treat it as no-go for automated forwarding; you can still log, watch, or refine inputs until it clears 65. This is rule-driven: no emotional override.
Threshold discipline

Risk read
I'm seeing risk around low here.
What's in the mix: No strong risk amplifiers detected from text and available context..

How I'd play it
WATCH.
No live guardrail policy is attached in this session; stay cautious and paper-only — no execution implied.

Want to go deeper? Throw me a scenario, or ping @data for system readouts / @cody for code.

Does that help?
```

---

## Benchmark 6 — Consecutive loss pause logic

### Prompt

> If we take three consecutive losses during low-volume conditions, what should the system do next?

### Metadata

- **route_selected:** `anna`
- **classifier (human_intent):** `{"intent": "QUESTION", "topic": "trading_general", "requires_reasoning": true, "bypass": null}`
- **fallback_fired:** `no` (normal `anna_analysis_v1` path)

### Structured interpretation (for review)

- **headline:** Loss streak + thin conditions
- **summary:** After three consecutive losses in a low-volume regime, the system should pause new signals (cooldown), require a regime reset or revalidation, and avoid firing blindly — edge is likely degraded until volume and structure improve.

### Anna reply (as user sees in Telegram)

```
[Anna]
Role: Anna — trading analyst (markets, risk, concepts; advisory only).
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [Anna].

Quick take
Sean, After three consecutive losses in a low-volume regime, the system should pause new signals (cooldown), require a regime reset or revalidation, and avoid firing blindly — edge is likely degraded until volume and structure improve.
Loss streak + thin conditions

Risk read
I'm seeing risk around low here.
What's in the mix: No strong risk amplifiers detected from text and available context..

How I'd play it
WATCH.
No live guardrail policy is attached in this session; stay cautious and paper-only — no execution implied.

Want to go deeper? Throw me a scenario, or ping @data for system readouts / @cody for code.

Does that help?
```

---

## Benchmark 7 — Partial profit vs full hold

### Prompt

> When would you take partial profit instead of holding for the full target?

### Metadata

- **route_selected:** `anna`
- **classifier (human_intent):** `{"intent": "QUESTION", "topic": "trading_general", "requires_reasoning": true, "bypass": null}`
- **fallback_fired:** `no` (normal `anna_analysis_v1` path)

### Structured interpretation (for review)

- **headline:** Partial vs full
- **summary:** Take partial profit when momentum fades before the target, structure shows lower highs or reversal risk, you approach resistance, spread widens, or volume dries up — lock some gain and manage the rest with a trail or clearer invalidation.

### Anna reply (as user sees in Telegram)

```
[Anna]
Role: Anna — trading analyst (markets, risk, concepts; advisory only).
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [Anna].

Quick take
Sean, Take partial profit when momentum fades before the target, structure shows lower highs or reversal risk, you approach resistance, spread widens, or volume dries up — lock some gain and manage the rest with a trail or clearer invalidation.
Partial vs full

Risk read
I'm seeing risk around low here.
What's in the mix: No strong risk amplifiers detected from text and available context..

How I'd play it
WATCH.
No live guardrail policy is attached in this session; stay cautious and paper-only — no execution implied.

Want to go deeper? Throw me a scenario, or ping @data for system readouts / @cody for code.

Do you want me to check current conditions next?
```

---

## Benchmark 8 — No-trade conditions

### Prompt

> What conditions would make you refuse a signal even if RSI divergence appears valid?

### Metadata

- **route_selected:** `anna`
- **classifier (human_intent):** `{"intent": "QUESTION", "topic": "trading_general", "requires_reasoning": true, "bypass": null}`
- **fallback_fired:** `no` (normal `anna_analysis_v1` path)

### Structured interpretation (for review)

- **headline:** Veto conditions
- **summary:** Even with valid RSI divergence you can refuse the trade: dead or weak volume, wide spread, conflicting structure, bad follow-through, or post-adjustment confidence below gate. Divergence is a filter input, not a blank check.

### Anna reply (as user sees in Telegram)

```
[Anna]
Role: Anna — trading analyst (markets, risk, concepts; advisory only).
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [Anna].

Quick take
Sean, Even with valid RSI divergence you can refuse the trade: dead or weak volume, wide spread, conflicting structure, bad follow-through, or post-adjustment confidence below gate. Divergence is a filter input, not a blank check.
Veto conditions

Risk read
I'm seeing risk around low here.
What's in the mix: No strong risk amplifiers detected from text and available context..

How I'd play it
WATCH.
No live guardrail policy is attached in this session; stay cautious and paper-only — no execution implied.

Want to go deeper? Throw me a scenario, or ping @data for system readouts / @cody for code.

Do you want me to check current conditions next?
```

---

## Benchmark 9 — Learning from a bad fill

### Prompt

> If a technically correct signal loses money because entry happened during a bad spread environment, what should Anna learn from that?

### Metadata

- **route_selected:** `anna`
- **classifier (human_intent):** `{"intent": "QUESTION", "topic": "trading_general", "requires_reasoning": true, "bypass": null}`
- **fallback_fired:** `no` (normal `anna_analysis_v1` path)

### Structured interpretation (for review)

- **headline:** Execution vs idea
- **summary:** If the idea was sound but you lost due to a bad spread environment, separate signal quality from fill quality: track spread at entry, tighten confidence or filter when spreads are wide, and learn execution conditions — not just win/loss.

### Anna reply (as user sees in Telegram)

```
[Anna]
Role: Anna — trading analyst (markets, risk, concepts; advisory only).
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [Anna].

Quick take
Sean, If the idea was sound but you lost due to a bad spread environment, separate signal quality from fill quality: track spread at entry, tighten confidence or filter when spreads are wide, and learn execution conditions — not just win/loss.
Execution vs idea

Risk read
I'm seeing risk around low here.
What's in the mix: No strong risk amplifiers detected from text and available context..

How I'd play it
WATCH.
No live guardrail policy is attached in this session; stay cautious and paper-only — no execution implied.

Want to go deeper? Throw me a scenario, or ping @data for system readouts / @cody for code.

Does that help?
```

---

## Benchmark 10 — Human pushback / clarification

### Prompt

> If Sean tells you "that signal was wrong because the move had no real follow-through," what should you do with that information?

### Metadata

- **route_selected:** `anna`
- **classifier (human_intent):** `{"intent": "CORRECTION", "topic": "feedback", "requires_reasoning": true, "bypass": null}`
- **fallback_fired:** `no` (normal `anna_analysis_v1` path)

### Structured interpretation (for review)

- **headline:** Human feedback
- **summary:** Treat that as correction: log it, classify as analytical feedback, ask a clarifying question if needed, and validate against trade evidence before changing rules — do not mutate strategy from one comment alone.

### Anna reply (as user sees in Telegram)

```
[Anna]
Role: Anna — trading analyst (markets, risk, concepts; advisory only).
Telegram: the name at the top of this bubble is the bot account (e.g. BB Trader), not the speaker. Who is speaking here: [Anna].

Quick take
Sean, Treat that as correction: log it, classify as analytical feedback, ask a clarifying question if needed, and validate against trade evidence before changing rules — do not mutate strategy from one comment alone.
Human feedback

Risk read
I'm seeing risk around low here.
What's in the mix: No strong risk amplifiers detected from text and available context..

How I'd play it
WATCH.
No live guardrail policy is attached in this session; stay cautious and paper-only — no execution implied.

Want to go deeper? Throw me a scenario, or ping @data for system readouts / @cody for code.

Do you want me to check current conditions next?
```

---

