# Student loop — SR-1 **deterministic** closed-trade proof (E2E)

**This README** holds the pinned SR-1 fixture, scripts index, SR-5 bundle pointer, Step 3 API proof, and **§Step 6 — operator runbook** (UI clicks + HTTP).

**Strict SR-1** — this folder implements **strict SR-1**: one **fixed** combination of database + manifest + scenario list such that **≥1 closed trade** is produced **every run** with **no operator tuning**.

## Fixed setup (do not swap ad hoc)

| Component | Path |
|-----------|------|
| **Database** | `runtime/student_loop_lab_proof_v1/sr1_deterministic.sqlite3` (8000 × 5m SOLUSDT bars; rebuilt by script below — deterministic) |
| **Manifest** | `renaissance_v4/configs/manifests/sr1_deterministic_trade_proof_v1.json` |
| **Scenarios JSON** | `runtime/student_loop_lab_proof_v1/scenarios_sr1_deterministic.json` |
| **Fusion floor** | `fusion_min_score: 0.10` on the SR-1 manifest only — **proof** that the fusion/risk/execution path can close trades when an active trend signal exists. Geometric-mean scores stay **below** the default `0.35` floor; this manifest deliberately lowers the floor so the **same** deterministic bar path always clears. **Not** a production tuning recommendation. |

## One command (exit 0 ⇒ ≥1 `replay_outcomes_json`)

From **repository root**:

```bash
export PYTHONPATH="$(pwd)"
python3 scripts/verify_student_loop_sr1.py
```

The script:

1. Builds the fixture DB if missing (`scripts/build_sr1_deterministic_fixture.py`).
2. Sets `RENAISSANCE_V4_DB_PATH` to that file **before** importing replay (see `renaissance_v4/utils/db.py`).
3. Runs one parallel scenario and asserts `len(replay_outcomes_json) >= 1`.

Optional proof file:

```bash
python3 scripts/verify_student_loop_sr1.py --write-proof runtime/student_loop_lab_proof_v1/my_proof.json
```

## Proof artifact

Example committed output: `sr1_verify_proof_sample.json` — includes `replay_outcomes_json_length` (must be ≥ 1).

## Rebuild fixture only (rare)

```bash
python3 scripts/build_sr1_deterministic_fixture.py
```

## Step 2 — SR-5 atomic proof bundle (Run A / B / C)

After SR-1 passes, generate the **single-folder** proof bundle (same pinned DB + scenarios):

```bash
export PYTHONPATH="$(pwd)"
python3 scripts/build_student_loop_sr5_proof_bundle.py
```

**Output:** `runtime/student_loop_lab_proof_v1/sr5_atomic_proof_bundle/` — `run_A.json`, `run_B.json`, `run_C.json`, `scorecard_excerpt.json`, `README.md`, `COMMIT_SHA.txt`, plus an isolated `student_learning_store_proof_bundle.jsonl` used only for this bundle.

The script exits **0** only if **SR-1** (closed trades + seam rows), **SR-2** (A vs B primary seam fields differ when retrieval applies), and **SR-3** (C matches A after store reset) all hold.

## Step 3 — Operator-visible path (AC-2): blocking `POST /api/run-parallel`

Proves SR-2 / SR-3 with the **same HTTP contract** the UI uses for parallel batches (blocking API), not only the SR-5 lab script:

```bash
export PYTHONPATH="$(pwd)"
python3 scripts/verify_student_loop_step3_operator_path.py
```

Sets **`PATTERN_GAME_STUDENT_LEARNING_STORE`** to `step3_operator_path_proof/student_learning_store_step3.jsonl` so the default operator learning file is untouched.

Optional: `--write-proof PATH` — JSON with `gates.sr2_cross_run_difference`, `gates.sr3_reset_matches_run_a`, `gates.ac2_observability_keys`.

---

## Step 6 — Operator runbook (single sequence)

Goal: an operator can reproduce **Run A → Run B → reset Student store → Run C** and **SR-1 closed trades** using either the **Pattern Game UI** or the **same blocking HTTP contract** the UI uses. Deeper contract proofs: SR-5 bundle script (§ above), SR-1 verifier, Step 3 script.

### Pinned inputs (do not swap ad hoc)

| Item | Path / value |
|------|----------------|
| Fixture DB | `runtime/student_loop_lab_proof_v1/sr1_deterministic.sqlite3` (build: `scripts/build_sr1_deterministic_fixture.py`) |
| Scenarios | `runtime/student_loop_lab_proof_v1/scenarios_sr1_deterministic.json` |
| Manifest in scenario row | `renaissance_v4/configs/manifests/sr1_deterministic_trade_proof_v1.json` |

Set **`RENAISSANCE_V4_DB_PATH`** to the absolute path of the fixture DB **before** starting the UI or any script that imports DB-backed replay.

### A) UI — start server

From repository root:

```bash
export PYTHONPATH="$(pwd)"
export RENAISSANCE_V4_DB_PATH="$(pwd)/runtime/student_loop_lab_proof_v1/sr1_deterministic.sqlite3"
python3 -m renaissance_v4.game_theory.web_app --host 127.0.0.1 --port 8765
```

Open **`http://127.0.0.1:8765/`**. Confirm the header shows the current **`PATTERN_GAME_WEB_UI_VERSION`** (capabilities: **`GET /api/capabilities`**).

### B) UI — one batch (custom scenario)

1. **Controls → Pattern:** **Custom (scenario JSON)**.
2. **Evaluation window:** leave as needed; SR-1 scenario row still carries `evaluation_window` (server merge applies).
3. **Upload / strategy:** ensure **no** active uploaded strategy is overriding manifests unless you intend it (`Strategy uploaded (active): NO` and/or leave **Use uploaded strategy** behavior consistent with your run — for proof, use scenario manifest only).
4. **Advanced → Custom scenario (JSON):** paste the contents of `scenarios_sr1_deterministic.json` (a JSON array of scenario objects) into the **Custom scenario** textarea.
5. Click **Run batch** and wait until the run finishes (**Run batch** enabled again; **Results workspace** / **Score card** update).

**Where to look:** **Student → learning → outcome** (primary) for seam summary; **Terminal** (secondary) for engine / DCR telemetry; **Score card** (secondary) for batch history and CSV export.

### C) UI — destructive / clear actions (AC-5)

Use the **Score card** toolbar and callout; do **not** assume one button clears everything.

| Action | What it affects | What it does **not** touch |
|--------|------------------|----------------------------|
| **Clear Card — Run New Experiment** | **`batch_scorecard.jsonl`** (table / history) | Engine memory, bundles, **Student Proctor** JSONL |
| **Reset Learning State** (typed confirm) | Experience / run-memory JSONL, signature **DCR** store, Groundhog bundle file (see confirmation text) | Scorecard file, retrospective log, **Student Proctor** store |
| **Clear Student Proctor store…** (typed confirm) | **Student Proctor** append-only learning JSONL only | Scorecard, engine files |

For **Run A / B / C** with store reset, prefer **Clear Student Proctor store…** between runs when you need an empty store; use **`POST /api/student-proctor/learning-store/clear`** in the API path (Step 3 script).

### D) UI — Step 4 hierarchy proof (optional)

Operator screenshots for SR-4 / AC-3 live under **`runtime/student_loop_lab_proof_v1/step4_ui_proof/`** (filenames `01_` … `04_`).

### E) HTTP — blocking batch (same as UI **`Run batch`**)

The UI submits a parallel batch to **`POST /api/run-parallel`** (blocking). Minimal JSON body:

- **`operator_recipe_id`:** `"custom"`
- **`scenarios_json`:** **string** containing the JSON text of the scenario array (same paste as the textarea)
- **`max_workers`:** `1` (or more)
- **`use_operator_uploaded_strategy`:** **`false`** when no upload should override per-row `manifest_path`

**Canonical automated sequence** (runs A/B/clear/C and asserts gates): **`python3 scripts/verify_student_loop_step3_operator_path.py`** — use this for CI-level proof; it sets **`PATTERN_GAME_STUDENT_LEARNING_STORE`** to an isolated file under `step3_operator_path_proof/`.

**Manual one-off** (server must be running as in §A; DB env set the same way):

```bash
export PYTHONPATH="$(pwd)"
export RENAISSANCE_V4_DB_PATH="$(pwd)/runtime/student_loop_lab_proof_v1/sr1_deterministic.sqlite3"
python3 - <<'PY'
import json
from pathlib import Path
from urllib.request import Request, urlopen

root = Path.cwd()
scenarios = json.loads((root / "runtime/student_loop_lab_proof_v1/scenarios_sr1_deterministic.json").read_text(encoding="utf-8"))
payload = {
    "operator_recipe_id": "custom",
    "scenarios_json": json.dumps(scenarios, ensure_ascii=False),
    "max_workers": 1,
    "use_operator_uploaded_strategy": False,
}
req = Request(
    "http://127.0.0.1:8765/api/run-parallel",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
resp = urlopen(req)
print(resp.status, resp.read()[:4000].decode("utf-8", errors="replace"))
PY
```

Adjust **`127.0.0.1:8765`** if you changed `--host` / `--port`.

### F) Related scripts (repository root)

| Script | Purpose |
|--------|---------|
| `scripts/verify_student_loop_sr1.py` | **SR-1** gate — ≥1 `replay_outcomes_json` |
| `scripts/build_student_loop_sr5_proof_bundle.py` | **SR-5** folder — Run A/B/C + excerpt |
| `scripts/verify_student_loop_step3_operator_path.py` | **AC-2** — **`POST /api/run-parallel`** + store clear |
