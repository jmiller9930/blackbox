"""
Local web UI for pattern game: **preset or paste** scenario JSON, then Run (parallel workers).

No manifest/ATR fields in the UI — policy lives in the JSON (or examples presets). Default 16 workers
(capped to host). ``POST /api/run`` remains for scripted single-manifest runs.

  pip install -r renaissance_v4/game_theory/requirements.txt
  PYTHONPATH=. python3 -m renaissance_v4.game_theory.web_app

Default bind is loopback; use ``--host 0.0.0.0`` for LAN/SSH access (prototype).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, request

from renaissance_v4.game_theory.parallel_runner import (
    clamp_parallel_workers,
    get_parallel_limits,
    run_scenarios_parallel,
)
from renaissance_v4.game_theory.pattern_game import _default_manifest_path, json_summary, run_pattern_game
from renaissance_v4.game_theory.scenario_contract import validate_scenarios

_GAME_THEORY = Path(__file__).resolve().parent


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        lim = get_parallel_limits()
        return PAGE_HTML.replace("__LIMITS_JSON__", json.dumps(lim))

    @app.get("/api/capabilities")
    def capabilities() -> Any:
        return jsonify(get_parallel_limits())

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
            return jsonify({"ok": True, "summary": json_summary(out)})
        except Exception as e:
            return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 400

    @app.post("/api/run-parallel")
    def api_parallel() -> Any:
        data = request.get_json(force=True, silent=True) or {}
        raw = data.get("scenarios_json")
        if not raw or not isinstance(raw, str):
            return jsonify({"ok": False, "error": "Missing scenarios_json string"}), 400
        try:
            scenarios = json.loads(raw)
            if isinstance(scenarios, dict) and "scenarios" in scenarios:
                scenarios = scenarios["scenarios"]
            if not isinstance(scenarios, list):
                raise ValueError("scenarios must be a JSON array")
            scenarios = [x for x in scenarios if isinstance(x, dict)]
        except (json.JSONDecodeError, ValueError) as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        for s in scenarios:
            if "manifest_path" in s and s["manifest_path"]:
                s["manifest_path"] = str(Path(s["manifest_path"]).expanduser().resolve())

        if not scenarios:
            return jsonify({"ok": False, "error": "No scenario objects in JSON array"}), 400

        ok_val, val_msgs = validate_scenarios(scenarios)
        if not ok_val:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": val_msgs[0] if val_msgs else "Invalid scenarios",
                        "scenario_validation": {"ok": False, "messages": val_msgs},
                    }
                ),
                400,
            )

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

        try:
            results = run_scenarios_parallel(
                scenarios,
                max_workers=max_workers,
                experience_log_path=log_path,
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
                    "limits_applied": get_parallel_limits(),
                    "workers_used": workers_used,
                    "scenario_validation": {"ok": True, "messages": val_msgs},
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
    input[type=checkbox] { width: auto; }
    input[type=range] { width: 100%; accent-color: #1d9bf0; }
    .progress-wrap { display: none; margin: 12px 0 8px; }
    .progress-wrap.active { display: block; }
    .progress-track {
      height: 8px; border-radius: 4px; background: #38444d; overflow: hidden;
    }
    .progress-indet {
      height: 100%; width: 35%; border-radius: 4px; background: #1d9bf0;
      animation: indet 1.1s ease-in-out infinite;
    }
    @keyframes indet {
      0% { transform: translateX(-100%); }
      100% { transform: translateX(400%); }
    }
    #statusLine { min-height: 1.3em; color: #e7e9ea; font-size: 0.9rem; margin-top: 8px; }
  </style>
</head>
<body>
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
  <div id="progressWrap" class="progress-wrap" role="progressbar" aria-label="Run in progress">
    <div class="progress-track"><div class="progress-indet"></div></div>
  </div>

  <h2>Result</h2>
  <pre id="out">(no run yet)</pre>

  <script>
    const LIMITS = __LIMITS_JSON__;
    const DEFAULT_UI_WORKERS = 16;
    const RUN_TIMEOUT_MS = 7200000;

    const rangeEl = document.getElementById('workersRange');
    const workersVal = document.getElementById('workersVal');
    const statusLine = document.getElementById('statusLine');
    const progressWrap = document.getElementById('progressWrap');

    rangeEl.min = '1';
    rangeEl.max = String(LIMITS.hard_cap_workers);
    rangeEl.value = String(Math.min(DEFAULT_UI_WORKERS, LIMITS.hard_cap_workers));
    workersVal.textContent = rangeEl.value;
    document.getElementById('workerHint').textContent =
      'This host: ' + LIMITS.cpu_logical_count + ' logical CPUs · max workers ' + LIMITS.hard_cap_workers +
      ' (slider). On a 16-core box you can use up to that cap; this server may be smaller — that is the machine limit, not a bug. ' + LIMITS.note;
    rangeEl.addEventListener('input', () => { workersVal.textContent = rangeEl.value; });

    async function show(el, data, err) {
      const pre = document.getElementById('out');
      if (err) { pre.innerHTML = '<span class="err">' + err + '</span>'; return; }
      pre.textContent = JSON.stringify(data, null, 2);
    }

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

    document.getElementById('runBtn').onclick = async () => {
      const btn = document.getElementById('runBtn');
      btn.disabled = true;
      statusLine.textContent = 'Running — replay in progress (often several minutes). This bar moves while the request is active.';
      progressWrap.classList.add('active');
      const ac = new AbortController();
      const tid = setTimeout(() => ac.abort(), RUN_TIMEOUT_MS);
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
        const r = await fetch('/api/run-parallel', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: ac.signal
        });
        const j = await r.json();
        if (!r.ok) { await show(null, null, j.error || JSON.stringify(j)); statusLine.textContent = 'Finished with error — see Result.'; return; }
        await show(null, j, null);
        statusLine.textContent = 'Finished — see Result below.';
      } catch (e) {
        const msg = (e && e.name === 'AbortError')
          ? ('Timed out after ' + (RUN_TIMEOUT_MS / 60000) + ' minutes — run may still be going on the server; refresh or check logs.')
          : friendlyFetchError(e);
        await show(null, null, msg);
        statusLine.textContent = 'Stopped or failed — see Result.';
      } finally {
        clearTimeout(tid);
        progressWrap.classList.remove('active');
        btn.disabled = false;
      }
    };

    fetch('/api/capabilities').then(r => r.json()).then(() => {});

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
