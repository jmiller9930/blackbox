"""Jupiter_2 baseline — **free_collateral_usd** for policy sizing (Sean ``calculate_position_size``).

**Authoritative bankroll for baseline paper:** call only
``resolve_free_collateral_usd_for_jupiter_policy`` from policy evaluation paths — do not duplicate
defaults or alternate account assumptions elsewhere.

**Source of truth:** paper capital (dashboard / journal) — **not** a decorative stub.

Uses ``build_paper_capital_summary.current_equity_ledger`` (net contributed + baseline lane realized PnL),
floored at ``MIN_COLLATERAL_USD`` when equity is uninitialized.

Optional override: env ``JUPITER_BASELINE_FREE_COLLATERAL_USD`` (ops/tests).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from modules.anna_training.jupiter_2_sean_policy import MIN_COLLATERAL_USD


def resolve_free_collateral_usd_for_jupiter_policy(
    *,
    training_state: dict[str, Any] | None = None,
    ledger_db_path: Path | None = None,
) -> tuple[float, dict[str, Any]]:
    """
    USD account size passed to ``calculate_position_size`` as ``free_collateral_usd``.

    Returns ``(usd, meta)`` where ``meta`` is safe to attach to policy ``features``.
    """
    raw = (os.environ.get("JUPITER_BASELINE_FREE_COLLATERAL_USD") or "").strip()
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v, {
                    "source": "env:JUPITER_BASELINE_FREE_COLLATERAL_USD",
                    "override": True,
                    "free_collateral_usd": v,
                    "authoritative_resolver": "resolve_free_collateral_usd_for_jupiter_policy",
                }
        except ValueError:
            pass

    from modules.anna_training.paper_capital import build_paper_capital_summary
    from modules.anna_training.store import load_state

    st = training_state if training_state is not None else load_state()
    s = build_paper_capital_summary(training_state=st, ledger_db_path=ledger_db_path)
    eq = float(s.get("current_equity_ledger") or 0.0)
    nc = float(s.get("net_contributed_capital") or 0.0)
    # Prefer headline equity; if zero (fresh), fall back to net contributed (journal).
    base = eq if eq > 1e-12 else nc
    usd = max(float(MIN_COLLATERAL_USD), base)
    return usd, {
        "source": "paper_capital:current_equity_ledger",
        "authoritative_resolver": "resolve_free_collateral_usd_for_jupiter_policy",
        "current_equity_ledger": float(s.get("current_equity_ledger") or 0.0),
        "net_contributed_capital": nc,
        "free_collateral_usd": usd,
        "note": (
            "Sizing uses paper bankroll (journal + baseline ledger PnL). "
            "Not Sean hardcoded; not live Solana wallet balance."
        ),
    }
