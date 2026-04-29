# NDE Studio (Control Plane UI)

React + Express placeholders under `nde_control_plane/`. Ops label: **finquantv1**.

## trx40 — always the route

**The web UI always runs on trx40.** Treat trx40 as the only canonical host for this surface.

## Stay in sync with dev

After changes land in git:

1. **Push** from dev (`origin/main` or integration branch).
2. On **trx40**: `git pull` in the blackbox checkout.
3. **Rebuild/restart** the UI (`./run-docker.sh`) so what you see on trx40 matches the repo.

Rule detail: **`.cursor/rules/nde-studio-host-trx40.mdc`**.

## Quick run (on trx40)

```bash
cd nde_control_plane
./run-docker.sh
```

URL: `http://127.0.0.1:3999` on trx40 (adjust bind/host firewall as needed).
