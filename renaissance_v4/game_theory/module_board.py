"""
Pattern-game module board — **truthful** green/red wiring checks + operator-facing explanations.

DEF-001: each row answers a concrete question (wired / active / not). No decorative “always green.”
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_GAME_THEORY = Path(__file__).resolve().parent


def _path_appendable(path: Path) -> bool:
    """True if we can create/append this file (parent dir exists and is writable)."""
    try:
        p = path.expanduser().resolve()
        parent = p.parent
        if not parent.is_dir():
            return False
        return os.access(parent, os.W_OK)
    except OSError:
        return False


def _import_ok(module: str) -> bool:
    try:
        __import__(module, fromlist=["_"])
        return True
    except Exception:
        return False


def compute_pattern_game_module_board() -> dict[str, Any]:
    """
    Build module rows for ``GET /api/module-board``.

    Each module has ``ok`` tied to a **specific** check (filesystem, import, API, env+file).
    ``body`` is plain text for the operator modal (DEF-001 / wiring truth).
    """
    from renaissance_v4.game_theory.data_health import get_data_health
    from renaissance_v4.game_theory.groundhog_memory import (
        groundhog_auto_merge_enabled,
        groundhog_bundle_path,
    )
    from renaissance_v4.game_theory.memory_paths import (
        default_batch_scorecard_jsonl,
        default_retrospective_log_jsonl,
        default_run_memory_jsonl,
    )

    dh = get_data_health()
    ghb = groundhog_bundle_path()
    gh_env = groundhog_auto_merge_enabled()
    sc_path = default_batch_scorecard_jsonl()
    rm_path = default_run_memory_jsonl()
    retro_path = default_retrospective_log_jsonl()

    modules: list[dict[str, Any]] = []

    modules.append(
        {
            "id": "web_ui",
            "label": "web_app.py",
            "role": "ui",
            "ok": True,
            "detail": "Flask UI is serving this request.",
            "title": "Web UI (Flask)",
            "body": (
                "Serves the pattern-game page and JSON APIs you are using right now.\n"
                "Green means the UI process is up. This is not Referee math — it is the shell."
            ),
        }
    )

    d_ok = bool(dh.get("overall_ok"))
    modules.append(
        {
            "id": "data_health",
            "label": "data_health.py",
            "role": "core_replay",
            "ok": d_ok,
            "detail": (dh.get("summary_line") or dh.get("error") or "data check")[:240],
            "title": "Financial / bar data (SQLite)",
            "body": (
                "Wired = SQLite DB reachable and core bar table usable for replay.\n"
                "Red = DB missing or query failed — Referee batches cannot run on market data.\n"
                "DEF-001: this is **measurement input**, not learning."
            ),
        }
    )

    pg_path = _GAME_THEORY / "pattern_game.py"
    pg_import = _import_ok("renaissance_v4.game_theory.pattern_game")
    pg_ok = pg_path.is_file() and pg_import
    modules.append(
        {
            "id": "pattern_game",
            "label": "pattern_game.py · Referee",
            "role": "core_replay",
            "ok": pg_ok,
            "detail": "Referee replay import OK." if pg_ok else "Referee module missing or import failed.",
            "title": "Referee (deterministic replay)",
            "body": (
                "Core path: load manifest → deterministic forward replay → binary WIN/LOSS.\n"
                "Green = module importable and on disk. Same inputs + same code → reproducible stats (DEF-001).\n"
                "This does **not** train policy inside the loop."
            ),
        }
    )

    pr_ok = _import_ok("renaissance_v4.game_theory.parallel_runner")
    modules.append(
        {
            "id": "parallel_runner",
            "label": "parallel_runner.py",
            "role": "core_replay",
            "ok": pr_ok,
            "detail": "Process-pool batch runner import OK." if pr_ok else "Import failed.",
            "title": "Parallel batch runner",
            "body": (
                "Runs one scenario per worker process. Green = import succeeds (wired for parallel batches).\n"
                "Red = broken install or import error — batches will fail."
            ),
        }
    )

    bs_ok = _path_appendable(sc_path)
    modules.append(
        {
            "id": "batch_scorecard",
            "label": "batch_scorecard.py",
            "role": "evidence",
            "ok": bs_ok,
            "detail": f"Log path writable: {sc_path}" if bs_ok else f"Cannot append scorecard log: {sc_path}",
            "title": "Batch scorecard (JSONL)",
            "body": (
                "Append-only timing + counts per parallel batch.\n"
                "Green = parent directory exists and is writable so new batches can log.\n"
                "Evidence only — does not change Referee math."
            ),
        }
    )

    ss_ok = False
    ss_detail = "not checked"
    try:
        from renaissance_v4.game_theory.search_space_estimate import build_search_space_estimate

        est = build_search_space_estimate(batch_size=1, workers=1)
        sig_n = est.get("catalog", {}).get("signals_count") if isinstance(est, dict) else None
        ss_ok = isinstance(est, dict) and sig_n is not None
        ss_detail = f"{sig_n} catalog signals" if ss_ok else "estimate incomplete"
    except Exception as e:
        ss_detail = str(e)[:200]
    modules.append(
        {
            "id": "search_space",
            "label": "search_space_estimate.py",
            "role": "ops_suggestion",
            "ok": ss_ok,
            "detail": ss_detail[:220],
            "title": "Search space estimate",
            "body": (
                "Counts catalog signals and bar rows for workload hints.\n"
                "Green = estimate API returns catalog signal count (DB + catalog readable).\n"
                "Operational only — not Referee outcomes."
            ),
        }
    )

    cat_ok = False
    cat_detail = ""
    try:
        from renaissance_v4.game_theory.catalog_batch_builder import catalog_batch_builder_meta

        meta = catalog_batch_builder_meta()
        cat_ok = isinstance(meta, dict) and "default_max_scenarios" in meta
        cat_detail = "Chef meta OK" if cat_ok else "unexpected meta shape"
    except Exception as e:
        cat_detail = str(e)[:200]
    modules.append(
        {
            "id": "catalog_batch",
            "label": "catalog_batch_builder.py",
            "role": "ops_suggestion",
            "ok": cat_ok,
            "detail": cat_detail[:220],
            "title": "Chef (ATR sweep builder)",
            "body": (
                "Builds parallel scenario JSON (ATR grids) from catalog defaults.\n"
                "Green = builder metadata loads. Suggestion only until you click Run."
            ),
        }
    )

    hunt_ok = False
    hunt_detail = ""
    try:
        from renaissance_v4.game_theory.hunter_planner import build_hunter_suggestion

        hs = build_hunter_suggestion()
        hunt_ok = (
            isinstance(hs, dict)
            and hs.get("schema") == "hunter_suggestion_v1"
            and hs.get("ok") is True
        )
        hunt_detail = (
            "Hunter suggestion v1 OK"
            if hunt_ok
            else str(hs.get("error", "planner returned ok=false"))[:200]
        )
    except Exception as e:
        hunt_detail = str(e)[:200]
    modules.append(
        {
            "id": "hunter",
            "label": "hunter_planner.py",
            "role": "ops_suggestion",
            "ok": hunt_ok,
            "detail": hunt_detail[:220],
            "title": "Hunter (batch suggestions)",
            "body": (
                "Suggests distinct ATR scenarios from scorecard + retrospective rotation.\n"
                "Green = planner returns the expected schema (wired). Bounded suggestion — not Referee truth."
            ),
        }
    )

    gh_ok = bool(gh_env and ghb.is_file())
    modules.append(
        {
            "id": "groundhog",
            "label": "groundhog_memory.py",
            "role": "behavioral_memory",
            "ok": gh_ok,
            "detail": (
                "Behavioral memory **armed**: merge ON + bundle on disk."
                if gh_ok
                else "Not armed: need PATTERN_GAME_GROUNDHOG_BUNDLE=1 and groundhog_memory_bundle.json"
            ),
            "title": "Groundhog (promoted bundle → next run)",
            "body": (
                "The **only** default path that merges whitelisted parameters into the manifest before replay.\n"
                "Green = env merge **on** **and** canonical bundle file exists — the next eligible run can apply it.\n"
                "Red = merge off or no file — **no** promoted ATR from Groundhog (DEF-001: not ‘learning’, it is explicit promotion).\n"
                f"Bundle path: {ghb}"
            ),
        }
    )

    rm_ok = _path_appendable(rm_path)
    modules.append(
        {
            "id": "run_memory",
            "label": "run_memory.py",
            "role": "evidence",
            "ok": rm_ok,
            "detail": f"Evidence log appendable: {rm_path}" if rm_ok else f"Cannot append run_memory: {rm_path}",
            "title": "Run memory (JSONL audit)",
            "body": (
                "Append-only hypothesis + Referee row + decision audit per run.\n"
                "Green = log path is appendable. This is **evidence** — it does **not** auto-change the next replay unless you promote via bundle.\n"
                "Aligns with DEF-001: measurement and audit, not in-band training."
            ),
        }
    )

    retro_ok = _path_appendable(retro_path)
    modules.append(
        {
            "id": "retrospective",
            "label": "retrospective_log.py",
            "role": "interpretation",
            "ok": retro_ok,
            "detail": f"Retrospective log appendable: {retro_path}" if retro_ok else f"Cannot append: {retro_path}",
            "title": "Retrospective (operator notes)",
            "body": (
                "Append-only ‘what we saw / try next’ lines for humans and hunters.\n"
                "Green = file path is appendable (wired). Empty file is fine — red means filesystem not writable.\n"
                "Interpretation only — does not change Referee unless you act on it."
            ),
        }
    )

    pa_ok = _import_ok("renaissance_v4.game_theory.player_agent")
    modules.append(
        {
            "id": "player_agent",
            "label": "player_agent.py",
            "role": "narrative",
            "ok": pa_ok,
            "detail": "Narrative / batch report layer import OK." if pa_ok else "Import failed.",
            "title": "Player agent (narrative echo)",
            "body": (
                "Optional markdown batch reports + Anna hooks. Green = module imports.\n"
                "This layer is **descriptive** — it does **not** govern Referee scores (DEF-001)."
            ),
        }
    )

    return {"ok": True, "modules": modules, "def001_note": "Green/red = wiring truth for this host; Groundhog green = behavioral bundle path armed."}
