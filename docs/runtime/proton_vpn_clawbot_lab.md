# Proton VPN — clawbot lab host

Operational runbook (Debian). **Do not commit credentials.** Sign-in is interactive (password prompt); store nothing in git.

## Host (verified)

- **OS:** Debian GNU/Linux **13 (trixie)** — `Linux clawbot … x86_64`
- **Lab egress (no VPN, sample):** `curl -sS ifconfig.me` → **24.234.254.194** (confirm current before/after on connect)

## What was installed

1. Official Proton APT repo: `protonvpn-stable-release` from  
   `https://repo.protonvpn.com/debian/dists/stable/main/binary-all/protonvpn-stable-release_1.0.8_all.deb`
2. Package: **`proton-vpn-cli`** (CLI entrypoint: **`protonvpn`**, v1.0.0)

Dependencies include **NetworkManager**, **gnome-keyring**, **proton-vpn-daemon**, **wireguard-tools**, etc. **NetworkManager is active** after install; Docker stacks on this host were still **Up** immediately after install — **re-check** after maintenance windows.

## Sign in (operator — required once)

```bash
protonvpn signin YOUR_EMAIL@proton.me
```

(Password is prompted; no echo. Use your Proton account that has VPN entitlement.)

There is **no** `API token` flow in `protonvpn signin --help` on this build — account username + password.

## Connect / disconnect / status

```bash
# Fastest server globally
protonvpn connect

# US (example)
protonvpn connect --country US

protonvpn status
protonvpn disconnect
protonvpn signout   # clears local session (optional)
```

## Verify egress (after connect)

```bash
curl -sS ifconfig.me
curl -sS ipinfo.io/ip
```

Expect a **non–lab** address (not `172.20.x.x` as the public IP; the lab LAN may still exist for SSH depending on routing/split tunnel).

## Persistence / reconnect

- **Manual:** run `protonvpn connect` again after reboot or `protonvpn disconnect`.
- **Daemon:** `proton-vpn-daemon` is installed; CLI uses it. For **boot-time** VPN, add a **reviewed** systemd unit or cron only after confirming routing does not break SSH or Docker (test in `tmux`).

## Risks (read before enabling always-on VPN)

- **SSH:** Full-tunnel VPN can change default route; you can **lock yourself out**. Prefer testing from **console/out-of-band**, or confirm **split tunneling** / **LAN exception** in Proton settings.
- **Docker:** Bridge networks may need routes/DNS validation after VPN connect.
- **Headless:** Proton docs warn the Linux CLI may need **secret service** / keyring; if `signin` fails on a pure SSH session, see Proton’s Linux CLI troubleshooting (dbus / user session / `loginctl enable-linger` patterns as applicable).

## Fallback (if CLI is not viable)

- **WireGuard / OpenVPN** configs from the Proton account (download in web), use `wg-quick` / `openvpn` with the same caution on routing and SSH.

## Reference

- https://protonvpn.com/support/linux-cli
