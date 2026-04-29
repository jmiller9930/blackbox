# NDE Studio (Control Plane UI)

React + Express under `nde_control_plane/`. Ops label: **finquantv1**.

## Where to run it (hard rule)

**Do not** rely on **Docker on your Mac** as the acceptance environment for this UI.

**Canonical test host:** **trx40** = **`172.20.1.66`** (lab — same route). After you **push** code:

1. SSH to **`172.20.1.66`**, **`cd ~/blackbox`**, **`git pull origin main`**
2. **`cd nde_control_plane && ./run-docker.sh`**
3. Open **`http://127.0.0.1:3999`** **on that machine** (or via VPN/LAN as you expose it)

Local Mac: edit code, **`npm run build`** if you want — optional **`npm run dev`** for quick layout checks only — **not** the signed-off container test.

Rule: **`.cursor/rules/nde-studio-host-trx40.mdc`**

## Quick run (on 172.20.1.66)

```bash
cd ~/blackbox/nde_control_plane
git pull origin main
./run-docker.sh
```

Check: `docker ps --filter name=nde-studio` and `curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3999/`
