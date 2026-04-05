"""Operator-designated Anna trading strategy (state.json) — not ledger lane=baseline.

Ledger baseline (strategy_id=baseline) remains Sean's economic anchor. Designated strategy is
operator intent: which Anna strategy id is treated as the live trading strategy when promoted.
Demotions move the prior id into the cookie jar (nothing is overwritten).

**Sustained** (registry): strategy_registry rows whose lifecycle is candidate → promoted (QEL).
test/experiment lifecycles are not eligible — they are not “trading strategies” for this control.
Baseline is the default system strategy (no Anna designation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.anna_training.catalog import default_state
from modules.anna_training.execution_ledger import (
    RESERVED_STRATEGY_BASELINE,
    connect_ledger,
    default_execution_ledger_path,
    ensure_execution_ledger_schema,
)
from modules.anna_training.quantitative_evaluation_layer.constants import (
    LIFECYCLE_CANDIDATE,
    LIFECYCLE_PROMOTED,
    LIFECYCLE_PROMOTION_READY,
    LIFECYCLE_VALIDATED_STRATEGY,
)
from modules.anna_training.store import load_state, save_state, utc_now_iso

_SUSTAINED_LIFECYCLES = frozenset(
    {
        LIFECYCLE_CANDIDATE,
        LIFECYCLE_VALIDATED_STRATEGY,
        LIFECYCLE_PROMOTION_READY,
        LIFECYCLE_PROMOTED,
    }
)


def list_sustained_strategy_ids_from_ledger(db_path: Path | None = None) -> list[str]:
    """
    Registry-backed ids that may be promoted / used as Anna replacements.
    Excludes test/experiment (and baseline).
    """
    db_path = db_path or default_execution_ledger_path()
    out: list[str] = []
    try:
        conn = connect_ledger(db_path)
        try:
            ensure_execution_ledger_schema(conn)
            cur = conn.execute("PRAGMA table_info(strategy_registry)")
            if not any(str(r[1]) == "lifecycle_state" for r in cur.fetchall()):
                return []
            cur = conn.execute(
                """
                SELECT strategy_id, COALESCE(lifecycle_state, '') FROM strategy_registry
                WHERE strategy_id != ?
                ORDER BY strategy_id ASC
                """,
                (RESERVED_STRATEGY_BASELINE,),
            )
            for row in cur.fetchall():
                sid = str(row[0]).strip()
                lc = str(row[1] or "").strip()
                if sid and lc in _SUSTAINED_LIFECYCLES:
                    out.append(sid)
        finally:
            conn.close()
    except Exception:
        return []
    return out


def build_operator_trading_bundle_part(db_path: Path | None = None) -> dict[str, Any]:
    """Payload merged into dashboard bundle: state + registry eligibility."""
    base = get_operator_trading_payload()
    eligible = list_sustained_strategy_ids_from_ledger(db_path)
    base["eligible_strategy_ids"] = eligible
    base["default_system_strategy_id"] = RESERVED_STRATEGY_BASELINE
    base["sustained_policy_note"] = (
        "Promote/demote lists only sustained registry strategies (lifecycle: candidate, validated_strategy, "
        "promotion_ready, promoted). test/experiment rows are not trading strategies for this control. "
        "Default system strategy is the baseline chain (strategy_id="
        + RESERVED_STRATEGY_BASELINE
        + ")."
    )
    return base


def get_operator_trading_payload() -> dict[str, Any]:
    st = load_state()
    op = st.get("operator_trading")
    if not isinstance(op, dict):
        op = default_state()["operator_trading"]
    designated = op.get("designated_strategy_id")
    jar = op.get("cookie_jar") or []
    if not isinstance(jar, list):
        jar = []
    ds = str(designated).strip() if designated else None
    return {
        "schema": "operator_trading_strategy_v1",
        "designated_strategy_id": ds or None,
        "cookie_jar": jar,
        "ledger_baseline_note": (
            "Ledger baseline lane stays strategy_id="
            + RESERVED_STRATEGY_BASELINE
            + " (economic anchor). Designated trading strategy is operator routing intent; "
            "demoted ids are preserved in the cookie jar."
        ),
    }


def _ensure_op_block(st: dict[str, Any]) -> dict[str, Any]:
    op = st.get("operator_trading")
    if not isinstance(op, dict):
        op = dict(default_state()["operator_trading"])
        st["operator_trading"] = op
    if not isinstance(op.get("cookie_jar"), list):
        op["cookie_jar"] = []
    return op


def promote_designated_strategy(
    *,
    strategy_id: str,
    ledger_db_path: Path | None = None,
) -> dict[str, Any]:
    sid = str(strategy_id or "").strip()
    if not sid:
        return {"ok": False, "reason_code": "missing_strategy_id", "detail": "strategy_id required"}
    if sid == RESERVED_STRATEGY_BASELINE:
        return {
            "ok": False,
            "reason_code": "baseline_reserved",
            "detail": "Use demote to baseline to return to default system strategy; baseline is not an Anna promotion target",
        }
    eligible = set(list_sustained_strategy_ids_from_ledger(ledger_db_path))
    if sid not in eligible:
        return {
            "ok": False,
            "reason_code": "not_sustained_in_registry",
            "detail": (
                "strategy_id must be a sustained registry strategy (lifecycle candidate → promoted). "
                "test/experiment ids are not eligible."
            ),
            "eligible_strategy_ids": sorted(eligible),
        }
    st = load_state()
    op = _ensure_op_block(st)
    prev = op.get("designated_strategy_id")
    prev = str(prev).strip() if prev else None
    if prev and prev != sid:
        jar = op.setdefault("cookie_jar", [])
        jar.append(
            {
                "strategy_id": prev,
                "action": "replaced_by_promote",
                "at_utc": utc_now_iso(),
            }
        )
    op["designated_strategy_id"] = sid
    save_state(st)
    return {
        "ok": True,
        "reason_code": "promoted",
        "designated_strategy_id": sid,
        "previous_designated_strategy_id": prev,
        "operator_trading": build_operator_trading_bundle_part(ledger_db_path),
    }


def demote_designated_strategy(
    *,
    strategy_id: str,
    replacement_strategy_id: str,
    ledger_db_path: Path | None = None,
) -> dict[str, Any]:
    sid = str(strategy_id or "").strip()
    rep_raw = str(replacement_strategy_id or "").strip()
    if not sid:
        return {"ok": False, "reason_code": "missing_strategy_id", "detail": "strategy_id required"}
    if not rep_raw:
        return {
            "ok": False,
            "reason_code": "missing_replacement",
            "detail": "replacement_strategy_id required — choose baseline (default system) or another sustained strategy",
        }
    rep_to_baseline = rep_raw == RESERVED_STRATEGY_BASELINE or rep_raw.lower() == "baseline"
    if rep_to_baseline:
        rep_effective: str | None = None
    else:
        rep_effective = rep_raw
    if rep_effective == sid:
        return {
            "ok": False,
            "reason_code": "replacement_same_as_demoted",
            "detail": "replacement must differ from the strategy being demoted",
        }
    if not rep_to_baseline and rep_effective:
        eligible = set(list_sustained_strategy_ids_from_ledger(ledger_db_path))
        if rep_effective not in eligible:
            return {
                "ok": False,
                "reason_code": "replacement_not_sustained",
                "detail": "replacement must be baseline or a sustained registry strategy",
                "eligible_strategy_ids": sorted(eligible),
            }
    st = load_state()
    op = _ensure_op_block(st)
    cur = op.get("designated_strategy_id")
    cur = str(cur).strip() if cur else None
    if not cur:
        return {"ok": False, "reason_code": "no_designated", "detail": "Already on default system strategy (baseline) — nothing to demote"}
    if cur != sid:
        return {
            "ok": False,
            "reason_code": "not_current_designated",
            "detail": "strategy_id must match the current designated trading strategy",
        }
    jar = op.setdefault("cookie_jar", [])
    jar.append(
        {
            "strategy_id": sid,
            "action": "demoted",
            "replacement_strategy_id": RESERVED_STRATEGY_BASELINE if rep_to_baseline else rep_effective,
            "at_utc": utc_now_iso(),
        }
    )
    op["designated_strategy_id"] = rep_effective
    save_state(st)
    return {
        "ok": True,
        "reason_code": "demoted",
        "designated_strategy_id": rep_effective,
        "demoted_strategy_id": sid,
        "operator_trading": build_operator_trading_bundle_part(ledger_db_path),
    }
