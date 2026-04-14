# seanv3py — Sean V3 Docker (end-to-end helper)

**`seanv3py`** (and optional **`seanv3.py`**) live next to `docker-compose.yml` so you can manage the **Sean V3** parity container (`seanv3`) from one entrypoint.

It does **not** replace **`README.md`** or **`VPN/README.md`** — the stack still **must** use **`network_mode: host`** for Binance via Proton on clawbot.

---

## Process (emulates “run → disconnect SSH → come back → still up → same log workspace”)

This is the operator workflow that matches that intent.

| Step | Action | What persists |
|------|--------|-----------------|
| 1 | `ssh` to **clawbot** | — |
| 2 | `cd ~/blackbox/vscode-test/seanv3` | — |
| 3 | `./seanv3py deploy --pull` (or `deploy`) | **Docker** starts **`seanv3`** on the **host** (`docker compose up -d`). |
| 4 | `./seanv3py status` | Confirm **Up** (optional but good hygiene). |
| 5 | `./seanv3py console` | Opens **tmux** session `seanv3` running `docker compose logs -f` (needs **`tmux`** installed). |
| 6 | **Detach** from tmux: `Ctrl+b`, then **`d`** | Log stream **keeps running inside tmux** on the server. |
| 7 | **Close SSH** (exit) | **Container still running.** tmux session **still running** on clawbot. |
| 8 | Later: **SSH in again**, `cd` to same dir | New SSH session (normal). |
| 9 | `./seanv3py status` | Confirms container **still Up** — answers “is it already running?” **Yes**, if you didn’t `stop`. |
| 10 | `./seanv3py console` | **Reattaches** to the **same tmux session** — same log workspace as before. |

If you **don’t** use **`console`**, use **`logs`** after reconnect; each run is a new tail, but **Docker** state is unchanged.

```mermaid
flowchart TD
  A[SSH clawbot] --> B[seanv3py deploy]
  B --> C[Container runs on host - survives SSH exit]
  C --> D{Use console?}
  D -->|yes| E[tmux: logs -f]
  E --> F[Detach tmux Ctrl+b d]
  F --> G[Exit SSH]
  G --> H[SSH again]
  H --> I[seanv3py status]
  I --> J[seanv3py console - reattach tmux]
  D -->|no| K[seanv3py logs - new tail each time]
```

### What is *not* possible

- **SSH** does **not** resume the old TCP session — each login is **new**. That’s normal.
- **“Same session”** here means: **tmux** on **clawbot** holds the **terminal workspace**; **Docker** holds the **app**.

---

## Requirements

- **Docker** + **Docker Compose** on the host.
- **`tmux`** for **`console`** (e.g. `sudo apt install tmux` on Debian).

## Location

| Item | Path |
|------|------|
| Shell entrypoint | `vscode-test/seanv3/seanv3py` |
| Python wrapper (same commands) | `vscode-test/seanv3/seanv3.py` |
| Compose | `vscode-test/seanv3/docker-compose.yml` |

## Make executable (once)

```bash
chmod +x ~/blackbox/vscode-test/seanv3/seanv3py ~/blackbox/vscode-test/seanv3/seanv3.py
```

Use either:

```bash
./seanv3py status
python3 seanv3.py status
```

## Commands

| Command | What it does |
|---------|----------------|
| `./seanv3py deploy` | `docker compose build` then `up -d` — container **keeps running** after you close SSH. |
| `./seanv3py deploy --pull` | `git pull origin main` at **repo root**, then deploy. |
| `./seanv3py status` | `docker compose ps` — see if **seanv3** is **Up**. |
| `./seanv3py logs` | `docker compose logs -f` — follow logs; **Ctrl+C** stops **tailing** only, not the container. |
| `./seanv3py console` | **tmux**: create or **reattach** to session `seanv3` (name via `SEANV3_TMUX_SESSION`) running `docker compose logs -f`. |
| `./seanv3py stop` | `docker compose down` — stops the stack. |
| `./seanv3py restart` | `down`, then `build` + `up -d`. |
| `./seanv3py restart --pull` | `down`, `git pull`, then `build` + `up -d`. |
| `./seanv3py pull` | `git pull origin main` only (repo root). |

## Environment

| Variable | Meaning |
|----------|---------|
| `BLACKBOX_REPO` | If set, **`git pull`** uses this directory as the repo root. |
| `SEANV3_TMUX_SESSION` | tmux session name for **`console`** (default: `seanv3`). |

## Related docs

- **`README.md`** (this folder) — Sean V3 purpose, VPN table, capture paths.
- **`VPN/README.md`** (repo root) — WireGuard / Binance split-tunnel.
- **`../README.md`** — vscode-test index.
