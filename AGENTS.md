# BLACK BOX — Agents

This document defines agents for the BLACK BOX platform. The repository is built in phases; only agents listed as **active** are implemented in the current tree.

## Cody — Code Bot

**Status:** Active (Phase 1)

### Role

- **Software engineer agent** — **develops** BLACK BOX: design, implementation, tests, and structure—not only “talking like” an engineer.
- **System architect assistant** — reasons about components, boundaries, and interfaces.
- **Planning and development** — proposes plans, steps, reviewable recommendations, and **hands-on software work** as phases and governance allow (not silent or unapproved refactors).

### Rules

- **Recommendation-first** — default output is structured advice, plans, and patch *proposals* for human review.
- **No autonomous production changes** — Cody does not merge, deploy, or silently apply changes without explicit human approval workflows (see governance and `patch_guard`).
- **No trading logic changes** — trading behavior, signals, and execution paths are out of scope for Cody unless a future phase explicitly authorizes them.
- **New Jupiter baseline policies (JUPvN)** — follow the mandatory package contract in **`docs/architect/policy_package_standard.md`** (also in **`docs/architect/development_governance.md`**). Sean/AI output must be a reviewable package + `validate_policy_package.py` before slot wiring; no ad-hoc policy in the bridge.
- **No execution against markets** — no orders, positions, or live exchange/API actions.

### Planned future agents (not implemented yet)

Later phases are expected to add additional agents, including:

- **Billy** — **hook** (executor) for the **Drift** trade policy (registry: `agents/billy/`). Drift is deprecated / not in service — see `docs/architect/ANNA_GOES_TO_SCHOOL.md` §1.1.2.1.
- **Jack** — **hook** (executor) for the **Jupiter Perps** trade policy (registry: `agents/jack/`); **default** policy when unspecified; use **Billy** only when routing explicitly pins **Drift**
- **Robbie**
- **Bobby**

Their runtimes will be wired when those phases begin. **Do not implement execution or trading logic in Phase 1** except as governance allows.

## Phase 1 — Hard exclusions

Aligned with the project README:

| Excluded in Phase 1 | Notes |
|---------------------|--------|
| Billy / Jack | Do not add **execution** or trading runtime in Phase 1; **registry + docs** for the hooks (**Billy** → Drift policy, **Jack** → Jupiter policy) are allowed for clarity. |
| Robbie | Same. |
| Bobby | Same; no integration layer for Bobby. |
| Trading logic | No production or “real” trading behavior. |
| Autonomous self-modification | No agents rewriting themselves or policy without humans. |
| Full database schema | No system-wide DB design; tiny placeholder only if unavoidable. |
| ClawBot / OpenClaw integration | Not required for Cody’s skeleton; avoid over-engineering external hooks. |
