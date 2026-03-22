# BLACK BOX

**BLACK BOX** is the project name for this repository: an agentic system being **built in phases**. Each phase adds or hardens specific capabilities; this README describes **Phase 1** only.

## Phase 1 goal

**Phase 1 exists to bootstrap Cody only** — the first engineering agent. This phase establishes identity, prompts, a minimal Python runtime skeleton, and planning/reporting scaffolding. It does **not** include trading logic, exchange integration, or the full agent team.

## Agents

- **Cody** is the **first engineering agent** (software / systems engineer for BLACK BOX).
- **Later phases** will introduce additional agents, including **Billy**, **Robbie**, and **Bobby** (names and roles will be defined as those phases land).

Details: `AGENTS.md`. Cody-specific files: `docs/cody/` and `agents/cody/`. **Full Phase 1 / OpenClaw master plan:** [`docs/blackbox_master_plan.md`](docs/blackbox_master_plan.md). **Phase 1 team clarification (OpenClaw first, Slack later):** [`docs/CURSOR_PHASE1_CLARIFICATION.md`](docs/CURSOR_PHASE1_CLARIFICATION.md).

## Cody — Phase 1 limits

No autonomous rewrites, no trading decisions, no self-modification, no guessing final trade logic, no direct exchange execution.

## Phase 1 — Out of scope (do not build)

- **Billy** — not implemented.
- **Robbie** — not implemented.
- **Bobby** — not implemented; no Bobby integration work.
- **Trading** — no real trading logic, signals, or execution paths.
- **Autonomy** — no autonomous self-modification of agents, prompts, or policy.
- **Database** — no schema for the full system; only a minimal placeholder if strictly needed (empty `data/sqlite/` is not a schema).
- **ClawBot / OpenClaw** — no integration work required to ship Cody’s skeleton; do not over-engineer external agent hooks in Phase 1.

**Environment note:** A future target is the ClawBot server (`clawbot.a51.corp`); Phase 1 does not depend on it.

**Python:** 3.11+

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m agents.cody.runtime.main --version
pytest
```

### Lab server (`clawbot`) without `python3-venv`

If `python -m venv` fails (missing `ensurepip`), ask an admin for `python3.13-venv` (or your distro’s `python3-venv`), **or** install deps into your user site and run tests via the interpreter (PEP 668):

```bash
cd ~/blackbox
python3 -m pip install --user --break-system-packages -r requirements.txt
python3 -m pytest -q
```

Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` if you want the `pytest` script on `PATH` (optional; `python3 -m pytest` always works).

### GitHub push from the lab

HTTPS push needs credentials (`gh auth login` or a PAT). SSH push needs a key in `~/.ssh` on the server and [GitHub SSH keys](https://github.com/settings/keys) for this host. Until then, push from a machine that is already authenticated or create the repo on GitHub and `git pull` on the lab.
