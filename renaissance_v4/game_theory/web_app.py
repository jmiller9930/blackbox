"""
Local web UI for pattern game: **preset or paste** scenario JSON, then Run (parallel workers).

No manifest/ATR fields in the UI — policy lives in the JSON (or examples presets). Default 16 workers
(capped to host). ``POST /api/run`` remains for scripted single-manifest runs.

  pip install -r renaissance_v4/game_theory/requirements.txt
  PYTHONPATH=. python3 -m renaissance_v4.game_theory.web_app

Binds 127.0.0.1 only (prototype).
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
  </style>
</head>
<body>
  <h1>Pattern game — local prototype</h1>
  <p class="caps">Referee-only scores. Bind: 127.0.0.1 · <code>PYTHONPATH</code> = repo root</p>

  <p class="caps" style="margin-top:16px"><strong>Two options only:</strong> (1) choose a <strong>preset</strong> (pre-filled policy from <code>game_theory/examples/</code>), <strong>or</strong> (2) paste your own scenario JSON in the box. Strategy details and agent story belong in that JSON — not here.</p>

  <label for="presetPick">Preset</label>
  <select id="presetPick" aria-describedby="presetHelp">
    <option value="">— Paste custom JSON below (no preset) —</option>
  </select>
  <p class="caps" id="presetHelp">Selecting a preset fills the textarea. You can edit it afterward. Or ignore the menu and paste only.</p>

  <label for="scenarios">Scenario batch (JSON array)</label>
  <textarea id="scenarios" spellcheck="false" placeholder='[{"scenario_id":"…","manifest_path":"…",…}]'></textarea>

  <label for="workers">Workers</label>
  <div class="row">
    <div>
      <input type="number" id="workers" min="1" value="16"/>
      <p class="caps" id="workerHint"></p>
    </div>
    <div>
      <label><input type="checkbox" id="doLog" checked/> Append results to <code>game_theory/experience_log.jsonl</code></label>
    </div>
  </div>

  <button type="button" id="runBtn">Run</button>

  <h2>Result</h2>
  <pre id="out">(no run yet)</pre>

  <script>
    const LIMITS = __LIMITS_JSON__;
    const DEFAULT_UI_WORKERS = 16;

    document.getElementById('workerHint').textContent =
      'Default ' + DEFAULT_UI_WORKERS + ' parallel worker processes (capped to this machine). ' +
      LIMITS.cpu_logical_count + ' logical CPUs · hard cap ' + LIMITS.hard_cap_workers + '. ' + LIMITS.note;

    const wEl = document.getElementById('workers');
    wEl.max = LIMITS.hard_cap_workers;
    wEl.value = Math.min(DEFAULT_UI_WORKERS, LIMITS.hard_cap_workers);

    async function show(el, data, err) {
      const pre = document.getElementById('out');
      if (err) { pre.innerHTML = '<span class="err">' + err + '</span>'; return; }
      pre.textContent = JSON.stringify(data, null, 2);
    }

    document.getElementById('runBtn').onclick = async () => {
      const btn = document.getElementById('runBtn');
      btn.disabled = true;
      try {
        let mw = parseInt(document.getElementById('workers').value, 10);
        if (isNaN(mw)) mw = null;
        if (mw !== null) {
          mw = Math.max(1, Math.min(mw, LIMITS.hard_cap_workers));
          document.getElementById('workers').value = mw;
        }
        const body = {
          scenarios_json: document.getElementById('scenarios').value,
          max_workers: mw,
          log_path: document.getElementById('doLog').checked
        };
        const r = await fetch('/api/run-parallel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const j = await r.json();
        if (!r.ok) { await show(null, null, j.error || JSON.stringify(j)); return; }
        await show(null, j, null);
      } catch (e) {
        await show(null, null, String(e));
      } finally {
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
