# Patch policy

## Preparation vs application

- **Cody may prepare patches** — diffs, branch suggestions, and review notes are in scope.
- **Cody may not silently apply risky changes** — anything touching production paths, security, data integrity, or trading-adjacent code requires explicit human review.
- **Humans approve meaningful changes** — merge to protected branches, releases, and operational rollouts remain human-gated unless a future phase defines automation with equivalent controls.

## Auto-apply

- Default posture: **no automatic application** of patches; use `patch_guard` and governance modules to enforce blocks.
- Low-risk automation (e.g., formatting-only) may be allowed later only with explicit policy—**not assumed in Phase 1**.
