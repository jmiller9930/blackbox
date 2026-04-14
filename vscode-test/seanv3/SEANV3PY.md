# seanv3py — Sean V3 Docker (end-to-end helper)

**`seanv3py`** is a small shell script next to `docker-compose.yml` so you can manage the **Sean V3** parity container (`seanv3`) from one entrypoint: deploy, status, logs, stop, restart, and optional `git pull`.

It does **not** replace reading **`README.md`** or **`VPN/README.md`** — the stack still **must** use **`network_mode: host`** for Binance via Proton on clawbot.

## Requirements

- **Docker** and **Docker Compose** on the host (e.g. clawbot).
- Script run from the repo: `vscode-test/seanv3/` ships with **`seanv3py`**.

## Location

| Item | Path |
|------|------|
| Script | `vscode-test/seanv3/seanv3py` |
| Compose | `vscode-test/seanv3/docker-compose.yml` |

## Make executable (once)

```bash
chmod +x ~/blackbox/vscode-test/seanv3/seanv3py
```

## Commands

| Command | What it does |
|---------|----------------|
| `./seanv3py deploy` | `docker compose build` then `up -d` — container **keeps running** after you close SSH. |
| `./seanv3py deploy --pull` | `git pull origin main` at **repo root**, then deploy. |
| `./seanv3py status` | `docker compose ps` — see if **seanv3** is **Up**. |
| `./seanv3py logs` | `docker compose logs -f` — follow logs; **Ctrl+C** stops **tailing** only, not the container. |
| `./seanv3py stop` | `docker compose down` — stops the stack. |
| `./seanv3py restart` | `down`, then `build` + `up -d`. |
| `./seanv3py restart --pull` | `down`, `git pull`, then `build` + `up -d`. |
| `./seanv3py pull` | `git pull origin main` only (repo root). |

## Typical flow (clawbot)

```bash
cd ~/blackbox/vscode-test/seanv3
./seanv3py deploy --pull
# disconnect SSH — container stays up
# later:
./seanv3py status
./seanv3py logs
```

## SSH disconnect vs app uptime

After **`deploy`** (or **`up -d`**), the **container runs on the server**. Closing your **SSH session does not stop Docker**. When you SSH back in, use **`status`** to confirm it is still **Up**.

## Environment

| Variable | Meaning |
|----------|---------|
| `BLACKBOX_REPO` | If set, **`git pull`** uses this directory as the repo root instead of auto-detected `../../..` from the script. |

## Related docs

- **`README.md`** (this folder) — Sean V3 purpose, VPN table, capture paths.
- **`VPN/README.md`** (repo root) — WireGuard / Binance split-tunnel.
- **`../README.md`** — vscode-test index.
