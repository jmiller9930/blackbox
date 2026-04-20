# Runtime Failure Trace

## Modules trace

### Endpoint used by the Modules panel

- Frontend banner text starts as `Loading subsystem list…` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L2363).
- Frontend fetch function is `refreshModuleBoard()` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L4019).
- That function calls `fetch('/api/module-board')` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L4035).
- Backend route is `api_module_board()` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L479).
- Backend response is built by `compute_pattern_game_module_board()` in [game_theory/module_board.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/module_board.py#L36) and returned as `{"ok": True, "modules": [...]}` in [game_theory/module_board.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/module_board.py#L304).

### Trace

1. Frontend should execute `refreshModuleBoard();` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L4082).
2. If that runs, it fetches `/api/module-board`.
3. Backend route returns JSON via `jsonify(compute_pattern_game_module_board())` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L482).
4. Frontend then renders rows into `#moduleBoardList` and updates `#bannerModulesV` and `#bannerModulesS` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L4049).

### Answers

- Is fetch triggered: No.
- Does endpoint return valid JSON: Yes.
- Does frontend render: No.

### Conclusion

Modules panel fails because the page script does not parse, so `refreshModuleBoard()` never executes and `/api/module-board` is never requested.

## Run trace

### A. Click handler

- Run button element is `#runBtn` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L2578).
- Click handler assignment is `document.getElementById('runBtn').onclick = async () => { ... }` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L3655).
- Result: handler is not attached because the script fails before reaching that line.

### B. API call

- Request would be sent by `fetch('/api/run-parallel/start', ...)` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L3717).
- Result: request is not sent.

### C. Backend route

- Backend start route is `api_parallel_start()` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L733).
- Success response includes `job_id` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L865).
- Result from UI path: not reached.

### D. Worker

- Background worker thread starts with `threading.Thread(target=run_job, daemon=True).start()` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L864).
- `run_scenarios_parallel(...)` executes inside `run_job()` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L793).
- Result from UI path: not reached.

### E. Polling

- Polling request is `fetch('/api/run-parallel/status/' + jobId)` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L3764).
- Status route is `api_parallel_status(job_id)` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L874).
- Result from UI path: not reached.

### F. Response JSON

- Status route returns JSON through `jsonify(out)` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L906).
- Result from UI path: no polling request is sent, so no status JSON is consumed by the browser.

## Break point

Execution stops at: `click handler not firing`

Exact reason:

- The inline page script fails to parse before the Run button handler and before `refreshModuleBoard()` are reached.
- The parse break is in `renderLiveTelemetryPanel` at [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L2903).
- That line is inside the Python `PAGE_HTML` template. In rendered output, the string literal becomes a real newline inside `lines.join('...')`, producing invalid JavaScript.
- Once the script fails parse, none of the following execute:
  - `refreshModuleBoard();`
  - `document.getElementById('runBtn').onclick = ...`
  - polling and UI updates

Chosen category: `click handler not firing`

## Evidence

### Source evidence from files

- Modules fetch is wired in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L4035).
- Modules fetch kickoff is at [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L4082).
- Run button handler assignment is at [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L3655).
- Start request is at [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L3717).
- Status poll is at [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L3764).
- Inline script parse break location is at [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L2903).

### Runtime evidence from local verification

- `/api/module-board` returns HTTP 200 and valid JSON when called through the Flask test client.
- Rendered page script fails JavaScript syntax check with:

```text
/private/tmp/pg_script.js:229
      el.textContent = lines.join('
                                  ^

SyntaxError: Invalid or unexpected token
```

- That syntax error proves the browser never gets a runnable script bundle from the page HTML.

## Fix

Exact file: [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py)

Exact function: `renderLiveTelemetryPanel` inside the `PAGE_HTML` inline script

Minimal code change only:

```diff
-      el.textContent = lines.join('\n');
+      el.textContent = lines.join('\\n');
```

Why this is the minimal fix:

- The template lives in a Python triple-quoted string.
- `'\n'` becomes an actual newline in the rendered JavaScript source.
- `'\\n'` preserves the backslash-n sequence so the browser receives valid JavaScript `lines.join('\n')`.
