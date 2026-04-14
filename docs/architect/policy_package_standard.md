# Policy package standard (Sean → Blackbox)

**Purpose:** One **repeatable shape** for every new baseline Jupiter policy (JUPv3, JUPv4, …) so Sean (or Grok on his spec) can hand engineering a **complete package**, and engineering can **integrate** it without reinventing wiring each time.

**What this is not:** It is **not** “upload policy in the browser and execute.” Blackbox **does not** run unreviewed strings as policy. A policy becomes active only after **merge**, **slot wiring**, **tests**, and **deploy** per governance.

**What “load” means here:** **Load into the system** = accepted package → code review → repo merge → extend `VALID_BASELINE_JUPITER_POLICY_SLOTS` + evaluator + dashboard/ledger hooks → operator can select the new slot when **validated**.

---

## 1. Package layout (recommended)

Deliver as a **folder** in-repo (e.g. under `docs/working/policy_packages/jupv4_sean_momentum/`) or a **zip** with the same structure:

| File | Required | Description |
|------|----------|-------------|
| `POLICY_SPEC.yaml` | **Yes** | Machine-readable identity, slots, inputs, constants summary (see §2). |
| `POLICY_SPEC.md` | Optional | Human narrative: intent, differences vs prior policy, risk stance. |
| `INTEGRATION_CHECKLIST.md` | **Yes** | Copy of §3 checklist with **file paths filled in** for this policy. |
| `jupiter_<N>_sean_policy.py` | **Yes** | Canonical Python evaluator(s); must match repo style and tests. |
| `jupiter_<N>_sean_policy.mjs` | If parity required | Sean mirror; must stay in lockstep with Python. |
| `fixtures/*.json` | Recommended | Tiny synthetic OHLCV fixtures + **expected** gates/signals for parity tests. |

Grok prompt for docstring depth: [`jupv4_grok_implementation_prompt.md`](jupv4_grok_implementation_prompt.md).

---

## 2. `POLICY_SPEC.yaml` (minimum fields)

Use UTF-8. Version the schema:

```yaml
policy_package_version: 1
policy:
  id: jupiter_4_sean_perps_v1          # stable id for catalog / docs
  display_name: "JUPv4 Sean Momentum"
  baseline_policy_slot: jup_v4         # must match new slot constant when wired
  signal_mode: sean_jupiter_v4         # execution_ledger / policy_evaluations (naming aligned with v2/v3)
  catalog_id: jupiter_4_sean_perps_v1
  timeframe: 5m
  instrument: SOL-PERP                 # or canonical symbol string used in code

inputs:
  canonical: ohlcv_lists              # preferred: list[float] aligned with jupiter_3_sean_policy style
  optional_note: "pandas DataFrame allowed only with explicit adapter in bundle"

constants:
  # name: value   # or reference “see module block 1”
  MIN_EXPECTED_MOVE: 0.50

gates:
  - id: volume_spike
    description: "Current bar volume > multiplier × series mean volume"

parity:
  typescript_reference_path: vscode-test/seanv3/…   # or superjup.ts.old — real paths only
  python_module_path: modules/anna_training/jupiter_4_sean_policy.py
```

**Rules:**

- **`baseline_policy_slot`** must eventually appear in **`VALID_BASELINE_JUPITER_POLICY_SLOTS`** (`execution_ledger.py`).
- **`signal_mode`** must be unique and used consistently in **`policy_evaluations`** / bridge code.
- Prefer **`ohlcv_lists`** as the canonical integration surface so **`dashboard_bundle`** and bar loaders do not depend on pandas in the API unless explicitly approved.

---

## 3. Engineering integration checklist (every new policy)

Complete before the operator dropdown may expose the slot:

1. **Ledger / slot**
   - [ ] Add `BASELINE_POLICY_SLOT_JUP_V4` (or equivalent) and `SIGNAL_MODE_JUPITER_4`.
   - [ ] Extend `VALID_BASELINE_JUPITER_POLICY_SLOTS`, `normalize_baseline_jupiter_policy_slot`, `signal_mode_for_baseline_policy_slot`, `baseline_jupiter_policy_label_for_slot`, `baseline_jupiter_policy_tag_from_signal_mode`.

2. **Evaluator**
   - [ ] Implement `modules/anna_training/jupiter_<N>_sean_policy.py` (pure math + structured diagnostics).
   - [ ] Wire **`sean_jupiter_baseline_signal`** (or successor) to call the evaluator for the new slot.

3. **Dashboard / bundle**
   - [ ] Extend **`dashboard_bundle.py`** (and `api_server.py` if needed) for new diagnostics keys / gates labels.
   - [ ] Rebuild **`web`** image if operator-visible HTML/JS changes.

4. **Tests**
   - [ ] Unit tests: fixtures, gate truth, edge cases (insufficient bars, NaN).
   - [ ] Parity tests (if Node mirror): same inputs → same booleans / thresholds.

5. **Docs**
   - [ ] Add `docs/architect/JUPv4.md` (or update master policy doc) with **catalog id**, **slot**, **signal_mode**, **parity** paths.

6. **Proof**
   - [ ] Clawbot / primary host verification per [`execution_context.md`](../runtime/execution_context.md) when the directive requires it.

---

## 4. Relationship to JUPv3

JUPv3 is the **reference** for how policy, slots, and Sean mirrors interact: [`JUPv3.md`](JUPv3.md). New policies must follow the same **hardened slot** model; no silent strings.

---

## 5. Eliminating failure points — “ready to run” from Grok (or any AI)

You cannot remove **every** human step (slot wiring is still a repo change), but you **can** remove **rehash loops** from bad handoffs.

### A. Contract before generation

Give Sean (and Grok) **only**:

1. This document’s **package layout** + **`POLICY_SPEC.yaml`** shape.
2. The Grok instruction block in [`jupv4_grok_implementation_prompt.md`](jupv4_grok_implementation_prompt.md) (generalize the “Sean spec” paste for each policy).
3. **Non‑negotiables:** canonical **`ohlcv_lists`** surface (no pandas‑only API unless you explicitly add an adapter); **no** `signal_mode` strings that don’t match `execution_ledger` naming.

If the model ignores the contract, **reject the package** before integration — don’t “fix” ad hoc in the bridge.

### B. Mechanical gate (before any review)

Run the repo validator on the **folder** Sean returns:

```bash
python3 scripts/validate_policy_package.py docs/working/policy_packages/<your_policy_folder>
```

Requires **`pip install pyyaml`**. The script checks: required files exist, **`POLICY_SPEC.yaml`** parses and has required keys, policy **`.py`** **syntax‑valid**, and warns about missing entrypoint names.

**Pass =** the package is **structurally** eligible. **Fail =** send back to Sean/Grok, not to engineering deep‑merge.

### C. Automated tests (non‑negotiable for merge)

Every policy package should ship **`fixtures/`** + **pytest** that assert:

- Known synthetic OHLCV → **expected** gates / signals (golden vectors).
- Insufficient bars → **fail closed** (no phantom signals).

Add **`pytest`** for that module under `tests/` and wire **CI** (or pre‑merge hook) to run **`validate_policy_package` + `pytest`** on the policy tests. **Green CI =** math is stable; **red =** model or spec drift, not “someone’s opinion.”

### D. One integration PR, not endless edits

After B + C pass, **one** engineering PR does:

- Slot + `signal_mode` + bridge + bundle (checklist §3).
- No more policy logic changes in that PR unless tests fail.

### E. Longer‑term (strongest reduction in AI failure)

If policies stay **parameter‑driven** (same gate shape, different thresholds), move toward **declarative constants in `POLICY_SPEC.yaml` + a small interpreter** in-repo — LLM fills **numbers and descriptions**, not arbitrary Python. That’s **less flexible** but **fewer** ways to break Blackbox.

---

## 6. Revision

| Version | Change |
|---------|--------|
| 1 | Initial standard: package layout, `POLICY_SPEC.yaml`, integration checklist. |
| 2 | §5 failure‑point pipeline: validator script, CI/tests, declarative future note. |
