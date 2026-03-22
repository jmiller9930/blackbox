# Soul registry — multiple agents, one structured source

## Why JSON + Markdown?

- **`agents/souls.json`** holds **one record per agent id** with a **unique** soul (voice, principles, taboos, etc.). It is the **canonical registry** for “who sounds like what” and avoids treating any one agent’s soul as the default for others.
- **`agents/<agent>/SOUL.md`** remains the file **OpenClaw injects** from each agent workspace today. Keep Markdown **aligned** with the JSON when you change behavior, or add a small generator script later.

## Rules

1. **Never** duplicate DATA’s (or Cody’s) soul text as the template for Mia, Anna, or Billy.
2. **Stubs** in `souls.json` use `status: "stub"` and a **headline** that says TBD — they are placeholders, not copies.
3. **Humans** (Sean, John) are **not** in `souls.json` unless you later add optional `type: "human"` entries for persona prompts—default is **software agents only**.

## File

- Registry: [`../../agents/souls.json`](../../agents/souls.json)
