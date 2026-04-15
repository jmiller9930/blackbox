# BlackBox policy system and Quant Research Kitchen — engineering integration write-up

**Audience:** Architect, engineering, operators planning Kitchen ↔ BlackBox alignment.  
**Intent:** One place that answers how policy works **today**, how assignment works, how the **standardized policy package** fits in, what a **Kitchen manifest** must become to run in BlackBox, and what **activation boundary** means (as implemented vs target).  
**This is not a code change** — alignment and unknown-reduction only.

**Deeper references:** [`policy_package_standard.md`](policy_package_standard.md) (binding contract), [`DV-ARCH-INTAKE-021_blackbox_engine_policy_kitchen_alignment.md`](DV-ARCH-INTAKE-021_blackbox_engine_policy_kitchen_alignment.md) (detailed as-is engine), [`policy_activation_lineage_spec.md`](policy_activation_lineage_spec.md) (target activation + lineage), **[`policy_wiring_surface_map_v1.md`](policy_wiring_surface_map_v1.md)** (all surfaces — functions, tables, failure modes).

---

## 0. Product rule — Kitchen-first before live assignment (DV-ARCH-POLICY-LOAD-028)

**Binding intent:** No policy is assigned to the **live** BlackBox baseline slot until it has completed **Quant Research Kitchen** evaluation on the **single canonical** submission pipeline. Dashboard and Kitchen must **not** diverge into separate “quick load” vs “research load” backends.

**Canonical path (conceptual):** policy package → validation → replay → Monte Carlo → baseline comparison → artifact generation → **approval / eligible state** → **only then** activation via BlackBox assignment.

**Dashboard UX:** Any control that submits a policy must read as **evaluation** (e.g. “Submit for Kitchen evaluation”), **not** immediate activation. Wording that implies “Load / Activate / Apply” is reserved for policies already **approved for activation**.

**Unified backend:** One ingestion and evaluation process serves both the main dashboard and Kitchen; implementation must route dashboard submissions into that pipeline.

**Explicit states (target):** e.g. `submitted` → … → `approved_for_activation` → `activated`. Policies below **`approved_for_activation`** must not be assignable to the live slot.

**Full directive:** [`DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md`](DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md).

**As-is note:** §1–§2 below describe **current** code paths (merged Python, operator KV + **activation log** for execution-effective slot). Full **Kitchen gate** for **new policy packages** (persisted states through `approved_for_activation`) is **not** yet enforced in API/UI for arbitrary uploads; **documentation** states the rule; **enforcement** for package submit is tracked under [DV-ARCH-POLICY-LOAD-028](DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md) §13.

**Canonical package ingest (replay slice):** `renaissance_v4/research/policy_package_ingest.py` — validation → `run_manifest_replay` path (**DV-ARCH-POLICY-INGESTION-024-A**).

---

## 1. How the current BlackBox policy system works

**Core idea:** Baseline “Jupiter” policies are **implemented as reviewed Python** in `modules/anna_training/` (e.g. `jupiter_4_sean_policy.py` for JUPv4). The runtime **imports** that code; it does **not** interpret arbitrary strategy scripts from the database or browser.

**What a policy does:** On each evaluation, it receives an ascending list of **closed** OHLCV bars (`bars_asc`), computes indicators and gates in code, and returns a structured result: **trade or not**, **side** (long / short / flat), **reason_code**, and a rich **`features`** dict (diagnostics, gates, optional `position_size_hint`, catalog/engine ids, parity markers).

**Where it plugs in:** The **baseline ledger bridge** (`baseline_ledger_bridge.py`) loads bars (from `market_bars_5m` for Jupiter_2, or **`binance_strategy_bars_5m`** for Jupiter_3 / Jupiter_4), resolves the **active policy slot**, calls the matching evaluator (`evaluate_sean_jupiter_baseline_v4`, etc.), upserts **`policy_evaluations`**, and runs **shared lifecycle** (virtual SL/TP, breakeven, trail) via `jupiter_2_baseline_lifecycle.py` when a position is open or a new signal opens one.

**Persistence:** Outcomes land in **`execution_ledger.db`**: e.g. `policy_evaluations` (per `market_event_id`, `signal_mode`, lane/strategy), baseline open state, `execution_trades`, traces — see the intake doc for schema-oriented detail.

**Anti-drift mantra for research:** Same **ordered bars** + same **evaluator code** + same **lifecycle constants** → comparable results; align on **`market_event_id`** and bar table for JUPv3/JUPv4.

---

## 2. How a policy is assigned (operator → engine)

**Selector:** Exactly **one** active **baseline Jupiter policy slot** at a time for baseline signal math: **`jup_v2`**, **`jup_v3`**, or **`jup_v4`**.

**Resolution (execution — which evaluator runs):** `resolve_baseline_jupiter_policy_for_execution()` — **active** row in `policy_activation_log` when present, else pending’s **previous** effective slot, else legacy KV/env (**DV-ARCH-POLICY-ACTIVATION-023**).

**Operator / display preference (KV):** `get_baseline_jupiter_policy_slot()` — reads **`baseline_operator_kv`** for the dashboard label, then env, then default `jup_v2`.

**Activation scheduling:** Dashboard **POST** `/api/v1/dashboard/baseline-jupiter-policy` enqueues **pending** activation (and does **not** treat built-in slot change as a Kitchen **package** submit). See [LOAD-028](DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md) §3.4 — this is **not** a substitute for evaluating a **new** policy package.

Invalid slot strings are **rejected** (warning, fallback) — not silently mapped to a random policy.

**Signal mode:** Each slot maps to a distinct **`policy_evaluations.signal_mode`** string (e.g. `jup_v4` → `sean_jupiter_v4`) for attribution and joins.

**Code vs selection:** **Assignment** chooses **which compiled policy module family** runs. **Changing** the slot does not load new logic from SQLite; new logic requires **merged code** (new module + wiring) and deploy/restart as usual.

**Open state:** Baseline open positions are keyed including **`policy_slot`** so different policies do not share the same persisted open state.

**Anna parallel runner:** Uses the **same** active baseline slot for the **gating signal**, then may write multiple Anna strategy rows — still one policy math for that signal.

---

## 3. How the standardized policy builder works (policy package)

**Governance:** [`policy_package_standard.md`](policy_package_standard.md) is the **mandatory contract** for new Jupiter baseline policies (JUPv3, JUPv4, …): not optional background reading.

**What “standardized” means here:**

| Piece | Role |
|-------|------|
| **Folder layout** | `POLICY_SPEC.yaml`, optional `POLICY_SPEC.md`, `INTEGRATION_CHECKLIST.md`, canonical Python `jupiter_<N>_sean_policy.py`, optional `.mjs` mirror, `fixtures/` |
| **`POLICY_SPEC.yaml`** | Machine-readable **identity**: `policy.id`, `baseline_policy_slot`, **`signal_mode`**, `catalog_id`, timeframe, instrument, inputs, constants/gates summary, parity paths |
| **Mechanical validation** | `python3 scripts/validate_policy_package.py <package_dir>` — structure, YAML keys, Python syntax (PyYAML required) |
| **Engineering checklist** | Extend `VALID_BASELINE_JUPITER_POLICY_SLOTS`, `signal_mode` mapping, evaluator, `sean_jupiter_baseline_signal`, `dashboard_bundle` / API if needed, tests, docs, deploy proof |

**Explicit non-goal:** BlackBox **does not** “upload and execute” unreviewed policy strings. **Activation** in this doc means **merge + wire + operator selects slot** for **built-in** baseline policies, not a runtime sandbox for arbitrary code. **Product rule:** new/custom policy packages destined for the **live** slot must go through **Kitchen evaluation first** ([DV-ARCH-POLICY-LOAD-028](DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md)); dashboard submission = **send to Kitchen**, not instant live load.

**Future direction (documented in the standard):** Parameter-only policies may move toward **declarative constants + a small interpreter**; full flexibility stays in **reviewed code** until then.

---

## 4. What a Kitchen manifest needs to become a BlackBox policy

A Kitchen manifest is useful as **research and validation** input. For BlackBox to run the same behavior **safely** and **reproducibly**, the path today is:

1. **Translate into a policy package** that satisfies [`policy_package_standard.md`](policy_package_standard.md): at minimum **`POLICY_SPEC.yaml`** fields aligned with a **real** `baseline_policy_slot` and **`signal_mode`** that engineering will register, plus the **canonical Python evaluator** (and optional TS mirror if parity is required).

2. **Implement evaluation on the canonical surface:** OHLCV as **lists / bar dicts** matching `bar_lookup` and policy modules — not pandas-only unless an adapter is explicitly added.

3. **Merge + wire:** New slot constant + bridge + `sean_jupiter_baseline_signal` branch + tests + golden fixtures (see checklist). **No** silent new slot strings.

4. **Prove parity:** Same inputs → same trade/side and key diagnostics as persisted in **`policy_evaluations.features_json`** for the target `market_event_id` and bar source.

5. **Lifecycle honesty:** If Kitchen backtests include exits, they must either use the **same** `jupiter_2_baseline_lifecycle` rules (SL/TP/trail) or document **explicit deltas** — entry-only parity is not full PnL parity.

**Metadata that should travel with the manifest** (for traceability and future activation): policy name, stable **id** / version, **catalog_id**, target **slot**, **evaluator** identity, **sizing model**, **provenance** (Kitchen run id, validation report). The **policy_activation_lineage_spec** lists a fuller metadata set for when activation is productized.

---

## 5. Activation boundary for a newly loaded policy

**Two layers:**

### 5.1 As implemented today

- **No** separate “pending policy until boundary” state machine in the ledger.
- When the operator **changes** the slot (KV or env), the **next** bridge tick that reads the ledger typically uses the **new** slot on the **next** evaluation pass.
- Evaluation is already **closed-bar**-oriented (signal on completed candles), which reduces intrabar ambiguity for **entries**.
- **Lineage nuance:** Historical rows keep their original **`signal_mode`** / snapshots; the **selector** does not rewrite past `policy_evaluations`. What is **not** yet first-class is “pending load → explicit effective **`market_event_id`**” for dashboard copy and audit.

### 5.2 Target (recommended product — see [`policy_activation_lineage_spec.md`](policy_activation_lineage_spec.md))

- **Apply on next closed evaluation boundary:** user selects a policy → system stores **pending** → first evaluation that counts uses the **next closed bar** (or next eligible event) → **first** tile/trades after that boundary are attributed to the **new** policy.

- **Why:** Avoids mid-bar “instant apply” and keeps **forward-only, lineage-aware** attribution so the dashboard does not lie about which policy produced which outcome.

**Engineering takeaway:** Until the target is implemented, treat “activation boundary” as **implicit** (next tick after KV change, on closed-bar evaluation) and document any **operator-facing** UX gap; **implement** explicit pending/effective boundary when the architect signs off on schema + API.

---

## 6. Summary table (architect ask → where it lives)

| Question | Answer in this doc | Canonical detail |
|----------|-------------------|------------------|
| How does the policy system work? | §1 | [`DV-ARCH-INTAKE-021_blackbox_engine_policy_kitchen_alignment.md`](DV-ARCH-INTAKE-021_blackbox_engine_policy_kitchen_alignment.md) |
| How is policy assigned? | §2 | `execution_ledger.py`, `baseline_operator_kv` |
| How does the standardized builder work? | §3 | [`policy_package_standard.md`](policy_package_standard.md), `scripts/validate_policy_package.py` |
| Manifest → BlackBox policy? | §4 | Same + integration checklist |
| Activation boundary? | §5 | [`policy_activation_lineage_spec.md`](policy_activation_lineage_spec.md) |

---

## 7. Revision

| Version | Change |
|---------|--------|
| 1 | Initial integration write-up for architect/engineering (single doc). |
| 2 | §0 Kitchen-first product rule (**DV-ARCH-POLICY-LOAD-028**); §3 non-goal aligned. |
