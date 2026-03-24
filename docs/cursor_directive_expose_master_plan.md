# Cursor Directive — Expose BlackBox Master Plan for ChatGPT Access

## Objective
Expose the project architecture file through a stable raw Git URL so ChatGPT can read it directly without repeated copy/paste.

## Required File
The master plan must exist at:

```text
docs/blackbox_master_plan.md
```

## Required Access Path
The file must be reachable at this raw URL format:

```text
https://raw.githubusercontent.com/jmiller9930/blackbox/main/docs/blackbox_master_plan.md
```

## Required Conditions
- The file must be committed to the `main` branch
- The repo/file must be publicly readable, or otherwise exposed through a supported connector path later
- The file must be plain UTF-8 Markdown
- Do not rely on the GitHub `blob` page URL
- Do not generate the file dynamically

## Validation
Run this exact check and confirm it returns the full file contents:

```bash
curl https://raw.githubusercontent.com/jmiller9930/blackbox/main/docs/blackbox_master_plan.md
```

## Why This Is Needed
ChatGPT cannot reliably use the GitHub `blob` webpage as the source of truth.  
ChatGPT needs the raw Markdown document so it can:

- read the current architecture
- stay aligned with project progress
- avoid repeated token-heavy copy/paste
- update the plan based on current work
- let Cursor read the same source-of-truth file

## Recommended Companion File
Also create and maintain:

```text
docs/runtime_state.md
```

This should track:
- current phase
- current directive
- implemented items
- broken items
- next actions
- proof/test status

## Operating Rule
Going forward, `docs/blackbox_master_plan.md` should be treated as the canonical architecture file that both ChatGPT and Cursor can reference.

## Deliverable Back
Return:
1. The confirmed raw URL
2. Proof that `curl` returns the file contents
3. Any path correction if the file name or branch differs
