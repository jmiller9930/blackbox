"""Read-only execution / system status text for DATA persona (no secrets)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import connect, ensure_schema
from _paths import default_sqlite_path, repo_root
from context_loader import build_output, execution_context_path, parse_context_md


def _ensure_repo_root_imports() -> Path:
    """`modules.*` lives at repo root; runtime cwd may differ (e.g. Slack)."""
    root = repo_root()
    r = str(root)
    if r not in sys.path:
        sys.path.insert(0, r)
    return root


def format_context_engine_status_for_chat() -> str:
    """
    Context engine health for #context_engine / #status — 🟢🟡🔴 + facts + restart hints when not healthy.
    """
    _ensure_repo_root_imports()
    from modules.context_engine.status import build_context_engine_status

    st = build_context_engine_status(repo_root())
    status = str(st.get("status") or "unknown")
    reason = str(st.get("reason_code") or "")
    fresh = st.get("freshness_seconds")
    last_hb = st.get("last_heartbeat_at")
    storage = st.get("storage_path")
    last_kind = st.get("last_event_kind")
    seq = st.get("record_count_hint")

    if status == "healthy":
        ball = "🟢"
        headline = "Online — context engine"
    elif status == "degraded":
        ball = "🟡"
        headline = "Degraded — context engine (heartbeat stale)"
    else:
        ball = "🔴"
        headline = "Offline / problem — context engine"

    lines = [
        f"{ball} {headline}",
        f"Reason: {reason}",
    ]
    if storage is not None:
        lines.append(f"Storage: {storage}")
    if last_hb is not None:
        lines.append(f"Last heartbeat: {last_hb}")
    if fresh is not None:
        lines.append(f"Freshness (s): {fresh:.1f}" if isinstance(fresh, (int, float)) else f"Freshness (s): {fresh}")
    if last_kind is not None:
        lines.append(f"Last event kind: {last_kind}")
    if seq is not None:
        lines.append(f"Seq hint: {seq}")
    detail = st.get("detail")
    if detail:
        lines.append(f"Detail: {detail}")

    if status != "healthy":
        lines.extend(
            [
                "",
                "If stuck offline: check `BLACKBOX_CONTEXT_ROOT` (default under repo `data/context_engine`),",
                "ensure the directory is writable, and that `BLACKBOX_CONTEXT_ENGINE_DISABLE` is not set by mistake.",
                "Restart the messaging process (`python3 -m messaging_interface` from repo root) or any service that probes the context-engine API.",
            ]
        )

    return "\n".join(lines)


def build_hashtag_combined_status_text() -> str:
    """#status — context engine snapshot plus execution context snapshot."""
    ce = format_context_engine_status_for_chat()
    ex = build_status_text()
    return f"{ce}\n\n---\n\nExecution / phase snapshot\n{ex}"


def _repo() -> Path:
    return repo_root()


def format_operator_system_rollup_text() -> str:
    """#system — planes + agents + Pyth (repo-relative artifacts)."""
    _ensure_repo_root_imports()
    from modules.operator_snapshot import format_system_rollup_text

    return format_system_rollup_text(_repo())


def format_operator_runtime_text() -> str:
    _ensure_repo_root_imports()
    from modules.operator_snapshot import format_runtime_text

    return format_runtime_text(_repo())


def format_operator_agents_text() -> str:
    _ensure_repo_root_imports()
    from modules.operator_snapshot import format_agents_text

    return format_agents_text(_repo())


def format_operator_pyth_text() -> str:
    _ensure_repo_root_imports()
    from modules.operator_snapshot import format_pyth_text

    return format_pyth_text(_repo())


def format_operator_billy_checkin_text() -> str:
    _ensure_repo_root_imports()
    from modules.operator_snapshot import format_billy_checkin_text

    return format_billy_checkin_text(_repo())


def format_operator_help_text() -> str:
    from modules.operator_snapshot import format_ops_restart_help

    tags = [
        "Grammar: one message = only hashtags (e.g. #status #system). Spaces optional between tokens.",
        "#status — legacy: context engine + execution phase file",
        "#status #system — FULL stack: system rollup + context engine + execution phase",
        "#status #context_engine — only context-engine slice",
        "#status #runtime | #agents | #pyth | #execution — single slice",
        "#runtime #agents — combine slices (no #status)",
        "#system — rollup only (same as #rollup)",
        "#context_engine — context store only",
        "#billy_checkin — drift-doctor gate",
        "#ops_help — this list + restart runbook (no auto-exec)",
        "#op_restart — safe instructions only (does not restart processes)",
        "#anna #report_card — Anna Grade-12 / Karpathy training snapshot (preflight + paper cohort + gate)",
        "#report_card — same training snapshot (#anna optional)",
    ]
    return format_ops_restart_help() + "\n\n📋 Hashtag index\n" + "\n".join(f"• {t}" for t in tags)


def format_operator_restart_advice_text() -> str:
    """#op_restart — instructions only."""
    from modules.operator_snapshot import format_ops_restart_help

    return format_ops_restart_help()


# --- Composable pure-hashtag grammar (multiple #tokens per message) ---

_KNOWN_TAGS = frozenset(
    {
        "status",
        "system",
        "rollup",
        "runtime",
        "agents",
        "pyth",
        "market",
        "context_engine",
        "execution",
        "phase",
        "billy_checkin",
        "ops_help",
        "help_ops",
        "operations",
        "op_restart",
        "help",
        "ops",
        "anna",
        "report_card",
    }
)

_TAG_ALIASES: dict[str, str] = {
    "context-engine": "context_engine",
    "rollup": "system",
    "market": "pyth",
    "phase": "execution",
    "ops": "ops_help",
    "help": "ops_help",
    "operations": "ops_help",
    "help_ops": "ops_help",
    "report-card": "report_card",
}

_SLICE_ORDER = ("system", "runtime", "pyth", "agents", "context_engine", "execution")


def format_anna_training_report_hashtag_text() -> str:
    """Slack/DATA reply for #anna #report_card / #report_card — training snapshot (read-only)."""
    _ensure_repo_root_imports()
    try:
        from modules.anna_training.catalog import CURRICULA
        from modules.anna_training.gates import evaluate_grade12_gates
        from modules.anna_training.paper_trades import load_paper_trades_for_gates, summarize_trades
        from modules.anna_training.progression import bachelor_eligibility_report, suggest_next_focus
        from modules.anna_training.readiness import ensure_anna_data_preflight
        from modules.anna_training.report_card_text import format_slack_report_card_text
        from modules.anna_training.store import load_state
    except Exception as e:  # noqa: BLE001
        return f"Anna training snapshot unavailable (import): {e}"

    try:
        pf = ensure_anna_data_preflight()
        st = load_state()
        trades = load_paper_trades_for_gates()
        summ = summarize_trades(trades)
        g12 = evaluate_grade12_gates()
        sf = suggest_next_focus(
            curriculum_id=st.get("curriculum_id"),
            training_method_id=st.get("training_method_id"),
        )
        be = bachelor_eligibility_report(
            curriculum_id=st.get("curriculum_id"),
            completed_milestones=st.get("completed_curriculum_milestones") or [],
        )
    except Exception as e:  # noqa: BLE001
        return f"Anna training snapshot unavailable (read): {e}"

    ok = bool(pf.get("ok")) or bool(pf.get("skipped"))
    blockers_pf = [str(x) for x in (pf.get("blockers") or [])]
    cid = (st.get("curriculum_id") or "") or ""
    cur = CURRICULA.get(cid) if cid else None
    cur_title = (cur or {}).get("title", cid or "(not assigned)")
    stage = str((cur or {}).get("stage", "—"))

    return format_slack_report_card_text(
        st=st,
        g12=g12,
        sf=sf,
        be=be,
        summ=summ,
        preflight_ok=ok,
        preflight_blockers=blockers_pf,
        curriculum_title=str(cur_title),
        stage=stage,
        training_method_id=st.get("training_method_id"),
    )


def normalize_operator_tag(raw: str) -> str:
    t = (raw or "").strip().lstrip("#").lower().replace("-", "_")
    return _TAG_ALIASES.get(t, t)


def compose_operator_hashtag_message(tokens: tuple[str, ...]) -> str:
    """
    Build DATA reply text from normalized hashtag tokens (pure-hashtag messages only).

    Grammar (examples):
    - ``#status`` — context engine + execution phase file (legacy).
    - ``#status #system`` — **everything**: system rollup + context engine + execution phase.
    - ``#status #context_engine`` — **only** that slice (narrow).
    - ``#runtime #agents`` — concatenate those slices (no ``#status``).
    """
    if not tokens:
        return "(no operator tags)"

    norm = [normalize_operator_tag(t) for t in tokens]
    unknown = [t for t in norm if t not in _KNOWN_TAGS]
    # Dedupe preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for t in norm:
        if t in _KNOWN_TAGS and t not in seen:
            seen.add(t)
            ordered.append(t)

    unk_line = ""
    if unknown:
        unk_line = "\n\n(Ignored unknown tokens: " + ", ".join(f"#{x}" for x in unknown) + ")"

    if not ordered:
        return "No recognized operator tokens." + unk_line

    # Short-circuit: help / restart / billy alone or dominant
    if ordered == ["ops_help"]:
        return format_operator_help_text() + unk_line
    if ordered == ["op_restart"]:
        return format_operator_restart_advice_text() + unk_line
    if ordered == ["billy_checkin"]:
        return format_operator_billy_checkin_text() + unk_line

    if "report_card" in seen:
        return format_anna_training_report_hashtag_text() + unk_line

    if ordered == ["anna"]:
        return (
            "Anna — add `#report_card` for a training snapshot (preflight, paper cohort, grade-12 gate).\n"
            "Examples: `#anna #report_card` or `#report_card` alone."
        ) + unk_line

    has_status = "status" in seen
    rest = [t for t in ordered if t != "status"]

    # Legacy: #status alone
    if ordered == ["status"]:
        return build_hashtag_combined_status_text() + unk_line

    # #status #system — full stack (rollup + context engine + execution phase)
    if has_status and rest == ["system"]:
        mega = "\n\n---\n\n".join(
            [
                format_operator_system_rollup_text(),
                format_context_engine_status_for_chat(),
                build_status_text(),
            ]
        )
        return f"📊 Full operator status (#status #system)\n\n{mega}{unk_line}"

    # #status + exactly one scope (other than system) → that slice only
    if has_status and len(rest) == 1:
        one = rest[0]
        if one == "context_engine":
            return format_context_engine_status_for_chat() + unk_line
        if one == "runtime":
            return format_operator_runtime_text() + unk_line
        if one == "agents":
            return format_operator_agents_text() + unk_line
        if one in ("pyth", "market"):
            return format_operator_pyth_text() + unk_line
        if one in ("execution", "phase"):
            return f"Execution / phase snapshot\n{build_status_text()}{unk_line}"

    # #status + multiple scopes — strip #status and compose the rest (e.g. #system #runtime)
    if has_status and len(rest) > 1:
        sub = tuple(t for t in ordered if t != "status")
        return compose_operator_hashtag_message(sub) + unk_line

    # No #status: single-token shortcuts
    if len(ordered) == 1:
        one = ordered[0]
        single = {
            "system": format_operator_system_rollup_text,
            "runtime": format_operator_runtime_text,
            "agents": format_operator_agents_text,
            "pyth": format_operator_pyth_text,
            "market": format_operator_pyth_text,
            "context_engine": format_context_engine_status_for_chat,
            "execution": lambda: f"Execution / phase snapshot\n{build_status_text()}",
            "phase": lambda: f"Execution / phase snapshot\n{build_status_text()}",
        }
        if one in single:
            return single[one]() + unk_line

    # Multi-scope without status: ordered union
    parts2: list[str] = []
    for key in _SLICE_ORDER:
        if key in seen:
            parts2.append(_slice_section(key))
    if parts2:
        return "\n\n---\n\n".join(parts2) + unk_line

    return "No matching operator hashtag combination." + unk_line


def _slice_section(key: str) -> str:
    if key == "system":
        return format_operator_system_rollup_text()
    if key == "runtime":
        return format_operator_runtime_text()
    if key == "pyth":
        return format_operator_pyth_text()
    if key == "agents":
        return format_operator_agents_text()
    if key == "context_engine":
        return format_context_engine_status_for_chat()
    if key == "execution":
        return f"Execution / phase snapshot\n{build_status_text()}"
    return ""


def get_learning_state_summary(conn=None) -> dict[str, int]:
    """
    Read-only learning record counts by lifecycle state.
    Visibility only: not used in DATA response generation yet.
    """
    own_conn = False
    if conn is None:
        own_conn = True
        conn = connect(default_sqlite_path())
        ensure_schema(conn, repo_root())
    states = ("candidate", "under_test", "validated", "rejected")
    out = {s: 0 for s in states}
    cur = conn.execute(
        "SELECT state, COUNT(*) FROM learning_records GROUP BY state"
    )
    for state, n in cur.fetchall():
        s = str(state)
        if s in out:
            out[s] = int(n)
    if own_conn:
        conn.close()
    return out


def get_recent_learning_transitions(*, limit: int = 10, conn=None) -> list[dict[str, Any]]:
    """
    Read-only transition inspection for audit visibility.
    Visibility only: not used in DATA response generation yet.
    """
    own_conn = False
    if conn is None:
        own_conn = True
        conn = connect(default_sqlite_path())
        ensure_schema(conn, repo_root())
    rows = conn.execute(
        """
        SELECT record_id, from_state, to_state, changed_at, notes
        FROM learning_record_transitions
        ORDER BY datetime(changed_at) DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "record_id": str(r[0]),
                "from_state": str(r[1]) if r[1] is not None else None,
                "to_state": str(r[2]),
                "changed_at": str(r[3]),
                "notes": str(r[4] or ""),
            }
        )
    if own_conn:
        conn.close()
    return out


def build_status_text() -> str:
    """Human-readable phase, host, proof flag, plus feedback row count."""
    lines: list[str] = []

    p = execution_context_path()
    if p.is_file():
        blob = parse_context_md(p.read_text(encoding="utf-8"))
        if "error" not in blob:
            out = build_output(blob)
            lines.extend(
                [
                    f"Current phase: {out.get('current_phase')}",
                    f"Last completed phase: {out.get('last_completed_phase')}",
                    f"Verification host: {out.get('execution_host')}",
                    f"Proof required: {out.get('proof_required')}",
                    f"Repo path (context): {out.get('repo_path')}",
                ]
            )
        else:
            lines.append(f"Execution context: {blob.get('error')}")
    else:
        lines.append("Execution context file not found.")

    root = repo_root()
    db = default_sqlite_path()
    try:
        conn = connect(db)
        ensure_schema(conn, root)
        cur = conn.execute(
            "SELECT COUNT(*) FROM system_events WHERE event_type = ?",
            ("execution_feedback_v1",),
        )
        n = int(cur.fetchone()[0])
        conn.close()
        lines.append(f"Execution feedback rows (execution_feedback_v1): {n}")
    except Exception as e:
        lines.append(f"DB status snippet unavailable: {e}")

    return "\n".join(lines)


def build_infra_snapshot() -> str:
    """
    Read-only infrastructure facts from the workspace SQLite (proves DATA has DB access on this host).
    No secrets; bounded table list + safe row counts.
    """
    lines: list[str] = []
    root = repo_root()
    db = default_sqlite_path()
    lines.append(f"SQLite path (this runtime): {db}")
    try:
        conn = connect(db)
        ensure_schema(conn, root)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in cur.fetchall()]
        if not tables:
            lines.append("No user tables found (empty or unreadable).")
        else:
            lines.append(f"Tables visible here ({len(tables)}): {', '.join(tables[:30])}")
            if len(tables) > 30:
                lines.append("… (truncated)")
        for tbl in ("tasks", "system_events", "alerts", "agents", "runs"):
            if tbl in tables:
                try:
                    n = conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
                    lines.append(f"Rows · {tbl}: {int(n)}")
                except Exception as e:
                    lines.append(f"Rows · {tbl}: (unavailable: {e})")
        conn.close()
    except Exception as e:
        lines.append(f"Could not open database: {e}")
    lines.append("")
    lines.append(
        "This is the same DB the runtime uses on this machine (read-only from chat). "
        "Anna does not query it unless you route to DATA."
    )
    return "\n".join(lines)
