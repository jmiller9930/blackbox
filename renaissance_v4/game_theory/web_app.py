"""
Local web UI for pattern game: **preset or paste** scenario JSON, then Run (parallel workers).

Batches use **``POST /api/run-parallel/start``** + polling **``GET /api/run-parallel/status/<job_id>``**
so the UI shows **per-scenario progress** (determinate bar) instead of a single long blocking request.
``POST /api/run-parallel`` remains as a blocking API for scripts.

Each completed batch also writes a **unique session folder** under the logs directory (default:
``renaissance_v4/game_theory/logs/``, or ``$PATTERN_GAME_MEMORY_ROOT/logs`` on a tmpfs/ramdisk for
instant I/O). Folders look like ``batch_<UTC>_<id>/`` with ``BATCH_README.md`` and per-scenario
``HUMAN_READABLE.md``, unless ``PATTERN_GAME_NO_SESSION_LOG=1``. The JSON result includes
``session_log_batch_dir`` when present.

Parallel batches append one line per run to ``batch_scorecard.jsonl`` (UTC start/end, duration,
counts, **run_ok_pct**, **referee_win_pct**, **avg_trade_win_pct**) and expose ``batch_timing`` on the API; see
``GET /api/batch-scorecard``.

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

No manifest/ATR fields in the UI — policy lives in the JSON (or examples presets). **Workers** slider defaults
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
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, jsonify, request

_GAME_THEORY = Path(__file__).resolve().parent

# Operator-visible web UI bundle version — bump when changing PAGE_HTML (HTML/CSS/JS) so deploys are provable.
PATTERN_GAME_WEB_UI_VERSION = "1.4.0"

from renaissance_v4.game_theory.groundhog_memory import (
    groundhog_auto_merge_enabled,
    groundhog_bundle_path,
    read_groundhog_bundle,
    write_groundhog_bundle,
)
from renaissance_v4.game_theory.batch_scorecard import (
    read_batch_scorecard_recent,
    record_parallel_batch_finished,
    utc_timestamp_iso,
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
from renaissance_v4.game_theory.parallel_runner import (
    clamp_parallel_workers,
    get_parallel_limits,
    run_scenarios_parallel,
)
from renaissance_v4.game_theory.pattern_game import (
    PATTERN_GAME_STARTING_EQUITY_USD_SPEC,
    _default_manifest_path,
    json_summary,
    run_pattern_game,
)
from renaissance_v4.game_theory.scenario_contract import (
    extract_policy_contract_summary,
    referee_session_outcome,
    validate_scenarios,
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
    raw = data.get("scenarios_json")
    if not raw or not isinstance(raw, str):
        return {"ok": False, "error": "Missing scenarios_json string"}
    try:
        scenarios = json.loads(raw)
        if isinstance(scenarios, dict) and "scenarios" in scenarios:
            scenarios = scenarios["scenarios"]
        if not isinstance(scenarios, list):
            raise ValueError("scenarios must be a JSON array")
        scenarios = [x for x in scenarios if isinstance(x, dict)]
    except (json.JSONDecodeError, ValueError) as e:
        return {"ok": False, "error": str(e)}

    for s in scenarios:
        if "manifest_path" in s and s["manifest_path"]:
            s["manifest_path"] = str(Path(s["manifest_path"]).expanduser().resolve())

    if not scenarios:
        return {"ok": False, "error": "No scenario objects in JSON array"}

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

    return {
        "ok": True,
        "scenarios": scenarios,
        "max_workers": max_workers,
        "log_path": log_path,
        "val_msgs": val_msgs,
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
        return jsonify(
            {
                **get_parallel_limits(),
                "pattern_game_web_ui_version": PATTERN_GAME_WEB_UI_VERSION,
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

    @app.get("/api/scenario-presets")
    def scenario_presets() -> Any:
        ex = _GAME_THEORY / "examples"
        rows: list[dict[str, str]] = []
        for p in sorted(ex.glob("*.json")):
            rows.append(
                {
                    "filename": p.name,
                    "label": p.name.replace("_", " ").replace(".example.json", "").replace(".json", ""),
                }
            )
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

    @app.post("/api/run")
    def api_run() -> Any:
        data = request.get_json(force=True, silent=True) or {}
        manifest = (data.get("manifest_path") or str(_default_manifest_path())).strip()
        atr_s = data.get("atr_stop_mult")
        atr_t = data.get("atr_target_mult")
        emit = bool(data.get("emit_baseline_artifacts"))
        mb = (data.get("memory_bundle_path") or "").strip() or None
        try:
            out = run_pattern_game(
                manifest,
                atr_stop_mult=float(atr_s) if atr_s not in (None, "") else None,
                atr_target_mult=float(atr_t) if atr_t not in (None, "") else None,
                memory_bundle_path=mb,
                emit_baseline_artifacts=emit,
                verbose=False,
            )
            js = json_summary(out)
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
                    "policy_contract": extract_policy_contract_summary(out.get("manifest_effective")),
                    "referee_session": referee_session_outcome(True, js),
                    "pnl_summary": pnl_summary,
                    "memory_bundle_audit": out.get("memory_bundle_audit"),
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

        _prune_jobs()
        job_id = uuid.uuid4().hex
        workers_used = clamp_parallel_workers(max_workers, len(scenarios))
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

        job_id = uuid.uuid4().hex
        started_iso = utc_timestamp_iso()
        start_unix = time.time()
        workers_used = clamp_parallel_workers(max_workers, len(scenarios))
        try:
            session_batch_dir: list[str | None] = [None]

            def on_session_batch(p: Path) -> None:
                session_batch_dir[0] = str(p.resolve())

            results = run_scenarios_parallel(
                scenarios,
                max_workers=max_workers,
                experience_log_path=log_path,
                on_session_log_batch=on_session_batch,
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
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      background: #0a0e12;
      color: #e7e9ea;
      --border: #2f3b47;
      --surface: #12181f;
      --surface2: #0d1218;
      --muted: #8b98a5;
      --accent: #1d9bf0;
    }
    body {
      max-width: min(1680px, calc(100vw - 32px));
      margin: 16px auto;
      padding: 0 16px 32px;
      box-sizing: border-box;
      line-height: 1.45;
    }
    .page-header { margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
    .page-header h1 { margin: 0 0 6px; font-size: 1.35rem; font-weight: 650; letter-spacing: -0.02em; display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
    .ui-version {
      display: inline-block;
      padding: 3px 10px;
      font-size: 0.68rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      border-radius: 999px;
      background: #152535;
      color: #7ec8f5;
      border: 1px solid #2a5a82;
      font-variant-numeric: tabular-nums;
    }
    .page-lead { margin: 0; color: var(--muted); font-size: 0.95rem; max-width: 56ch; }
    .page-lead strong { color: #e7e9ea; font-weight: 600; }
    .def001-science {
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 8px;
      border: 1px solid #2a4a60;
      background: linear-gradient(180deg, #121c24 0%, #0f1419 100%);
      font-size: 0.82rem;
      line-height: 1.5;
      color: #c8d0d8;
    }
    .def001-science .def001-tag {
      display: inline-block;
      font-size: 0.65rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: #5eb8e8;
      margin-bottom: 6px;
    }
    .def001-science strong { color: #e7edf2; }
    .def001-science a { color: #5eb8e8; }
    details.help-details {
      margin-top: 12px; border-radius: 8px; border: 1px solid var(--border);
      background: var(--surface); padding: 0 12px;
    }
    details.help-details summary {
      cursor: pointer; font-size: 0.82rem; color: var(--accent); font-weight: 600;
      padding: 10px 0; list-style: none;
    }
    details.help-details summary::-webkit-details-marker { display: none; }
    .help-details-body { font-size: 0.8rem; color: var(--muted); padding: 0 0 12px; }
    .help-details-body p { margin: 0 0 8px; }
    .help-details-body p:last-child { margin-bottom: 0; }
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px 16px;
      margin-bottom: 16px;
    }
    .panel-title {
      margin: 0 0 12px;
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }
    details.inline-details {
      margin: 6px 0 10px;
      font-size: 0.78rem;
      color: var(--muted);
      border-left: 2px solid #38444d;
      padding-left: 10px;
    }
    details.inline-details summary { cursor: pointer; color: #c4ccd4; font-weight: 500; }
    details.inline-details[open] summary { margin-bottom: 6px; }
    .tool-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin-bottom: 10px; }
    .tool-row .btn-secondary { margin-top: 0; background: #2f3f4d; font-weight: 500; font-size: 0.85rem; padding: 8px 12px; }
    .tool-row .btn-chef { margin-top: 0; background: #166a4a; font-weight: 600; font-size: 0.85rem; padding: 8px 12px; }
    .workers-panel { margin-top: 4px; }
    .workers-panel label[for="workersRange"] { margin-top: 0; }
    #workerCpuHint { font-size: 0.72rem; color: #6b7a88; margin: 6px 0 0; line-height: 1.4; }
    #workerEffectiveLine {
      margin: 10px 0 0;
      padding: 10px 12px;
      border-radius: 8px;
      background: var(--surface2);
      border: 1px solid var(--border);
      font-size: 0.82rem;
      line-height: 1.45;
      color: #d5dce3;
    }
    #workerEffectiveLine strong { color: #e7e9ea; }
    .run-actions { margin-top: 16px; padding-top: 4px; }
    #runBtn { width: 100%; max-width: 320px; padding: 12px 20px; font-size: 1rem; border-radius: 10px; }
    .status-stack { margin-top: 12px; }
    .top-bars {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-bottom: 18px;
      align-items: stretch;
    }
    .top-bars > * { min-width: 0; }
    .top-bars .health-bar,
    .top-bars .pnl-strip,
    .top-bars .estimate-strip {
      background: var(--surface);
      border-color: var(--border);
    }
    .main-layout {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
      gap: 20px;
      align-items: start;
    }
    @media (max-width: 1024px) {
      .main-layout { grid-template-columns: 1fr; }
    }
    .col-controls { min-width: 0; }
    .col-sidebar { min-width: 0; position: sticky; top: 8px; }
    @media (max-width: 1024px) {
      .col-sidebar { position: static; }
    }
    .results-split {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 16px;
      margin-top: 16px;
      align-items: start;
    }
    @media (max-width: 900px) {
      .results-split { grid-template-columns: 1fr; }
    }
    .results-split:has(#policyOutcomePanel[hidden]) {
      grid-template-columns: 1fr;
    }
    .results-split .result-json-wrap { min-width: 0; }
    h1 { font-size: 1.25rem; font-weight: 600; }
    h2 { font-size: 1rem; margin-top: 0; color: #8b98a5; }
    label { display: block; margin: 10px 0 4px; font-size: 0.85rem; color: #8b98a5; }
    input[type=text], input[type=number], textarea, select {
      width: 100%; box-sizing: border-box; padding: 8px 10px;
      border: 1px solid #38444d; border-radius: 6px; background: #15202b; color: #e7e9ea;
    }
    textarea {
      min-height: 160px;
      max-height: min(48vh, 480px);
      font-family: ui-monospace, monospace;
      font-size: 0.8rem;
      resize: vertical;
    }
    button {
      margin-top: 12px; padding: 10px 18px; border: 0; border-radius: 8px;
      background: #1d9bf0; color: #fff; font-weight: 600; cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .row { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-end; }
    .row > div { flex: 1; min-width: 120px; }
    .caps { font-size: 0.8rem; color: #8b98a5; margin: 8px 0 0; }
    pre {
      background: #15202b; border: 1px solid #38444d; border-radius: 8px;
      padding: 12px; overflow: auto; font-size: 0.75rem;
      max-height: min(42vh, 420px);
    }
    .err { color: #f4212e; }
    .health-bar {
      display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      padding: 10px 12px; margin-bottom: 16px; border-radius: 8px;
      background: #15202b; border: 1px solid #38444d; font-size: 0.85rem;
    }
    .health-bar .status-dot {
      width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
      background: #536471;
    }
    .health-bar .status-dot.ok { background: #00ba7c; box-shadow: 0 0 8px rgba(0,186,124,0.45); }
    .health-bar .status-dot.bad { background: #f4212e; box-shadow: 0 0 8px rgba(244,33,46,0.35); }
    .health-title { font-weight: 600; color: #e7e9ea; margin-right: 6px; }
    .health-detail { color: #8b98a5; }
    .pnl-strip {
      padding: 12px 12px; margin-bottom: 16px; border-radius: 8px;
      background: #15202b; border: 1px solid #38444d; font-size: 0.88rem;
    }
    .pnl-strip .pnl-row1 {
      display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 16px;
      margin-bottom: 8px;
    }
    .pnl-strip .pnl-title { font-weight: 600; color: #e7e9ea; }
    .pnl-strip .pnl-baseline { color: #8b98a5; font-size: 0.8rem; }
    .pnl-strip .pnl-ending { font-size: 1.15rem; font-weight: 700; font-variant-numeric: tabular-nums; color: #e7e9ea; }
    .pnl-strip .pnl-delta { font-weight: 600; font-variant-numeric: tabular-nums; }
    .pnl-strip .pnl-delta.up { color: #00ba7c; }
    .pnl-strip .pnl-delta.down { color: #f4212e; }
    .pnl-strip .pnl-delta.neutral { color: #8b98a5; }
    .pnl-bar-wrap { position: relative; margin-top: 4px; }
    .pnl-bar-track {
      height: 10px; border-radius: 5px; background: linear-gradient(90deg, #2a1a1a 0%, #38444d 50%, #1a2a1f 100%);
      position: relative;
    }
    .pnl-bar-ticks {
      display: flex; justify-content: space-between; font-size: 0.65rem; color: #536471; margin-top: 4px;
    }
    .pnl-marker {
      position: absolute; top: -3px; width: 4px; height: 16px; margin-left: -2px;
      border-radius: 2px; background: #e7e9ea; box-shadow: 0 0 6px rgba(231,233,234,0.35);
      transform: translateX(-50%); left: 50%;
    }
    .pnl-fill {
      position: absolute; top: 0; height: 10px; border-radius: 5px; opacity: 0.65;
      pointer-events: none;
    }
    .pnl-fill.up { background: #00ba7c; }
    .pnl-fill.down { background: #f4212e; }
    .estimate-strip {
      padding: 10px 12px;
      margin-bottom: 0;
      border-radius: 8px;
      background: var(--surface);
      border: 1px solid var(--border);
      font-size: 0.78rem;
      color: var(--muted);
      line-height: 1.45;
    }
    .estimate-strip strong { color: #e7e9ea; }
    #groundhogStrip details { margin-top: 8px; font-size: 0.74rem; color: #6b7a88; }
    #groundhogStrip summary { cursor: pointer; color: var(--accent); font-weight: 600; }
    .scorecard-panel {
      margin: 0;
      padding: 12px 14px;
      border-radius: 10px;
      background: var(--surface);
      border: 1px solid var(--border);
      overflow-x: auto;
      max-height: min(70vh, 640px);
      overflow-y: auto;
    }
    .scorecard-panel h2 { margin-top: 0; }
    .scorecard-panel .last-run {
      font-size: 0.85rem;
      color: #e7e9ea;
      margin: 0 0 12px 0;
      line-height: 1.45;
    }
    .scorecard-legend {
      font-size: 0.76rem;
      color: #8b98a5;
      margin: 0 0 12px 0;
      line-height: 1.5;
      padding: 10px 12px;
      border-radius: 8px;
      background: var(--surface2);
      border: 1px solid var(--border);
    }
    .scorecard-legend strong { color: #d5dce3; }
    .scorecard-panel .path-hint { font-size: 0.72rem; color: #536471; margin: 8px 0 0 0; word-break: break-all; }
    .scorecard-table { width: 100%; border-collapse: collapse; font-size: 0.75rem; }
    .scorecard-table th, .scorecard-table td {
      border: 1px solid #38444d;
      padding: 5px 7px;
      text-align: left;
    }
    .scorecard-table th { background: #1a2732; color: #8b98a5; white-space: nowrap; }
    .st-ok { color: #00ba7c; font-weight: 600; }
    .st-err { color: #f97316; font-weight: 600; }
    .policy-outcome-panel {
      margin: 0;
      padding: 12px 14px;
      border-radius: 10px;
      background: var(--surface);
      border: 1px solid var(--border);
      overflow-x: auto;
      max-height: min(70vh, 640px);
      overflow-y: auto;
    }
    .policy-outcome-panel h2 { margin-top: 0; }
    .policy-outcome-panel .hint { font-size: 0.78rem; color: #8b98a5; margin: 0 0 10px 0; line-height: 1.4; }
    .policy-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.78rem;
    }
    .policy-table th, .policy-table td {
      border: 1px solid #38444d;
      padding: 6px 8px;
      text-align: left;
      vertical-align: top;
    }
    .policy-table th { background: #1a2732; color: #8b98a5; font-weight: 600; white-space: nowrap; }
    .policy-table td { color: #e7e9ea; }
    .tag-win { color: #00ba7c; font-weight: 700; }
    .tag-loss { color: #f4212e; font-weight: 700; }
    .tag-err { color: #f97316; font-weight: 700; }
    .signals-cell { font-family: ui-monospace, monospace; font-size: 0.72rem; max-width: 320px; word-break: break-word; }
    input[type=checkbox] { width: auto; }
    input[type=range] { width: 100%; accent-color: #1d9bf0; }
    .batch-concurrency-banner {
      display: none; margin: 10px 0 8px; padding: 10px 12px; border-radius: 8px;
      background: var(--surface2); border: 1px solid var(--border); font-size: 0.85rem; line-height: 1.45; color: #e7e9ea;
    }
    .batch-concurrency-banner.visible { display: block; }
    .batch-concurrency-banner strong { color: #1d9bf0; font-weight: 600; }
    .batch-concurrency-banner .warn { color: #ffb020; }
    .progress-wrap { display: none; margin: 12px 0 8px; }
    .progress-wrap.active { display: block; }
    .progress-track {
      height: 10px; border-radius: 5px; background: #38444d; overflow: hidden;
    }
    .progress-fill {
      height: 100%; width: 0%; border-radius: 5px;
      background: linear-gradient(90deg, #175cd3, #1d9bf0);
      transition: width 0.35s ease;
    }
    #progressSub { margin-top: 6px; font-size: 0.8rem; color: #8b98a5; }
    #statusLine { min-height: 1.3em; color: #e7e9ea; font-size: 0.9rem; margin-top: 8px; }
  </style>
</head>
<body>
  <div class="top-bars">
  <div class="health-bar" id="dataHealthBar" aria-live="polite">
    <span class="status-dot" id="healthDot" title="Data status"></span>
    <span class="health-title">Financial data</span>
    <span class="health-detail" id="healthText">Checking database…</span>
  </div>

  <div class="pnl-strip" id="pnlStrip" title="Paper equity vs spec $1k baseline; updates after each batch run.">
    <div class="pnl-row1">
      <span class="pnl-title">Paper P&amp;L</span>
      <span class="pnl-baseline">Baseline <span id="pnlBaselineLabel">$1,000.00</span> (spec)</span>
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

  <div class="estimate-strip" id="searchSpaceStrip" aria-live="polite">
    <strong>Search space</strong> — loading catalog + bar counts…
  </div>

  <div class="estimate-strip" id="groundhogStrip" aria-live="polite" style="font-size:0.82rem;border-color:#2a4a38">
    <strong>Groundhog memory</strong> — <span id="groundhogText">loading…</span>
    <details>
      <summary>Server env &amp; promotion</summary>
      <span class="caps" style="display:block;margin-top:6px;line-height:1.45">
        Set <code>PATTERN_GAME_GROUNDHOG_BUNDLE=1</code> to merge <code>game_theory/state/groundhog_memory_bundle.json</code> when a scenario has no <code>memory_bundle_path</code>. POST <code>/api/groundhog-memory</code> to promote ATR from review.
      </span>
    </details>
  </div>
  </div>

  <div class="main-layout">
  <div class="col-controls">
  <header class="page-header">
    <h1>Pattern game <span class="ui-version" title="Web UI bundle — bump PATTERN_GAME_WEB_UI_VERSION in web_app.py when this page changes">v__PATTERN_GAME_WEB_UI_VERSION__</span></h1>
    <p class="page-lead">Pick a <strong>preset</strong> or paste <strong>scenario JSON</strong>, then run the batch. Referee scores and paper P&amp;L update below.</p>
    <div class="def001-science" role="region" aria-label="DEF-001 Science evaluation contract">
      <span class="def001-tag">DEF-001 · SCIENCE / EVALUATION ONLY</span>
      <p style="margin:0">
        This lab run is <strong>deterministic replay</strong>: fixed manifest + engine rules on historical bars.
        It <strong>does not</strong> train or auto-tune policy weights from your batch (no in-band “machine learning” from outcomes).
        We <strong>measure</strong> (P&amp;L, win rates, scorecard) and you <strong>iterate</strong> (hypothesis, manifests, next scenarios).
        Full work record: <code>docs/architect/pattern_game_operator_deficiencies_work_record.md</code> (DEF-001).
      </p>
    </div>
    <details class="help-details">
      <summary>Setup, PYTHONPATH, and where policy lives</summary>
      <div class="help-details-body">
        <p>Run from repo root with <code>PYTHONPATH</code> including the repo. This form does not edit manifests — policy and hypothesis strings live in the JSON.</p>
        <p>Presets load from <code>game_theory/examples/</code>. After load you can edit the textarea, or ignore the menu and paste only.</p>
      </div>
    </details>
  </header>

  <section class="panel" aria-labelledby="batch-heading">
    <h2 class="panel-title" id="batch-heading">Batch</h2>
    <label for="presetPick">Preset</label>
    <select id="presetPick" aria-describedby="presetHelp">
      <option value="">— Custom JSON only (no preset) —</option>
    </select>
    <p class="caps" id="presetHelp" style="margin-top:6px">Preset fills the box below; you can still edit before Run.</p>

    <label for="scenarios" style="margin-top:14px">Scenario JSON</label>
    <details class="inline-details">
      <summary>Validation (hypothesis)</summary>
      <p style="margin:0;line-height:1.45">Each scenario needs a non-empty <code>agent_explanation.hypothesis</code>. Server override: <code>PATTERN_GAME_REQUIRE_HYPOTHESIS=0</code>.</p>
    </details>

    <div class="tool-row">
      <button type="button" class="btn-secondary" id="suggestHuntersBtn"
        title="Fills the textarea with the next parallel scenarios from batch scorecard + retrospective logs (deterministic ladder — not a live prediction)">Suggest hunters</button>
      <span class="caps" id="hunterSuggestHint" style="margin:0;flex:1;min-width:180px;align-self:center"></span>
    </div>
    <p class="caps" style="margin:0 0 10px;line-height:1.45">Hunter = next batch suggestions from <strong>memory</strong> (scorecard + retrospective JSONL), same logic as the agent context bundle — not Referee output.</p>
    <div class="tool-row">
      <div style="flex:2;min-width:200px">
        <label for="chefManifestPath" style="margin:0;font-size:0.8rem">Chef manifest (repo path)</label>
        <input type="text" id="chefManifestPath" style="margin-top:4px" value="renaissance_v4/configs/manifests/baseline_v1_recipe.json" spellcheck="false"/>
      </div>
      <button type="button" class="btn-chef" id="chefAtrSweepBtn">ATR sweep</button>
      <span class="caps" id="chefHint" style="margin:0;flex:1;min-width:140px;align-self:center"></span>
    </div>
    <textarea id="scenarios" spellcheck="false" placeholder='[{"scenario_id":"…","manifest_path":"…","agent_explanation":{"hypothesis":"…"},…}]'></textarea>
  </section>

  <section class="panel workers-panel" aria-labelledby="workers-heading">
    <h2 class="panel-title" id="workers-heading">Parallelism &amp; logging</h2>
    <label for="workersRange">Worker processes <span id="workersVal" style="color:#e7e9ea;font-weight:600">1</span></label>
    <input type="range" id="workersRange" min="1" max="64" value="1" step="1" />
    <p id="workerCpuHint"></p>
    <div id="workerEffectiveLine" aria-live="polite"></div>
    <div style="margin-top:14px">
      <label style="margin:0;font-size:0.85rem"><input type="checkbox" id="doLog" checked/> Append runs to experience JSONL (<code>PATTERN_GAME_MEMORY_ROOT</code> optional)</label>
    </div>
  </section>

  <div class="run-actions">
    <button type="button" id="runBtn">Run batch</button>
    <div class="status-stack">
      <div id="statusLine" aria-live="polite"></div>
      <div id="batchConcurrencyBanner" class="batch-concurrency-banner" aria-live="polite"></div>
      <div id="progressWrap" class="progress-wrap" role="progressbar" aria-label="Batch replay progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <div class="progress-track" id="progressTrack">
          <div class="progress-fill" id="progressFill" style="width:0%"></div>
        </div>
        <p class="caps" id="progressSub"></p>
      </div>
    </div>
  </div>
  </div>

  <aside class="col-sidebar" aria-label="Batch scorecard">
  <div class="scorecard-panel" id="scorecardPanel">
    <h2>Batch scorecard</h2>
    <p class="scorecard-legend">
      <strong>Three different numbers:</strong>
      <strong>Run OK</strong> — jobs finished without a worker crash (says nothing about P&amp;L).
      <strong>Session WIN</strong> — share of scenarios with paper session WIN vs LOSS (cumulative P&amp;L vs baseline).
      <strong>Trade win</strong> — mean of per-scenario trade win rates (wins÷trades); this is the <strong>~34%</strong>-style column.
      “Learning” is not a single % — use Session + Trade win + Policy table below after each run.
    </p>
    <p class="last-run" id="lastBatchRunLine">Last completed batch: — (run a batch to record start/end and totals)</p>
    <table class="scorecard-table" id="scorecardHistoryTable">
      <thead>
        <tr>
          <th>Started (UTC)</th>
          <th>Ended (UTC)</th>
          <th>Duration</th>
          <th>Processed</th>
          <th>OK</th>
          <th>Failed</th>
          <th title="Scenarios whose worker finished without exception">Run OK %</th>
          <th title="Paper session WIN ÷ (WIN+LOSS) across scenarios in this batch">Session WIN %</th>
          <th title="Mean of per-scenario trade win rates (summary.win_rate); e.g. 34.4%">Trade win %</th>
          <th>Workers</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="scorecardHistoryTbody"></tbody>
    </table>
    <p class="path-hint" id="scorecardPathHint"></p>
  </div>
  </aside>
  </div>

  <div class="results-split">
  <div class="policy-outcome-panel" id="policyOutcomePanel" hidden>
    <h2>Referee outcomes (per scenario)</h2>
    <p class="hint">
      After a run, <strong>Trade win %</strong> here is the per-scenario value (e.g. <strong>34.4%</strong>) — winning trades ÷ total trades on the tape.
      <strong>Session</strong> WIN/LOSS is from cumulative paper P&amp;L vs baseline (one row per scenario). Manifest columns summarize what was replayed. Full JSON is on the right.
    </p>
    <table class="policy-table" id="policyOutcomeTable">
      <thead>
        <tr>
          <th>Scenario</th>
          <th>Session</th>
          <th>Cum. P&amp;L</th>
          <th>Trade win %</th>
          <th>Trades</th>
          <th>Signal modules</th>
          <th>Fusion</th>
          <th>Strategy id</th>
        </tr>
      </thead>
      <tbody id="policyOutcomeTbody"></tbody>
    </table>
  </div>
  <div class="result-json-wrap">
  <h2>Result</h2>
  <p class="caps" id="sessionLogNote" style="margin:0 0 8px 0;color:#8b98a5;"></p>
  <pre id="out">(no run yet)</pre>
  </div>
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
    function refreshWorkerEffectiveLine() {
      const el = document.getElementById('workerEffectiveLine');
      if (!el) return;
      const n = parseScenarioCountFromTextarea();
      const w = parseInt(rangeEl.value, 10) || 1;
      if (n < 1) {
        el.innerHTML = '<strong>Effective parallelism</strong> — Load valid JSON above. The run uses <strong>min(scenario count, slider)</strong>.';
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
      if (atw != null && atw !== undefined && !Number.isNaN(Number(atw))) {
        pctBit += ' · trade win (mean) ' + (Math.round(Number(atw) * 10) / 10).toFixed(1) + '%';
      }
      el.textContent = 'Last completed batch: start ' + (bt.started_at_utc || '—') +
        ' → end ' + (bt.ended_at_utc || '—') + ' · duration ' + formatDurationSec(bt.duration_sec) +
        ' · processed ' + proc + ' / planned ' + tot + pctBit;
    }

    async function refreshScorecardHistory() {
      const tbody = document.getElementById('scorecardHistoryTbody');
      const hint = document.getElementById('scorecardPathHint');
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
        const rows = j.entries || [];
        if (!rows.length) {
          const tr = document.createElement('tr');
          tr.innerHTML = '<td colspan="11" style="color:#8b98a5">No batches logged yet.</td>';
          tbody.appendChild(tr);
          return;
        }
        for (const e of rows) {
          const tr = document.createElement('tr');
          const st = e.status === 'done'
            ? '<span class="st-ok">done</span>'
            : '<span class="st-err">' + escapeHtml(e.status || '—') + '</span>';
          const proc = (e.total_processed != null) ? e.total_processed : '—';
          const dur = (e.duration_sec != null) ? formatDurationSec(e.duration_sec) : '—';
          function pctCell(v) {
            if (v == null || v === undefined || Number.isNaN(Number(v))) return '—';
            const n = Number(v);
            return (Math.round(n * 10) / 10).toFixed(1) + '%';
          }
          tr.innerHTML =
            '<td>' + escapeHtml(e.started_at_utc || '—') + '</td>' +
            '<td>' + escapeHtml(e.ended_at_utc || '—') + '</td>' +
            '<td>' + escapeHtml(dur) + '</td>' +
            '<td>' + escapeHtml(String(proc)) + '</td>' +
            '<td>' + escapeHtml(e.ok_count != null ? String(e.ok_count) : '—') + '</td>' +
            '<td>' + escapeHtml(e.failed_count != null ? String(e.failed_count) : '—') + '</td>' +
            '<td>' + escapeHtml(pctCell(e.run_ok_pct)) + '</td>' +
            '<td>' + escapeHtml(pctCell(e.referee_win_pct)) + '</td>' +
            '<td>' + escapeHtml(pctCell(e.avg_trade_win_pct)) + '</td>' +
            '<td>' + escapeHtml(e.workers_used != null ? String(e.workers_used) : '—') + '</td>' +
            '<td>' + st + '</td>';
          tbody.appendChild(tr);
        }
      } catch (err) {
        if (hint) hint.textContent = 'Scorecard history: ' + friendlyFetchError(err);
      }
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
      if (err) {
        pre.innerHTML = '<span class="err">' + err + '</span>';
        renderPolicyOutcomePanel(null);
        return;
      }
      pre.textContent = JSON.stringify(data, null, 2);
      renderPolicyOutcomePanel(data);
      if (data && data.batch_timing) updateLastBatchRunLine(data.batch_timing);
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
      clearBatchConcurrencyBanner();
      const sn = document.getElementById('sessionLogNote');
      if (sn) sn.textContent = '';
      statusLine.textContent = 'Starting batch…';
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
        const scenariosTa = document.getElementById('scenarios').value;
        const body = {
          scenarios_json: scenariosTa,
          max_workers: mw,
          log_path: document.getElementById('doLog').checked
        };
        const startR = await fetch('/api/run-parallel/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const startJ = await startR.json();
        if (!startR.ok) {
          await show(null, null, startJ.error || JSON.stringify(startJ));
          statusLine.textContent = 'Validation failed — see Result.';
          return;
        }
        const jobId = startJ.job_id;
        const total = resolveScenarioBatchTotal(startJ.total, scenariosTa);
        runWorkersCap = startJ.workers_used != null ? startJ.workers_used : null;
        showBatchConcurrencyBanner(total, runWorkersCap, 'run');
        statusLine.textContent =
          'Running — ' + total + ' scenario(s) · up to ' + (runWorkersCap != null ? runWorkersCap : '?') +
          ' parallel process(es) (min of batch size and slider) · updates every 1.5s below.';
        setProgressUI(0, total, 'Queued — up to ' + (runWorkersCap != null ? runWorkersCap : '?') + ' process(es) · waiting for first replay to finish…');

        const pollOnce = async () => {
          const pr = await fetch('/api/run-parallel/status/' + jobId);
          const pj = await pr.json();
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
            return false;
          }
          if (pj.status === 'error') {
            showBatchConcurrencyBanner(total, wCap, 'error');
            if (pj.batch_timing) updateLastBatchRunLine(pj.batch_timing);
            refreshScorecardHistory();
            await show(null, null, pj.error || 'Job failed');
            statusLine.textContent = 'Failed — see Result.';
            setProgressUI(pj.completed || 0, statusPollTotal(pj, total), pj.error || '');
            return true;
          }
          if (pj.status === 'done') {
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
          return true;
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
        progressWrap.classList.remove('active');
        btn.disabled = false;
      }
    };

    fetch('/api/capabilities').then(r => r.json()).then(() => {});

    async function refreshDataHealth() {
      const dot = document.getElementById('healthDot');
      const text = document.getElementById('healthText');
      try {
        const r = await fetch('/api/data-health');
        const j = await r.json();
        dot.className = 'status-dot ' + (j.overall_ok ? 'ok' : 'bad');
        dot.title = j.overall_ok ? 'Data OK' : 'Data issue — see text';
        if (j.summary_line) {
          text.textContent = j.summary_line;
        } else if (j.error) {
          text.textContent = j.error;
        } else {
          text.textContent = 'Unknown status';
        }
      } catch (e) {
        dot.className = 'status-dot bad';
        dot.title = 'Health request failed';
        text.textContent = 'Health check failed: ' + friendlyFetchError(e);
      }
    }
    refreshDataHealth();
    setInterval(refreshDataHealth, 45000);

    async function refreshGroundhog() {
      const el = document.getElementById('groundhogText');
      if (!el) return;
      try {
        const r = await fetch('/api/groundhog-memory');
        const j = await r.json();
        if (!r.ok || !j.ok) {
          el.textContent = 'unavailable';
          return;
        }
        const en = j.env_enabled ? 'merge ON' : 'merge OFF (set PATTERN_GAME_GROUNDHOG_BUNDLE=1)';
        const ex = j.exists ? 'file exists' : 'no file yet (POST /api/groundhog-memory to promote)';
        const ap = j.bundle && j.bundle.apply
          ? ('ATR stop ' + j.bundle.apply.atr_stop_mult + ' / target ' + j.bundle.apply.atr_target_mult)
          : '—';
        el.textContent = en + ' · ' + ex + ' · ' + ap;
      } catch (e) {
        el.textContent = 'could not load — ' + friendlyFetchError(e);
      }
    }
    refreshGroundhog();
    setInterval(refreshGroundhog, 60000);

    async function refreshSearchSpaceEstimate() {
      const el = document.getElementById('searchSpaceStrip');
      if (!el) return;
      try {
        const w = parseInt(rangeEl.value, 10) || 1;
        let batchN = 0;
        try {
          const raw = (scenariosEl && scenariosEl.value) ? scenariosEl.value.trim() : '';
          if (raw) {
            const parsed = JSON.parse(raw);
            const arr = Array.isArray(parsed) ? parsed : (parsed.scenarios || []);
            if (Array.isArray(arr)) batchN = arr.length;
          }
        } catch (e) { batchN = 0; }
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
          line += 'Your textarea: <strong>' + batchN + '</strong> scenarios, <strong>' + w + '</strong> workers → ~<strong>' + rounds + '</strong> parallel round(s). ';
        } else {
          line += 'Paste scenarios to see batch rounds; workers use slider (' + w + '). ';
        }
        if (br != null && batchN > 0) {
          line += 'Coarse bar steps ≈ ' + br.toLocaleString() + ' (scenarios×bars).';
        }
        el.innerHTML = line;
      } catch (e) {
        el.innerHTML = '<strong>Search space</strong> — could not load estimate. ' + friendlyFetchError(e);
      }
    }

    const presetPick = document.getElementById('presetPick');
    const scenariosEl = document.getElementById('scenarios');

    async function loadPreset(name) {
      if (!name) return;
      const r = await fetch('/api/scenario-preset?name=' + encodeURIComponent(name));
      if (!r.ok) {
        document.getElementById('out').innerHTML = '<span class="err">Preset load failed: ' + r.status + '</span>';
        return;
      }
      const j = await r.json();
      if (j.ok) scenariosEl.value = j.content;
    }

    fetch('/api/scenario-presets')
      .then(r => r.json())
      .then((rows) => {
        rows.forEach((row) => {
          const o = document.createElement('option');
          o.value = row.filename;
          o.textContent = row.label || row.filename;
          presetPick.appendChild(o);
        });
        const tier1 = rows.find((x) => x.filename === 'tier1_twelve_month.example.json');
        if (tier1) {
          presetPick.value = tier1.filename;
          return loadPreset(tier1.filename);
        }
        return Promise.resolve();
      })
      .then(() => {
        if (typeof refreshSearchSpaceEstimate === 'function') return refreshSearchSpaceEstimate();
      })
      .then(() => { refreshWorkerEffectiveLine(); })
      .catch(() => {});

    scenariosEl.addEventListener('input', () => {
      if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
      refreshWorkerEffectiveLine();
    });

    presetPick.onchange = () => {
      const name = presetPick.value;
      if (!name) {
        if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
        refreshWorkerEffectiveLine();
        return;
      }
      loadPreset(name)
        .then(() => {
          if (typeof refreshSearchSpaceEstimate === 'function') return refreshSearchSpaceEstimate();
        })
        .then(() => { refreshWorkerEffectiveLine(); })
        .catch((e) => {
          document.getElementById('out').innerHTML = '<span class="err">' + String(e) + '</span>';
        });
    };

    if (typeof refreshSearchSpaceEstimate === 'function') refreshSearchSpaceEstimate();
    refreshWorkerEffectiveLine();
    refreshScorecardHistory();
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
