# BLACKBOX / PML — MEMORY + CONTEXT TURNOVER LOG

**Generated (UTC):** 2026-04-20T16:04:18Z  
**Local (authoring host):** 2026-04-20 11:04:18 CDT  
**Environment (proof runs):** clawbot.a51.corp  
**System:** Renaissance V4 Pattern Game (PML)  
**Focus:** Memory + context → decision impact + LLM-facing facts  
**Repo state (local):** `git rev-parse HEAD` → `f49fbe6` (includes run-level memory impact surfacing)

**Verification note:** Section 3.2 below was **corrected** from an earlier draft that used an AND chain on recall counters. The **canonical operator truth** for “did memory/context change decisions?” matches `build_memory_context_impact_audit_v1` in `renaissance_v4/game_theory/learning_run_audit.py` (aggregated from per-scenario `learning_run_audit_v1`).

---

## 1. EXECUTIVE SUMMARY

Resolved ambiguity:

> Does memory/context actually affect trading (replay) decisions?

**Answer:** **Yes** when mechanisms fire (bundle merge and/or recall fusion bias and/or recall signal bias). **No** when those audit counters are all zero—even if memory mode is `read` / `read_write` or records were loaded without a match/apply.

**Product gap (historical):** “Memory active” / “learning active” style signals could **imply** influence without proving it.

**Product response (shipped in tree):** Per-batch **`memory_context_impact_audit_v1`** on `batch_scorecard.jsonl` and `batch_timing`, **Memory / Context Impact** panel in `web_app.py`, Barney + Ask DATA truth line from **`barney_operator_truth_line_v1`**, optional browser **sessionStorage** baseline for trade/PnL delta vs a same-fingerprint memory-OFF run.

---

## 2. CURRENT SYSTEM STATE

### 2.1 Core architecture

- Deterministic replay engine (truth layer)
- Signal modules
- Fusion layer
- Execution / risk handling (ATR paths as configured in manifests)
- Memory / context:
  - **Memory bundles** (pre-run merge when applied)
  - **Decision Context Recall (DCR)** — JSONL, signature match, fusion/signal bias counters
  - **Learning ledger / run memory** — observational; not a hidden self-tuning execution loop in the sense of “gradient learning”

### 2.2 Determinism

- Same manifest + same tape + **same effective memory/recall application** → repeatable results.
- Enabling read/write does **not** guarantee a different path; **matching + apply** does.

---

## 3. MEMORY SYSTEM BREAKDOWN

### 3.1 Types of “memory”

**A. Promoted memory bundle**  
Applied when the harness applies a bundle to the effective manifest (see `memory_bundle_proof` / `memory_bundle_applied` in audit).

**B. Decision Context Recall (DCR)**  
Reads context-signature memory (JSONL), matches windows, increments **`recall_match_windows_total`**, **`recall_bias_applied_total`**, **`recall_signal_bias_applied_total`** when bias paths execute.

**C. Learning ledger / run logs**  
Record outcomes for operators and downstream tooling; **do not** silently rewrite policy on the next bar inside the same contract unless a separate promoted mechanism is wired.

### 3.2 Activation / “impact YES” (canonical — code-aligned)

**`memory_impact_yes_no` = YES** for a completed batch when **any** OK scenario aggregate satisfies **any** of:

- `memory_bundle_applied == true` **or**
- `recall_bias_applied_total` (sum across OK scenarios) **> 0** **or**
- `recall_signal_bias_applied_total` (sum across OK scenarios) **> 0**

**NO** otherwise (including “mode on but zero bundle and zero bias”).

**Important:** Impact YES does **not** require `recall_match_windows_total > 0` as a separate AND—matches are **reported** and should align with bias when both fire, but the **truth gate** for product copy is the three-way OR above (see `learning_run_audit.py`).

**Modes:** `context_signature_memory_mode` must allow recall for DCR paths to run (`read` / `read_write` per harness); bundle apply is a separate proof field.

---

## 4. CRITICAL DISCOVERY (SESSION)

### 4.1 Initial observation

UI / operator view could show memory “on” or loaded while **behavior** matched a deterministic run: **zero** bias apply, **zero** bundle merge.

### 4.2 Root cause

**Loaded ≠ matched ≠ applied.** No signature hit / no bundle merge → no counter movement → no decision path change.

### 4.3 Proof (A/B on UI-equivalent path)

**Path:** `POST /api/run-parallel` (same contract as operator batch).

**Run A — memory/context effectively OFF**

- Recall matches / bias: **0**
- Representative totals (reported during lab session): trades **954**, combined PnL **~9.47** (units as shown in UI)

**Run B — `read_write` with real recall**

- Large **recall_match_windows_total** and **recall_bias_applied_total** (reported: on order of **10⁵** windows in that lab batch)
- Different **validation_checksum**, different **trade count**, different **combined PnL** (reported: **740** trades, **~16.23** PnL)

**Conclusion:** Memory/context **can** move the needle when DCR (and/or bundle) actually applies; otherwise the run is **impact-NO** on audit.

---

## 5. PRODUCT ISSUE (RESOLVED IN REPO)

Mismatch between **capability** and **operator perception** when only “active/loaded” language existed.

### 5.1 Shipped mitigations (this turnover)

| Artifact | Role |
|----------|------|
| `memory_context_impact_audit_v1` | Batch JSONL + `batch_timing`; fingerprint for baseline key |
| Scorecard panel | Counters without opening raw JSON |
| `barney_operator_truth_line_v1` | Mandated YES/NO phrasing for Barney + Ask DATA fallback |
| Ask DATA whitelist | `memory_context_impact_audit_v1` on `scorecard_snapshot` |

**Operator strings (mandated):**

- **NO (read/read_write, zero counters):** “Memory was enabled but had zero impact; this run is deterministic.”
- **YES:** “Memory matched prior context on N windows, applied fusion bias N times, changed the trade set (Δ trades), and altered outcome (Δ PnL).” (N from audit; Δ trades/PnL vs baseline when browser baseline exists.)

---

## 6. LLM INTEGRATION GOAL (UNCHANGED INTENT)

- LLM **does not** replace the engine or invent trades.
- LLM **does** format / explain bounded facts: scorecard, job telemetry, **memory impact audit**, and (where present) **`signal_behavior_proof_v1`** from replay outputs (`replay_runner.py` / pattern game wiring).

**Gap:** Not every operator surface yet bundles **all** proof objects into one “Ask” context; extend deliberately when a directive requires it.

---

## 7. CURRENT LIMITATIONS

- Signal internals remain partially opaque in the UI; **`signal_behavior_proof_v1`** exists in engine outputs for engineering / future bundling.
- Recall **match rate** and “why no match” need scenario/memory design and clear paths—not automatic fixes.
- No closed-loop autonomous policy promotion in PML scope without a future directive.

---

## 8. NEXT PHASE OBJECTIVES (ROLLING)

**Immediate**

- Operator hard-refresh after deploy; confirm panel + JSONL on clawbot at current `main`.
- Keep A/B protocol in `renaissance_v4/game_theory/directives/GT_DIRECTIVE_002_ui_memory_context_proof.md`.

**Near-term**

- Stronger signal-participation storytelling (without breaking engine/policy boundaries).
- Optional server-stored memory-OFF baseline (today: browser sessionStorage fingerprint baseline).

**Long-term**

- Optional closed-loop learning **only** under governance; manifest evolution automation is out of scope unless explicitly authorized.

---

## 9. FINAL TRUTH

The system is **deterministic at core**, **conditionally adaptive** via memory bundles and DCR when counters prove apply, and **honest in UI** when `memory_context_impact_audit_v1` is present: **YES** vs **NO** is from counters, not from “loaded” or “learning lane” alone.

---

## ONE-LINE SUMMARY

> Memory and context are real and functional; they change outcomes when bundle merge or recall bias/signal-bias counters prove application—otherwise the run is impact-NO and deterministic on audit.

---

*End of turnover log.*
