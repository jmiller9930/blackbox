# v1 training governance — implementation artifact (Training Architect / Advisor)

**Repo:** BLACK BOX  
**Contract ID:** `blackbox_v1_training_semantics_2026`  
**Code:** `UIUX.Web/api_server.py` — `V1_GOVERNANCE_CONTRACT`, dashboard + `/api/v1/anna/training-dashboard`

---

## What was implemented (product + API)

- **Dashboard copy** no longer implies “PASS = durable skill.” The Grade-12 line uses **QUALIFIED (provisional)** / **NOT QUALIFIED** with a **v1 governance** subtitle.
- **Scorecard “Grade-12 gates”** shows **`pass_label_v1`**: `QUALIFIED (provisional)` or `NOT QUALIFIED` (falls back to PASS/NOT PASS only if the field is missing).
- **New collapsible:** “Governance — v1 PASS semantics (contract)” with the full **`v1_governance_contract`** JSON (same as API).
- **API payload** includes **`v1_governance_contract`** (machine-readable contract text) and **`gates.pass_label_v1`**.
- **`training_run_digest`** includes **`grade12_bar_title`** and **`grade12_bar_subtitle`** for clients that render their own UI.

---

## Before vs after (operator-visible)

| Surface | Before | After |
|--------|--------|--------|
| Digest bar (when gate satisfied) | “Grade-12 training bar: **PASS**” | “Grade-12 gate: **QUALIFIED (provisional)**” + subtitle explaining provisional / drift |
| Digest bar (when not satisfied) | “Grade-12 training bar: **NOT PASS**” | “Grade-12 gate: **NOT QUALIFIED**” + subtitle (operator-driven improvement; no hard reset required) |
| Scorecard gate cell | **PASS** / **NOT PASS** | **QUALIFIED (provisional)** / **NOT QUALIFIED** |
| Lead paragraph | Generic refresh text | States **v1 governance**: PASS = *qualified (provisional)*, not universal trust |
| API | No contract object | **`v1_governance_contract`**, **`gates.pass_label_v1`**, digest bar fields |

**Unchanged:** Gate **logic** (`evaluate_grade12_gates`) — same thresholds; only **labels and explicit contract** changed.

---

## Hard reset vs soft reset boundary (architect intent)

- **Hard reset** = wipe runtime training files (e.g. `flush-runtime --yes`) so the **ledger** and **state** start clean. **Not required** to adopt the v1 **wording** contract; use only if you **want** a clean evidence file or to remove bad history.
- **Soft reset boundary** = **no data wipe**: agree a **baseline** (date, iteration, or “contract effective” moment) so **reporting** and **expectations** separate **pre-contract** vs **post-contract** narratives. Optional: evaluate **new windows** (e.g. rolling metrics from baseline) **without** deleting existing rows.

Existing **data** remains valid historical evidence; **semantics** of what PASS **means** are now explicit in UI/API.

---

## Verification

1. Open Anna training dashboard → confirm new lead text, digest titles, Governance panel JSON.
2. `GET /api/v1/anna/training-dashboard` → confirm `v1_governance_contract`, `gates.pass_label_v1`, `training_run_digest.grade12_bar_title`.

---

## Handoff

This file is the **artifact** for the Training Architect Advisor to show that **governance wording is implemented**, not only discussed.
