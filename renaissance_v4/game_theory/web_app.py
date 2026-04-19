"""
Local web UI for pattern game: **curated operator recipes** + **evaluation window**, or **Custom JSON**,
then Run (parallel workers). Recipes are defined in ``operator_recipes.py`` (not a glob of every file
in ``examples/``). The evaluation window (12 / 18 / 24 / custom months) is merged into each scenario
and drives **replay bar slicing** in ``run_manifest_replay`` (see ``replay_data_audit`` on results).

Batches use **``POST /api/run-parallel/start``** + polling **``GET /api/run-parallel/status/<job_id>``**
(or **``GET /api/run-status/<job_id>``**, same payload) so the UI shows **per-scenario progress** plus
**live telemetry** (decision windows, trades, candidate phase) from worker-written JSON snapshots.
``POST /api/run-parallel`` remains as a blocking API for scripts.

Each completed batch also writes a **unique session folder** under the logs directory (default:
``renaissance_v4/game_theory/logs/``, or ``$PATTERN_GAME_MEMORY_ROOT/logs`` on a tmpfs/ramdisk for
instant I/O). Folders look like ``batch_<UTC>_<id>/`` with ``BATCH_README.md`` and per-scenario
``HUMAN_READABLE.md``, unless ``PATTERN_GAME_NO_SESSION_LOG=1``. The JSON result includes
``session_log_batch_dir`` when present.

Parallel batches append one line per run to ``batch_scorecard.jsonl`` (UTC start/end, duration,
counts, **run_ok_pct**, **referee_win_pct**, **avg_trade_win_pct**) and expose ``batch_timing`` on the API; see
``GET /api/batch-scorecard``. Operators may truncate that log with
``POST /api/batch-scorecard/clear`` (does not touch engine memory files). Destructive engine reset:
``POST /api/pattern-game/reset-learning`` with typed confirm phrase (see UI).

Operator **retrospective** (learn / next experiment): ``GET /api/retrospective-log``,
``POST /api/retrospective-append`` — persists to ``retrospective_log.jsonl`` (see
``renaissance_v4/game_theory/retrospective_log.py``).

**Hunter planner (memory-aware batch suggestions):** ``GET /api/suggest-hunters`` returns
distinct parallel scenarios from scorecard + retrospective (see ``hunter_planner.py``); not
Referee predictions.

**Chef (catalog batch builder):** ``GET /api/catalog-batch-meta`` returns defaults (ATR grids, caps).
``POST /api/catalog-batch-generate`` with ``{"mode":"atr_sweep","manifest_path":"…"}`` builds a
validator-ready scenario array (same manifest, ATR geometry sweep) for paste or parallel run —
see ``catalog_batch_builder.py``.

**API:** ``GET /api/operator-recipes``, ``GET /api/operator-recipe-preview`` — curated playbooks.
**Advanced:** ``GET /api/scenario-presets`` lists raw ``examples/*.json`` for templates and debugging.

No manifest/ATR fields in the main controls — policy lives in the recipe / JSON. **Workers** slider defaults
to **logical CPU count** (capped by host hard max, see ``GET /api/capabilities``). ``POST /api/run`` remains for
scripted single-manifest runs (optional JSON field ``memory_bundle_path``).

  pip install -r renaissance_v4/game_theory/requirements.txt
  PYTHONPATH=. python3 -m renaissance_v4.game_theory.web_app

Default bind is loopback; use ``--host 0.0.0.0`` for LAN/SSH access (prototype).

**Hypothesis (default on):** parallel runs validate a non-empty ``agent_explanation.hypothesis`` per
scenario unless ``PATTERN_GAME_REQUIRE_HYPOTHESIS=0`` (or ``false`` / ``no`` / ``off``). Shipped
presets include a starter hypothesis string.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, jsonify, request

_GAME_THEORY = Path(__file__).resolve().parent

# Operator-visible web UI bundle version — bump when changing PAGE_HTML (HTML/CSS/JS) so deploys are provable.
PATTERN_GAME_WEB_UI_VERSION = "2.5.3"

from renaissance_v4.game_theory.groundhog_memory import (
    groundhog_auto_merge_enabled,
    groundhog_bundle_path,
    read_groundhog_bundle,
    write_groundhog_bundle,
)
from renaissance_v4.game_theory.batch_scorecard import (
    read_batch_scorecard_recent,
    record_parallel_batch_finished,
    truncate_batch_scorecard_jsonl,
    utc_timestamp_iso,
)
from renaissance_v4.game_theory.pattern_game_operator_reset import (
    RESET_PATTERN_GAME_LEARNING_CONFIRM,
    reset_pattern_game_engine_learning_state_v1,
)
from renaissance_v4.game_theory.data_health import get_data_health
from renaissance_v4.game_theory.search_space_estimate import build_search_space_estimate
from renaissance_v4.game_theory.memory_paths import (
    default_batch_scorecard_jsonl,
    default_experience_log_jsonl,
    default_retrospective_log_jsonl,
    ensure_memory_root_tree,
)
from renaissance_v4.game_theory.catalog_batch_builder import (
    build_atr_sweep_scenarios,
    catalog_batch_builder_meta,
)
from renaissance_v4.game_theory.hunter_planner import build_hunter_suggestion
from renaissance_v4.game_theory.retrospective_log import append_retrospective, read_retrospective_recent
from renaissance_v4.game_theory.live_telemetry_v1 import (
    clear_job_telemetry_files,
    default_telemetry_dir,
    read_job_telemetry_v1,
)
from renaissance_v4.game_theory.evaluation_window_runtime import (
    annotate_scenarios_with_window_and_recipe,
    resolve_ui_evaluation_window,
)
from renaissance_v4.game_theory.operator_recipes import (
    build_scenarios_for_recipe,
    default_recipe_id,
    operator_recipe_catalog,
    policy_catalog,
    recipe_meta_by_id,
)
from renaissance_v4.game_theory.parallel_runner import (
    REFERENCE_COMPARISON_RECIPE_ID,
    clamp_parallel_workers,
    get_parallel_limits,
    run_scenarios_parallel,
    validate_reference_comparison_batch_results,
)
from renaissance_v4.game_theory.pattern_game import (
    PATTERN_GAME_STARTING_EQUITY_USD_SPEC,
    _default_manifest_path,
    json_summary,
    run_pattern_game,
)
from renaissance_v4.game_theory.policy_framework import attach_policy_framework_audits
from renaissance_v4.game_theory.scenario_contract import (
    extract_policy_contract_summary,
    referee_session_outcome,
    validate_scenarios,
)
from renaissance_v4.game_theory.module_board import compute_pattern_game_module_board
from renaissance_v4.game_theory.scorecard_drill import (
    batch_detail_csv_rows,
    build_scenario_list_for_batch,
    find_scorecard_entry_by_job_id,
    read_scenario_artifact,
    scorecard_history_csv,
)

_JOBS_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_JOB_MAX_AGE_SEC = 7200


def _prune_jobs() -> None:
    now = time.time()
    with _JOBS_LOCK:
        stale = [k for k, v in _JOBS.items() if now - float(v.get("created", 0)) > _JOB_MAX_AGE_SEC]
        for k in stale:
            del _JOBS[k]


def _slug_preset_display_name(name: str) -> str:
    """Filesystem-safe slug from operator display name (user_*.json stem)."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:72] if s else "preset") or "preset"


def _web_ui_require_hypothesis() -> bool:
    """
    Require ``agent_explanation.hypothesis`` on each scenario for POST /api/run-parallel*.

    Default **True**. Disable with ``PATTERN_GAME_REQUIRE_HYPOTHESIS=0`` (or ``false`` / ``no`` / ``off``).
    """
    v = os.environ.get("PATTERN_GAME_REQUIRE_HYPOTHESIS", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


def _prepare_parallel_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Validate POST body for parallel run. Returns ``ok`` + fields or ``ok: False`` + ``error``."""
    recipe_id_in = (data.get("operator_recipe_id") or "").strip() or "custom"
    window_mode = (data.get("evaluation_window_mode") or "12").strip().lower()
    custom_m = data.get("evaluation_window_custom_months")

    try:
        resolved = resolve_ui_evaluation_window(window_mode, custom_m)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    health = get_data_health()
    cap = health.get("max_evaluation_window_calendar_months")
    req_m = int(resolved["effective_calendar_months"])
    if isinstance(cap, int) and cap > 0 and req_m > cap:
        span_d = health.get("replay_tape_span_days_approx") or health.get("all_bars_span_days")
        span_bit = f"~{round(float(span_d))}d of 5m bars" if isinstance(span_d, (int, float)) else "available 5m bars"
        return {
            "ok": False,
            "error": (
                f"Evaluation window ({req_m} mo) exceeds replay tape length "
                f"(max ~{cap} mo from {span_bit}). "
                "Pick a shorter window or ingest more history."
            ),
            "max_evaluation_window_calendar_months": cap,
            "evaluation_window_requested_months": req_m,
        }

    scenarios: list[dict[str, Any]] = []
    recipe_default_months = 12
    recipe_label = "Custom JSON"

    if recipe_id_in != "custom":
        meta = recipe_meta_by_id(recipe_id_in)
        if not meta:
            return {"ok": False, "error": f"Unknown operator_recipe_id: {recipe_id_in!r}"}
        try:
            scenarios = build_scenarios_for_recipe(recipe_id_in)
        except (FileNotFoundError, ValueError) as e:
            return {"ok": False, "error": str(e)}
        recipe_default_months = int(meta["default_evaluation_window_months"])
        recipe_label = str(meta["operator_label"])
    else:
        raw = data.get("scenarios_json")
        if not raw or not isinstance(raw, str):
            return {"ok": False, "error": "Missing scenarios_json string (Custom JSON mode)"}
        try:
            scenarios = json.loads(raw)
            if isinstance(scenarios, dict) and "scenarios" in scenarios:
                scenarios = scenarios["scenarios"]
            if not isinstance(scenarios, list):
                raise ValueError("scenarios must be a JSON array")
            scenarios = [x for x in scenarios if isinstance(x, dict)]
        except (json.JSONDecodeError, ValueError) as e:
            return {"ok": False, "error": str(e)}
        if scenarios:
            ew0 = scenarios[0].get("evaluation_window")
            if isinstance(ew0, dict) and ew0.get("calendar_months") is not None:
                try:
                    recipe_default_months = int(ew0["calendar_months"])
                except (TypeError, ValueError):
                    recipe_default_months = 12

    if not scenarios:
        return {"ok": False, "error": "No scenario objects in JSON array"}

    annotate_scenarios_with_window_and_recipe(
        scenarios,
        recipe_id=recipe_id_in,
        recipe_label=recipe_label,
        recipe_default_calendar_months=recipe_default_months,
        resolved=resolved,
    )

    for s in scenarios:
        if "manifest_path" in s and s["manifest_path"]:
            s["manifest_path"] = str(Path(s["manifest_path"]).expanduser().resolve())

    fw_ok, fw_msgs = attach_policy_framework_audits(scenarios)
    if not fw_ok:
        return {
            "ok": False,
            "error": fw_msgs[0] if fw_msgs else "Policy framework attach failed",
            "scenario_validation": {"ok": False, "messages": fw_msgs},
        }

    ok_val, val_msgs = validate_scenarios(
        scenarios,
        require_hypothesis=_web_ui_require_hypothesis(),
    )
    if not ok_val:
        return {
            "ok": False,
            "error": val_msgs[0] if val_msgs else "Invalid scenarios",
            "scenario_validation": {"ok": False, "messages": val_msgs},
        }

    val_msgs = list(val_msgs) + list(fw_msgs)

    max_workers = data.get("max_workers")
    if max_workers is not None:
        try:
            max_workers = int(max_workers)
        except (TypeError, ValueError):
            max_workers = None

    log_path = data.get("log_path")
    if log_path is True or log_path == "1":
        log_path = default_experience_log_jsonl()
    elif log_path:
        log_path = Path(str(log_path))
    else:
        log_path = None

    ew0 = scenarios[0].get("evaluation_window") if scenarios else {}
    operator_batch_audit: dict[str, Any] = {
        "operator_recipe_id": recipe_id_in,
        "operator_recipe_label": recipe_label,
        "evaluation_window_mode": resolved["evaluation_window_mode"],
        "evaluation_window_effective_calendar_months": int(resolved["effective_calendar_months"]),
        "recipe_default_calendar_months": recipe_default_months,
        "window_overrode_recipe_default": bool(
            isinstance(ew0, dict) and ew0.get("window_overrode_recipe_default")
        ),
        "manifest_path_primary": scenarios[0].get("manifest_path") if scenarios else None,
        "policy_framework_path": scenarios[0].get("policy_framework_path") if scenarios else None,
        "policy_framework_audit": scenarios[0].get("policy_framework_audit") if scenarios else None,
    }

    return {
        "ok": True,
        "scenarios": scenarios,
        "max_workers": max_workers,
        "log_path": log_path,
        "val_msgs": val_msgs,
        "operator_batch_audit": operator_batch_audit,
        "evaluation_window_resolved": resolved,
    }


def _telemetry_context_for_parallel_job(operator_batch_audit: dict[str, Any]) -> dict[str, Any]:
    """Static fields merged into per-worker telemetry files (plus live counters from replay)."""
    rid = str(operator_batch_audit.get("operator_recipe_id") or "").strip()
    pfa = operator_batch_audit.get("policy_framework_audit")
    fw_id = pfa.get("framework_id") if isinstance(pfa, dict) else None
    return {
        "operator_recipe_id": rid or None,
        "operator_recipe_label": operator_batch_audit.get("operator_recipe_label"),
        "policy_framework_id": fw_id,
        "evaluation_window_calendar_months": operator_batch_audit.get(
            "evaluation_window_effective_calendar_months"
        ),
        "learning_path_mode": (
            "operator_harness_candidate_search"
            if rid == REFERENCE_COMPARISON_RECIPE_ID
            else "baseline_replay_only"
        ),
        "candidate_search_active": rid == REFERENCE_COMPARISON_RECIPE_ID,
    }


def _batch_pnl_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum Referee ``cumulative_pnl`` across successful scenarios (independent replays, not one portfolio)."""
    start = float(PATTERN_GAME_STARTING_EQUITY_USD_SPEC)
    total = 0.0
    for r in results:
        if not r.get("ok"):
            continue
        p = r.get("cumulative_pnl")
        if isinstance(p, (int, float)):
            total += float(p)
    return {
        "starting_equity_usd": start,
        "batch_total_pnl_usd": total,
        "ending_equity_usd": start + total,
        "note": (
            "Paper baseline is the spec $1k starting equity per replay. "
            "A multi-scenario batch sums each scenario’s cumulative PnL (separate runs)."
        ),
    }


def _render_page_html() -> str:
    lim = get_parallel_limits()
    return (
        PAGE_HTML.replace("__LIMITS_JSON__", json.dumps(lim))
        .replace("__STARTING_EQUITY__", str(float(PATTERN_GAME_STARTING_EQUITY_USD_SPEC)))
        .replace("__PATTERN_GAME_WEB_UI_VERSION__", PATTERN_GAME_WEB_UI_VERSION)
    )


def create_app() -> Flask:
    ensure_memory_root_tree()
    app = Flask(__name__)

    @app.get("/")
    def index() -> Response:
        resp = Response(_render_page_html(), mimetype="text/html; charset=utf-8")
        resp.headers["X-Pattern-Game-UI-Version"] = PATTERN_GAME_WEB_UI_VERSION
        return resp

    @app.get("/api/capabilities")
    def capabilities() -> Any:
        h = get_data_health()
        return jsonify(
            {
                **get_parallel_limits(),
                "pattern_game_web_ui_version": PATTERN_GAME_WEB_UI_VERSION,
                "max_evaluation_window_calendar_months": h.get("max_evaluation_window_calendar_months"),
                "replay_tape_span_days_approx": h.get("replay_tape_span_days_approx"),
            }
        )

    @app.get("/api/groundhog-memory")
    def api_groundhog_memory_get() -> Any:
        """Canonical Groundhog bundle status — same tape, smarter execution when bundle + env enabled."""
        p = groundhog_bundle_path()
        return jsonify(
            {
                "ok": True,
                "path": str(p),
                "env_enabled": groundhog_auto_merge_enabled(),
                "exists": p.is_file(),
                "bundle": read_groundhog_bundle(),
            }
        )

    @app.post("/api/groundhog-memory")
    def api_groundhog_memory_post() -> Any:
        """Write promoted ATR geometry to the canonical bundle (``pattern_game_memory_bundle_v1``)."""
        data = request.get_json(force=True, silent=True) or {}
        try:
            a = float(data["atr_stop_mult"])
            b = float(data["atr_target_mult"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"ok": False, "error": "Need numeric atr_stop_mult and atr_target_mult"}), 400
        rid = (data.get("from_run_id") or "").strip() or None
        note = (data.get("note") or "").strip() or None
        path = write_groundhog_bundle(
            atr_stop_mult=a,
            atr_target_mult=b,
            from_run_id=rid,
            note=note,
        )
        return jsonify({"ok": True, "path": str(path), "bundle": read_groundhog_bundle()})

    @app.get("/api/data-health")
    def data_health() -> Any:
        """SQLite reachable, ``market_bars_5m`` present, replay row count, SOLUSDT ~12mo span."""
        return jsonify(get_data_health())

    @app.get("/api/module-board")
    def api_module_board() -> Any:
        """Subsystem wiring truth (DEF-001): each row green/red + modal copy from ``module_board``."""
        return jsonify(compute_pattern_game_module_board())

    @app.get("/api/search-space-estimate")
    def search_space_estimate() -> Any:
        """Finite catalog counts, bar rows, optional batch/worker parallel rounds (see ``search_space_estimate``)."""
        bs = request.args.get("batch_size")
        w = request.args.get("workers")
        try:
            batch_size = int(bs) if bs not in (None, "") else None
        except ValueError:
            batch_size = None
        try:
            workers = int(w) if w not in (None, "") else None
        except ValueError:
            workers = None
        return jsonify(build_search_space_estimate(batch_size=batch_size, workers=workers))

    @app.get("/api/operator-recipes")
    def api_operator_recipes() -> Any:
        """Curated operator playbooks (main UI). Not a directory glob."""
        return jsonify(
            {
                "ok": True,
                "recipes": operator_recipe_catalog(),
                "policy_catalog": policy_catalog(),
                "default_recipe_id": default_recipe_id(),
            }
        )

    @app.get("/api/operator-recipe-preview")
    def api_operator_recipe_preview() -> Any:
        """Return validated scenario JSON for a curated recipe + evaluation window (fills the textarea)."""
        recipe_id = (request.args.get("recipe_id") or default_recipe_id()).strip()
        window_mode = (request.args.get("evaluation_window_mode") or "12").strip().lower()
        cs = request.args.get("evaluation_window_custom_months")
        custom_m: int | None = None
        if cs not in (None, ""):
            try:
                custom_m = int(cs)
            except ValueError:
                return jsonify({"ok": False, "error": "evaluation_window_custom_months must be an integer"}), 400
        prep = _prepare_parallel_payload(
            {
                "operator_recipe_id": recipe_id,
                "evaluation_window_mode": window_mode,
                "evaluation_window_custom_months": custom_m,
                "scenarios_json": "[]",
            }
        )
        if not prep["ok"]:
            if recipe_id == "custom":
                return jsonify(
                    {
                        "ok": False,
                        "error": "Recipe 'custom' is filled from the textarea — no server preview.",
                    }
                ), 400
            return jsonify(dict(prep)), 400
        return jsonify(
            {
                "ok": True,
                "operator_batch_audit": prep["operator_batch_audit"],
                "scenario_count": len(prep["scenarios"]),
                "scenarios_json": json.dumps(prep["scenarios"], indent=2, ensure_ascii=False) + "\n",
            }
        )

    @app.get("/api/scenario-presets")
    def scenario_presets() -> Any:
        """
        **Advanced / examples:** raw ``*.json`` files under ``game_theory/examples/``.

        The main operator dropdown uses :func:`api_operator_recipes` instead of this glob.
        """
        ex = _GAME_THEORY / "examples"
        rows: list[dict[str, Any]] = []
        for p in sorted(ex.glob("*.json")):
            fn = p.name
            if fn.startswith("user_") and fn.endswith(".json"):
                label = "Uploaded: " + fn[5:-5].replace("_", " ")
                kind = "user"
            else:
                label = fn.replace("_", " ").replace(".example.json", "").replace(".json", "")
                kind = "builtin"
            rows.append({"filename": fn, "label": label, "kind": kind})
        return jsonify(rows)

    @app.get("/api/scenario-preset")
    def scenario_preset() -> Any:
        name = (request.args.get("name") or "").strip()
        if not name or Path(name).name != name:
            abort(400)
        allowed = {p.name for p in (_GAME_THEORY / "examples").glob("*.json")}
        if name not in allowed:
            abort(404)
        p = _GAME_THEORY / "examples" / name
        return jsonify({"ok": True, "filename": name, "content": p.read_text(encoding="utf-8")})

    @app.post("/api/scenario-preset-upload")
    def scenario_preset_upload() -> Any:
        """
        Upload a scenario JSON file and save as **user_<slug>.json** under ``game_theory/examples/``.

        **Standard format:** UTF-8 JSON — either a **JSON array** of scenario objects, or
        ``{\"scenarios\": [ ... ]}``. Same contract as the textarea / ``POST /api/run-parallel``.

        Multipart form: ``file`` (required), ``preset_name`` (required display name for the slug).
        """
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "missing form field: file"}), 400
        preset_name = (request.form.get("preset_name") or "").strip()
        if not preset_name:
            return jsonify({"ok": False, "error": "missing form field: preset_name"}), 400
        up = request.files["file"]
        if not up or not up.filename:
            return jsonify({"ok": False, "error": "empty file upload"}), 400
        raw = up.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"ok": False, "error": "file must be UTF-8 encoded text"}), 400
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return jsonify({"ok": False, "error": f"invalid JSON: {e}"}), 400
        if isinstance(data, dict) and "scenarios" in data:
            scenarios = data["scenarios"]
        elif isinstance(data, list):
            scenarios = data
        else:
            return jsonify(
                {
                    "ok": False,
                    "error": 'JSON must be a list of scenarios or an object with "scenarios" array',
                }
            ), 400
        if not isinstance(scenarios, list):
            return jsonify({"ok": False, "error": "scenarios must be a JSON array"}), 400
        scenarios = [x for x in scenarios if isinstance(x, dict)]
        if not scenarios:
            return jsonify({"ok": False, "error": "no scenario objects in list"}), 400
        ok_val, val_msgs = validate_scenarios(
            scenarios,
            require_hypothesis=_web_ui_require_hypothesis(),
        )
        if not ok_val:
            return jsonify(
                {
                    "ok": False,
                    "error": val_msgs[0] if val_msgs else "scenario validation failed",
                    "messages": val_msgs,
                }
            ), 400
        slug = _slug_preset_display_name(preset_name)
        filename = f"user_{slug}.json"
        dest = _GAME_THEORY / "examples" / filename
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return jsonify({"ok": False, "error": f"cannot create examples directory: {e}"}), 500
        if dest.is_file():
            return jsonify(
                {
                    "ok": False,
                    "error": f"Preset file already exists: {filename}. Pick another name or rename/delete the existing preset.",
                }
            ), 409
        try:
            dest.write_text(
                json.dumps(scenarios, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            return jsonify({"ok": False, "error": f"cannot write preset: {e}"}), 500
        return jsonify({"ok": True, "filename": filename, "saved_as": str(dest)})

    @app.post("/api/scenario-preset-rename")
    def scenario_preset_rename() -> Any:
        """Rename **user_*.json** only. Body JSON: ``old_filename``, ``new_preset_name`` (display name)."""
        data = request.get_json(force=True, silent=True) or {}
        old_fn = (data.get("old_filename") or "").strip()
        new_name = (data.get("new_preset_name") or "").strip()
        if not old_fn or not new_name:
            return jsonify({"ok": False, "error": "old_filename and new_preset_name are required"}), 400
        if Path(old_fn).name != old_fn or not old_fn.startswith("user_") or not old_fn.endswith(".json"):
            return jsonify({"ok": False, "error": "only user-uploaded presets (user_*.json) can be renamed"}), 400
        ex = _GAME_THEORY / "examples"
        old_path = ex / old_fn
        if not old_path.is_file():
            return jsonify({"ok": False, "error": "preset not found"}), 404
        new_slug = _slug_preset_display_name(new_name)
        new_fn = f"user_{new_slug}.json"
        new_path = ex / new_fn
        if new_path.resolve() == old_path.resolve():
            return jsonify({"ok": True, "filename": old_fn, "message": "name unchanged"})
        if new_path.is_file():
            return jsonify({"ok": False, "error": f"target file already exists: {new_fn}"}), 409
        try:
            old_path.rename(new_path)
        except OSError as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        return jsonify({"ok": True, "filename": new_fn})

    @app.post("/api/run")
    def api_run() -> Any:
        data = request.get_json(force=True, silent=True) or {}
        manifest = (data.get("manifest_path") or str(_default_manifest_path())).strip()
        atr_s = data.get("atr_stop_mult")
        atr_t = data.get("atr_target_mult")
        emit = bool(data.get("emit_baseline_artifacts"))
        mb = (data.get("memory_bundle_path") or "").strip() or None
        scen_echo: dict[str, Any] = {}
        if mb:
            scen_echo["memory_bundle_path"] = mb
        if data.get("skip_groundhog_bundle") is not None:
            scen_echo["skip_groundhog_bundle"] = bool(data.get("skip_groundhog_bundle"))
        try:
            out = run_pattern_game(
                manifest,
                atr_stop_mult=float(atr_s) if atr_s not in (None, "") else None,
                atr_target_mult=float(atr_t) if atr_t not in (None, "") else None,
                memory_bundle_path=mb,
                emit_baseline_artifacts=emit,
                verbose=False,
            )
            js = json_summary(out, scenario=scen_echo or None)
            cpn = out.get("cumulative_pnl")
            pnl = float(cpn) if isinstance(cpn, (int, float)) else 0.0
            start = float(PATTERN_GAME_STARTING_EQUITY_USD_SPEC)
            pnl_summary = {
                "starting_equity_usd": start,
                "batch_total_pnl_usd": pnl,
                "ending_equity_usd": start + pnl,
                "note": "Single manifest replay: cumulative PnL vs spec $1k paper baseline.",
            }
            return jsonify(
                {
                    "ok": True,
                    "summary": js,
                    "learning_run_audit_v1": js.get("learning_run_audit_v1"),
                    "operator_learning_status_line_v1": js.get("operator_learning_status_line_v1"),
                    "policy_contract": extract_policy_contract_summary(out.get("manifest_effective")),
                    "referee_session": referee_session_outcome(True, js),
                    "pnl_summary": pnl_summary,
                    "memory_bundle_audit": out.get("memory_bundle_audit"),
                    "memory_bundle_proof": out.get("memory_bundle_proof"),
                }
            )
        except Exception as e:
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 400

    @app.post("/api/run-parallel/start")
    def api_parallel_start() -> Any:
        """Start batch in a background thread; poll with ``GET /api/run-parallel/status/<job_id>``."""
        data = request.get_json(force=True, silent=True) or {}
        prep = _prepare_parallel_payload(data)
        if not prep["ok"]:
            return jsonify(dict(prep)), 400
        scenarios = prep["scenarios"]
        max_workers = prep["max_workers"]
        log_path = prep["log_path"]
        val_msgs = prep["val_msgs"]
        operator_batch_audit = prep["operator_batch_audit"]

        _prune_jobs()
        job_id = uuid.uuid4().hex
        workers_used = clamp_parallel_workers(max_workers, len(scenarios))
        telem_dir = default_telemetry_dir()
        clear_job_telemetry_files(job_id, base=telem_dir)
        telemetry_ctx = _telemetry_context_for_parallel_job(operator_batch_audit)
        with _JOBS_LOCK:
            _JOBS[job_id] = {
                "status": "running",
                "created": time.time(),
                "total": len(scenarios),
                "completed": 0,
                "workers_used": workers_used,
                "last_scenario_id": None,
                "last_ok": None,
                "last_message": None,
                "error": None,
                "result": None,
                "batch_timing": None,
                "telemetry_dir": str(telem_dir),
                "telemetry_context_echo": telemetry_ctx,
            }

        def run_job() -> None:
            session_batch_dir: list[str | None] = [None]
            started_iso = utc_timestamp_iso()
            start_unix = time.time()

            def on_session_batch(p: Path) -> None:
                session_batch_dir[0] = str(p.resolve())

            def cb(completed: int, total: int, row: dict[str, Any]) -> None:
                sid = row.get("scenario_id", "?")
                ok = bool(row.get("ok"))
                msg = f"{sid}: {'ok' if ok else 'failed'}"
                if not ok and row.get("error"):
                    msg += f" ({row.get('error')})"
                with _JOBS_LOCK:
                    j = _JOBS.get(job_id)
                    if j:
                        j["completed"] = completed
                        j["last_scenario_id"] = sid
                        j["last_ok"] = ok
                        j["last_message"] = msg

            try:
                results = run_scenarios_parallel(
                    scenarios,
                    max_workers=max_workers,
                    experience_log_path=log_path,
                    progress_callback=cb,
                    on_session_log_batch=on_session_batch,
                    telemetry_job_id=job_id,
                    telemetry_dir=telem_dir,
                    telemetry_context=telemetry_ctx,
                )
                validate_reference_comparison_batch_results(
                    results, operator_recipe_id=operator_batch_audit.get("operator_recipe_id")
                )
                ok_n = sum(1 for r in results if r.get("ok"))
                timing = record_parallel_batch_finished(
                    job_id=job_id,
                    started_at_utc=started_iso,
                    start_unix=start_unix,
                    total_scenarios=len(scenarios),
                    workers_used=workers_used,
                    results=results,
                    session_log_batch_dir=session_batch_dir[0],
                    error=None,
                    operator_batch_audit=operator_batch_audit,
                )
                payload = {
                    "ok": True,
                    "job_id": job_id,
                    "ran": len(results),
                    "ok_count": ok_n,
                    "failed_count": len(results) - ok_n,
                    "results": results,
                    "pnl_summary": _batch_pnl_summary(results),
                    "limits_applied": get_parallel_limits(),
                    "workers_used": workers_used,
                    "scenario_validation": {"ok": True, "messages": val_msgs},
                    "session_log_batch_dir": session_batch_dir[0],
                    "batch_timing": timing,
                    "operator_batch_audit": operator_batch_audit,
                    "learning_batch_audit_v1": timing.get("learning_batch_audit_v1"),
                    "batch_depth_v1": timing.get("batch_depth_v1"),
                    "batch_run_classification_v1": timing.get("batch_run_classification_v1"),
                    "operator_learning_status_line_v1": timing.get("operator_learning_status_line_v1"),
                }
                with _JOBS_LOCK:
                    j = _JOBS.get(job_id)
                    if j:
                        j["status"] = "done"
                        j["completed"] = len(results)
                        j["result"] = payload
                        j["batch_timing"] = timing
            except Exception as e:
                err_s = f"{type(e).__name__}: {e}"
                timing = record_parallel_batch_finished(
                    job_id=job_id,
                    started_at_utc=started_iso,
                    start_unix=start_unix,
                    total_scenarios=len(scenarios),
                    workers_used=workers_used,
                    results=None,
                    session_log_batch_dir=None,
                    error=err_s,
                    operator_batch_audit=operator_batch_audit,
                )
                with _JOBS_LOCK:
                    j = _JOBS.get(job_id)
                    if j:
                        j["status"] = "error"
                        j["error"] = err_s
                        j["batch_timing"] = timing

        threading.Thread(target=run_job, daemon=True).start()
        return jsonify(
            {
                "ok": True,
                "job_id": job_id,
                "total": len(scenarios),
                "workers_used": workers_used,
            }
        )

    @app.get("/api/run-parallel/status/<job_id>")
    @app.get("/api/run-status/<job_id>")
    def api_parallel_status(job_id: str) -> Any:
        _prune_jobs()
        with _JOBS_LOCK:
            j = _JOBS.get(job_id)
        if not j:
            return jsonify({"ok": False, "error": "Unknown or expired job_id"}), 404
        out: dict[str, Any] = {
            "ok": True,
            "status": j["status"],
            "total": j["total"],
            "completed": j["completed"],
            "workers_used": j.get("workers_used"),
            "last_scenario_id": j.get("last_scenario_id"),
            "last_ok": j.get("last_ok"),
            "last_message": j.get("last_message"),
        }
        if j.get("telemetry_context_echo") is not None:
            out["telemetry_context_echo"] = j["telemetry_context_echo"]
        td = j.get("telemetry_dir")
        if td:
            try:
                out["telemetry"] = read_job_telemetry_v1(job_id, base=Path(td))
            except OSError:
                out["telemetry"] = {
                    "schema": "pattern_game_live_telemetry_v1",
                    "job_id": job_id,
                    "scenarios": [],
                    "read_at_unix": time.time(),
                }
        if j.get("error"):
            out["error"] = j["error"]
        if j.get("batch_timing") is not None:
            out["batch_timing"] = j["batch_timing"]
        if j["status"] == "done" and j.get("result"):
            out["result"] = j["result"]
        return jsonify(out)

    @app.post("/api/run-parallel")
    def api_parallel() -> Any:
        """Blocking batch run (same work as ``/start`` + poll until done). Prefer ``/start`` for the UI."""
        data = request.get_json(force=True, silent=True) or {}
        prep = _prepare_parallel_payload(data)
        if not prep["ok"]:
            return jsonify(dict(prep)), 400
        scenarios = prep["scenarios"]
        max_workers = prep["max_workers"]
        log_path = prep["log_path"]
        val_msgs = prep["val_msgs"]
        operator_batch_audit = prep["operator_batch_audit"]

        job_id = uuid.uuid4().hex
        started_iso = utc_timestamp_iso()
        start_unix = time.time()
        workers_used = clamp_parallel_workers(max_workers, len(scenarios))
        telem_dir = default_telemetry_dir()
        clear_job_telemetry_files(job_id, base=telem_dir)
        telemetry_ctx = _telemetry_context_for_parallel_job(operator_batch_audit)
        try:
            session_batch_dir: list[str | None] = [None]

            def on_session_batch(p: Path) -> None:
                session_batch_dir[0] = str(p.resolve())

            results = run_scenarios_parallel(
                scenarios,
                max_workers=max_workers,
                experience_log_path=log_path,
                on_session_log_batch=on_session_batch,
                telemetry_job_id=job_id,
                telemetry_dir=telem_dir,
                telemetry_context=telemetry_ctx,
            )
            validate_reference_comparison_batch_results(
                results, operator_recipe_id=operator_batch_audit.get("operator_recipe_id")
            )
            ok_n = sum(1 for r in results if r.get("ok"))
            timing = record_parallel_batch_finished(
                job_id=job_id,
                started_at_utc=started_iso,
                start_unix=start_unix,
                total_scenarios=len(scenarios),
                workers_used=workers_used,
                results=results,
                session_log_batch_dir=session_batch_dir[0],
                error=None,
                operator_batch_audit=operator_batch_audit,
            )
            return jsonify(
                {
                    "ok": True,
                    "job_id": job_id,
                    "ran": len(results),
                    "ok_count": ok_n,
                    "failed_count": len(results) - ok_n,
                    "results": results,
                    "pnl_summary": _batch_pnl_summary(results),
                    "limits_applied": get_parallel_limits(),
                    "workers_used": workers_used,
                    "scenario_validation": {"ok": True, "messages": val_msgs},
                    "session_log_batch_dir": session_batch_dir[0],
                    "batch_timing": timing,
                    "operator_batch_audit": operator_batch_audit,
                    "learning_batch_audit_v1": timing.get("learning_batch_audit_v1"),
                    "batch_depth_v1": timing.get("batch_depth_v1"),
                    "batch_run_classification_v1": timing.get("batch_run_classification_v1"),
                    "operator_learning_status_line_v1": timing.get("operator_learning_status_line_v1"),
                }
            )
        except Exception as e:
            err_s = f"{type(e).__name__}: {e}"
            timing = record_parallel_batch_finished(
                job_id=job_id,
                started_at_utc=started_iso,
                start_unix=start_unix,
                total_scenarios=len(scenarios),
                workers_used=workers_used,
                results=None,
                session_log_batch_dir=None,
                error=err_s,
                operator_batch_audit=operator_batch_audit,
            )
            return jsonify({"ok": False, "error": err_s, "job_id": job_id, "batch_timing": timing}), 400

    @app.get("/api/batch-scorecard")
    def api_batch_scorecard() -> Any:
        """Recent batch timing lines from ``batch_scorecard.jsonl`` (newest first)."""
        try:
            limit = int(request.args.get("limit") or 25)
        except (TypeError, ValueError):
            limit = 25
        limit = max(1, min(200, limit))
        p = default_batch_scorecard_jsonl()
        rows = read_batch_scorecard_recent(limit, path=p)
        return jsonify(
            {
                "ok": True,
                "path": str(p.resolve()),
                "limit": limit,
                "entries": rows,
            }
        )

    @app.get("/api/batch-scorecard.csv")
    def api_batch_scorecard_csv() -> Any:
        """CSV export of recent batch scorecard rows (same columns as GT_DIRECTIVE_001)."""
        try:
            limit = int(request.args.get("limit") or 25)
        except (TypeError, ValueError):
            limit = 25
        limit = max(1, min(200, limit))
        p = default_batch_scorecard_jsonl()
        rows = read_batch_scorecard_recent(limit, path=p)
        body = scorecard_history_csv(rows)
        return Response(
            body,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="pattern_game_batch_scorecard_history.csv"'
            },
        )

    @app.post("/api/batch-scorecard/clear")
    def api_batch_scorecard_clear() -> Any:
        """
        Truncate ``batch_scorecard.jsonl`` only (batch audit / UI / hunter rotation input).

        Does **not** modify experience log, run memory, Groundhog bundle, context signature memory,
        retrospective, or session batch folders on disk.
        """
        data = request.get_json(force=True, silent=True) or {}
        if not data.get("confirm"):
            return jsonify({"ok": False, "error": 'Request JSON must include "confirm": true'}), 400
        p = truncate_batch_scorecard_jsonl()
        return jsonify(
            {
                "ok": True,
                "path": str(p),
                "note": (
                    "Truncated batch scorecard file only. Engine learning files "
                    "(bundles, recall memory JSONL, experience/run logs) were not modified."
                ),
            }
        )

    @app.post("/api/pattern-game/reset-learning")
    def api_pattern_game_reset_learning() -> Any:
        """
        Destructive: truncate experience + run memory JSONL, context-signature memory, delete Groundhog bundle.

        Does **not** truncate ``batch_scorecard.jsonl`` or ``retrospective_log.jsonl``.
        """
        data = request.get_json(force=True, silent=True) or {}
        c = data.get("confirm")
        if not isinstance(c, str):
            return jsonify(
                {
                    "ok": False,
                    "error": f'confirm must be the exact string {RESET_PATTERN_GAME_LEARNING_CONFIRM!r}',
                }
            ), 400
        out = reset_pattern_game_engine_learning_state_v1(confirm=c.strip())
        if not out.get("ok") and not out.get("cleared"):
            return jsonify(out), 400
        return jsonify(out), (200 if out.get("ok") else 500)

    @app.get("/api/batch-detail")
    def api_batch_detail() -> Any:
        """Drill-down: scorecard line + scenario list from session batch folder."""
        job_id = (request.args.get("job_id") or "").strip()
        if not job_id:
            return jsonify({"ok": False, "error": "job_id query parameter required"}), 400
        entry = find_scorecard_entry_by_job_id(job_id)
        if not entry:
            return jsonify({"ok": False, "error": f"job_id not found in scorecard log: {job_id!r}"}), 404
        _bd, scenarios, s_err = build_scenario_list_for_batch(job_id, entry.get("session_log_batch_dir"))
        return jsonify(
            {
                "ok": True,
                "scorecard": entry,
                "batch_dir": str(_bd.resolve()) if _bd and _bd.is_dir() else None,
                "scenarios": scenarios,
                "scenario_list_error": s_err,
            }
        )

    @app.get("/api/batch-detail.csv")
    def api_batch_detail_csv() -> Any:
        job_id = (request.args.get("job_id") or "").strip()
        if not job_id:
            return jsonify({"ok": False, "error": "job_id query parameter required"}), 400
        entry = find_scorecard_entry_by_job_id(job_id)
        if not entry:
            return jsonify({"ok": False, "error": f"job_id not found: {job_id!r}"}), 404
        _bd, scenarios, _err = build_scenario_list_for_batch(job_id, entry.get("session_log_batch_dir"))
        body = batch_detail_csv_rows(job_id, scenarios)
        safe = job_id.replace("/", "_")[:48]
        return Response(
            body,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="pattern_game_batch_{safe}_scenarios.csv"'
            },
        )

    @app.get("/api/batch-scenario-file")
    def api_batch_scenario_file() -> Any:
        """Artifact-backed HUMAN_READABLE.md or run_record.json for one scenario in a batch."""
        job_id = (request.args.get("job_id") or "").strip()
        scenario_id = (request.args.get("scenario_id") or "").strip()
        kind = (request.args.get("kind") or "human").strip().lower()
        if kind not in ("human", "json"):
            return jsonify({"ok": False, "error": "kind must be human or json"}), 400
        if not job_id or not scenario_id:
            return jsonify({"ok": False, "error": "job_id and scenario_id required"}), 400
        data, ct, err = read_scenario_artifact(job_id, scenario_id, "human" if kind == "human" else "json")
        if err or data is None:
            return jsonify({"ok": False, "error": err or "not found"}), 404
        return Response(data, mimetype=ct or "application/octet-stream")

    @app.get("/api/retrospective-log")
    def api_retrospective_log() -> Any:
        """Recent ``retrospective_log.jsonl`` lines (newest first)."""
        try:
            limit = int(request.args.get("limit") or 25)
        except (TypeError, ValueError):
            limit = 25
        limit = max(1, min(200, limit))
        p = default_retrospective_log_jsonl()
        rows = read_retrospective_recent(limit, path=p)
        return jsonify({"ok": True, "path": str(p.resolve()), "limit": limit, "entries": rows})

    @app.post("/api/retrospective-append")
    def api_retrospective_append() -> Any:
        """Append one retrospective line (what you saw / try next). Local prototype — no auth."""
        data = request.get_json(force=True, silent=True) or {}
        obs = (data.get("what_observed") or data.get("observed") or "").strip()
        nxt = (data.get("what_to_try_next") or data.get("try_next") or "").strip()
        if not obs or not nxt:
            return jsonify({"ok": False, "error": "what_observed and what_to_try_next are required strings"}), 400
        rr = (data.get("run_ref") or data.get("job_id") or "").strip() or None
        src = (data.get("source") or "web_ui").strip() or "web_ui"
        p = append_retrospective(what_observed=obs, what_to_try_next=nxt, run_ref=rr, source=src)
        return jsonify({"ok": True, "path": str(p)})

    @app.get("/api/suggest-hunters")
    def api_suggest_hunters() -> Any:
        """Return memory-aware parallel scenario JSON (scorecard + retrospective); deterministic ladder."""
        out = build_hunter_suggestion()
        if not out.get("ok"):
            return jsonify(out), 400
        return jsonify(out)

    _REPO_ROOT = Path(__file__).resolve().parent.parent.parent

    @app.get("/api/catalog-batch-meta")
    def api_catalog_batch_meta() -> Any:
        """Defaults for Chef ATR sweep (Anna / UI)."""
        return jsonify({"ok": True, **catalog_batch_builder_meta()})

    @app.post("/api/catalog-batch-generate")
    def api_catalog_batch_generate() -> Any:
        """
        Build parallel-ready scenarios: one manifest, many (stop, target) pairs (capped).

        Body JSON: ``mode`` (only ``atr_sweep``), ``manifest_path`` (optional, repo-relative),
        ``max_scenarios`` (1–200, default 24), optional ``pairs`` or ``stop_values``/``target_values``.
        """
        data = request.get_json(force=True, silent=True) or {}
        mode = (data.get("mode") or "atr_sweep").strip().lower()
        if mode != "atr_sweep":
            return jsonify({"ok": False, "error": f"unsupported mode {mode!r} (only atr_sweep)"}), 400

        mp = (data.get("manifest_path") or "").strip() or "renaissance_v4/configs/manifests/baseline_v1_recipe.json"
        cand = Path(mp)
        if not cand.is_absolute():
            cand = (_REPO_ROOT / mp).resolve()
        else:
            cand = cand.resolve()
        if not cand.is_file():
            return jsonify({"ok": False, "error": f"manifest not found: {mp}"}), 404

        try:
            max_n = int(data.get("max_scenarios") or 24)
        except (TypeError, ValueError):
            max_n = 24
        max_n = max(1, min(200, max_n))

        pairs_raw = data.get("pairs")
        pairs: list[tuple[float, float]] | None = None
        if pairs_raw is not None:
            if not isinstance(pairs_raw, list):
                return jsonify({"ok": False, "error": "pairs must be an array of [stop, target] pairs"}), 400
            pairs = []
            for row in pairs_raw:
                if not isinstance(row, (list, tuple)) or len(row) != 2:
                    return jsonify({"ok": False, "error": "each pairs entry must be [atr_stop_mult, atr_target_mult]"}), 400
                try:
                    pairs.append((float(row[0]), float(row[1])))
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "pairs must be numeric [stop, target]"}), 400

        sv_raw = data.get("stop_values")
        tv_raw = data.get("target_values")
        if sv_raw is not None and not isinstance(sv_raw, list):
            return jsonify({"ok": False, "error": "stop_values must be an array of numbers or omitted"}), 400
        if tv_raw is not None and not isinstance(tv_raw, list):
            return jsonify({"ok": False, "error": "target_values must be an array of numbers or omitted"}), 400
        sv = [float(x) for x in sv_raw] if sv_raw else None
        tv = [float(x) for x in tv_raw] if tv_raw else None

        try:
            scenarios = build_atr_sweep_scenarios(
                cand,
                pairs=pairs if pairs else None,
                stop_values=sv,
                target_values=tv,
                max_scenarios=max_n,
            )
        except FileNotFoundError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        ok, msgs = validate_scenarios(scenarios, require_hypothesis=_web_ui_require_hypothesis())
        if not ok:
            return jsonify({"ok": False, "error": "; ".join(msgs)}), 400
        return jsonify({"ok": True, "count": len(scenarios), "scenarios": scenarios, "warnings": msgs})

    return app


PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Pattern game · UI __PATTERN_GAME_WEB_UI_VERSION__</title>
  <style>
    :root {
      --pg-bg: #f2efe8;
      --pg-bg-accent: #e7e1d3;
      --pg-surface: rgba(255, 252, 246, 0.92);
      --pg-surface-strong: #fffdf8;
      --pg-ink: #1d232c;
      --pg-muted: #66707b;
      --pg-line: rgba(54, 64, 74, 0.14);
      --pg-shadow: 0 20px 50px rgba(35, 44, 56, 0.08);
      --pg-radius-xl: 26px;
      --pg-radius-lg: 18px;
      --pg-header-accent: #d7b56d;
      --pg-teal: #2f7f79;
      --pg-teal-soft: rgba(47, 127, 121, 0.14);
      --pg-amber: #b7772c;
      --pg-amber-soft: rgba(183, 119, 44, 0.14);
      --pg-rose: #9c544c;
      --pg-rose-soft: rgba(156, 84, 76, 0.14);
      --pg-steel: #50647a;
      --pg-steel-soft: rgba(80, 100, 122, 0.12);
      --pg-mono: ui-monospace, "SFMono-Regular", Menlo, monospace;
      --pg-sans: system-ui, -apple-system, "Segoe UI", "Avenir Next", "Helvetica Neue", sans-serif;
      --pg-accent: #1d6fa5;
      font-family: var(--pg-sans);
    }
    * { box-sizing: border-box; }
    body.pg-theme {
      margin: 0;
      color: var(--pg-ink);
      background:
        radial-gradient(circle at top left, rgba(255,255,255,0.85), transparent 35%),
        linear-gradient(180deg, var(--pg-bg) 0%, var(--pg-bg-accent) 100%);
      min-height: 100vh;
      line-height: 1.45;
    }
    .pg-shell {
      max-width: min(1920px, calc(100vw - 16px));
      margin: 0 auto;
      padding: 24px 24px 40px;
    }
    .pg-header {
      display: block;
      padding: 24px 26px 22px;
      background: linear-gradient(135deg, #14202a 0%, #243341 100%);
      color: #f7f1e6;
      border-radius: var(--pg-radius-xl);
      box-shadow: var(--pg-shadow);
      margin-bottom: 22px;
      overflow: hidden;
      position: relative;
    }
    .pg-header::after {
      content: "";
      position: absolute;
      inset: auto -80px -80px auto;
      width: 220px;
      height: 220px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(215,181,109,0.22), transparent 65%);
      pointer-events: none;
    }
    .pg-header-drawers {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 16px;
      position: relative;
      z-index: 2;
    }
    @media (max-width: 960px) {
      .pg-header-drawers { grid-template-columns: 1fr; }
    }
    .pg-header-evidence,
    .pg-header-modules {
      position: relative;
      z-index: 2;
      margin-top: 0;
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 16px;
      background: rgba(0,0,0,0.2);
    }
    .pg-header-evidence > summary,
    .pg-header-modules > summary {
      list-style: none;
      cursor: pointer;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px 14px;
      padding: 12px 14px;
      font-size: 0.95rem;
      font-weight: 700;
      color: #f7f1e6;
    }
    .pg-header-evidence > summary::-webkit-details-marker,
    .pg-header-modules > summary::-webkit-details-marker { display: none; }
    .pg-header-evidence > summary::before,
    .pg-header-modules > summary::before {
      content: "▸";
      display: inline-block;
      font-size: 0.85rem;
      opacity: 0.85;
      transition: transform 0.15s ease;
    }
    .pg-header-evidence[open] > summary::before,
    .pg-header-modules[open] > summary::before { transform: rotate(90deg); }
    .pg-header-evidence-hint {
      flex: 1 1 100%;
      margin: 0;
      padding-left: 1.35rem;
      font-size: 0.8rem;
      font-weight: 500;
      color: rgba(247, 241, 230, 0.65);
    }
    .pg-header-drawer-inner {
      padding: 0 14px 14px;
      border-top: 1px solid rgba(255,255,255,0.08);
    }
    .pg-header-modules .pg-pill-row { margin-top: 4px; }
    .pg-header-modules .pg-pill {
      background: rgba(255,255,255,0.08);
      border-color: rgba(255,255,255,0.15);
      color: rgba(247, 241, 230, 0.88);
    }
    .pg-header-modules .pg-status-item {
      background: rgba(255,255,255,0.06);
      border-color: rgba(255,255,255,0.1);
    }
    .pg-header-modules .pg-status-name { color: #f0f4f8; }
    .pg-header-modules .pg-status-meta { color: rgba(247, 241, 230, 0.72); }
    .pg-header-evidence .pg-tab-strip { margin-top: 10px; }
    .pg-header-evidence .pg-tab {
      background: rgba(255,255,255,0.08);
      border-color: rgba(255,255,255,0.18);
      color: rgba(247, 241, 230, 0.9);
    }
    .pg-header-evidence .pg-tab.active {
      background: rgba(255,255,255,0.92);
      border-color: rgba(255,255,255,0.92);
      color: #183343;
    }
    .pg-header-evidence .pg-pre-json {
      background: rgba(15, 22, 28, 0.55);
      border-color: rgba(255,255,255,0.12);
      color: #e8ecf0;
    }
    .pg-header-evidence .policy-outcome-panel .hint { color: rgba(247, 241, 230, 0.7); }
    .pg-header-evidence .policy-table th { background: rgba(255,255,255,0.1); color: rgba(247, 241, 230, 0.85); }
    .pg-header-evidence .policy-table td { color: #f0f4f8; border-color: rgba(255,255,255,0.12); }
    .pg-header-evidence #sessionLogNote { color: rgba(247, 241, 230, 0.75) !important; }
    details.pg-panel-fold {
      background: var(--pg-surface);
      border: 1px solid var(--pg-line);
      border-radius: var(--pg-radius-xl);
      box-shadow: var(--pg-shadow);
      min-width: 0;
      backdrop-filter: blur(12px);
    }
    details.pg-panel-fold > summary {
      list-style: none;
      cursor: pointer;
      padding: 14px 16px;
      display: flex;
      flex-wrap: nowrap;
      align-items: flex-start;
      gap: 10px;
      width: 100%;
      box-sizing: border-box;
    }
    details.pg-panel-fold > summary .pg-panel-header { flex: 1; min-width: 0; }
    details.pg-panel-fold > summary::-webkit-details-marker { display: none; }
    details.pg-panel-fold > summary::before {
      content: "▸";
      flex-shrink: 0;
      margin-top: 4px;
      font-size: 0.85rem;
      color: var(--pg-muted);
      transition: transform 0.15s ease;
    }
    details.pg-panel-fold[open] > summary::before { transform: rotate(90deg); }
    details.pg-panel-fold .pg-panel-fold-body { padding: 0 16px 16px; }
    details.pg-panel-fold .pg-panel-header { margin-bottom: 12px; }
    .pg-title-wrap { position: relative; z-index: 1; max-width: 980px; }
    .pg-eyebrow {
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: rgba(247, 241, 230, 0.68);
    }
    .pg-title {
      margin: 8px 0 6px;
      font-size: clamp(1.5rem, 2.5vw, 2rem);
      line-height: 1.08;
      letter-spacing: -0.03em;
      font-weight: 800;
    }
    .pg-title em { font-style: normal; color: var(--pg-header-accent); font-weight: 700; }
    .pg-lead {
      margin: 0;
      max-width: 760px;
      color: rgba(247, 241, 230, 0.82);
      font-size: 15px;
      line-height: 1.5;
    }
    .pg-lead strong { color: #fff; font-weight: 600; }
    .pg-orientation-note {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 12px;
      padding: 8px 11px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.1);
      color: rgba(247, 241, 230, 0.82);
      font-size: 12px;
      font-weight: 700;
    }
    .ui-version {
      display: inline-block;
      margin-left: 8px;
      padding: 3px 10px;
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      border-radius: 999px;
      background: rgba(255,255,255,0.1);
      color: #a8d4f5;
      border: 1px solid rgba(168,212,245,0.35);
      font-variant-numeric: tabular-nums;
      vertical-align: middle;
    }
    .pg-banner-strip {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin-top: 18px;
      max-width: min(1600px, 100%);
    }
    .pg-banner-stat {
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 16px;
      padding: 12px 14px;
      background: rgba(255,255,255,0.06);
      backdrop-filter: blur(10px);
      min-height: 78px;
    }
    .pg-banner-stat .pg-k {
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: rgba(247, 241, 230, 0.62);
      font-weight: 800;
      margin-bottom: 8px;
    }
    .pg-banner-stat .pg-v {
      font-size: 17px;
      font-weight: 800;
      line-height: 1.15;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .pg-banner-stat .pg-s {
      font-size: 12px;
      color: rgba(247, 241, 230, 0.72);
      line-height: 1.35;
    }
    .pg-banner-stat .pg-s.pg-s-tall { min-height: 2.8em; }
    .pg-banner-stat .status-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      flex-shrink: 0;
      background: #6b7a88;
    }
    .pg-banner-stat .status-dot.ok { background: #2fa46a; box-shadow: 0 0 8px rgba(47,164,106,0.45); }
    .pg-banner-stat .status-dot.bad { background: #d15959; box-shadow: 0 0 8px rgba(209,89,89,0.35); }
    .pg-row {
      display: grid;
      gap: 18px;
      margin-bottom: 18px;
    }
    .pg-row-main {
      grid-template-columns: minmax(280px, 1fr) minmax(420px, 2.6fr);
      align-items: start;
    }
    @media (max-width: 1680px) {
      .pg-row-main {
        grid-template-columns: minmax(240px, 1fr) minmax(360px, 2.4fr);
        overflow-x: auto;
        padding-bottom: 6px;
        -webkit-overflow-scrolling: touch;
      }
    }
    .pg-panel {
      background: var(--pg-surface);
      border: 1px solid var(--pg-line);
      border-radius: var(--pg-radius-xl);
      box-shadow: var(--pg-shadow);
      padding: 18px 20px 20px;
      min-width: 0;
      backdrop-filter: blur(12px);
    }
    .pg-panel-controls { min-height: 0; }
    .pg-panel-score .pg-table-scroll,
    .pg-header-evidence .pg-table-scroll {
      max-height: min(48vh, 480px);
      overflow: auto;
      border-radius: 12px;
      border: 1px solid var(--pg-line);
    }
    .pg-header-evidence .pg-tab-strip { gap: 6px; flex-wrap: wrap; }
    .pg-header-evidence .pg-tab { padding: 8px 10px; font-size: 11px; }
    .pg-panel-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 14px;
    }
    .pg-panel-h {
      margin: 0;
      font-size: 1.15rem;
      letter-spacing: -0.02em;
      font-weight: 800;
      color: var(--pg-ink);
    }
    .pg-panel-sub {
      margin: 6px 0 0;
      color: var(--pg-muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .pg-chip {
      flex-shrink: 0;
      border-radius: 999px;
      padding: 7px 10px;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 800;
      border: 1px solid transparent;
    }
    .pg-chip-teal { background: var(--pg-teal-soft); color: var(--pg-teal); border-color: rgba(47, 127, 121, 0.18); }
    .pg-chip-amber { background: var(--pg-amber-soft); color: var(--pg-amber); border-color: rgba(183, 119, 44, 0.18); }
    .pg-chip-rose { background: var(--pg-rose-soft); color: var(--pg-rose); border-color: rgba(156, 84, 76, 0.18); }
    .pg-chip-steel { background: var(--pg-steel-soft); color: var(--pg-steel); border-color: rgba(80, 100, 122, 0.16); }
    .def001-science {
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid rgba(47, 127, 121, 0.25);
      background: linear-gradient(180deg, rgba(47,127,121,0.08) 0%, rgba(47,127,121,0.03) 100%);
      font-size: 0.82rem;
      line-height: 1.5;
      color: #3a4f4c;
    }
    .def001-science .def001-tag {
      display: inline-block;
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: var(--pg-teal);
      margin-bottom: 6px;
    }
    .def001-science code { font-size: 0.85em; }
    details.help-details.pg-help {
      margin-top: 12px;
      border-radius: 12px;
      border: 1px solid var(--pg-line);
      background: var(--pg-surface-strong);
      padding: 0 12px;
    }
    details.help-details.pg-help summary {
      cursor: pointer;
      font-size: 0.82rem;
      color: var(--pg-accent);
      font-weight: 600;
      padding: 10px 0;
      list-style: none;
    }
    details.help-details summary::-webkit-details-marker { display: none; }
    .help-details-body { font-size: 0.8rem; color: var(--pg-muted); padding: 0 0 12px; }
    .help-details-body p { margin: 0 0 8px; }
    .pg-block {
      margin-top: 14px;
      padding: 14px;
      border-radius: var(--pg-radius-lg);
      border: 1px dashed rgba(54, 64, 74, 0.2);
      background: var(--pg-surface-strong);
    }
    .pg-block-title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--pg-muted);
      font-weight: 800;
      margin-bottom: 10px;
    }
    .pg-run-config {
      margin-top: 12px;
      padding: 12px 12px 10px;
      border-radius: var(--pg-radius-lg);
      border: 1px solid rgba(45, 138, 106, 0.35);
      background: rgba(45, 138, 106, 0.06);
    }
    .pg-run-config-dl {
      display: grid;
      grid-template-columns: minmax(0, 7rem) 1fr;
      gap: 4px 12px;
      font-size: 0.85rem;
      margin: 0;
    }
    .pg-run-config-dl dt {
      margin: 0;
      color: var(--pg-muted);
      font-weight: 600;
    }
    .pg-run-config-dl dd { margin: 0; color: var(--pg-ink); }
    .pg-goal-readonly {
      margin-top: 12px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid #c5cdd6;
      background: #fafbfc;
    }
    .pg-goal-line { margin: 0 0 6px; font-size: 0.84rem; line-height: 1.45; color: var(--pg-ink); }
    .pg-policy-line { margin: 8px 0 0; font-size: 0.88rem; color: var(--pg-ink); }
    textarea#scenarios:disabled {
      opacity: 0.55;
      cursor: not-allowed;
      background: #eceff2;
    }
    .pg-mini-grid { display: grid; gap: 10px; }
    .pg-mini-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    @media (max-width: 900px) {
      .pg-mini-3 { grid-template-columns: 1fr; }
    }
    details.inline-details {
      margin: 6px 0 10px;
      font-size: 0.78rem;
      color: var(--pg-muted);
      border-left: 2px solid #c5cdd6;
      padding-left: 10px;
    }
    details.inline-details summary { cursor: pointer; color: #4a5560; font-weight: 500; }
    .tool-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin-bottom: 10px; }
    .tool-row .btn-secondary {
      margin-top: 0;
      background: #e8edf2;
      color: #2c3844;
      font-weight: 600;
      font-size: 0.85rem;
      padding: 8px 12px;
      border: 1px solid var(--pg-line);
    }
    .tool-row .btn-chef {
      margin-top: 0;
      background: #2d8a6a;
      color: #fff;
      font-weight: 600;
      font-size: 0.85rem;
      padding: 8px 12px;
    }
    label { display: block; margin: 10px 0 4px; font-size: 0.85rem; color: var(--pg-muted); }
    input[type=text], input[type=number], textarea, select {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid #c5cdd6;
      border-radius: 8px;
      background: #fffefb;
      color: var(--pg-ink);
      font-size: 0.88rem;
    }
    textarea {
      min-height: 160px;
      max-height: min(48vh, 480px);
      font-family: var(--pg-mono);
      font-size: 0.8rem;
      resize: vertical;
    }
    button {
      margin-top: 12px;
      padding: 10px 18px;
      border: 0;
      border-radius: 10px;
      background: var(--pg-accent);
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    #runBtn { width: 100%; max-width: 340px; padding: 12px 20px; font-size: 1rem; border-radius: 12px; }
    .caps { font-size: 0.8rem; color: var(--pg-muted); margin: 8px 0 0; }
    .run-actions { margin-top: 8px; padding-top: 4px; }
    .status-stack { margin-top: 12px; }
    #workerCpuHint { font-size: 0.72rem; color: var(--pg-muted); margin: 6px 0 0; line-height: 1.4; }
    #workerEffectiveLine {
      margin: 10px 0 0;
      padding: 10px 12px;
      border-radius: 10px;
      background: #f4f1ea;
      border: 1px solid var(--pg-line);
      font-size: 0.82rem;
      line-height: 1.45;
      color: #3a4450;
    }
    #workerEffectiveLine strong { color: var(--pg-ink); }
    .pnl-strip {
      padding: 12px;
      border-radius: 12px;
      background: #f4f1ea;
      border: 1px solid var(--pg-line);
      font-size: 0.88rem;
    }
    .pnl-strip .pnl-row1 {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 10px 16px;
      margin-bottom: 8px;
    }
    .pnl-strip .pnl-baseline { color: var(--pg-muted); font-size: 0.8rem; }
    .pnl-strip .pnl-ending { font-size: 1.1rem; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--pg-ink); }
    .pnl-strip .pnl-delta { font-weight: 600; font-variant-numeric: tabular-nums; }
    .pnl-strip .pnl-delta.up { color: #1f8a54; }
    .pnl-strip .pnl-delta.down { color: #c43b3b; }
    .pnl-strip .pnl-delta.neutral { color: var(--pg-muted); }
    .pnl-bar-wrap { position: relative; margin-top: 4px; }
    .pnl-bar-track {
      height: 10px;
      border-radius: 5px;
      background: linear-gradient(90deg, #ebe4dc 0%, #d8dde3 50%, #ebe4dc 100%);
      position: relative;
    }
    .pnl-bar-ticks {
      display: flex;
      justify-content: space-between;
      font-size: 0.65rem;
      color: var(--pg-muted);
      margin-top: 4px;
    }
    .pnl-marker {
      position: absolute;
      top: -3px;
      width: 4px;
      height: 16px;
      margin-left: -2px;
      border-radius: 2px;
      background: var(--pg-ink);
      box-shadow: 0 0 6px rgba(0,0,0,0.12);
      transform: translateX(-50%);
      left: 50%;
    }
    .pnl-fill {
      position: absolute;
      top: 0;
      height: 10px;
      border-radius: 5px;
      opacity: 0.7;
      pointer-events: none;
    }
    .pnl-fill.up { background: #1f8a54; }
    .pnl-fill.down { background: #c43b3b; }
    .scorecard-legend {
      font-size: 0.76rem;
      color: var(--pg-muted);
      margin: 0 0 10px 0;
      line-height: 1.5;
      padding: 10px 12px;
      border-radius: 10px;
      background: #f4f1ea;
      border: 1px solid var(--pg-line);
    }
    .scorecard-legend strong { color: #3a4450; }
    .last-run {
      font-size: 0.85rem;
      color: var(--pg-ink);
      margin: 0 0 10px 0;
      line-height: 1.45;
    }
    .scorecard-learning-summary {
      font-size: 0.78rem;
      line-height: 1.5;
      color: var(--pg-ink);
      background: #f6f9fc;
      border: 1px solid var(--pg-line);
      border-radius: 10px;
      padding: 10px 12px;
      margin: 0 0 10px 0;
    }
    .scorecard-learning-summary .sls-line { margin: 0; }
    .scorecard-learning-summary .sls-title { font-weight: 700; color: #2d6a4f; margin-bottom: 4px; }
    .scorecard-learning-summary.exec-only .sls-title { color: #6c757d; }
    .scorecard-table-wrap-wide { overflow-x: auto; max-width: 100%; }
    .scorecard-table.scorecard-table-learning th,
    .scorecard-table.scorecard-table-learning td {
      font-size: 0.62rem;
      padding: 4px 4px;
      white-space: nowrap;
    }
    .chip-learn-yes { color: #1f6a45; font-weight: 700; }
    .chip-learn-no { color: #6c757d; font-weight: 600; }
    .drill-pre {
      max-height: 280px;
      overflow: auto;
      font-size: 0.72rem;
      background: #fff;
      border: 1px solid #d5dce3;
      border-radius: 8px;
      padding: 8px;
    }
    .path-hint { font-size: 0.72rem; color: var(--pg-muted); margin: 8px 0 0 0; word-break: break-all; }
    .scorecard-table { width: 100%; border-collapse: collapse; font-size: 0.72rem; }
    .scorecard-table th, .scorecard-table td {
      border: 1px solid #d5dce3;
      padding: 5px 6px;
      text-align: left;
    }
    .scorecard-table th { background: #eef1f4; color: #5a6570; white-space: nowrap; }
    .st-ok { color: #1f8a54; font-weight: 600; }
    .st-err { color: #c65a16; font-weight: 600; }
    .scorecard-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      align-items: center;
      margin: 0 0 10px 0;
    }
    .scorecard-toolbar a {
      font-size: 0.78rem;
      padding: 8px 12px;
      border-radius: 8px;
      border: 1px solid var(--pg-line);
      background: #fff;
      color: var(--pg-accent);
      text-decoration: none;
      font-weight: 600;
    }
    .scorecard-toolbar a:hover { background: #f4f8ff; }
    .scorecard-toolbar-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin: 8px 0 4px;
    }
    .btn-scorecard-clear {
      font-size: 0.78rem;
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid var(--pg-line);
      background: #fff;
      color: #2d4a6f;
      cursor: pointer;
      font-weight: 600;
    }
    .btn-scorecard-clear:hover { background: #f0f6ff; }
    .btn-learning-reset-danger {
      font-size: 0.78rem;
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid #c43b3b;
      background: #fff5f5;
      color: #a32b2b;
      cursor: pointer;
      font-weight: 600;
    }
    .btn-learning-reset-danger:hover { background: #ffe8e8; }
    tr.scorecard-row { cursor: pointer; }
    tr.scorecard-row:hover { background: #f0f4f8; }
    tr.scorecard-row.selected { background: #e8f0fe; }
    .batch-drill-panel {
      margin-top: 12px;
      padding: 12px;
      border-radius: 12px;
      border: 1px solid var(--pg-line);
      background: #faf8f5;
      font-size: 0.78rem;
      display: none;
    }
    .batch-drill-panel.visible { display: block; }
    .batch-drill-panel h3 { margin: 0 0 8px 0; font-size: 0.95rem; color: var(--pg-ink); }
    .batch-drill-meta { margin: 0 0 10px 0; line-height: 1.5; word-break: break-all; }
    .drill-scenario-table { width: 100%; border-collapse: collapse; font-size: 0.72rem; margin-top: 8px; }
    .drill-scenario-table th, .drill-scenario-table td {
      border: 1px solid #d5dce3;
      padding: 5px 6px;
      text-align: left;
      vertical-align: top;
    }
    .drill-scenario-table th { background: #eef1f4; color: #5a6570; }
    .mem-pill {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 0.68rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .mem-yes { background: #e3f4ea; color: #1f6a44; }
    .mem-no { background: #f0e8e8; color: #8a3a3a; }
    .gh-on { background: #e8f0fe; color: #175cd3; }
    .gh-off { background: #f4f1ea; color: #6a6570; }
    .pg-module-dialog {
      border: none;
      border-radius: 16px;
      padding: 0;
      max-width: min(540px, 94vw);
      background: #fffefb;
      color: #24303d;
      box-shadow: 0 16px 48px rgba(0, 0, 0, 0.35);
    }
    .pg-module-dialog::backdrop { background: rgba(10, 22, 30, 0.55); }
    .pg-module-dialog-inner { padding: 20px 44px 18px 22px; position: relative; }
    .pg-module-dialog-h2 { margin: 0 0 8px; font-size: 1.15rem; color: #183343; }
    .pg-module-role { margin: 0 0 12px; font-size: 0.78rem; color: #5a6570; font-weight: 600; }
    .pg-module-body { margin: 0; white-space: pre-wrap; font-family: var(--pg-mono); font-size: 0.78rem; line-height: 1.5; color: #3a4450; max-height: min(52vh, 420px); overflow: auto; }
    .pg-module-dialog-close { position: absolute; top: 8px; right: 10px; border: 0; background: transparent; font-size: 1.5rem; line-height: 1; cursor: pointer; color: #6a7580; padding: 4px 8px; border-radius: 8px; }
    .pg-module-dialog-close:hover { background: #f0f4f8; color: #183343; }
    #moduleBoardList .pg-status-item { cursor: pointer; }
    #moduleBoardList .pg-status-item:hover { filter: brightness(1.03); }
    #moduleBoardList .pg-status-item:focus { outline: 2px solid #2a8fd9; outline-offset: 2px; }
    .pg-upload-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin-top: 10px;
    }
    .btn-upload {
      padding: 10px 16px;
      border-radius: 10px;
      border: 1px solid var(--pg-line);
      background: #fff;
      color: #175cd3;
      font-weight: 600;
      font-size: 0.85rem;
      cursor: pointer;
    }
    .btn-upload:hover { background: #f4f8ff; }
    .btn-upload:disabled { opacity: 0.55; cursor: not-allowed; }
    .pg-upload-hint { font-size: 0.72rem; color: var(--pg-muted); margin: 0; flex: 1 1 200px; }
    .pg-spinner {
      width: 22px;
      height: 22px;
      border: 3px solid #d5dce3;
      border-top-color: #175cd3;
      border-radius: 50%;
      animation: pg-spin 0.7s linear infinite;
      display: none;
      vertical-align: middle;
    }
    .pg-spinner.visible { display: inline-block; }
    @keyframes pg-spin { to { transform: rotate(360deg); } }
    .pg-upload-dialog {
      border: none;
      border-radius: 16px;
      padding: 0;
      max-width: min(480px, 94vw);
      background: #fffefb;
      color: #24303d;
      box-shadow: 0 16px 48px rgba(0, 0, 0, 0.35);
    }
    .pg-upload-dialog::backdrop { background: rgba(10, 22, 30, 0.55); }
    .pg-upload-dialog-inner { padding: 20px 22px 18px; position: relative; }
    .pg-upload-dialog h2 { margin: 0 0 12px; font-size: 1.05rem; color: #183343; }
    .pg-upload-dialog label { display: block; font-size: 0.8rem; font-weight: 600; margin-bottom: 6px; color: #485360; }
    .pg-upload-dialog input[type="text"] {
      width: 100%;
      box-sizing: border-box;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--pg-line);
      font-size: 0.9rem;
      margin-bottom: 8px;
    }
    .pg-upload-steps { font-size: 0.78rem; color: #5a6570; margin: 0 0 14px; line-height: 1.5; }
    .pg-upload-result {
      margin-top: 12px;
      padding: 10px 12px;
      border-radius: 10px;
      font-size: 0.82rem;
      line-height: 1.45;
      display: none;
    }
    .pg-upload-result.visible { display: block; }
    .pg-upload-result.ok { background: #e8f6ee; border: 1px solid #9dceb7; color: #1a5c38; }
    .pg-upload-result.err { background: #fdecec; border: 1px solid #e0a0a0; color: #8a2222; }
    .pg-upload-actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 14px; }
    .btn-rename-preset {
      font-size: 0.78rem;
      padding: 8px 12px;
      border-radius: 8px;
      border: 1px dashed var(--pg-line);
      background: transparent;
      color: #175cd3;
      cursor: pointer;
      font-weight: 600;
    }
    .btn-rename-preset:disabled { opacity: 0.45; cursor: not-allowed; }
    .policy-outcome-panel .hint { font-size: 0.78rem; color: var(--pg-muted); margin: 0 0 10px 0; line-height: 1.4; }
    .pg-evidence-panel .policy-outcome-panel {
      margin: 0;
      padding: 0;
      border: 0;
      background: transparent;
      box-shadow: none;
      max-height: none;
      overflow: visible;
    }
    .policy-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.76rem;
    }
    .policy-table th, .policy-table td {
      border: 1px solid #d5dce3;
      padding: 6px 7px;
      text-align: left;
      vertical-align: top;
    }
    .policy-table th { background: #eef1f4; color: #5a6570; font-weight: 600; white-space: nowrap; }
    .policy-table td { color: var(--pg-ink); }
    .tag-win { color: #1f8a54; font-weight: 700; }
    .tag-loss { color: #c43b3b; font-weight: 700; }
    .tag-err { color: #c65a16; font-weight: 700; }
    .signals-cell { font-family: var(--pg-mono); font-size: 0.72rem; max-width: 320px; word-break: break-word; }
    input[type=checkbox] { width: auto; }
    input[type=range] { width: 100%; accent-color: var(--pg-accent); }
    .batch-concurrency-banner {
      display: none;
      margin: 10px 0 8px;
      padding: 10px 12px;
      border-radius: 10px;
      background: #f4f1ea;
      border: 1px solid var(--pg-line);
      font-size: 0.85rem;
      line-height: 1.45;
      color: var(--pg-ink);
    }
    .batch-concurrency-banner.visible { display: block; }
    .batch-concurrency-banner strong { color: var(--pg-accent); font-weight: 600; }
    .batch-concurrency-banner .warn { color: #b7772c; }
    .progress-wrap { display: none; margin: 12px 0 8px; }
    .progress-wrap.active { display: block; }
    .progress-track {
      height: 10px;
      border-radius: 5px;
      background: #d5dce3;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      width: 0%;
      border-radius: 5px;
      background: linear-gradient(90deg, #175cd3, #2a8fd9);
      transition: width 0.35s ease;
    }
    #progressSub { margin-top: 6px; font-size: 0.8rem; color: var(--pg-muted); }
    .live-telemetry-wrap {
      margin: 10px 0 14px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--pg-line);
      background: #0f1419;
      color: #e6edf3;
    }
    .live-telemetry-wrap[hidden] { display: none !important; }
    .live-telemetry-title {
      margin: 0 0 8px;
      font-size: 0.72rem;
      font-weight: 700;
      color: #8b98a5;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .live-telemetry-panel {
      margin: 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.74rem;
      line-height: 1.5;
      white-space: pre-wrap;
      max-height: 260px;
      overflow: auto;
    }
    #statusLine { min-height: 1.3em; color: var(--pg-ink); font-size: 0.9rem; margin-top: 8px; }
    .err { color: #c43b3b; }
    .pg-pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
    .pg-pill {
      padding: 8px 10px;
      border-radius: 999px;
      border: 1px solid var(--pg-line);
      background: #fff;
      font-size: 12px;
      font-weight: 700;
      color: #485360;
    }
    .pg-status-list { display: grid; gap: 10px; }
    .pg-status-item {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 10px 12px;
      align-items: start;
      padding: 11px 12px;
      border-radius: 14px;
      border: 1px solid var(--pg-line);
      background: linear-gradient(180deg, #fffdf9 0%, #f7f2e8 100%);
    }
    .pg-status-item .status-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      margin-top: 4px;
      flex-shrink: 0;
    }
    .pg-status-item .status-dot.ok { background: #2fa46a; box-shadow: 0 0 0 3px rgba(47, 164, 106, 0.14); }
    .pg-status-item .status-dot.bad { background: #d15959; box-shadow: 0 0 0 3px rgba(209, 89, 89, 0.14); }
    .pg-status-name { font-size: 13px; font-weight: 800; color: #24303d; margin-bottom: 3px; }
    .pg-status-meta { font-size: 12px; line-height: 1.45; color: var(--pg-muted); }
    .pg-tab-strip { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .pg-tab {
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--pg-line);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.02em;
      background: #fffefb;
      color: #4d5967;
      margin-top: 0;
      cursor: pointer;
    }
    .pg-tab.active {
      background: #183343;
      border-color: #183343;
      color: #f7f1e6;
    }
    .pg-evidence-panel { min-height: 120px; }
    .pg-pre-json {
      background: #f8f6f0;
      border: 1px solid var(--pg-line);
      border-radius: 12px;
      padding: 10px;
      overflow: auto;
      font-size: 0.7rem;
      font-family: var(--pg-mono);
      max-height: min(40vh, 360px);
      margin: 0;
    }
    #searchSpaceStrip strong { color: #f7f1e6; }
    #searchSpaceStrip code { font-size: 0.85em; color: rgba(247, 241, 230, 0.95); }
    @media (max-width: 1220px) {
      .pg-banner-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .pg-row-main { grid-template-columns: 1fr; overflow-x: visible; }
    }
    @media (max-width: 640px) {
      .pg-banner-strip { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      .pg-shell { padding: 14px; }
      .pg-banner-strip { grid-template-columns: 1fr; }
    }

  </style>
</head>
<body class="pg-theme">
  <div class="pg-shell">
    <header class="pg-header">
      <div class="pg-title-wrap">
        <div class="pg-eyebrow">Pattern game lab</div>
        <h1 class="pg-title">Pattern game <em>scorecard-first · five status tiles · header results &amp; modules</em>
          <span class="ui-version" title="Bump PATTERN_GAME_WEB_UI_VERSION in web_app.py">v__PATTERN_GAME_WEB_UI_VERSION__</span></h1>
        <p class="pg-lead">Pick <strong>recipe</strong> and <strong>evaluation window</strong>, then <strong>Run</strong> — the lab builds scenarios for you. <strong>Scorecard</strong> is the main view. <strong>Five status tiles</strong> include <strong>Modules</strong>. Custom JSON lives under <em>Advanced</em> only.</p>
        <div class="pg-orientation-note">Twisty on each panel · DEF record: <code>docs/architect/pattern_game_operator_deficiencies_work_record.md</code></div>
      </div>
      <div class="pg-banner-strip">
        <div class="pg-banner-stat">
          <div class="pg-k">Financial data</div>
          <div class="pg-v"><span class="status-dot" id="healthDot"></span> <span id="bannerFinancialV">—</span></div>
          <div class="pg-s" id="healthText">Checking database…</div>
        </div>
        <div class="pg-banner-stat">
          <div class="pg-k">Groundhog</div>
          <div class="pg-v" id="groundhogV">—</div>
          <div class="pg-s"><span id="groundhogText">loading…</span></div>
        </div>
        <div class="pg-banner-stat">
          <div class="pg-k">Search space</div>
          <div class="pg-s pg-s-tall" id="searchSpaceStrip" aria-live="polite"><strong>Search space</strong> — loading…</div>
        </div>
        <div class="pg-banner-stat">
          <div class="pg-k">Paper P&amp;L &amp; run</div>
          <div class="pg-v" id="bannerRunV">Idle</div>
          <div class="pg-s" id="bannerRunS">— run a batch —</div>
        </div>
        <div class="pg-banner-stat" title="Subsystem health from /api/module-board — expand Modules drawer below for the full list">
          <div class="pg-k">Modules</div>
          <div class="pg-v"><span class="status-dot" id="moduleBannerDot"></span> <span id="bannerModulesV">—</span></div>
          <div class="pg-s" id="bannerModulesS">Loading subsystem list…</div>
        </div>
      </div>
      <div class="pg-header-drawers">
      <details class="pg-header-evidence">
        <summary>
          <span class="pg-header-evidence-title">Results workspace</span>
          <span class="pg-chip pg-chip-steel" style="border-color:rgba(255,255,255,0.25);color:#e8ecf0">Evidence</span>
          <p class="pg-header-evidence-hint">Last run: Referee outcomes · raw JSON · session folder path — expand to inspect.</p>
        </summary>
        <div class="pg-header-drawer-inner">
          <div class="pg-tab-strip" role="tablist">
            <button type="button" class="pg-tab active" data-tab="outcomes" role="tab">Referee outcomes</button>
            <button type="button" class="pg-tab" data-tab="json" role="tab">Raw JSON</button>
            <button type="button" class="pg-tab" data-tab="session" role="tab">Session log</button>
          </div>
          <div id="pgEvidenceOutcomes" class="pg-evidence-panel">
            <div class="policy-outcome-panel" id="policyOutcomePanel" hidden>
              <p class="hint">Trade win % per scenario; session from cumulative P&amp;L.</p>
              <div class="pg-table-scroll">
                <table class="policy-table" id="policyOutcomeTable">
                  <thead>
                    <tr>
                      <th>Scenario</th><th>Session</th><th>Cum. P&amp;L</th><th>Trade win %</th><th>Trades</th>
                      <th>Signal modules</th><th>Fusion</th><th>Strategy id</th>
                    </tr>
                  </thead>
                  <tbody id="policyOutcomeTbody"></tbody>
                </table>
              </div>
            </div>
          </div>
          <p class="caps" id="sessionLogNote" style="display:none;margin:10px 0 8px"></p>
          <pre id="out" class="pg-pre-json" style="display:none">(no run yet)</pre>
        </div>
      </details>
      <details class="pg-header-modules">
        <summary>
          <span class="pg-header-evidence-title">Modules online</span>
          <span class="pg-chip pg-chip-rose" style="border-color:rgba(255,255,255,0.25);color:#f5d0cc">Health</span>
          <p class="pg-header-evidence-hint">Each dot = a real wiring check (not decoration). Groundhog green = behavioral bundle <strong>armed</strong>. Click any row for what it does (DEF-001).</p>
        </summary>
        <div class="pg-header-drawer-inner">
          <div class="pg-pill-row"><span class="pg-pill">Green = check passed</span><span class="pg-pill">Red = not wired / not armed</span></div>
          <div class="pg-status-list" id="moduleBoardList"><p class="caps" style="margin:0;color:rgba(247,241,230,0.75)">Loading…</p></div>
        </div>
      </details>
      </div>
    </header>

    <dialog id="moduleDetailDialog" class="pg-module-dialog" aria-labelledby="moduleModalTitle">
      <div class="pg-module-dialog-inner">
        <button type="button" class="pg-module-dialog-close" id="moduleModalClose" aria-label="Close">×</button>
        <h2 id="moduleModalTitle" class="pg-module-dialog-h2"></h2>
        <p id="moduleModalRole" class="pg-module-role"></p>
        <pre id="moduleModalBody" class="pg-module-body"></pre>
      </div>
    </dialog>

    <dialog id="uploadPresetDialog" class="pg-upload-dialog" aria-labelledby="uploadPresetDialogTitle">
      <div class="pg-upload-dialog-inner">
        <h2 id="uploadPresetDialogTitle">Upload scenario preset</h2>
        <p class="pg-upload-steps">1. Pick a <strong>.json</strong> file · 2. Name your preset · 3. Validate &amp; save (pass/fail shown here)</p>
        <p id="uploadChosenFileLabel" style="font-size:0.8rem;color:#5a6570;margin:0 0 10px"></p>
        <label for="uploadPresetNameInput">Preset name</label>
        <input type="text" id="uploadPresetNameInput" placeholder="e.g. SOL 12m grid" autocomplete="off" />
        <div class="pg-upload-result" id="uploadPresetResult" role="status" aria-live="polite"></div>
        <div class="pg-upload-actions">
          <span class="pg-spinner" id="uploadDialogSpinner" aria-hidden="true"></span>
          <button type="button" class="btn-chef" id="uploadPresetSubmitBtn">Validate &amp; save</button>
          <button type="button" class="btn-secondary" id="uploadPresetDoneBtn" style="display:none">Back to controls</button>
          <button type="button" class="btn-secondary" id="uploadPresetCancelBtn">Cancel</button>
        </div>
      </div>
    </dialog>

    <dialog id="renamePresetDialog" class="pg-upload-dialog" aria-labelledby="renamePresetDialogTitle">
      <div class="pg-upload-dialog-inner">
        <h2 id="renamePresetDialogTitle">Rename uploaded preset</h2>
        <p style="font-size:0.78rem;color:#5a6570;margin:0 0 10px">Only <code>user_*.json</code> uploads can be renamed (new slug from the name below).</p>
        <label for="renamePresetInput">New preset name</label>
        <input type="text" id="renamePresetInput" autocomplete="off" />
        <div class="pg-upload-result" id="renamePresetResult" role="status"></div>
        <div class="pg-upload-actions">
          <span class="pg-spinner" id="renameDialogSpinner"></span>
          <button type="button" class="btn-chef" id="renamePresetSubmitBtn">Rename</button>
          <button type="button" class="btn-secondary" id="renamePresetCancelBtn">Cancel</button>
        </div>
      </div>
    </dialog>

    <section class="pg-row pg-row-main">
      <details class="pg-panel-fold pg-panel-controls" open>
        <summary>
          <div class="pg-panel-header" style="margin:0;flex:1">
            <div>
              <h2 class="pg-panel-h">1. Game controls</h2>
              <p class="pg-panel-sub">Structured controls, run summary, workers.</p>
            </div>
            <span class="pg-chip pg-chip-teal">Controls</span>
          </div>
        </summary>
        <div class="pg-panel-fold-body">
        <div class="def001-science" role="region" aria-label="DEF-001">
          <span class="def001-tag">DEF-001 · SCIENCE / EVALUATION ONLY</span>
          <p style="margin:0">Same inputs + same code → reproducible Referee stats. <strong>No</strong> automatic policy training in the replay loop. “Memory” in logs is evidence or promoted bundle — not silent learning. Full contract: <code>docs/architect/pattern_game_operator_deficiencies_work_record.md</code> (DEF-001).</p>
        </div>
        <details class="help-details pg-help">
          <summary>Setup, PYTHONPATH, Groundhog</summary>
          <div class="help-details-body">
            <p>Run from repo root with <code>PYTHONPATH</code> including the repo. Example files load from <code>game_theory/examples/</code> (Advanced only).</p>
            <p><code>PATTERN_GAME_GROUNDHOG_BUNDLE=1</code> merges <code>game_theory/state/groundhog_memory_bundle.json</code> when a scenario has no <code>memory_bundle_path</code>. POST <code>/api/groundhog-memory</code> to promote ATR from review.</p>
          </div>
        </details>

        <div class="pg-block">
          <div class="pg-block-title">Run setup</div>
          <div class="pg-mini-grid pg-mini-3">
            <div><label for="operatorRecipePick">Recipe</label><select id="operatorRecipePick" aria-describedby="presetHelp">
              <option value="pattern_learning">Pattern Learning Run</option>
              <option value="reference_comparison">Reference Comparison Run</option>
              <option value="custom">Custom</option>
            </select></div>
            <div><label for="evaluationWindowPick">Evaluation window</label><select id="evaluationWindowPick" aria-describedby="presetHelp">
              <option value="12">12 months</option>
              <option value="18">18 months</option>
              <option value="24">24 months</option>
              <option value="custom">Custom…</option>
            </select></div>
            <div id="customMonthsWrap" style="display:none"><label for="evaluationWindowCustomMonths">Months</label><input type="number" id="evaluationWindowCustomMonths" min="1" max="600" value="36" style="width:100%;margin-top:4px"/></div>
          </div>
          <div id="policyMultiWrap" style="display:none;margin-top:10px">
            <label for="policyPick">Policy / manifest</label>
            <select id="policyPick" aria-label="Policy manifest"></select>
          </div>
          <p class="pg-policy-line" id="policyReadonly" style="display:none" role="status">Policy: —</p>
          <p class="caps" id="presetHelp">The server builds scenarios for curated recipes — no JSON required. Evaluation window controls how much tape is replayed (approximate months from the end of the series). Presets longer than your <code>market_bars_5m</code> span are disabled automatically (see Data health).</p>
          <div class="pg-run-config" id="runConfigPanel" role="region" aria-label="Run configuration">
            <div class="pg-block-title" style="margin-top:0">Run configuration</div>
            <dl class="pg-run-config-dl" id="runConfigDl">
              <dt>Recipe</dt><dd id="runConfigRecipe">—</dd>
              <dt>Policy</dt><dd id="runConfigPolicy">—</dd>
              <dt>Evaluation window</dt><dd id="runConfigWindow">—</dd>
              <dt>Goal</dt><dd id="runConfigGoalSummary">—</dd>
            </dl>
          </div>
          <div class="pg-goal-readonly" id="goalReadonlyPanel" aria-live="polite">
            <div class="pg-block-title" style="margin-top:0;margin-bottom:8px">Goal (read-only)</div>
            <p id="goalReadonlyTitle" class="pg-goal-line"></p>
            <p id="goalReadonlyMetrics" class="pg-goal-line"></p>
            <p id="goalReadonlyConstraints" class="pg-goal-line caps"></p>
            <p id="goalReadonlyNote" class="pg-goal-line caps" style="margin-bottom:0"></p>
          </div>
          <details class="help-details pg-help" style="margin-top:12px" id="advancedOperatorPanel">
            <summary>Advanced — examples, uploads &amp; custom JSON</summary>
            <div class="help-details-body">
              <div class="pg-mini-grid pg-mini-3" style="margin-top:8px">
                <div><label for="examplesFilePick">Load example file</label><select id="examplesFilePick"><option value="">— pick file —</option></select></div>
                <div><label>&nbsp;</label><button type="button" class="btn-secondary" style="width:100%;margin-top:0" id="suggestHuntersBtn" title="Scorecard + retrospective">Suggest hunters</button></div>
                <div><label>&nbsp;</label><button type="button" class="btn-chef" style="width:100%;margin-top:0" id="chefAtrSweepBtn">ATR sweep</button></div>
              </div>
              <span class="caps" id="hunterSuggestHint"></span>
              <div class="tool-row" style="margin-top:8px">
                <div style="flex:1;min-width:200px">
                  <label for="chefManifestPath" style="margin:0;font-size:0.8rem">Chef manifest</label>
                  <input type="text" id="chefManifestPath" style="margin-top:4px" value="renaissance_v4/configs/manifests/baseline_v1_recipe.json" spellcheck="false"/>
                </div>
                <span class="caps" id="chefHint" style="align-self:flex-end"></span>
              </div>
              <input type="file" id="presetFileInput" accept=".json,application/json" style="display:none" aria-hidden="true" />
              <div class="pg-upload-row">
                <button type="button" class="btn-upload" id="presetUploadBtn">Upload scenario JSON…</button>
                <button type="button" class="btn-rename-preset" id="presetRenameBtn" disabled title="Only for uploaded presets (user_*.json)">Rename preset…</button>
              </div>
              <p class="pg-upload-hint">Uploads validate against the scenario contract and appear in the example list. For a normal run, use <strong>Recipe</strong> above — not this file list.</p>
              <details class="inline-details" style="margin-top:12px;border-left-color:#2d8a6a" id="advancedJsonDetails">
                <summary>Custom scenario (JSON)</summary>
                <p class="caps" id="structuredJsonHint" style="margin:6px 0 8px">This field is <strong>disabled</strong> for curated recipes — the server injects manifest, window, and goal.</p>
                <details class="inline-details"><summary>Validation (hypothesis)</summary>
                  <p style="margin:0">Non-empty <code>agent_explanation.hypothesis</code> per scenario unless <code>PATTERN_GAME_REQUIRE_HYPOTHESIS=0</code>.</p>
                </details>
                <textarea id="scenarios" spellcheck="false" placeholder="Used only when Recipe = Custom. Array of scenario objects or {&quot;scenarios&quot;:[…]}."></textarea>
              </details>
            </div>
          </details>
        </div>

        <div class="pg-block">
          <div class="pg-block-title">Parallelism &amp; logging</div>
          <label for="workersRange">Workers <span id="workersVal" style="font-weight:700">1</span></label>
          <input type="range" id="workersRange" min="1" max="64" value="1" step="1" />
          <p id="workerCpuHint"></p>
          <div id="workerEffectiveLine" aria-live="polite"></div>
          <label style="margin-top:10px;font-size:0.85rem"><input type="checkbox" id="doLog" checked/> Append to experience JSONL</label>
        </div>

        <div class="pg-block">
          <div class="pg-block-title">Paper P&amp;L (batch)</div>
          <div class="pnl-strip" id="pnlStrip">
            <div class="pnl-row1">
              <span class="pnl-baseline">Baseline <span id="pnlBaselineLabel">$1,000.00</span></span>
              <span class="pnl-ending" id="pnlEnding">$1,000.00</span>
              <span class="pnl-delta neutral" id="pnlDelta">— run a batch —</span>
            </div>
            <div class="pnl-bar-wrap" aria-hidden="true">
              <div class="pnl-bar-track" id="pnlBarTrack">
                <div class="pnl-fill" id="pnlFill" style="left:50%;width:0;"></div>
                <div class="pnl-marker" id="pnlMarker"></div>
              </div>
              <div class="pnl-bar-ticks"><span>$0</span><span>$1k</span><span>$2k</span></div>
            </div>
          </div>
        </div>

        <div class="run-actions">
          <button type="button" id="runBtn">Run batch</button>
          <div class="status-stack">
            <div id="statusLine" aria-live="polite"></div>
            <div id="batchConcurrencyBanner" class="batch-concurrency-banner" aria-live="polite"></div>
            <div id="progressWrap" class="progress-wrap" role="progressbar" aria-label="Batch replay progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
              <div class="progress-track" id="progressTrack"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
              <p class="caps" id="progressSub"></p>
            </div>
          </div>
        </div>
        </div>
      </details>

      <div id="liveTelemetryWrap" class="live-telemetry-wrap" hidden>
        <p class="live-telemetry-title">Live run telemetry</p>
        <pre id="liveTelemetryPanel" class="live-telemetry-panel" aria-live="polite"></pre>
      </div>

      <details class="pg-panel-fold pg-panel-score" open>
        <summary>
          <div class="pg-panel-header" style="margin:0;flex:1">
            <div>
              <h2 class="pg-panel-h">2. Scorecard</h2>
              <p class="pg-panel-sub">Your visual cue for <strong>better vs worse</strong> across batches: compare Session WIN % and trade win % on newer rows to older ones (human iteration from metrics — not automatic online learning).</p>
            </div>
            <span class="pg-chip pg-chip-amber">Learning signal</span>
          </div>
        </summary>
        <div class="pg-panel-fold-body">
        <div class="scorecard-panel-inner" id="scorecardPanel">
          <p class="scorecard-legend"><strong>Run OK %</strong> — workers finished. <strong>Session WIN %</strong> — referee WIN vs LOSS among judged sessions only; <strong>n sess</strong> is that denominator (never infer from a bare percentage). <strong>Trade win %</strong> — batch mean when trades exist (with trade count). <strong>Learning</strong> — <code>execution_only</code> vs <code>learning_active</code> from replay counters (candidate search, memory records loaded, recall matches, signal bias). <strong>Work</strong> — decision windows, bars, and candidate-stack replays. Scan <em>down</em> for newest batches. <strong>Scorecard file</strong> (<code>batch_scorecard.jsonl</code>) is batch audit for this table and hunter suggestions; replay does <em>not</em> read it to apply memory or recall. <strong>Clear Card</strong> truncates that log only. <strong>Reset Learning State</strong> is separate and destructive (engine files — see confirmation).</p>
          <p class="last-run" id="lastBatchRunLine">Last completed batch: —</p>
          <div id="scorecardLearningSummary" class="scorecard-learning-summary exec-only" aria-live="polite" hidden>
            <p class="sls-title">Latest batch — learning summary</p>
            <p class="sls-line" id="scorecardLearningSummaryBody">—</p>
          </div>
          <div class="scorecard-toolbar">
            <a id="scorecardCsvLink" href="/api/batch-scorecard.csv?limit=50">Download scorecard history (CSV)</a>
            <div class="scorecard-toolbar-actions">
              <button type="button" class="btn-scorecard-clear" id="clearScorecardBtn">Clear Card — Run New Experiment</button>
              <button type="button" class="btn-learning-reset-danger" id="resetLearningStateBtn">Reset Learning State</button>
            </div>
            <span style="font-size:0.72rem;color:var(--pg-muted)">Click a row to open batch detail, scenarios, and per-scenario report links (GT_DIRECTIVE_001).</span>
          </div>
          <div class="pg-table-scroll scorecard-table-wrap-wide">
            <table class="scorecard-table scorecard-table-learning" id="scorecardHistoryTable">
              <thead>
                <tr>
                  <th title="job_id">Job</th>
                  <th title="started_at_utc">Start</th>
                  <th title="ended_at_utc">End</th>
                  <th title="duration_sec">Dur</th>
                  <th title="work_units_v1 — decision windows, bars, candidate-stack replays">Work</th>
                  <th title="learning_status">Learn</th>
                  <th title="decision_windows_total">DW</th>
                  <th title="bars_processed">Bars</th>
                  <th title="candidate_count">Cand</th>
                  <th title="selected_candidate_id">Sel</th>
                  <th title="winner_vs_control_delta">WΔ</th>
                  <th title="memory_used">Mem</th>
                  <th title="memory_records_loaded">MRec</th>
                  <th title="groundhog_status">GH</th>
                  <th title="recall_attempts">RAtt</th>
                  <th title="recall_matches">RMt</th>
                  <th title="recall_bias_applied">RBias</th>
                  <th title="signal_bias_applied_count">SBc</th>
                  <th title="suppressed_modules_count">Sup</th>
                  <th title="trade_entries_total">TIn</th>
                  <th title="trade_exits_total">TOut</th>
                  <th title="batch_trade_win_pct / avg_trade_win_pct when trades exist">TW%</th>
                  <th title="batch_trades_count">#Tr</th>
                  <th title="expectancy_per_trade (mean scenarios with trades)">E/tr</th>
                  <th title="exit_efficiency">Xeff</th>
                  <th title="win_loss_size_ratio">WLR</th>
                  <th title="referee_win_pct">SWin%</th>
                  <th title="batch_sessions_judged">#Sess</th>
                  <th title="run_ok_pct">RunOK%</th>
                  <th title="ok_count">OK</th>
                  <th title="failed_count">Fail</th>
                  <th title="workers_used">Wkr</th>
                  <th title="status">St</th>
                </tr>
              </thead>
              <tbody id="scorecardHistoryTbody"></tbody>
            </table>
          </div>
          <div id="batchDrillPanel" class="batch-drill-panel" aria-live="polite"></div>
          <p class="path-hint" id="scorecardPathHint"></p>
        </div>
        </div>
      </details>
    </section>
  </div>

  
  <script>
    const LIMITS = __LIMITS_JSON__;
    const STARTING_EQUITY = __STARTING_EQUITY__;
    const RUN_TIMEOUT_MS = 7200000;

    const rangeEl = document.getElementById('workersRange');
    const workersVal = document.getElementById('workersVal');
    const statusLine = document.getElementById('statusLine');
    const progressWrap = document.getElementById('progressWrap');

    const hardMax = LIMITS.hard_cap_workers;
    const recommended = LIMITS.recommended_max_workers;
    const defaultWorkers = Math.max(1, Math.min(recommended, hardMax));

    rangeEl.min = '1';
    rangeEl.max = String(hardMax);
    rangeEl.value = String(defaultWorkers);
    workersVal.textContent = rangeEl.value;
    document.getElementById('workerCpuHint').textContent =
      'Host: ' + LIMITS.cpu_logical_count + ' logical CPUs · default slider ' + recommended +
      ' · max ' + hardMax + '. ' + LIMITS.note;

    function parseScenarioCountFromTextarea() {
      const ta = document.getElementById('scenarios');
      if (!ta || !ta.value.trim()) return 0;
      try {
        const parsed = JSON.parse(ta.value.trim());
        const arr = Array.isArray(parsed) ? parsed : (parsed && Array.isArray(parsed.scenarios) ? parsed.scenarios : null);
        return (arr && arr.length) ? arr.length : 0;
      } catch (e) { return 0; }
    }
    /** Curated recipes: scenario count from server preview (textarea may be empty/disabled). */
    let STRUCTURED_SCENARIO_COUNT = 1;
    function getEffectiveScenarioCount() {
      const rp = document.getElementById('operatorRecipePick');
      const rid = rp && rp.value;
      if (rid && rid !== 'custom') {
        return STRUCTURED_SCENARIO_COUNT > 0 ? STRUCTURED_SCENARIO_COUNT : 1;
      }
      return parseScenarioCountFromTextarea();
    }
    function refreshWorkerEffectiveLine() {
      const el = document.getElementById('workerEffectiveLine');
      if (!el) return;
      const n = getEffectiveScenarioCount();
      const w = parseInt(rangeEl.value, 10) || 1;
      if (n < 1) {
        el.innerHTML = '<strong>Effective parallelism</strong> — For <em>Custom</em>, paste valid JSON in Advanced. The run uses <strong>min(scenario count, slider)</strong>.';
        return;
      }
      const eff = Math.min(n, w);
      let extra = '';
      if (n === 1) {
        extra = '<div style="margin-top:8px;color:#c9a227;font-size:0.9em">Single scenario: only one process runs; raising the slider does not speed it up.</div>';
      }
      el.innerHTML =
        '<strong>' + eff + '</strong> parallel process(es) for this batch ' +
        '(<strong>' + n + '</strong> scenario(s) × slider <strong>' + w + '</strong>, capped at the smaller). ' + extra;
    }

    rangeEl.addEventListener('input', () => {
      workersVal.textContent = rangeEl.value;
      if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
      refreshWorkerEffectiveLine();
    });

    function escapeHtml(s) {
      if (s == null) return '';
      const d = document.createElement('div');
      d.textContent = String(s);
      return d.innerHTML;
    }

    function recipeLabelFromDom() {
      const rp = document.getElementById('operatorRecipePick');
      if (!rp || !rp.options) return '—';
      const o = rp.options[rp.selectedIndex];
      return (o && o.text) ? String(o.text).trim() : String(rp.value || '—');
    }
    function evaluationWindowLabelFromDom() {
      const w = document.getElementById('evaluationWindowPick');
      if (!w) return '—';
      if (w.value === 'custom') {
        const c = document.getElementById('evaluationWindowCustomMonths');
        const n = c ? parseInt(c.value, 10) : NaN;
        return (n > 0) ? (String(n) + ' months (custom)') : 'custom';
      }
      return String(w.value) + ' months';
    }
    function fmtTelemetryHMS(sec) {
      const s = Math.max(0, Math.floor(Number(sec) || 0));
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const rs = s % 60;
      if (h > 0) {
        return h + ':' + String(m).padStart(2, '0') + ':' + String(rs).padStart(2, '0');
      }
      return String(m).padStart(2, '0') + ':' + String(rs).padStart(2, '0');
    }
    function renderLiveTelemetryPanel(pj, opts) {
      const wrap = document.getElementById('liveTelemetryWrap');
      const el = document.getElementById('liveTelemetryPanel');
      if (!wrap || !el) return;
      if (!pj || pj.status !== 'running') {
        wrap.hidden = true;
        return;
      }
      wrap.hidden = false;
      const echo = pj.telemetry_context_echo || {};
      const telem = pj.telemetry || {};
      const rows = Array.isArray(telem.scenarios) ? telem.scenarios.slice() : [];
      const completed = pj.completed != null ? pj.completed : 0;
      const total = pj.total != null ? pj.total : 0;
      const elapsed = opts && opts.elapsedSec != null ? opts.elapsedSec : 0;
      const lm = pj.last_message || '';
      const recipe =
        echo.operator_recipe_label || echo.operator_recipe_id || (opts && opts.recipeLabel) || '—';
      const fw =
        echo.policy_framework_id != null && String(echo.policy_framework_id) !== ''
          ? String(echo.policy_framework_id)
          : '—';
      const winM = echo.evaluation_window_calendar_months;
      const winStr =
        winM != null ? String(winM) + ' months' : ((opts && opts.windowLabel) ? opts.windowLabel : '—');
      let hot = null;
      if (rows.length) {
        rows.sort(
          (a, b) => (Number(b.decision_windows_processed) || 0) - (Number(a.decision_windows_processed) || 0)
        );
        hot = rows[0];
      }
      const lines = [];
      lines.push('Run: ' + recipe);
      lines.push('Framework: ' + fw);
      lines.push('Window: ' + winStr);
      lines.push('');
      lines.push(
        'Batch: ' + completed + ' / ' + total + ' scenario(s) finished (parallel)' +
        (lm ? (' · last: ' + lm) : '')
      );
      if (hot) {
        const si = hot.scenario_index;
        const st = hot.scenario_total;
        const sid = hot.scenario_id || '—';
        lines.push(
          'Busiest worker — scenario slot ' + (si != null ? si : '?') + '/' + (st != null ? st : '?') +
            ' — ' + sid
        );
        const csa = hot.candidate_search_active === true || echo.candidate_search_active === true;
        if (!csa) {
          lines.push('Candidate phase: baseline only (no multi-replay candidate search)');
        } else {
          const phase = hot.candidate_phase || '—';
          const ci = hot.candidate_index;
          const ct = hot.candidates_total;
          const cpart =
            ci != null && ct != null
              ? 'current index ' + ci + ' / ' + ct
              : ci != null
                ? 'index ' + ci
                : '';
          lines.push('Candidate phase: ' + phase + (cpart ? ' (' + cpart + ')' : ''));
        }
        const dw = Number(hot.decision_windows_processed || 0);
        const dset = hot.dataset_bars;
        const dwTot = dset != null ? Number(dset) : null;
        lines.push(
          'Decision windows: ' + dw.toLocaleString() +
            (dwTot != null ? ' / ' + dwTot.toLocaleString() + ' (bars in slice)' : '') +
            ' · bars processed: ' +
            (hot.bars_processed != null ? Number(hot.bars_processed).toLocaleString() : String(dw))
        );
        lines.push(
          'Trades (closed): ' + (hot.trades_closed_so_far != null ? hot.trades_closed_so_far : '0') +
            ' · entry attempts: ' + (hot.entries_attempted_so_far != null ? hot.entries_attempted_so_far : '0')
        );
        lines.push('');
        lines.push(
          'Candidates tested (search progress): ' +
            (hot.candidates_tested_so_far != null ? hot.candidates_tested_so_far : '0') +
            (hot.candidates_total != null ? ' / ' + hot.candidates_total : '')
        );
        lines.push('Recall match windows: ' + (hot.recall_match_windows_so_far != null ? hot.recall_match_windows_so_far : '0'));
        lines.push('Signal bias applications: ' + (hot.signal_bias_applied_so_far != null ? hot.signal_bias_applied_so_far : '0'));
        lines.push('');
        const rate = elapsed > 0.5 ? (dw / elapsed).toFixed(2) : null;
        lines.push(
          'Elapsed: ' + fmtTelemetryHMS(elapsed) +
            (rate != null ? ' · ~' + rate + ' decision windows/s (busiest worker)' : '')
        );
      } else {
        lines.push('');
        lines.push('Workers starting — counters appear when the first decision windows are processed.');
        lines.push('Elapsed: ' + fmtTelemetryHMS(elapsed));
      }
      if (rows.length > 1) {
        lines.push('');
        lines.push('(' + rows.length + ' telemetry file(s); busiest worker shown by decision window count.)');
      }
      el.textContent = lines.join('\n');
    }
    function hideLiveTelemetryPanel() {
      const wrap = document.getElementById('liveTelemetryWrap');
      if (wrap) wrap.hidden = true;
    }

    function setBannerRun(main, sub) {
      const v = document.getElementById('bannerRunV');
      const s = document.getElementById('bannerRunS');
      if (v && main != null) v.textContent = main;
      if (s && sub != null) s.textContent = sub;
    }
    function syncBannerRunFromStatusLine() {
      const st = document.getElementById('statusLine');
      const t = (st && st.textContent) ? st.textContent.trim() : '';
      if (!t) {
        setBannerRun('Idle', '— run a batch —');
        return;
      }
      if (t.indexOf('Running') === 0 || t.indexOf('Starting') === 0) {
        setBannerRun('Running', t.length > 140 ? t.slice(0, 137) + '…' : t);
        return;
      }
      if (t.indexOf('Finished') === 0) {
        setBannerRun('Done', t.length > 140 ? t.slice(0, 137) + '…' : t);
        return;
      }
      if (t.indexOf('Failed') === 0 || t.indexOf('Stopped') === 0 || t.indexOf('Client timeout') === 0) {
        setBannerRun('Error', t.length > 140 ? t.slice(0, 137) + '…' : t);
        return;
      }
      setBannerRun('Idle', t.length > 140 ? t.slice(0, 137) + '…' : t);
    }
    function setEvidenceTab(tab) {
      const outcomes = document.getElementById('pgEvidenceOutcomes');
      const pre = document.getElementById('out');
      const sn = document.getElementById('sessionLogNote');
      const tabs = document.querySelectorAll('.pg-tab-strip .pg-tab');
      const id = tab || 'outcomes';
      tabs.forEach((b) => {
        b.classList.toggle('active', b.getAttribute('data-tab') === id);
      });
      if (outcomes) outcomes.style.display = (id === 'outcomes') ? '' : 'none';
      if (pre) pre.style.display = (id === 'json') ? 'block' : 'none';
      if (sn) sn.style.display = (id === 'session') ? 'block' : 'none';
      const hdr = document.querySelector('.pg-header-evidence');
      if (hdr && (id === 'json' || id === 'session' || id === 'outcomes')) hdr.open = true;
    }
    document.querySelectorAll('.pg-tab-strip .pg-tab').forEach((btn) => {
      btn.addEventListener('click', () => setEvidenceTab(btn.getAttribute('data-tab')));
    });

    function formatUsdPlain(n) {
      const x = Number(n);
      if (Number.isNaN(x)) return '—';
      const abs = Math.abs(x);
      return (x < 0 ? '−' : '') + '$' + abs.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function formatDurationSec(s) {
      const n = Number(s);
      if (Number.isNaN(n)) return '—';
      if (n < 60) return n.toFixed(1) + 's';
      const m = Math.floor(n / 60);
      const sec = n - m * 60;
      return m + 'm ' + sec.toFixed(0) + 's';
    }

    function fmtIntCommas(v) {
      if (v == null || v === '') return '—';
      const n = Number(v);
      if (!Number.isFinite(n)) return '—';
      return n.toLocaleString();
    }

    function fmtFloatShort(v, digits) {
      const n = Number(v);
      if (!Number.isFinite(n)) return '—';
      const d = (digits != null && digits !== undefined) ? digits : 4;
      return n.toFixed(d);
    }

    function pctDisplay(v) {
      if (v == null || v === undefined || Number.isNaN(Number(v))) return '—';
      const n = Number(v);
      return (Math.round(n * 10) / 10).toFixed(1) + '%';
    }

    function tradeWinDisplay(e) {
      const bt = e.batch_trades_count;
      const btN = bt != null ? Number(bt) : 0;
      const pct = (btN > 0 && e.batch_trade_win_pct != null && e.batch_trade_win_pct !== undefined)
        ? e.batch_trade_win_pct
        : e.avg_trade_win_pct;
      const nTr = btN > 0 ? btN : (e.trade_win_rate_n != null ? Number(e.trade_win_rate_n) : 0);
      const p = pctDisplay(pct);
      if (nTr > 0 && p !== '—') {
        return p + ' <span style="color:#6c757d">(' + nTr + ')</span>';
      }
      return p;
    }

    function learningStatusChip(ls) {
      const s = (ls != null && ls !== undefined) ? String(ls) : '';
      if (s === 'learning_active') {
        return '<span class="chip-learn-yes" title="learning_active">ACTIVE</span>';
      }
      if (s === 'execution_only') {
        return '<span class="chip-learn-no" title="execution_only">exec</span>';
      }
      return '<span class="chip-learn-no">—</span>';
    }

    function workUnitsCell(e) {
      const w = e.work_units_v1;
      if (w != null && String(w).trim()) {
        const t = String(w);
        return escapeHtml(t.length > 72 ? t.slice(0, 70) + '…' : t);
      }
      const proc = e.total_processed;
      const tot = e.total_scenarios;
      if (proc != null || tot != null) {
        return escapeHtml(String(proc != null ? proc : '—') + ' / ' + String(tot != null ? tot : '—') + ' scen');
      }
      return '—';
    }

    function updateScorecardLearningSummaryFromRow(row) {
      const wrap = document.getElementById('scorecardLearningSummary');
      const body = document.getElementById('scorecardLearningSummaryBody');
      if (!wrap || !body) return;
      const lines = row && row.operator_learning_table_summary_v1;
      if (!row || !Array.isArray(lines) || !lines.length) {
        wrap.hidden = true;
        return;
      }
      wrap.hidden = false;
      const active = row.learning_status === 'learning_active';
      wrap.classList.toggle('exec-only', !active);
      body.innerHTML = lines.map(function (ln) {
        return '<p class="sls-line">' + escapeHtml(String(ln)) + '</p>';
      }).join('');
    }

    function updateLastBatchRunLine(bt) {
      const el = document.getElementById('lastBatchRunLine');
      if (!el || !bt) return;
      const proc = (bt.total_processed != null) ? bt.total_processed : '—';
      const tot = (bt.total_scenarios != null) ? bt.total_scenarios : '—';
      const ro = bt.run_ok_pct;
      const rw = bt.referee_win_pct;
      const atw = bt.avg_trade_win_pct;
      let pctBit = '';
      if (ro != null && ro !== undefined && !Number.isNaN(Number(ro))) {
        pctBit += ' · run OK ' + (Math.round(Number(ro) * 10) / 10).toFixed(1) + '%';
      }
      if (rw != null && rw !== undefined && !Number.isNaN(Number(rw))) {
        pctBit += ' · session WIN ' + (Math.round(Number(rw) * 10) / 10).toFixed(1) + '%';
      }
      const btc = bt.batch_trades_count;
      if (btc != null && Number(btc) > 0 && bt.batch_trade_win_pct != null) {
        pctBit += ' · trade win (batch) ' + pctDisplay(bt.batch_trade_win_pct) + ' on ' + btc + ' trades';
      } else if (atw != null && atw !== undefined && !Number.isNaN(Number(atw))) {
        pctBit += ' · trade win (mean) ' + pctDisplay(atw) +
          (bt.trade_win_rate_n != null ? ' (n=' + bt.trade_win_rate_n + ' scen)' : '');
      }
      const bmj = bt.batch_sessions_judged;
      if (bmj != null && Number(bmj) > 0 && rw != null) {
        pctBit += ' · sessions judged ' + bmj;
      }
      const ls0 = bt.operator_learning_table_summary_v1;
      let learn0 = '';
      if (Array.isArray(ls0) && ls0.length) {
        learn0 = ' · ' + ls0[0];
      }
      el.textContent = 'Last completed batch: start ' + (bt.started_at_utc || '—') +
        ' → end ' + (bt.ended_at_utc || '—') + ' · duration ' + formatDurationSec(bt.duration_sec) +
        ' · rows ' + proc + ' / planned ' + tot + pctBit + learn0;
    }

    let selectedScorecardJobId = null;

    function fileLink(jobId, scenarioId, kind) {
      const q = 'job_id=' + encodeURIComponent(jobId) + '&scenario_id=' + encodeURIComponent(scenarioId) + '&kind=' + encodeURIComponent(kind);
      return '/api/batch-scenario-file?' + q;
    }

    async function loadBatchDrill(jobId) {
      const panel = document.getElementById('batchDrillPanel');
      if (!panel) return;
      panel.classList.add('visible');
      panel.innerHTML = '<p>Loading batch…</p>';
      try {
        const r = await fetch('/api/batch-detail?job_id=' + encodeURIComponent(jobId));
        const j = await r.json();
        if (!r.ok || !j.ok) {
          panel.innerHTML = '<p class="err">' + escapeHtml(j.error || 'Failed to load batch') + '</p>';
          return;
        }
        const sc = j.scorecard || {};
        const csvHref = '/api/batch-detail.csv?job_id=' + encodeURIComponent(jobId);
        let meta = '<h3>Batch detail</h3><div class="batch-drill-meta">';
        meta += '<strong>job_id</strong> <code>' + escapeHtml(String(sc.job_id || '')) + '</code><br/>';
        meta += '<strong>started</strong> ' + escapeHtml(String(sc.started_at_utc || '—')) +
          ' → <strong>ended</strong> ' + escapeHtml(String(sc.ended_at_utc || '—')) +
          ' · <strong>duration</strong> ' + escapeHtml(formatDurationSec(sc.duration_sec)) + '<br/>';
        meta += '<strong>scenarios</strong> ' + escapeHtml(String(sc.total_processed != null ? sc.total_processed : '—')) +
          ' / ' + escapeHtml(String(sc.total_scenarios != null ? sc.total_scenarios : '—')) +
          ' · <strong>ok</strong> ' + escapeHtml(String(sc.ok_count != null ? sc.ok_count : '—')) +
          ' · <strong>failed</strong> ' + escapeHtml(String(sc.failed_count != null ? sc.failed_count : '—')) +
          ' · <strong>workers</strong> ' + escapeHtml(String(sc.workers_used != null ? sc.workers_used : '—')) +
          ' · <strong>status</strong> ' + escapeHtml(String(sc.status || '—')) + '<br/>';
        meta += '<strong>session_log_batch_dir</strong> ' + escapeHtml(String(sc.session_log_batch_dir || '(none)')) + '<br/>';
        meta += '<a href="' + csvHref + '">Download this batch (CSV, scenarios)</a>';
        meta += '</div>';
        const la = sc.learning_audit_v1;
        if (la && typeof la === 'object') {
          meta += '<h4>learning_audit_v1</h4><pre class="drill-pre">' +
            escapeHtml(JSON.stringify(la, null, 2)) + '</pre>';
        }
        const oba = sc.operator_batch_audit;
        if (oba && typeof oba === 'object' && Object.keys(oba).length) {
          meta += '<h4>operator_batch_audit</h4><pre class="drill-pre">' +
            escapeHtml(JSON.stringify(oba, null, 2)) + '</pre>';
        }
        const lba = sc.learning_batch_audit_v1;
        if (lba && typeof lba === 'object') {
          meta += '<h4>learning_batch_audit_v1</h4><pre class="drill-pre">' +
            escapeHtml(JSON.stringify(lba, null, 2)) + '</pre>';
        }
        if (j.scenario_list_error) {
          meta += '<p style="color:#b7772c">' + escapeHtml(j.scenario_list_error) + '</p>';
        }
        const scenarios = j.scenarios || [];
        if (!scenarios.length) {
          panel.innerHTML = meta + '<p>No scenario rows (session logs missing or empty folder).</p>';
          return;
        }
        let tbl = '<table class="drill-scenario-table"><thead><tr>' +
          '<th>scenario</th><th>session</th><th>memory</th><th>Groundhog</th><th>reports</th>' +
          '</tr></thead><tbody>';
        for (const s of scenarios) {
          const sid = String(s.scenario_id != null ? s.scenario_id : '');
          const mem = s.memory_applied
            ? '<span class="mem-pill mem-yes">yes</span>'
            : '<span class="mem-pill mem-no">no</span>';
          const gh = (s.groundhog_mode === 'active')
            ? '<span class="mem-pill gh-on">active</span>'
            : '<span class="mem-pill gh-off">inactive</span>';
          const rs = s.referee_session != null ? String(s.referee_session) : '—';
          tbl += '<tr><td><code>' + escapeHtml(sid) + '</code></td>' +
            '<td>' + escapeHtml(rs) + '</td>' +
            '<td>' + mem + '</td>' +
            '<td>' + gh + '</td>' +
            '<td>' +
            '<a href="' + fileLink(jobId, sid, 'human') + '" target="_blank" rel="noopener">HUMAN</a> · ' +
            '<a href="' + fileLink(jobId, sid, 'json') + '" target="_blank" rel="noopener">JSON</a>' +
            '</td></tr>';
        }
        tbl += '</tbody></table>';
        panel.innerHTML = meta + tbl;
      } catch (err) {
        panel.innerHTML = '<p class="err">' + escapeHtml(friendlyFetchError(err)) + '</p>';
      }
    }

    async function refreshScorecardHistory() {
      const tbody = document.getElementById('scorecardHistoryTbody');
      const hint = document.getElementById('scorecardPathHint');
      const csvLink = document.getElementById('scorecardCsvLink');
      if (!tbody) return;
      tbody.innerHTML = '';
      try {
        const r = await fetch('/api/batch-scorecard?limit=15');
        const j = await r.json();
        if (!r.ok) {
          if (hint) hint.textContent = 'Could not load scorecard history.';
          return;
        }
        if (hint && j.path) {
          hint.textContent = 'Persisted at: ' + j.path + ' (append-only JSONL; set PATTERN_GAME_MEMORY_ROOT for tmpfs)';
        }
        if (csvLink) {
          csvLink.href = '/api/batch-scorecard.csv?limit=50';
        }
        const rows = j.entries || [];
        if (rows.length) {
          updateScorecardLearningSummaryFromRow(rows[0]);
        } else {
          updateScorecardLearningSummaryFromRow(null);
        }
        if (!rows.length) {
          const tr = document.createElement('tr');
          tr.innerHTML = '<td colspan="33" style="color:#8b98a5">No batches logged yet.</td>';
          tbody.appendChild(tr);
          return;
        }
        for (const e of rows) {
          const tr = document.createElement('tr');
          tr.className = 'scorecard-row';
          const jid = (e.job_id != null && e.job_id !== undefined) ? String(e.job_id) : '';
          tr.setAttribute('data-job-id', jid);
          if (selectedScorecardJobId && jid === selectedScorecardJobId) {
            tr.classList.add('selected');
          }
          const st = e.status === 'done'
            ? '<span class="st-ok">done</span>'
            : '<span class="st-err">' + escapeHtml(e.status || '—') + '</span>';
          const dur = (e.duration_sec != null) ? formatDurationSec(e.duration_sec) : '—';
          const memY = (e.memory_used === true || e.memory_used === 'yes' || e.memory_used === 1);
          const memCell = (e.memory_used != null && e.memory_used !== '')
            ? (memY ? '<span title="memory_used">Y</span>' : '<span title="memory_used">N</span>')
            : '—';
          tr.innerHTML =
            '<td title="' + escapeHtml(jid) + '"><code style="font-size:0.68rem">' + escapeHtml(jid ? (jid.length > 14 ? jid.slice(0, 12) + '…' : jid) : '—') + '</code></td>' +
            '<td>' + escapeHtml(e.started_at_utc || '—') + '</td>' +
            '<td>' + escapeHtml(e.ended_at_utc || '—') + '</td>' +
            '<td>' + escapeHtml(dur) + '</td>' +
            '<td title="' + escapeHtml(e.work_units_v1 != null ? String(e.work_units_v1) : '') + '">' + workUnitsCell(e) + '</td>' +
            '<td>' + learningStatusChip(e.learning_status) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.decision_windows_total)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.bars_processed)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.candidate_count)) + '</td>' +
            '<td>' + escapeHtml(e.selected_candidate_id != null ? String(e.selected_candidate_id) : '—') + '</td>' +
            '<td>' + escapeHtml(e.winner_vs_control_delta != null ? String(e.winner_vs_control_delta) : '—') + '</td>' +
            '<td>' + memCell + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.memory_records_loaded)) + '</td>' +
            '<td>' + escapeHtml(e.groundhog_status != null ? String(e.groundhog_status) : '—') + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.recall_attempts)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.recall_matches)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.recall_bias_applied)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.signal_bias_applied_count)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.suppressed_modules_count)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.trade_entries_total)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.trade_exits_total)) + '</td>' +
            '<td>' + tradeWinDisplay(e) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.batch_trades_count)) + '</td>' +
            '<td>' + escapeHtml(fmtFloatShort(e.expectancy_per_trade, 4)) + '</td>' +
            '<td>' + escapeHtml(fmtFloatShort(e.exit_efficiency, 4)) + '</td>' +
            '<td>' + escapeHtml(fmtFloatShort(e.win_loss_size_ratio, 4)) + '</td>' +
            '<td title="referee session WIN % (denominator = #Sess)">' + escapeHtml(pctDisplay(e.referee_win_pct)) + '</td>' +
            '<td>' + escapeHtml(fmtIntCommas(e.batch_sessions_judged)) + '</td>' +
            '<td>' + escapeHtml(pctDisplay(e.run_ok_pct)) + '</td>' +
            '<td>' + escapeHtml(e.ok_count != null ? String(e.ok_count) : '—') + '</td>' +
            '<td>' + escapeHtml(e.failed_count != null ? String(e.failed_count) : '—') + '</td>' +
            '<td>' + escapeHtml(e.workers_used != null ? String(e.workers_used) : '—') + '</td>' +
            '<td>' + st + '</td>';
          tr.addEventListener('click', () => {
            document.querySelectorAll('#scorecardHistoryTbody tr.scorecard-row').forEach(function (x) {
              x.classList.remove('selected');
            });
            tr.classList.add('selected');
            selectedScorecardJobId = jid;
            if (jid) loadBatchDrill(jid);
          });
          tbody.appendChild(tr);
        }
      } catch (err) {
        if (hint) hint.textContent = 'Scorecard history: ' + friendlyFetchError(err);
      }
    }

    const RESET_LEARNING_CONFIRM_PHRASE = 'RESET_PATTERN_GAME_LEARNING';
    const clearScorecardBtn = document.getElementById('clearScorecardBtn');
    if (clearScorecardBtn) {
      clearScorecardBtn.onclick = async () => {
        if (!window.confirm(
          'Clear scorecard and start a new experiment?\nLearning state will be preserved.'
        )) {
          return;
        }
        try {
          const r = await fetch('/api/batch-scorecard/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: true }),
          });
          const j = await r.json();
          if (!r.ok || !j.ok) {
            await show(null, null, j.error || ('Clear failed: ' + r.status));
            return;
          }
          selectedScorecardJobId = null;
          const drill = document.getElementById('batchDrillPanel');
          if (drill) drill.innerHTML = '';
          updateScorecardLearningSummaryFromRow(null);
          const lr = document.getElementById('lastBatchRunLine');
          if (lr) {
            lr.textContent = 'Last completed batch: — (scorecard file cleared; engine memory and bundles unchanged)';
          }
          await refreshScorecardHistory();
        } catch (e) {
          await show(null, null, friendlyFetchError(e));
        }
      };
    }
    const resetLearningStateBtn = document.getElementById('resetLearningStateBtn');
    if (resetLearningStateBtn) {
      resetLearningStateBtn.onclick = async () => {
        if (!window.confirm(
          'DANGER: Reset Learning State will truncate the experience log and run memory JSONL, ' +
            'truncate context signature memory (recall / signature store), and delete the Groundhog bundle file if present.\n\n' +
            'It does NOT clear the scorecard table file or retrospective notes.\n\nContinue?'
        )) {
          return;
        }
        const typed = window.prompt(
          'Type the confirmation phrase exactly (case-sensitive):\n' + RESET_LEARNING_CONFIRM_PHRASE
        );
        if (typed !== RESET_LEARNING_CONFIRM_PHRASE) {
          if (typed !== null) window.alert('Confirmation mismatch — nothing was changed.');
          return;
        }
        try {
          const r = await fetch('/api/pattern-game/reset-learning', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: RESET_LEARNING_CONFIRM_PHRASE }),
          });
          const j = await r.json();
          if (!r.ok || !j.ok) {
            await show(null, null, j.error || JSON.stringify(j.errors || j));
            return;
          }
          await show(null, j, null);
          if (typeof refreshGroundhog === 'function') refreshGroundhog();
        } catch (e) {
          await show(null, null, friendlyFetchError(e));
        }
      };
    }

    function renderPolicyOutcomePanel(data) {
      const panel = document.getElementById('policyOutcomePanel');
      const tbody = document.getElementById('policyOutcomeTbody');
      if (!panel || !tbody) return;
      tbody.innerHTML = '';
      let rows = [];
      if (data && Array.isArray(data.results)) {
        rows = data.results;
      }
      if (!rows.length) {
        panel.hidden = true;
        return;
      }
      panel.hidden = false;
      for (const r of rows) {
        const pc = r.policy_contract || {};
        const summ = r.summary || {};
        const sigs = (pc.signal_modules && pc.signal_modules.length) ? pc.signal_modules.join(', ') : '—';
        const wr = (summ.win_rate != null && summ.win_rate !== undefined)
          ? (Math.round(Number(summ.win_rate) * 1000) / 10 + '%')
          : '—';
        const trades = (summ.trades != null && summ.trades !== undefined) ? String(summ.trades) : '—';
        const pnl = summ.cumulative_pnl;
        let outc = r.referee_session;
        if (!outc) {
          outc = r.ok ? 'LOSS' : 'ERROR';
        }
        const tagClass = outc === 'WIN' ? 'tag-win' : (outc === 'LOSS' ? 'tag-loss' : 'tag-err');
        const sid = r.scenario_id != null ? String(r.scenario_id) : ('—');
        const strat = pc.strategy_id ? String(pc.strategy_id) : '—';
        const fus = pc.fusion_module ? String(pc.fusion_module) : '—';
        const tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + escapeHtml(sid) + '</td>' +
          '<td><span class="' + tagClass + '">' + escapeHtml(outc) + '</span></td>' +
          '<td>' + escapeHtml(formatUsdPlain(pnl)) + '</td>' +
          '<td>' + escapeHtml(wr) + '</td>' +
          '<td>' + escapeHtml(trades) + '</td>' +
          '<td class="signals-cell">' + escapeHtml(sigs) + '</td>' +
          '<td>' + escapeHtml(fus) + '</td>' +
          '<td>' + escapeHtml(strat.length > 56 ? strat.slice(0, 54) + '…' : strat) + '</td>';
        tbody.appendChild(tr);
      }
    }

    async function show(el, data, err) {
      const pre = document.getElementById('out');
      const hdr = document.querySelector('.pg-header-evidence');
      if (hdr) hdr.open = true;
      if (!pre) {
        console.error('pattern game UI: missing #out element');
        return;
      }
      if (err) {
        pre.innerHTML = '<span class="err">' + escapeHtml(String(err)) + '</span>';
        renderPolicyOutcomePanel(null);
        setEvidenceTab('json');
        return;
      }
      pre.textContent = JSON.stringify(data, null, 2);
      renderPolicyOutcomePanel(data);
      if (data && data.batch_timing) updateLastBatchRunLine(data.batch_timing);
      setEvidenceTab('outcomes');
    }

    function openGameControlsPanel() {
      const p = document.querySelector('details.pg-panel-controls');
      if (p) p.open = true;
    }
    function scrollRunStatusIntoView() {
      const el = document.getElementById('statusLine') || document.getElementById('progressWrap');
      if (el && typeof el.scrollIntoView === 'function') {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }

    function formatUsd(n) {
      const x = Number(n);
      if (Number.isNaN(x)) return '$—';
      const abs = Math.abs(x);
      const s = (x < 0 ? '-' : '') + '$' + abs.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      return s;
    }

    function updatePnlStrip(pnl) {
      if (!pnl || typeof pnl.ending_equity_usd !== 'number') return;
      const end = pnl.ending_equity_usd;
      const delta = pnl.batch_total_pnl_usd;
      document.getElementById('pnlEnding').textContent = formatUsd(end);
      const dEl = document.getElementById('pnlDelta');
      if (Math.abs(delta) < 1e-9) {
        dEl.textContent = '$0.00 vs baseline';
        dEl.className = 'pnl-delta neutral';
      } else {
        dEl.textContent = (delta >= 0 ? '+' : '−') + formatUsd(Math.abs(delta)) + ' vs baseline';
        dEl.className = 'pnl-delta ' + (delta >= 0 ? 'up' : 'down');
      }
      const lo = 0, hi = 2000;
      const pct = Math.max(0, Math.min(100, ((end - lo) / (hi - lo)) * 100));
      const m = document.getElementById('pnlMarker');
      m.style.left = pct + '%';
      const baselinePct = ((STARTING_EQUITY - lo) / (hi - lo)) * 100;
      const fill = document.getElementById('pnlFill');
      const left = Math.min(baselinePct, pct);
      const width = Math.abs(pct - baselinePct);
      fill.style.left = left + '%';
      fill.style.width = width + '%';
      fill.className = 'pnl-fill ' + (end >= STARTING_EQUITY ? 'up' : 'down');
      document.getElementById('pnlStrip').title = (pnl.note || '') + ' Ending equity shown on 0–$2k track (clamp).';
    }

    function resetPnlStrip() {
      document.getElementById('pnlEnding').textContent = formatUsd(STARTING_EQUITY);
      document.getElementById('pnlDelta').textContent = '— run a batch —';
      document.getElementById('pnlDelta').className = 'pnl-delta neutral';
      document.getElementById('pnlMarker').style.left = Math.max(0, Math.min(100, (STARTING_EQUITY / 2000) * 100)) + '%';
      const f = document.getElementById('pnlFill');
      f.style.left = '50%';
      f.style.width = '0';
      f.className = 'pnl-fill up';
    }
    document.getElementById('pnlBaselineLabel').textContent = formatUsd(STARTING_EQUITY);
    resetPnlStrip();

    function friendlyFetchError(e) {
      const m = (e && (e.message || String(e))) || '';
      const isNet =
        (e && e.name === 'TypeError' && (m.indexOf('NetworkError') >= 0 || m.indexOf('Failed to fetch') >= 0 || m.indexOf('Load failed') >= 0)) ||
        (e && e.name === 'AbortError');
      if (isNet && e && e.name !== 'AbortError') {
        return 'Connection lost while talking to the server. Common causes: the app was restarted or killed mid-run, Wi‑Fi/VPN blip, or the page URL changed. Hard-refresh this page (reload) and click Run again.';
      }
      return String(e);
    }

    function clearBatchConcurrencyBanner() {
      const b = document.getElementById('batchConcurrencyBanner');
      if (b) {
        b.innerHTML = '';
        b.classList.remove('visible');
      }
    }

    function showBatchConcurrencyBanner(total, workers, mode) {
      const b = document.getElementById('batchConcurrencyBanner');
      if (!b) return;
      if (mode === 'clear' || total == null || total === 0) {
        clearBatchConcurrencyBanner();
        return;
      }
      const w = (workers != null && workers !== undefined) ? String(workers) : '?';
      const t = Math.max(0, parseInt(String(total), 10) || 0);
      const wn = parseInt(w, 10);
      const eff = (!Number.isNaN(wn) && wn > 0 && t > 0) ? Math.min(t, wn) : '—';
      b.classList.add('visible');
      if (mode === 'done') {
        b.innerHTML =
          '<strong>Batch finished</strong> — <strong>' + t + '</strong> scenario(s) completed · parallel processes used: <strong>' +
          w + '</strong> <span style="color:#8b98a5;font-weight:400">(min of scenario count and slider — one scenario always uses one process)</span>. Result is below.';
        return;
      }
      if (mode === 'error') {
        b.innerHTML = '<strong>Batch stopped</strong> — see Result for details.';
        return;
      }
      let oneWarn = '';
      if (t === 1) {
        oneWarn =
          '<span class="warn"> Only one scenario in the array — one replay at a time. Add more scenarios to the JSON (or use &quot;Suggest next hunters&quot;) to use more cores.</span>';
      }
      b.innerHTML =
        '<strong>Parallelism</strong> — <strong>' + t + '</strong> scenario(s) in this batch · up to <strong>' + w +
        '</strong> parallel process(es) at once (at most <strong>' + eff + '</strong> replays run in parallel until one finishes).' +
        oneWarn;
    }

    const suggestHuntersBtn = document.getElementById('suggestHuntersBtn');
    if (suggestHuntersBtn) {
      suggestHuntersBtn.onclick = async () => {
        const hint = document.getElementById('hunterSuggestHint');
        const ta = document.getElementById('scenarios');
        if (hint) hint.textContent = 'Loading memory-aware suggestion…';
        try {
          const r = await fetch('/api/suggest-hunters');
          const j = await r.json();
          if (!r.ok || !j.ok) {
            if (hint) hint.textContent = j.error || 'Suggestion failed.';
            return;
          }
          ta.value = JSON.stringify(j.scenarios, null, 2);
          refreshWorkerEffectiveLine();
          const w = j.warnings || [];
          const short = w.length ? (w.join(' ')) : ('Ladder round ' + (j.ladder_round != null ? j.ladder_round : '?') +
            ', bias ' + (j.bias || '?') + '. Full rationale in API JSON.');
          if (hint) hint.textContent = short;
        } catch (e) {
          if (hint) hint.textContent = friendlyFetchError(e);
        }
      };
    }

    const chefAtrSweepBtn = document.getElementById('chefAtrSweepBtn');
    if (chefAtrSweepBtn) {
      chefAtrSweepBtn.onclick = async () => {
        const hint = document.getElementById('chefHint');
        const ta = document.getElementById('scenarios');
        const mpEl = document.getElementById('chefManifestPath');
        const mp = mpEl ? String(mpEl.value || '').trim() : '';
        if (hint) hint.textContent = 'Building catalog ATR sweep…';
        try {
          const r = await fetch('/api/catalog-batch-generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              mode: 'atr_sweep',
              manifest_path: mp,
              max_scenarios: 24,
            }),
          });
          const j = await r.json();
          if (!r.ok || !j.ok) {
            if (hint) hint.textContent = j.error || 'Chef batch failed.';
            return;
          }
          ta.value = JSON.stringify(j.scenarios, null, 2);
          refreshWorkerEffectiveLine();
          const w = j.warnings || [];
          const extra = w.length ? (' · ' + w.join(' ')) : '';
          if (hint) hint.textContent = 'Chef: ' + (j.count || (j.scenarios || []).length) +
            ' scenarios (ATR sweep).' + extra;
        } catch (e) {
          if (hint) hint.textContent = friendlyFetchError(e);
        }
      };
    }

    function setProgressUI(completed, total, subtext) {
      const fill = document.getElementById('progressFill');
      const sub = document.getElementById('progressSub');
      if (!fill || !sub || !progressWrap) return;
      const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
      fill.style.width = pct + '%';
      progressWrap.setAttribute('aria-valuenow', String(pct));
      if (subtext) sub.textContent = subtext;
      else sub.textContent = total > 0 ? ('Scenarios ' + completed + ' / ' + total + ' complete (replay is CPU-bound; each bar can take minutes).') : '';
    }

    /** Prefer API total; never default to 1 (that showed 0/1 for 15-scenario batches if total was missing). */
    function resolveScenarioBatchTotal(apiTotal, textareaValue) {
      const n = Number(apiTotal);
      if (Number.isFinite(n) && n >= 1) return n;
      try {
        const raw = JSON.parse(textareaValue);
        const arr = Array.isArray(raw) ? raw : (raw && Array.isArray(raw.scenarios) ? raw.scenarios : null);
        if (arr && arr.length >= 1) return arr.length;
      } catch (e) {}
      return 1;
    }

    function statusPollTotal(pj, fallbackTotal) {
      const n = Number(pj.total);
      if (Number.isFinite(n) && n >= 1) return n;
      return fallbackTotal;
    }

    document.getElementById('runBtn').onclick = async () => {
      const btn = document.getElementById('runBtn');
      btn.disabled = true;
      openGameControlsPanel();
      clearBatchConcurrencyBanner();
      hideLiveTelemetryPanel();
      const sn = document.getElementById('sessionLogNote');
      if (sn) sn.textContent = '';
      statusLine.textContent = 'Starting batch…';
      scrollRunStatusIntoView();
      document.getElementById('progressSub').textContent = '';
      setProgressUI(0, 0, '');
      progressWrap.classList.add('active');
      const t0 = Date.now();
      let runWorkersCap = null;
      try {
        let mw = parseInt(rangeEl.value, 10);
        if (isNaN(mw)) mw = null;
        if (mw !== null) {
          mw = Math.max(1, Math.min(mw, LIMITS.hard_cap_workers));
          rangeEl.value = String(mw);
          workersVal.textContent = String(mw);
        }
        const recipeId = document.getElementById('operatorRecipePick') ? document.getElementById('operatorRecipePick').value : 'custom';
        const scenariosTa = document.getElementById('scenarios') ? document.getElementById('scenarios').value : '';
        const wm = document.getElementById('evaluationWindowPick') ? document.getElementById('evaluationWindowPick').value : '12';
        let customM = null;
        if (wm === 'custom') {
          const cEl = document.getElementById('evaluationWindowCustomMonths');
          customM = cEl ? parseInt(cEl.value, 10) : null;
          if (!customM || customM < 1) {
            await show(null, null, 'Evaluation window is Custom — enter a valid number of months (1–600).');
            statusLine.textContent = 'Set custom months before run.';
            btn.disabled = false;
            return;
          }
        }
        if (recipeId === 'custom') {
          if (!scenariosTa || !scenariosTa.trim()) {
            await show(null, null, 'Recipe is Custom — paste valid scenario JSON under Advanced → Custom scenario.');
            statusLine.textContent = 'Missing JSON for Custom recipe.';
            btn.disabled = false;
            return;
          }
          try {
            const p = JSON.parse(scenariosTa.trim());
            const arr = Array.isArray(p) ? p : (p && Array.isArray(p.scenarios) ? p.scenarios : null);
            if (!arr || arr.length < 1) throw new Error('need a non-empty scenario array');
          } catch (ve) {
            await show(null, null, 'Invalid JSON: ' + String(ve && ve.message ? ve.message : ve));
            statusLine.textContent = 'JSON parse failed.';
            btn.disabled = false;
            return;
          }
        }
        const doLogEl = document.getElementById('doLog');
        const body = {
          scenarios_json: recipeId === 'custom' ? scenariosTa : '[]',
          max_workers: mw,
          log_path: !!(doLogEl && doLogEl.checked),
          operator_recipe_id: recipeId,
          evaluation_window_mode: wm,
          evaluation_window_custom_months: customM
        };
        const startR = await fetch('/api/run-parallel/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const startRaw = await startR.text();
        let startJ;
        try {
          startJ = startRaw ? JSON.parse(startRaw) : {};
        } catch (pe) {
          await show(
            null,
            null,
            'Server returned non-JSON from /api/run-parallel/start (HTTP ' + startR.status + '): ' + String(pe && pe.message ? pe.message : pe) + ' — body: ' + (startRaw || '').slice(0, 1200)
          );
          statusLine.textContent = 'Start request failed — see Result (Results workspace).';
          return;
        }
        if (!startR.ok) {
          await show(null, null, startJ.error || JSON.stringify(startJ));
          statusLine.textContent = 'Validation failed — see Result.';
          return;
        }
        const jobId = startJ.job_id;
        const total = resolveScenarioBatchTotal(startJ.total, scenariosTa);
        runWorkersCap = startJ.workers_used != null ? startJ.workers_used : null;
        const ltw = document.getElementById('liveTelemetryWrap');
        const ltp = document.getElementById('liveTelemetryPanel');
        if (ltw && ltp) {
          ltw.hidden = false;
          ltp.textContent = 'Live telemetry — waiting for worker snapshots…';
        }
        showBatchConcurrencyBanner(total, runWorkersCap, 'run');
        statusLine.textContent =
          'Running — ' + total + ' scenario(s) · up to ' + (runWorkersCap != null ? runWorkersCap : '?') +
          ' parallel process(es) (min of batch size and slider) · updates every 1.5s below.';
        setProgressUI(0, total, 'Queued — up to ' + (runWorkersCap != null ? runWorkersCap : '?') + ' process(es) · waiting for first replay to finish…');

        const pollOnce = async () => {
          const pr = await fetch('/api/run-parallel/status/' + jobId);
          const prText = await pr.text();
          let pj;
          try {
            pj = prText ? JSON.parse(prText) : {};
          } catch (e) {
            throw new Error(
              'Status poll returned non-JSON (HTTP ' + pr.status + '): ' + String(e && e.message ? e.message : e) +
                ' — ' + (prText || '').slice(0, 500)
            );
          }
          if (!pr.ok) {
            throw new Error(pj.error || 'status failed');
          }
          const elapsed = Math.floor((Date.now() - t0) / 1000);
          const elapsedStr = elapsed >= 60 ? (Math.floor(elapsed / 60) + 'm ' + (elapsed % 60) + 's') : (elapsed + 's');
          const wCap = pj.workers_used != null ? pj.workers_used : runWorkersCap;
          if (pj.status === 'running') {
            const c = pj.completed || 0;
            const t = statusPollTotal(pj, total);
            const lm = pj.last_message || '';
            const sub = (lm ? (lm + ' · ') : '') + 'up to ' + (wCap != null ? wCap : '?') + ' parallel · ' + elapsedStr;
            setProgressUI(c, t, sub);
            statusLine.textContent =
              'Running — ' + c + '/' + t + ' scenario(s) finished · up to ' + (wCap != null ? wCap : '?') +
              ' parallel process(es) · ' + elapsedStr + ' elapsed';
            renderLiveTelemetryPanel(pj, {
              elapsedSec: elapsed,
              recipeLabel: recipeLabelFromDom(),
              windowLabel: evaluationWindowLabelFromDom(),
            });
            return false;
          }
          if (pj.status === 'error') {
            hideLiveTelemetryPanel();
            showBatchConcurrencyBanner(total, wCap, 'error');
            if (pj.batch_timing) updateLastBatchRunLine(pj.batch_timing);
            refreshScorecardHistory();
            await show(null, null, pj.error || 'Job failed');
            statusLine.textContent = 'Failed — see Result.';
            setProgressUI(pj.completed || 0, statusPollTotal(pj, total), pj.error || '');
            return true;
          }
          if (pj.status === 'done') {
            hideLiveTelemetryPanel();
            const tDone = statusPollTotal(pj, total);
            const cDone = (pj.completed != null && pj.completed >= 0) ? pj.completed : tDone;
            setProgressUI(cDone, tDone, '');
            if (pj.result) {
              const j = pj.result;
              const doneN = j.ran != null ? j.ran : tDone;
              const doneW = j.workers_used != null ? j.workers_used : wCap;
              showBatchConcurrencyBanner(doneN, doneW, 'done');
              setProgressUI(doneN, doneN, 'All ' + doneN + ' scenario(s) finished · parallel processes used: ' + (doneW != null ? doneW : '?') + ' · ' + elapsedStr);
              if (j.pnl_summary) { updatePnlStrip(j.pnl_summary); }
              const sl = document.getElementById('sessionLogNote');
              if (sl) {
                sl.textContent = j.session_log_batch_dir
                  ? ('Session logs (human-readable): ' + j.session_log_batch_dir)
                  : '';
              }
              await show(null, j, null);
              refreshScorecardHistory();
              statusLine.textContent =
                'Finished — ' + doneN + ' scenario(s) · parallel processes used: ' + (doneW != null ? doneW : '?') +
                ' (not the same as the slider when you only have one scenario) · see Result below.';
            } else {
              showBatchConcurrencyBanner(tDone, wCap, 'done');
              setProgressUI(cDone, tDone, 'Batch marked done — full JSON not in this response; see scorecard below.');
              refreshScorecardHistory();
              statusLine.textContent =
                'Finished — ' + cDone + '/' + tDone + ' (details in scorecard; hard-refresh if Result is empty).';
            }
            return true;
          }
          /* Missing or unknown status: keep polling (treating as non-terminal avoids silent no-op). */
          return false;
        };

        const deadline = Date.now() + RUN_TIMEOUT_MS;
        while (Date.now() < deadline) {
          const done = await pollOnce();
          if (done) break;
          await new Promise((r) => setTimeout(r, 1500));
        }
        if (Date.now() >= deadline) {
          await show(null, null, 'Timed out after ' + (RUN_TIMEOUT_MS / 60000) + ' minutes — job may still be running on the server; open /api/run-parallel/status/<job_id> or check logs.');
          statusLine.textContent = 'Client timeout — check server or logs.';
        }
      } catch (e) {
        if (runWorkersCap != null) {
          showBatchConcurrencyBanner(1, 1, 'error');
        } else {
          clearBatchConcurrencyBanner();
        }
        await show(null, null, friendlyFetchError(e));
        statusLine.textContent = 'Stopped or failed — see Result.';
      } finally {
        hideLiveTelemetryPanel();
        progressWrap.classList.remove('active');
        btn.disabled = false;
        syncBannerRunFromStatusLine();
      }
    };

    function applyEvaluationWindowCapFromPayload(h) {
      const maxM = h && typeof h.max_evaluation_window_calendar_months === 'number' ? h.max_evaluation_window_calendar_months : null;
      const ew = document.getElementById('evaluationWindowPick');
      if (!ew) return;
      if (maxM == null || maxM < 1) {
        Array.from(ew.options).forEach(function (opt) { opt.disabled = false; });
        ew.title = '';
        const cm0 = document.getElementById('evaluationWindowCustomMonths');
        if (cm0) cm0.removeAttribute('max');
        return;
      }
      const spanD = h && h.replay_tape_span_days_approx;
      const spanStr = (typeof spanD === 'number' && !Number.isNaN(spanD)) ? ('~' + Math.round(spanD) + 'd tape → max ' + maxM + ' mo') : ('max ' + maxM + ' mo (data limit)');
      Array.from(ew.options).forEach(function (opt) {
        const v = opt.value;
        if (v === 'custom') {
          opt.disabled = false;
          return;
        }
        const mo = parseInt(v, 10);
        opt.disabled = !Number.isFinite(mo) || mo > maxM;
      });
      ew.title = spanStr;
      const cm = document.getElementById('evaluationWindowCustomMonths');
      if (cm) {
        cm.max = String(maxM);
        if (!cm.min) cm.min = '1';
      }
      const cur = ew.value;
      if (cur !== 'custom') {
        const mo = parseInt(cur, 10);
        if (Number.isFinite(mo) && mo > maxM) {
          let pick = 'custom';
          if (maxM >= 24) pick = '24';
          else if (maxM >= 18) pick = '18';
          else if (maxM >= 12) pick = '12';
          ew.value = pick;
          if (pick === 'custom' && cm) cm.value = String(maxM);
          if (typeof syncCustomMonthsVisibility === 'function') syncCustomMonthsVisibility();
          if (typeof refreshStructuredMetadata === 'function') void refreshStructuredMetadata();
        }
      } else if (cm) {
        const c = parseInt(cm.value, 10);
        if (Number.isFinite(c) && c > maxM) {
          cm.value = String(maxM);
          if (typeof refreshStructuredMetadata === 'function') void refreshStructuredMetadata();
        }
      }
    }

    fetch('/api/capabilities').then(function (r) { return r.json(); }).then(function (c) {
      applyEvaluationWindowCapFromPayload(c);
    }).catch(function () {});

    async function refreshDataHealth() {
      const dot = document.getElementById('healthDot');
      const text = document.getElementById('healthText');
      const bannerV = document.getElementById('bannerFinancialV');
      try {
        const r = await fetch('/api/data-health');
        const j = await r.json();
        dot.className = 'status-dot ' + (j.overall_ok ? 'ok' : 'bad');
        dot.title = j.overall_ok ? 'Data OK' : 'Data issue — see text';
        if (bannerV) bannerV.textContent = j.overall_ok ? 'OK' : 'Issue';
        if (j.summary_line) {
          text.textContent = j.summary_line;
        } else if (j.error) {
          text.textContent = j.error;
        } else {
          text.textContent = 'Unknown status';
        }
        applyEvaluationWindowCapFromPayload(j);
      } catch (e) {
        dot.className = 'status-dot bad';
        dot.title = 'Health request failed';
        if (bannerV) bannerV.textContent = '—';
        text.textContent = 'Health check failed: ' + friendlyFetchError(e);
      }
    }
    refreshDataHealth();
    setInterval(refreshDataHealth, 45000);

    async function refreshGroundhog() {
      const el = document.getElementById('groundhogText');
      const gv = document.getElementById('groundhogV');
      if (!el) return;
      try {
        const r = await fetch('/api/groundhog-memory');
        const j = await r.json();
        if (!r.ok || !j.ok) {
          el.textContent = 'unavailable';
          if (gv) gv.textContent = '—';
          return;
        }
        const en = j.env_enabled ? 'merge ON' : 'merge OFF (set PATTERN_GAME_GROUNDHOG_BUNDLE=1)';
        const ex = j.exists ? 'file exists' : 'no file yet (POST /api/groundhog-memory to promote)';
        const ap = j.bundle && j.bundle.apply
          ? ('ATR stop ' + j.bundle.apply.atr_stop_mult + ' / target ' + j.bundle.apply.atr_target_mult)
          : '—';
        el.textContent = en + ' · ' + ex + ' · ' + ap;
        if (gv) gv.textContent = j.env_enabled ? 'merge ON' : 'merge OFF';
      } catch (e) {
        el.textContent = 'could not load — ' + friendlyFetchError(e);
        if (gv) gv.textContent = '—';
      }
    }
    refreshGroundhog();
    setInterval(refreshGroundhog, 60000);

    function openModuleModal(m) {
      const d = document.getElementById('moduleDetailDialog');
      const t = document.getElementById('moduleModalTitle');
      const rr = document.getElementById('moduleModalRole');
      const b = document.getElementById('moduleModalBody');
      if (!d || !t || !b) return;
      t.textContent = m.title || m.label || m.id || 'Module';
      const roleMap = {
        ui: 'UI shell',
        core_replay: 'Core replay (Referee path)',
        evidence: 'Evidence / audit (does not change next run by itself)',
        behavioral_memory: 'Behavioral memory (promoted bundle may merge into manifest)',
        interpretation: 'Interpretation / notes',
        ops_suggestion: 'Suggestion / planning (not Referee truth)',
        narrative: 'Narrative / reporting (not Referee scoring)',
      };
      const rn = m.role ? (roleMap[m.role] || m.role) : '';
      if (rr) rr.textContent = rn ? ('Category: ' + rn) : '';
      b.textContent = (m.body != null && String(m.body).trim()) ? String(m.body) : String(m.detail || '');
      if (d.showModal) d.showModal();
    }
    (function wireModuleModalClose() {
      const d = document.getElementById('moduleDetailDialog');
      const c = document.getElementById('moduleModalClose');
      if (c && d) {
        c.addEventListener('click', function () { if (d.close) d.close(); });
      }
      if (d) {
        d.addEventListener('click', function (ev) {
          if (ev.target === d && d.close) d.close();
        });
      }
    })();

    async function refreshModuleBoard() {
      const list = document.getElementById('moduleBoardList');
      const dot = document.getElementById('moduleBannerDot');
      const bv = document.getElementById('bannerModulesV');
      const bs = document.getElementById('bannerModulesS');
      function setModuleBanner(okCount, total, sub) {
        if (bv) bv.textContent = (total > 0) ? (okCount + '/' + total + ' passed') : '—';
        if (bs) bs.textContent = sub || '';
        if (dot) {
          if (!total) dot.className = 'status-dot';
          else if (okCount === total) dot.className = 'status-dot ok';
          else dot.className = 'status-dot bad';
        }
      }
      if (!list) return;
      try {
        const r = await fetch('/api/module-board');
        const j = await r.json();
        const errStyle = 'margin:0;color:rgba(247,241,230,0.75)';
        if (!r.ok || !j.ok) {
          list.innerHTML = '<p class="caps" style="' + errStyle + '">Could not load module board.</p>';
          setModuleBanner(0, 0, 'Module API unavailable');
          return;
        }
        const mods = j.modules || [];
        if (!mods.length) {
          list.innerHTML = '<p class="caps" style="' + errStyle + '">No modules.</p>';
          setModuleBanner(0, 0, 'No rows');
          return;
        }
        list.innerHTML = '';
        let okCount = 0;
        for (const m of mods) {
          if (m.ok) okCount++;
          const row = document.createElement('div');
          row.className = 'pg-status-item';
          row.setAttribute('role', 'button');
          row.setAttribute('tabindex', '0');
          const det = (m.detail != null) ? String(m.detail) : '';
          row.innerHTML =
            '<span class="status-dot ' + (m.ok ? 'ok' : 'bad') + '" title="' + escapeHtml(det.slice(0, 500)) + '"></span>' +
            '<div><div class="pg-status-name">' + escapeHtml(m.label || m.id || '—') + '</div>' +
            '<div class="pg-status-meta">' + escapeHtml(det.slice(0, 280)) + '</div></div>';
          row.addEventListener('click', function () { openModuleModal(m); });
          row.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
              ev.preventDefault();
              openModuleModal(m);
            }
          });
          list.appendChild(row);
        }
        const bad = mods.length - okCount;
        const sub = (bad === 0)
          ? 'All wiring checks passed'
          : (okCount + ' passed · ' + bad + ' not wired / not armed');
        setModuleBanner(okCount, mods.length, sub);
      } catch (e) {
        list.innerHTML = '<p class="caps" style="margin:0;color:rgba(247,241,230,0.75)">' + escapeHtml(friendlyFetchError(e)) + '</p>';
        setModuleBanner(0, 0, 'Fetch failed');
        if (dot) dot.className = 'status-dot bad';
      }
    }
    refreshModuleBoard();
    setInterval(refreshModuleBoard, 90000);

    async function refreshSearchSpaceEstimate() {
      const el = document.getElementById('searchSpaceStrip');
      if (!el) return;
      try {
        const w = parseInt(rangeEl.value, 10) || 1;
        const batchN = getEffectiveScenarioCount();
        const q = batchN > 0
          ? ('?batch_size=' + encodeURIComponent(batchN) + '&workers=' + encodeURIComponent(w))
          : ('?workers=' + encodeURIComponent(w));
        const r = await fetch('/api/search-space-estimate' + q);
        const j = await r.json();
        const m = j.catalog && j.catalog.signals_count;
        const sub = j.combinatorics && j.combinatorics.non_empty_signal_subsets_upper_bound;
        const bars = j.dataset && j.dataset.market_bars_5m_count;
        const rounds = j.workload_hints && j.workload_hints.parallel_rounds_ceil_batch_over_workers;
        const br = j.bar_replay_units;
        let line = '<strong>Search space</strong> — ';
        if (m != null && sub != null) {
          line += m + ' catalog signals → up to <strong>' + sub + '</strong> non-empty signal subsets (2^' + m + '−1; validation may disallow some). ';
        }
        if (bars != null) {
          line += '<strong>' + bars.toLocaleString() + '</strong> rows in <code>market_bars_5m</code>. ';
        } else if (j.dataset && j.dataset.error) {
          line += 'Bars: unavailable (' + String(j.dataset.error).slice(0, 120) + '). ';
        }
        if (batchN > 0 && rounds != null) {
          line += 'This batch: <strong>' + batchN + '</strong> scenario(s), <strong>' + w + '</strong> workers → ~<strong>' + rounds + '</strong> parallel round(s). ';
        } else {
          line += 'Pick a recipe (or Custom JSON) to see batch rounds; workers use slider (' + w + '). ';
        }
        if (br != null && batchN > 0) {
          line += 'Coarse bar steps ≈ ' + br.toLocaleString() + ' (scenarios×bars).';
        }
        el.innerHTML = line;
      } catch (e) {
        el.innerHTML = '<strong>Search space</strong> — could not load estimate. ' + friendlyFetchError(e);
      }
    }

    const operatorRecipePick = document.getElementById('operatorRecipePick');
    const evaluationWindowPick = document.getElementById('evaluationWindowPick');
    const evaluationWindowCustomMonths = document.getElementById('evaluationWindowCustomMonths');
    const customMonthsWrap = document.getElementById('customMonthsWrap');
    const examplesFilePick = document.getElementById('examplesFilePick');
    const scenariosEl = document.getElementById('scenarios');
    let PG_OPERATOR_RECIPES = [];
    let PG_POLICY_CATALOG = [];

    function recipeMeta(rid) {
      return PG_OPERATOR_RECIPES.find(function (x) { return x.recipe_id === rid; }) || null;
    }

    function syncCustomMonthsVisibility() {
      if (!customMonthsWrap || !evaluationWindowPick) return;
      customMonthsWrap.style.display = evaluationWindowPick.value === 'custom' ? '' : 'none';
    }

    function evaluationWindowLabel() {
      if (!evaluationWindowPick) return '—';
      const wm = evaluationWindowPick.value;
      if (wm === 'custom') {
        const cm = evaluationWindowCustomMonths ? parseInt(evaluationWindowCustomMonths.value, 10) : 0;
        return (cm && cm > 0) ? (String(cm) + ' months (custom)') : 'Custom months (set value)';
      }
      return wm + ' months';
    }

    function syncPolicyPickUi() {
      const multi = document.getElementById('policyMultiWrap');
      const ro = document.getElementById('policyReadonly');
      const pick = document.getElementById('policyPick');
      if (!multi || !ro || !pick) return;
      if (!PG_POLICY_CATALOG.length) {
        multi.style.display = 'none';
        ro.style.display = 'none';
        return;
      }
      if (PG_POLICY_CATALOG.length === 1) {
        multi.style.display = 'none';
        ro.style.display = 'block';
        ro.textContent = 'Policy: ' + (PG_POLICY_CATALOG[0].display_label || PG_POLICY_CATALOG[0].manifest_path);
      } else {
        ro.style.display = 'none';
        multi.style.display = 'block';
        pick.innerHTML = '';
        PG_POLICY_CATALOG.forEach(function (p) {
          const o = document.createElement('option');
          o.value = p.manifest_path;
          o.textContent = p.display_label || p.policy_id;
          pick.appendChild(o);
        });
      }
    }

    function policyLineForRunConfig() {
      if (PG_POLICY_CATALOG.length === 1) {
        return PG_POLICY_CATALOG[0].display_label || PG_POLICY_CATALOG[0].manifest_path;
      }
      const pick = document.getElementById('policyPick');
      const sel = pick && pick.selectedOptions && pick.selectedOptions[0];
      return sel ? sel.textContent : '—';
    }

    function updateRunConfigurationPanel() {
      const rr = document.getElementById('runConfigRecipe');
      const rp = document.getElementById('runConfigPolicy');
      const rw = document.getElementById('runConfigWindow');
      const rg = document.getElementById('runConfigGoalSummary');
      const rid = operatorRecipePick && operatorRecipePick.value;
      if (rr) rr.textContent = (operatorRecipePick && operatorRecipePick.selectedOptions[0])
        ? operatorRecipePick.selectedOptions[0].textContent : '—';
      if (rp) rp.textContent = policyLineForRunConfig();
      if (rw) rw.textContent = evaluationWindowLabel();
      if (!rg) return;
      if (!rid || rid === 'custom') {
        rg.textContent = 'Defined in your JSON (Advanced).';
      } else {
        const m = recipeMeta(rid);
        const gs = m && m.goal_summary;
        rg.textContent = gs && gs.title ? gs.title : '—';
      }
      const gTitle = document.getElementById('goalReadonlyTitle');
      const gMet = document.getElementById('goalReadonlyMetrics');
      const gCon = document.getElementById('goalReadonlyConstraints');
      const gNote = document.getElementById('goalReadonlyNote');
      if (rid === 'custom') {
        if (gTitle) gTitle.textContent = 'Custom scenario';
        if (gMet) gMet.textContent = 'Goal, manifest, and window must appear in your JSON (or rely on server merge for evaluation window from the control above).';
        if (gCon) gCon.textContent = '';
        if (gNote) gNote.textContent = 'Open Advanced → Custom scenario (JSON) to edit.';
      } else {
        const m = recipeMeta(rid);
        const gs = m && m.goal_summary;
        if (gTitle) gTitle.textContent = gs && gs.title ? gs.title : '—';
        if (gMet) gMet.textContent = (gs && gs.primary_metric)
          ? ('Primary metric: ' + gs.primary_metric + (gs.goal_name && gs.goal_name !== '—' ? ' · Goal id: ' + gs.goal_name : ''))
          : '';
        if (gCon) gCon.textContent = (gs && gs.constraints_line) ? ('Constraints: ' + gs.constraints_line) : '';
        if (gNote) gNote.textContent = (gs && gs.note) ? gs.note : '';
      }
    }

    function applyRecipeModeToTextarea() {
      const rid = operatorRecipePick && operatorRecipePick.value;
      const isCustom = rid === 'custom';
      const hint = document.getElementById('structuredJsonHint');
      const ad = document.getElementById('advancedJsonDetails');
      if (scenariosEl) {
        scenariosEl.disabled = !isCustom;
        scenariosEl.title = isCustom ? 'Edit scenario JSON for this run' : 'Disabled — server builds scenarios for curated recipes.';
      }
      if (hint) {
        hint.textContent = isCustom
          ? 'Edit JSON below. It is validated on Run (same contract as before).'
          : 'Disabled for curated recipes — server injects manifest, evaluation window, goal, and recipe metadata.';
      }
      if (!isCustom && scenariosEl) {
        scenariosEl.value = '';
      }
      if (isCustom && ad && !ad.open) {
        /* optional: leave collapsed; user opens Advanced */
      }
    }

    async function refreshStructuredMetadata() {
      if (!operatorRecipePick || !evaluationWindowPick) return;
      const rid = operatorRecipePick.value;
      syncCustomMonthsVisibility();
      applyRecipeModeToTextarea();
      updateRunConfigurationPanel();
      if (rid === 'custom') {
        STRUCTURED_SCENARIO_COUNT = 1;
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
        return;
      }
      const wm = evaluationWindowPick.value;
      let url = '/api/operator-recipe-preview?recipe_id=' + encodeURIComponent(rid) +
        '&evaluation_window_mode=' + encodeURIComponent(wm);
      if (wm === 'custom') {
        const cm = evaluationWindowCustomMonths ? parseInt(evaluationWindowCustomMonths.value, 10) : 36;
        url += '&evaluation_window_custom_months=' + encodeURIComponent(String(cm && cm > 0 ? cm : 36));
      }
      try {
        const r = await fetch(url);
        const j = await r.json();
        if (!r.ok || !j.ok) {
          document.getElementById('out').innerHTML = '<span class="err">Run setup: ' + escapeHtml(j.error || r.status) + '</span>';
          setEvidenceTab('json');
          return;
        }
        STRUCTURED_SCENARIO_COUNT = typeof j.scenario_count === 'number' && j.scenario_count > 0 ? j.scenario_count : 1;
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
      } catch (e) {
        document.getElementById('out').innerHTML = '<span class="err">' + escapeHtml(friendlyFetchError(e)) + '</span>';
        setEvidenceTab('json');
      }
    }

    async function loadOperatorRecipesApi() {
      try {
        const r = await fetch('/api/operator-recipes');
        const j = await r.json();
        if (!r.ok || !j.ok) return;
        PG_OPERATOR_RECIPES = j.recipes || [];
        PG_POLICY_CATALOG = j.policy_catalog || [];
        syncPolicyPickUi();
        updateRunConfigurationPanel();
      } catch (e) { /* non-fatal */ }
    }

    async function loadExamplesFile(name) {
      if (!name) return;
      const r = await fetch('/api/scenario-preset?name=' + encodeURIComponent(name));
      if (!r.ok) {
        document.getElementById('out').innerHTML = '<span class="err">Example file load failed: ' + r.status + '</span>';
        setEvidenceTab('json');
        return;
      }
      const j = await r.json();
      if (j.ok) {
        scenariosEl.value = j.content;
        if (operatorRecipePick) operatorRecipePick.value = 'custom';
        applyRecipeModeToTextarea();
        updateRunConfigurationPanel();
        const ad = document.getElementById('advancedJsonDetails');
        const outer = document.getElementById('advancedOperatorPanel');
        if (outer && outer.open === false) outer.open = true;
        if (ad) ad.open = true;
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
      }
    }

    function updateRenameButton() {
      const btn = document.getElementById('presetRenameBtn');
      const v = examplesFilePick && examplesFilePick.value;
      if (btn) btn.disabled = !v || v.indexOf('user_') !== 0;
    }

    async function populateExamplesFileDropdown(selectFilename) {
      const r = await fetch('/api/scenario-presets');
      const rows = await r.json();
      if (!examplesFilePick) return rows;
      examplesFilePick.innerHTML = '<option value="">— pick file —</option>';
      rows.forEach((row) => {
        const o = document.createElement('option');
        o.value = row.filename;
        o.textContent = row.label || row.filename;
        examplesFilePick.appendChild(o);
      });
      if (selectFilename) {
        const has = Array.from(examplesFilePick.options).some(function (opt) { return opt.value === selectFilename; });
        if (has) examplesFilePick.value = selectFilename;
      }
      updateRenameButton();
      return rows;
    }

    let pendingUploadFile = null;

    function resetUploadDialog() {
      const res = document.getElementById('uploadPresetResult');
      const sp = document.getElementById('uploadDialogSpinner');
      const sub = document.getElementById('uploadPresetSubmitBtn');
      const done = document.getElementById('uploadPresetDoneBtn');
      const ni = document.getElementById('uploadPresetNameInput');
      if (res) { res.className = 'pg-upload-result'; res.textContent = ''; res.classList.remove('visible', 'ok', 'err'); }
      if (sp) sp.classList.remove('visible');
      if (sub) sub.style.display = '';
      if (done) done.style.display = 'none';
      if (ni) ni.value = '';
      pendingUploadFile = null;
      var fiClear = document.getElementById('presetFileInput');
      if (fiClear) fiClear.value = '';
    }

    const presetUploadBtn = document.getElementById('presetUploadBtn');
    const presetFileInput = document.getElementById('presetFileInput');
    const uploadDlg = document.getElementById('uploadPresetDialog');
    const uploadPresetNameInput = document.getElementById('uploadPresetNameInput');
    const uploadPresetResult = document.getElementById('uploadPresetResult');
    const uploadDialogSpinner = document.getElementById('uploadDialogSpinner');
    const uploadPresetSubmitBtn = document.getElementById('uploadPresetSubmitBtn');
    const uploadPresetCancelBtn = document.getElementById('uploadPresetCancelBtn');
    const uploadPresetDoneBtn = document.getElementById('uploadPresetDoneBtn');
    const uploadChosenFileLabel = document.getElementById('uploadChosenFileLabel');

    if (presetUploadBtn && presetFileInput) {
      presetUploadBtn.addEventListener('click', function () { presetFileInput.click(); });
      presetFileInput.addEventListener('change', function () {
        const f = presetFileInput.files && presetFileInput.files[0];
        pendingUploadFile = f || null;
        if (!f) return;
        if (uploadChosenFileLabel) {
          uploadChosenFileLabel.textContent = 'Selected file: ' + f.name + ' (' + (f.size / 1024).toFixed(1) + ' KB)';
        }
        resetUploadDialog();
        if (uploadPresetNameInput) uploadPresetNameInput.value = f.name.replace(/\.json$/i, '').replace(/[_-]+/g, ' ');
        if (uploadPresetResult) { uploadPresetResult.classList.remove('visible', 'ok', 'err'); uploadPresetResult.textContent = ''; }
        if (uploadDlg && uploadDlg.showModal) uploadDlg.showModal();
        if (uploadPresetNameInput) uploadPresetNameInput.focus();
      });
    }

    if (uploadPresetCancelBtn && uploadDlg) {
      uploadPresetCancelBtn.addEventListener('click', function () {
        if (uploadDlg.close) uploadDlg.close();
        resetUploadDialog();
      });
    }

    if (uploadPresetSubmitBtn) {
      uploadPresetSubmitBtn.addEventListener('click', async function () {
        if (!pendingUploadFile) {
          if (uploadPresetResult) {
            uploadPresetResult.className = 'pg-upload-result visible err';
            uploadPresetResult.textContent = 'FAIL — choose a .json file first (use Upload preset…).';
          }
          return;
        }
        const name = (uploadPresetNameInput && uploadPresetNameInput.value) ? uploadPresetNameInput.value.trim() : '';
        if (!name) {
          if (uploadPresetResult) {
            uploadPresetResult.className = 'pg-upload-result visible err';
            uploadPresetResult.textContent = 'FAIL — enter a preset name.';
          }
          return;
        }
        if (uploadDialogSpinner) uploadDialogSpinner.classList.add('visible');
        if (uploadPresetResult) {
          uploadPresetResult.className = 'pg-upload-result visible';
          uploadPresetResult.style.background = '#f4f1ea';
          uploadPresetResult.style.border = '1px solid var(--pg-line)';
          uploadPresetResult.textContent = 'Validating…';
        }
        const fd = new FormData();
        fd.append('file', pendingUploadFile, pendingUploadFile.name);
        fd.append('preset_name', name);
        try {
          const r = await fetch('/api/scenario-preset-upload', { method: 'POST', body: fd });
          const j = await r.json();
          if (uploadDialogSpinner) uploadDialogSpinner.classList.remove('visible');
          if (j.ok) {
            if (uploadPresetResult) {
              uploadPresetResult.className = 'pg-upload-result visible ok';
              uploadPresetResult.textContent = 'PASS — Saved as ' + j.filename + '. Appears under Advanced → Load example file; switch Recipe to Custom to run.';
            }
            if (uploadPresetSubmitBtn) uploadPresetSubmitBtn.style.display = 'none';
            if (uploadPresetDoneBtn) uploadPresetDoneBtn.style.display = '';
            await populateExamplesFileDropdown(j.filename);
            await loadExamplesFile(j.filename);
            if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
            refreshWorkerEffectiveLine();
          } else {
            if (uploadPresetResult) {
              uploadPresetResult.className = 'pg-upload-result visible err';
              uploadPresetResult.textContent = 'FAIL — ' + (j.error || r.status);
            }
          }
        } catch (e) {
          if (uploadDialogSpinner) uploadDialogSpinner.classList.remove('visible');
          if (uploadPresetResult) {
            uploadPresetResult.className = 'pg-upload-result visible err';
            uploadPresetResult.textContent = 'FAIL — ' + friendlyFetchError(e);
          }
        }
      });
    }

    if (uploadPresetDoneBtn && uploadDlg) {
      uploadPresetDoneBtn.addEventListener('click', function () {
        if (uploadDlg.close) uploadDlg.close();
        resetUploadDialog();
      });
    }

    const renameDlg = document.getElementById('renamePresetDialog');
    const renamePresetBtn = document.getElementById('presetRenameBtn');
    const renamePresetInput = document.getElementById('renamePresetInput');
    const renamePresetResult = document.getElementById('renamePresetResult');
    const renameDialogSpinner = document.getElementById('renameDialogSpinner');
    const renamePresetSubmitBtn = document.getElementById('renamePresetSubmitBtn');
    const renamePresetCancelBtn = document.getElementById('renamePresetCancelBtn');

    if (renamePresetBtn && renameDlg && renameDlg.showModal) {
      renamePresetBtn.addEventListener('click', function () {
        const v = examplesFilePick && examplesFilePick.value;
        if (!v || v.indexOf('user_') !== 0) return;
        if (renamePresetResult) { renamePresetResult.className = 'pg-upload-result'; renamePresetResult.textContent = ''; }
        if (renamePresetInput) renamePresetInput.value = v.replace(/^user_/, '').replace(/\.json$/, '').replace(/_/g, ' ');
        renameDlg.showModal();
        if (renamePresetInput) renamePresetInput.focus();
      });
    }
    if (renamePresetCancelBtn && renameDlg) {
      renamePresetCancelBtn.addEventListener('click', function () { if (renameDlg.close) renameDlg.close(); });
    }
    if (renamePresetSubmitBtn) {
      renamePresetSubmitBtn.addEventListener('click', async function () {
        const oldFn = examplesFilePick && examplesFilePick.value;
        const newName = (renamePresetInput && renamePresetInput.value) ? renamePresetInput.value.trim() : '';
        if (!oldFn || !newName) return;
        if (renameDialogSpinner) renameDialogSpinner.classList.add('visible');
        try {
          const r = await fetch('/api/scenario-preset-rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_filename: oldFn, new_preset_name: newName }),
          });
          const j = await r.json();
          if (renameDialogSpinner) renameDialogSpinner.classList.remove('visible');
          if (j.ok) {
            if (renamePresetResult) {
              renamePresetResult.className = 'pg-upload-result visible ok';
              renamePresetResult.textContent = 'PASS — Renamed to ' + j.filename;
            }
            await populateExamplesFileDropdown(j.filename);
            await loadExamplesFile(j.filename);
            if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
            refreshWorkerEffectiveLine();
            setTimeout(function () { if (renameDlg.close) renameDlg.close(); }, 900);
          } else {
            if (renamePresetResult) {
              renamePresetResult.className = 'pg-upload-result visible err';
              renamePresetResult.textContent = 'FAIL — ' + (j.error || 'rename failed');
            }
          }
        } catch (e) {
          if (renameDialogSpinner) renameDialogSpinner.classList.remove('visible');
          if (renamePresetResult) {
            renamePresetResult.className = 'pg-upload-result visible err';
            renamePresetResult.textContent = 'FAIL — ' + friendlyFetchError(e);
          }
        }
      });
    }

    (async function initOperatorUi() {
      try {
        await loadOperatorRecipesApi();
        await populateExamplesFileDropdown(null);
        if (operatorRecipePick) operatorRecipePick.value = 'pattern_learning';
        syncCustomMonthsVisibility();
        applyRecipeModeToTextarea();
        await refreshStructuredMetadata();
        if (typeof refreshSearchSpaceEstimate === 'function') await refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
      } catch (e) {}
    })();

    if (evaluationWindowPick) evaluationWindowPick.addEventListener('change', function () {
      syncCustomMonthsVisibility();
      refreshStructuredMetadata();
    });
    if (evaluationWindowCustomMonths) evaluationWindowCustomMonths.addEventListener('change', function () {
      refreshStructuredMetadata();
    });
    if (evaluationWindowCustomMonths) evaluationWindowCustomMonths.addEventListener('input', function () {
      const cm = evaluationWindowCustomMonths;
      const maxS = cm.getAttribute('max');
      if (!maxS) return;
      const mx = parseInt(maxS, 10);
      const v = parseInt(cm.value, 10);
      if (Number.isFinite(mx) && Number.isFinite(v) && v > mx) cm.value = String(mx);
    });
    if (operatorRecipePick) operatorRecipePick.addEventListener('change', function () {
      refreshStructuredMetadata();
    });

    scenariosEl.addEventListener('input', () => {
      if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
      refreshWorkerEffectiveLine();
    });

    if (examplesFilePick) examplesFilePick.addEventListener('change', function () {
      updateRenameButton();
      const name = examplesFilePick.value;
      if (!name) {
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
        return;
      }
      loadExamplesFile(name)
        .then(function () {
          if (typeof refreshSearchSpaceEstimate === 'function') return refreshSearchSpaceEstimate();
        })
        .then(function () { refreshWorkerEffectiveLine(); })
        .catch(function (e) {
          document.getElementById('out').innerHTML = '<span class="err">' + String(e) + '</span>';
          setEvidenceTab('json');
        });
    });

    if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
    refreshWorkerEffectiveLine();
    refreshScorecardHistory();
    setEvidenceTab('outcomes');
  </script>
</body>
</html>
"""


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Pattern game local web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    app = create_app()
    print(f"[web_app] Open http://{args.host}:{args.port}/  (PYTHONPATH must include repo root)")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
