# NDE Studio (Control Plane UI)

React + Express placeholders under `nde_control_plane/`. Ops label: **finquantv1**.

## Host policy — hard rule

**NDE Studio must reside on trx40 only** — not clawbot, not other lab servers, unless governance explicitly changes this.

- Run Docker/build (`./run-docker.sh`) on **trx40** for the canonical lab deployment.
- Keep the trx40 repo **synced** with **`git pull origin main`** (or the integration branch in use) before claiming deployment.

See **`.cursor/rules/nde-studio-host-trx40.mdc`** for agent enforcement.

## Quick run

```bash
cd nde_control_plane
./run-docker.sh
```

URL: `http://127.0.0.1:3999` (bind ports as needed on trx40).
