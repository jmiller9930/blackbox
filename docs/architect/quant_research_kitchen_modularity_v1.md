# Quant Research Kitchen V1 — modular, manifest-driven strategy system

**Status:** Normative engineering direction (permanent layer).  
**Rule:** New factors, signals, regime logic, and risk models are added as **plug-ins** and registered in the **catalog**; strategy **recipes** are **manifests**. The **core replay and validation engine** stays one authoritative path.

---

## 1. Modular architecture summary

| Layer | Role | Stability |
|-------|------|-----------|
| **Core engine** | Historical load, deterministic replay, feature **interface**, fusion/risk/execution **interfaces**, outcomes, reporting, Monte Carlo, baseline comparison, validation gates | **Stable** — not rewritten per strategy |
| **Plug-in layer** | Factors (feature pipelines), signals, regime classifiers, risk models, fusion engines, execution templates, stop/target templates (future) | **Extensible** — add modules + catalog entries |
| **Manifest layer** | JSON recipe: which modules to run, symbol/timeframe/range, experiment type, Monte Carlo config, baseline reference | **What varies** per run — SME-facing |

**Principle:** *One engine, many recipes.* Different strategies enter through **configuration and module selection**, not duplicate engines.

**Implementation anchor (v1 skeleton):**

- Plugin catalog: [`renaissance_v4/registry/catalog_v1.json`](../../renaissance_v4/registry/catalog_v1.json)
- Manifest schema: [`renaissance_v4/schemas/strategy_manifest_v1.schema.json`](../../renaissance_v4/schemas/strategy_manifest_v1.schema.json)
- Validation + resolution: [`renaissance_v4/manifest/`](../../renaissance_v4/manifest/)
- Example manifests: [`renaissance_v4/configs/manifests/`](../../renaissance_v4/configs/manifests/)

---

## 2. Registry structure (proposed and implemented as v1 skeleton)

Registries are **data-first**: `catalog_v1.json` lists module **id**, **version**, **import path**, **class or callable name**, and **contracts** (required inputs, outputs). Code implements the module; the catalog declares it **approved** for manifest resolution.

| Registry key | Contents |
|----------------|----------|
| `factor_pipelines` | Callables producing `FeatureSet` from `MarketState` |
| `signals` | Classes extending `BaseSignal` |
| `regime_classifiers` | Callables `classify_regime(features) -> str` |
| `risk_models` | Callables `evaluate_risk(...)` |
| `fusion_engines` | Callables `fuse_signal_results(...)` |
| `execution_templates` | Classes such as `ExecutionManager` |
| `stop_target_templates` | Placeholder until split from execution manager |
| `allowed_experiment_types` | Governed experiment class names |

Adding a plug-in: implement the class/callable → add one JSON object → validate manifests reference the new **id**.

---

## 3. Manifest schema (v1)

- **Machine-readable:** [`strategy_manifest_v1.schema.json`](../../renaissance_v4/schemas/strategy_manifest_v1.schema.json) (JSON Schema).
- **Fields:** `strategy_id`, `strategy_name`, `baseline_tag`, `symbol`, `timeframe`, optional date range, `factor_pipeline`, ordered `signal_modules[]`, `regime_module`, `risk_model`, `fusion_module`, `execution_template`, optional `stop_target_template`, `monte_carlo_config`, `experiment_type`, `notes`.

Processing must **validate** (see below) before replay.

---

## 4. Example manifests

| File | Purpose |
|------|---------|
| [`baseline_v1_recipe.json`](../../renaissance_v4/configs/manifests/baseline_v1_recipe.json) | Current **RenaissanceV4** locked stack as a manifest (matches `replay_runner` signal list). |
| [`candidate_robustness_compare.json`](../../renaissance_v4/configs/manifests/candidate_robustness_compare.json) | **Conceptual** recipe for a robustness compare — same stack; compare harness still uses candidate JSON path (extended wiring in a later slice). |

Validate locally:

```bash
cd /path/to/blackbox && export PYTHONPATH=.
python3 -m renaissance_v4.manifest renaissance_v4/configs/manifests/baseline_v1_recipe.json
```

---

## 5. Code plan — plug-ins enter the engine without rewriting it

1. **Done (v7.2):** [`replay_runner.py`](../../renaissance_v4/research/replay_runner.py) loads **`baseline_v1_recipe.json`** (or `RENAISSANCE_REPLAY_MANIFEST`), validates, then uses **`build_signals_from_manifest`** and **`resolve_*` / `build_execution_manager_from_manifest`** for the full bar loop. **Integration note:** [`MANIFEST_REPLAY_INTEGRATION.md`](../../renaissance_v4/game_theory/MANIFEST_REPLAY_INTEGRATION.md).

2. **Next:** Robustness runner / workbench jobs — optional manifest path in job payload; validate before subprocess; pass `--manifest` when runner supports it.

3. **No second replay engine:** Single deterministic replay file; behavior differences come from manifest + catalog only.

---

## 6. Manifest rules (governance)

Before replay or compare:

- Manifest schema and `schema` / `manifest_version` must match supported v1.
- Every module id must exist in `catalog_v1.json`.
- `experiment_type` must be in `allowed_experiment_types` (extend catalog when adding new governed types).

Malformed manifests **fail before replay** ([`validate.py`](../../renaissance_v4/manifest/validate.py)).

---

## 7. SME operating model (target)

- Work with **manifests** (load, duplicate, tweak **approved** module ids) — not source edits for normal recipe exploration.
- Launch experiments from the workbench using **governed** types; exports remain artifact-based.

**Not in scope for this thesis pass:** full UI manifest builder, arbitrary formulas, browser code injection.

---

## 8. Module compatibility (direction)

v1 validation checks **registry membership** and **allowed experiment types**. Finer rules (e.g. signal ↔ regime compatibility matrices) are **catalog metadata** fields (`compatible_regimes`) for future validators.

---

## 9. Non-goals (unchanged)

Arbitrary formula editor, unrestricted strategy creator, baseline promotion in UI, live trading from kitchen, uncontrolled ML — see [`quant_research_kitchen_v1.md`](quant_research_kitchen_v1.md) §10–11 and project governance.

---

## 10. Strategy Research Agent (SRA)

The **Strategy Research Agent** will operate this kitchen via the same **manifest**, **registry**, and **experiment APIs** — assembling candidate recipes, submitting jobs, reading artifacts, comparing to baseline, emitting **advisory** recommendations. She is **not** authorized to promote baselines or bypass validation. **Permanent role definition:** [`strategy_research_agent_v1.md`](strategy_research_agent_v1.md).

---

## 11. Related

- Parent frame: [`quant_research_kitchen_v1.md`](quant_research_kitchen_v1.md)
- Product/API v1: [`renaissance_v4/WORKBENCH_V1.md`](../../renaissance_v4/WORKBENCH_V1.md)
- SRA role: [`strategy_research_agent_v1.md`](strategy_research_agent_v1.md)
