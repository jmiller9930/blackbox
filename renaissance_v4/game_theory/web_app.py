"""
Local web UI for pattern game: **preset or paste** scenario JSON, then Run (parallel workers).

Batches use **``POST /api/run-parallel/start``** + polling **``GET /api/run-parallel/status/<job_id>``**
so the UI shows **per-scenario progress** (determinate bar) instead of a single long blocking request.
``POST /api/run-parallel`` remains as a blocking API for scripts.

Each completed batch also writes a **unique session folder** under ``renaissance_v4/game_theory/logs/``
(``batch_<UTC>_<id>/`` with ``BATCH_README.md`` and per-scenario ``HUMAN_READABLE.md``), unless
``PATTERN_GAME_NO_SESSION_LOG=1``. The JSON result includes ``session_log_batch_dir`` when present.

No manifest/ATR fields in the UI — policy lives in the JSON (or examples presets). Default 16 workers
(capped to host). ``POST /api/run`` remains for scripted single-manifest runs.

  pip install -r renaissance_v4/game_theory/requirements.txt
  PYTHONPATH=. python3 -m renaissance_v4.game_theory.web_app

Default bind is loopback; use ``--host 0.0.0.0`` for LAN/SSH access (prototype).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, request

_GAME_THEORY = Path(__file__).resolve().parent

from renaissance_v4.game_theory.data_health import get_data_health
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
from renaissance_v4.game_theory.scenario_contract import validate_scenarios

_JOBS_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_JOB_MAX_AGE_SEC = 7200


def _prune_jobs() -> None:
    now = time.time()
    with _JOBS_LOCK:
        stale = [k for k, v in _JOBS.items() if now - float(v.get("created", 0)) > _JOB_MAX_AGE_SEC]
        for k in stale:
            del _JOBS[k]


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

    ok_val, val_msgs = validate_scenarios(scenarios)
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
        log_path = _GAME_THEORY / "experience_log.jsonl"
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


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        lim = get_parallel_limits()
        return (
            PAGE_HTML.replace("__LIMITS_JSON__", json.dumps(lim)).replace(
                "__STARTING_EQUITY__", str(float(PATTERN_GAME_STARTING_EQUITY_USD_SPEC))
            )
        )

    @app.get("/api/capabilities")
    def capabilities() -> Any:
        return jsonify(get_parallel_limits())

    @app.get("/api/data-health")
    def data_health() -> Any:
        """SQLite reachable, ``market_bars_5m`` present, replay row count, SOLUSDT ~12mo span."""
        return jsonify(get_data_health())

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
        try:
            out = run_pattern_game(
                manifest,
                atr_stop_mult=float(atr_s) if atr_s not in (None, "") else None,
                atr_target_mult=float(atr_t) if atr_t not in (None, "") else None,
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
            return jsonify({"ok": True, "summary": js, "pnl_summary": pnl_summary})
        except Exception as e:
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 400

    @app.post("/api/run-parallel/start")
    def api_parallel_start() -> Any:
        """Start batch in a background thread; poll with ``GET /api/run-parallel/status/<job_id>``."""
        data = request.get_json(force=True, silent=True) or {}
        prep = _prepare_parallel_payload(data)
        if not prep["ok"]:
            err_body = {k: v for k, v in prep.items() if k != "ok"}
            return jsonify(err_body), 400
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
            }

        def run_job() -> None:
            session_batch_dir: list[str | None] = [None]

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
                payload = {
                    "ok": True,
                    "ran": len(results),
                    "ok_count": ok_n,
                    "failed_count": len(results) - ok_n,
                    "results": results,
                    "pnl_summary": _batch_pnl_summary(results),
                    "limits_applied": get_parallel_limits(),
                    "workers_used": workers_used,
                    "scenario_validation": {"ok": True, "messages": val_msgs},
                    "session_log_batch_dir": session_batch_dir[0],
                }
                with _JOBS_LOCK:
                    j = _JOBS.get(job_id)
                    if j:
                        j["status"] = "done"
                        j["completed"] = len(results)
                        j["result"] = payload
            except Exception as e:
                with _JOBS_LOCK:
                    j = _JOBS.get(job_id)
                    if j:
                        j["status"] = "error"
                        j["error"] = f"{type(e).__name__}: {e}"

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
        if j["status"] == "done" and j.get("result"):
            out["result"] = j["result"]
        return jsonify(out)

    @app.post("/api/run-parallel")
    def api_parallel() -> Any:
        """Blocking batch run (same work as ``/start`` + poll until done). Prefer ``/start`` for the UI."""
        data = request.get_json(force=True, silent=True) or {}
        prep = _prepare_parallel_payload(data)
        if not prep["ok"]:
            err_body = {k: v for k, v in prep.items() if k != "ok"}
            return jsonify(err_body), 400
        scenarios = prep["scenarios"]
        max_workers = prep["max_workers"]
        log_path = prep["log_path"]
        val_msgs = prep["val_msgs"]

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
            workers_used = clamp_parallel_workers(max_workers, len(scenarios))
            return jsonify(
                {
                    "ok": True,
                    "ran": len(results),
                    "ok_count": ok_n,
                    "failed_count": len(results) - ok_n,
                    "results": results,
                    "pnl_summary": _batch_pnl_summary(results),
                    "limits_applied": get_parallel_limits(),
                    "workers_used": workers_used,
                    "scenario_validation": {"ok": True, "messages": val_msgs},
                    "session_log_batch_dir": session_batch_dir[0],
                }
            )
        except Exception as e:
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 400

    return app


PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Pattern game (local)</title>
  <style>
    :root { font-family: system-ui, sans-serif; background: #0f1419; color: #e7e9ea; }
    body { max-width: 880px; margin: 24px auto; padding: 0 16px; }
    h1 { font-size: 1.25rem; font-weight: 600; }
    h2 { font-size: 1rem; margin-top: 28px; color: #8b98a5; }
    label { display: block; margin: 10px 0 4px; font-size: 0.85rem; color: #8b98a5; }
    input[type=text], input[type=number], textarea, select {
      width: 100%; box-sizing: border-box; padding: 8px 10px;
      border: 1px solid #38444d; border-radius: 6px; background: #15202b; color: #e7e9ea;
    }
    textarea { min-height: 140px; font-family: ui-monospace, monospace; font-size: 0.8rem; }
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
      padding: 12px; overflow: auto; font-size: 0.75rem; max-height: 360px;
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
    input[type=checkbox] { width: auto; }
    input[type=range] { width: 100%; accent-color: #1d9bf0; }
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

  <h1>Pattern game — local prototype</h1>
  <p class="caps">Referee-only scores. Run from repo root with <code>PYTHONPATH</code> set.</p>

  <p class="caps" style="margin-top:16px"><strong>Two options only:</strong> (1) choose a <strong>preset</strong> (pre-filled policy from <code>game_theory/examples/</code>), <strong>or</strong> (2) paste your own scenario JSON in the box. Strategy details and agent story belong in that JSON — not here.</p>

  <label for="presetPick">Preset</label>
  <select id="presetPick" aria-describedby="presetHelp">
    <option value="">— Paste custom JSON below (no preset) —</option>
  </select>
  <p class="caps" id="presetHelp">Selecting a preset fills the textarea. You can edit it afterward. Or ignore the menu and paste only.</p>

  <label for="scenarios">Scenario batch (JSON array)</label>
  <textarea id="scenarios" spellcheck="false" placeholder='[{"scenario_id":"…","manifest_path":"…",…}]'></textarea>

  <label for="workersRange">Workers <span id="workersVal" style="color:#e7e9ea;font-weight:600">1</span></label>
  <input type="range" id="workersRange" min="1" max="64" value="1" step="1" />
  <p class="caps" id="workerHint"></p>
  <div class="row">
    <div>
      <label><input type="checkbox" id="doLog" checked/> Append results to <code>game_theory/experience_log.jsonl</code></label>
    </div>
  </div>

  <button type="button" id="runBtn">Run</button>
  <div id="statusLine" aria-live="polite"></div>
  <div id="progressWrap" class="progress-wrap" role="progressbar" aria-label="Batch replay progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
    <div class="progress-track" id="progressTrack">
      <div class="progress-fill" id="progressFill" style="width:0%"></div>
    </div>
    <p class="caps" id="progressSub"></p>
  </div>

  <h2>Result</h2>
  <p class="caps" id="sessionLogNote" style="margin:0 0 8px 0;color:#8b98a5;"></p>
  <pre id="out">(no run yet)</pre>

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
    document.getElementById('workerHint').textContent =
      'This host: ' + LIMITS.cpu_logical_count + ' logical CPUs · recommended default ' + recommended +
      ' (one process per CPU for CPU-bound replay) · hard max ' + hardMax +
      ' (slider top). Pick fewer if you want headroom; never above max. ' + LIMITS.note;
    rangeEl.addEventListener('input', () => { workersVal.textContent = rangeEl.value; });

    async function show(el, data, err) {
      const pre = document.getElementById('out');
      if (err) { pre.innerHTML = '<span class="err">' + err + '</span>'; return; }
      pre.textContent = JSON.stringify(data, null, 2);
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

    function setProgressUI(completed, total, subtext) {
      const fill = document.getElementById('progressFill');
      const sub = document.getElementById('progressSub');
      const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
      fill.style.width = pct + '%';
      progressWrap.setAttribute('aria-valuenow', String(pct));
      if (subtext) sub.textContent = subtext;
      else sub.textContent = total > 0 ? ('Scenarios ' + completed + ' / ' + total + ' complete (replay is CPU-bound; each bar can take minutes).') : '';
    }

    document.getElementById('runBtn').onclick = async () => {
      const btn = document.getElementById('runBtn');
      btn.disabled = true;
      const sn = document.getElementById('sessionLogNote');
      if (sn) sn.textContent = '';
      statusLine.textContent = 'Starting batch…';
      document.getElementById('progressSub').textContent = '';
      setProgressUI(0, 0, '');
      progressWrap.classList.add('active');
      const t0 = Date.now();
      try {
        let mw = parseInt(rangeEl.value, 10);
        if (isNaN(mw)) mw = null;
        if (mw !== null) {
          mw = Math.max(1, Math.min(mw, LIMITS.hard_cap_workers));
          rangeEl.value = String(mw);
          workersVal.textContent = String(mw);
        }
        const body = {
          scenarios_json: document.getElementById('scenarios').value,
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
        const total = startJ.total || 1;
        statusLine.textContent = 'Running — ' + total + ' scenario(s) · workers ' + (startJ.workers_used || '?') + ' · live progress below.';
        setProgressUI(0, total, 'Queued — waiting for first replay to finish…');

        const pollOnce = async () => {
          const pr = await fetch('/api/run-parallel/status/' + jobId);
          const pj = await pr.json();
          if (!pr.ok) {
            throw new Error(pj.error || 'status failed');
          }
          const elapsed = Math.floor((Date.now() - t0) / 1000);
          const elapsedStr = elapsed >= 60 ? (Math.floor(elapsed / 60) + 'm ' + (elapsed % 60) + 's') : (elapsed + 's');
          if (pj.status === 'running') {
            const c = pj.completed || 0;
            const t = pj.total || total;
            const lm = pj.last_message || '';
            setProgressUI(c, t, lm + ' · elapsed ' + elapsedStr);
            statusLine.textContent = 'Running — ' + c + '/' + t + ' done · ' + elapsedStr + ' elapsed';
            return false;
          }
          if (pj.status === 'error') {
            await show(null, null, pj.error || 'Job failed');
            statusLine.textContent = 'Failed — see Result.';
            setProgressUI(pj.completed || 0, pj.total || total, pj.error || '');
            return true;
          }
          if (pj.status === 'done' && pj.result) {
            const j = pj.result;
            setProgressUI(j.ran || total, j.ran || total, 'All scenarios finished · ' + elapsedStr);
            if (j.pnl_summary) { updatePnlStrip(j.pnl_summary); }
            const sl = document.getElementById('sessionLogNote');
            if (sl) {
              sl.textContent = j.session_log_batch_dir
                ? ('Session logs (human-readable): ' + j.session_log_batch_dir)
                : '';
            }
            await show(null, j, null);
            statusLine.textContent = 'Finished — see Result below.';
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
      .catch(() => {});

    presetPick.onchange = () => {
      const name = presetPick.value;
      if (!name) return;
      loadPreset(name).catch((e) => {
        document.getElementById('out').innerHTML = '<span class="err">' + String(e) + '</span>';
      });
    };
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
