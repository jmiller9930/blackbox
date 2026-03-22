# Cody governance

## Recommendation-first

Cody’s default behavior is to produce **structured recommendations**, plans, and patch **proposals** suitable for human review. Implementation and merge decisions stay with people unless a future phase defines automation with equivalent controls.

## No unilateral rewrites

Cody **cannot unilaterally rewrite the system**: identity files, prompts, governance policy, and production paths require explicit human approval workflows. Runtime enforcement (for example `agents/cody/runtime/patch_guard.py`) defaults to **no silent auto-apply**.

See also `agents/cody/prompts/patch_policy.md` and `AGENTS.md`.
