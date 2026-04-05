"""
Wallet status: keypair on disk, RPC balance, Jupiter quote sample, signing proof via Node.

Env:
  BLACKBOX_SOLANA_KEYPAIR_PATH or KEYPAIR_PATH — path to Solana keypair JSON array (64 bytes).
  SOLANA_RPC_URL — optional (default public mainnet RPC).
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_TRADING_CORE = _REPO / "trading_core"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore[import-untyped]

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _keypair_path() -> Path | None:
    raw = (os.environ.get("BLACKBOX_SOLANA_KEYPAIR_PATH") or os.environ.get("KEYPAIR_PATH") or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (_REPO / p).resolve()
    return p if p.is_file() else None


def _rpc_url() -> str:
    return (os.environ.get("SOLANA_RPC_URL") or "").strip() or "https://api.mainnet-beta.solana.com"


def _rpc_post(body: dict[str, Any]) -> dict[str, Any]:
    url = _rpc_url()
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    ctx = _ssl_context()
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _pubkey_via_node(keypair_path: Path) -> tuple[str | None, str | None]:
    """Return (base58_pubkey, error)."""
    script = _TRADING_CORE / "scripts" / "wallet_pubkey.ts"
    if not script.is_file():
        return None, "wallet_pubkey.ts missing"
    try:
        proc = subprocess.run(
            ["npx", "--yes", "tsx", str(script), str(keypair_path)],
            cwd=str(_TRADING_CORE),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)[:200]
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "tsx_failed")[:300]
    line = (proc.stdout or "").strip().splitlines()
    pk = line[-1].strip() if line else ""
    return (pk if pk else None), None


def _sign_proof_via_node(keypair_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    script = _TRADING_CORE / "scripts" / "wallet_sign_proof.ts"
    if not script.is_file():
        return None, "wallet_sign_proof.ts missing"
    try:
        proc = subprocess.run(
            ["npx", "--yes", "tsx", str(script), str(keypair_path)],
            cwd=str(_TRADING_CORE),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)[:200]
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "sign_failed")[:400]
    try:
        return json.loads((proc.stdout or "").strip().splitlines()[-1]), None
    except json.JSONDecodeError:
        return None, "invalid_json_from_sign_script"


def _get_balance_lamports(pubkey_b58: str) -> tuple[int | None, str | None]:
    try:
        out = _rpc_post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [pubkey_b58, {"commitment": "confirmed"}],
            }
        )
        if isinstance(out, dict) and "result" in out and "value" in out["result"]:
            return int(out["result"]["value"]), None
        return None, str(out)[:200]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, KeyError, TypeError) as e:
        return None, str(e)[:200]


def _jupiter_quote_v6() -> dict[str, Any]:
    """
    Minimal Jupiter Swap API v6 quote (SOL -> USDC) — public, no wallet required for quote.
    Proves route/quote path; not a live swap.
    """
    # https://station.jup.ag/docs/apis/swap-api
    base = "https://quote-api.jup.ag/v6/quote"
    q = urllib.parse.urlencode(
        {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "amount": "1000000",
            "slippageBps": "100",
        }
    )
    url = f"{base}?{q}"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
        if isinstance(data, dict) and data.get("routePlan"):
            return {
                "ok": True,
                "in_amount": data.get("inAmount"),
                "out_amount": data.get("outAmount"),
                "price_impact_pct": data.get("priceImpactPct"),
                "route_steps": len(data.get("routePlan") or []),
            }
        return {"ok": False, "detail": str(data)[:300]}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return {"ok": False, "detail": str(e)[:200]}


def _rpc_health() -> dict[str, Any]:
    try:
        out = _rpc_post({"jsonrpc": "2.0", "id": 1, "method": "getHealth"})
        ok = isinstance(out, dict) and out.get("result") == "ok"
        return {"ok": ok, "detail": out}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return {"ok": False, "detail": str(e)[:200]}


def build_wallet_status_payload() -> dict[str, Any]:
    """
    Full status for dashboard + architect proof package.
    """
    import uuid

    tid = uuid.uuid4().hex
    kp = _keypair_path()
    health = _rpc_health()
    jup = _jupiter_quote_v6()

    out: dict[str, Any] = {
        "schema": "blackbox_wallet_status_v1",
        "trace_id": tid,
        "wallet_connected": False,
        "public_address": None,
        "keypair_path_configured": bool(
            (os.environ.get("BLACKBOX_SOLANA_KEYPAIR_PATH") or os.environ.get("KEYPAIR_PATH") or "").strip()
        ),
        "keypair_file_present": kp is not None,
        "rpc_url_host": urllib.parse.urlparse(_rpc_url()).netloc or "default",
        "solana_rpc": health,
        "jupiter_quote_sample": jup,
        "balance_lamports": None,
        "balance_sol": None,
        "balance_usd_approx": None,
        "signing_proof": None,
        "live_trading_blocked": True,
        "note": "LIVE remains disabled until governance enables it; wallet proves connectivity only.",
    }

    if kp is None:
        out["disconnect_reason"] = "BLACKBOX_SOLANA_KEYPAIR_PATH or KEYPAIR_PATH not set or file missing"
        return out

    pk, err = _pubkey_via_node(kp)
    if err or not pk:
        out["disconnect_reason"] = f"pubkey_derivation_failed:{err}"
        return out

    out["wallet_connected"] = True
    out["public_address"] = pk

    lamports, berr = _get_balance_lamports(pk)
    if berr:
        out["balance_error"] = berr
    else:
        out["balance_lamports"] = lamports
        if lamports is not None:
            out["balance_sol"] = round(lamports / 1e9, 9)

    if jup.get("ok") and jup.get("out_amount") and lamports is not None and lamports > 0:
        # Rough USD from micro-quote: 1M lamports worth of SOL -> USDC out (6 decimals)
        try:
            out_amt = int(jup["out_amount"])
            in_amt = int(jup.get("in_amount") or 1_000_000)
            usdc_units = out_amt / 1e6
            sol_in = in_amt / 1e9
            if sol_in > 0:
                px = usdc_units / sol_in
                out["balance_usd_approx"] = round((lamports / 1e9) * px, 2)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    sig, serr = _sign_proof_via_node(kp)
    if serr:
        out["signing_proof"] = {"ok": False, "error": serr}
    else:
        out["signing_proof"] = {"ok": True, **(sig or {})}

    return out
