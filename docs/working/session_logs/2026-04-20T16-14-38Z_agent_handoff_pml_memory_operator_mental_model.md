# Agent handoff — PML memory, determinism, operator mental model

**Stamp (UTC):** 2026-04-20T16:14:38Z  
**Stamp (authoring host):** 2026-04-20 11:14:38 CDT  
**Scope:** Long-thread context for turnover to a **new agent** — Pattern Machine Learning (PML) / `renaissance_v4/game_theory`, not UIUX.Web dashboard unless explicitly invoked.

---

## 1. Prior engineering already on `main` (do not redo)

- **Memory/context impact surfacing:** `build_memory_context_impact_audit_v1` in `renaissance_v4/game_theory/learning_run_audit.py`; wired in `batch_scorecard.py`; UI + sessionStorage baseline in `web_app.py`; Barney + Ask DATA in `barney_summary.py`, `ask_data_explainer.py`. **Impact YES** = OR of `memory_bundle_applied`, `recall_bias_applied_total > 0`, `recall_signal_bias_applied_total > 0` (summed OK rows) — **not** “recall matches > 0” AND bias as an AND gate.
- **Turnover log (memory + context product narrative):** `docs/working/session_logs/2026-04-20T16-04-18Z_blackbox_pml_memory_context_turnover.md`
- **Operator proof protocol:** `renaissance_v4/game_theory/directives/GT_DIRECTIVE_002_ui_memory_context_proof.md`
- **Repo HEAD at handoff authoring:** `7a1abe8` (includes turnover doc + prior `f49fbe6` PML UI audit work).

---

## 2. This session — operator questions and answers (journey)

### 2.1 Sandbox / “agent in training” inside the app

**Q:** Can the assistant simulate being an agent in training in a sandbox of this application?

**A:** **No** for an embodied autonomous agent inside the app. Yes only for **operator-style** interaction if a human runs the stack and grants tools (browser/SSH). Do not imply the LLM is the replay “player.”

### 2.2 Confirmation — memory affects outcomes?

**A:** Yes when audit counters prove apply; “mode on” or “loaded” alone is insufficient. Point operators to **Memory / Context Impact** and `learning_run_audit_v1`.

### 2.3 “Multi tries” + same pattern template + same data

**A:** Same recipe + same tape + **same full state** (including memory files after any writes) → **deterministic repeat** — not a random re-roll. Multi-scenario batches or comparison recipes give **new rows / comparisons**, not noise. **`read_write`** can change stored state between runs so **run 2 ≠ run 1** when persistence + match fire.

### 2.4 Operator mental model (user pushback — treat as requirements signal)

The operator described a **narrative**: an agent who only “sees” a short window (e.g. five minutes), plays, gets a score, uses memory “in that iteration”; on a **second** full test they expect **prior knowledge** so **different conclusions** — “you’re wrong” if the system is purely static repeat.

**Reconciliation for the next agent:**

| Their intent | Engine reality |
|--------------|----------------|
| Second lap smarter / different because of first lap | Achieves when **lap 1 persists** (e.g. `read_write` writes to JSONL or bundle evolution) **and** lap 2 **reads** those records with matching signatures so bias/bundle applies. |
| Omniscient re-play (“knows whole trip” on second pass without persisted store) | **Not** the default story of forward replay + DCR; would be a **different product/design** if required. |
| “She” = policy / Referee path | Trades and PnL; memory is **rule-based recall** from store, not human-like reinterpretation. |
| “She” = Anna / LLM | Does **not** drive execution; explain/propose only unless explicitly wired elsewhere. |

**Action:** If the operator still cannot “get what they want,” clarify in one question: **two full replays with persisted memory between them** vs **within-single-replay long-horizon narrative memory** — only the first is aligned with current `read_write` + store design without new features.

### 2.5 Ops — `gsync.py` vs `sync.py`

User corrected: they meant **`python3 scripts/gsync.py`**, not `sync.py`.

- **`gsync.py`:** Commit if dirty, push, remote pull, **restart only if pulled commits touch monitored prefixes** (or `--force-restart`). Pattern-game: `--pattern-game` always restarts Flask on 8765 after pull.
- **`sync.py`:** Unconditional UIUX.Web remote pull + `docker compose build web` + `up -d` + `api` restart.

**Ran:** `gsync.py` when remote already at `7a1abe8` → **no restart** (expected). Earlier **`sync.py --skip-push`** had pulled clawbot `982fb26→7a1abe8` and restarted compose.

**Local Mac:** Docker daemon was **not running** — cannot restart UIUX.Web locally without starting Docker Desktop.

---

## 3. Files the next agent should read first (PML + memory)

| Path | Why |
|------|-----|
| `renaissance_v4/game_theory/learning_run_audit.py` | Impact YES/NO, `memory_context_impact_audit_v1` |
| `renaissance_v4/game_theory/web_app.py` | UI panel, `PATTERN_GAME_WEB_UI_VERSION` |
| `renaissance_v4/game_theory/directives/GT_DIRECTIVE_002_ui_memory_context_proof.md` | Operator A/B protocol |
| `docs/working/session_logs/2026-04-20T16-04-18Z_blackbox_pml_memory_context_turnover.md` | Product + lab narrative |
| `scripts/gsync.py` docstring | Deploy loop semantics |

---

## 4. Open items (no code requested this turn)

- Validate on **clawbot** after deploy: operator sees Memory / Context Impact panel + Barney line (browser hard refresh).
- If architect wants **single-replay “whole trip memory”** semantics, that is a **new directive / design** — do not assume it exists today.

---

*End of handoff log.*
