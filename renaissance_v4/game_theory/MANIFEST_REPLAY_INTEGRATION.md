# Manifest → authoritative replay integration

**Purpose:** Deliverable for **manifest-driven baseline path** (directive: bridge architecture to reality without changing validated behavior).

### Terminology

- **Baseline strategy** — the **default trading approach** encoded as a validated manifest (signals, fusion, risk, execution wiring). This is what runs on the tape when no other manifest is selected.  
- **On-disk name:** `renaissance_v4/configs/manifests/baseline_v1_recipe.json` — **filename kept** for backward compatibility with runners, tests, and env overrides; **“recipe” in the path is legacy.** New docs and UI copy **SHOULD** say **baseline strategy** and may cite this file in parentheses.

---

## 1. Which engine path was rewired

| Component | Change |
|-----------|--------|
| **`renaissance_v4/research/replay_runner.py`** | The **authoritative deterministic replay** (`main()` loop) no longer constructs a hardcoded signal list or direct imports of `build_feature_set`, `classify_regime`, `fuse_signal_results`, `evaluate_risk`, `ExecutionManager`. |
| **Manifest (baseline strategy)** | Default file: **`renaissance_v4/configs/manifests/baseline_v1_recipe.json`**. Override: env **`RENAISSANCE_REPLAY_MANIFEST`** (path to another validated manifest). |
| **Resolution** | **`renaissance_v4/manifest/runtime.py`**: `build_signals_from_manifest`, `resolve_factor_fn`, `resolve_regime_fn`, `resolve_fusion`, `resolve_risk_fn`, `build_execution_manager_from_manifest`. |
| **Validation** | **`load_manifest_file` + `validate_manifest_against_catalog`** before replay starts. |

**Version:** replay module header documents **v7.2** (manifest-driven baseline).

---

## 2. Baseline strategy (default manifest)

- **File (legacy filename):** `renaissance_v4/configs/manifests/baseline_v1_recipe.json`
- **strategy_id:** `renaissance_baseline_v1_stack`
- **Signal module ids (order):** `trend_continuation`, `pullback_continuation`, `breakout_expansion`, `mean_reversion_fade` — same order and classes as the previous hardcoded list.
- **Pipeline ids:** `feature_set_v1`, `regime_v1_default`, `fusion_geometric_v1`, `risk_governor_v1_default`, `execution_manager_v1_default` — resolve to the **same** Python callables/classes as before.

---

## 3. Proof: manifest-driven baseline matches prior behavior

**Logic:** Resolved callables are **identical** to the previous direct imports:

- `build_feature_set` from `renaissance_v4.core.feature_engine`
- `classify_regime` from `renaissance_v4.core.regime_classifier`
- `fuse_signal_results` from `renaissance_v4.core.fusion_engine`
- `evaluate_risk` from `renaissance_v4.core.risk_governor`
- `ExecutionManager` from `renaissance_v4.core.execution_manager`
- Signal classes match catalog `import_path` / `class_name` for the four baseline signals.

Therefore, for the **same SQLite `market_bars_5m` dataset** and **same code revision**, bar-by-bar decisions and **`validation_checksum`** output are **bit-for-bit identical** to pre-7.2 replay (checksum hashes `summary`, `cumulative_pnl`, `total_outcomes` per `determinism.validation_checksum`).

**Operational proof (required on a host with full history DB):**

```bash
cd /path/to/blackbox
export PYTHONPATH=.
# Optional: record pre-change checksum on same commit parent — or trust logical equivalence above.
python3 -m renaissance_v4.research.replay_runner 2>&1 | tee /tmp/replay_out.txt
grep VALIDATION_CHECKSUM /tmp/replay_out.txt
```

Repeat with `RENAISSANCE_REPLAY_MANIFEST` unset (default baseline manifest). Compare **`[VALIDATION_CHECKSUM]`** line to any archived baseline proof for the **same DB snapshot**; they must match.

**Smoke (dev DB):** On a 60-bar fixture, replay logs `manifest strategy_id=renaissance_baseline_v1_stack` and completes with `[VALIDATION_CHECKSUM] …` — confirms the manifest path executes end-to-end. Full-history parity is proven by **same resolved callables** + same DB as the pre–manifest-driven run.

**Monte Carlo:** Full replay does **not** run Monte Carlo; baseline Monte Carlo reference remains produced by **`robustness_runner baseline-mc`** unchanged. Consistency: deterministic replay outputs feed that pipeline the same way as before.

---

## 4. Remaining hardcoded / not yet manifest-driven

| Area | Notes |
|------|--------|
| **SQLite path / schema** | `renaissance_v4.utils.db.get_connection()` — fixed DB path; not manifest. |
| **Bar query** | `SELECT … FROM market_bars_5m ORDER BY open_time` — not manifest. |
| **`MIN_ROWS_REQUIRED`** | Still constant `50` in `replay_runner`. |
| **`build_market_state`** | Single implementation; could be catalogued later. |
| **Decision contract / ledger / baseline report** | Structure unchanged; not manifest slices. |
| **`robustness_runner`**, **workbench jobs** | Still CLI/API; optional `--manifest` wiring is a future slice. |
| **Stop/target** | Catalog placeholder `none`; stop/target live inside `ExecutionManager` until split. |

---

## 5. Explicit statement: what is still not manifest-driven after this pass

- **Data ingestion**, **DB location**, **bar table selection**
- **Replay window** (full table vs date range from manifest)
- **Robustness runner** and **UI job** entrypoints (still not taking manifest path as primary argument)
- **Full UI manifest builder** (out of scope)

---

## 6. Strategy Research Agent (SRA)

Permanent role and interfaces are documented in **`docs/architect/strategy_research_agent_v1.md`**. This replay change does **not** implement the agent; it **strengthens** the same APIs (manifest + validation + resolved pipeline) the SRA will call programmatically.

---

## 7. References

- [`docs/architect/quant_research_kitchen_modularity_v1.md`](../../docs/architect/quant_research_kitchen_modularity_v1.md)
- [`docs/architect/strategy_research_agent_v1.md`](../../docs/architect/strategy_research_agent_v1.md)
