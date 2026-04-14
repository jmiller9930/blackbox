# Quant Research Kitchen V1 — architecture

**Status:** Normative product + platform thesis (governed research, not ad hoc).  
**Route (v1):** `/dashboard.html#/renaissance` — display name **Quant Research Kitchen V1**; implementation path remains `renaissance_v4/`.

---

## 1. Definition

**Quant Research Kitchen V1** is the formal name for the BlackBox **governed, web-based strategy research and validation platform**. It is not a single-strategy project.

**RenaissanceV4_baseline_v1** is the **first validated recipe** (locked baseline) inside this kitchen. The **RenaissanceV4** codebase (replay, robustness runner, Monte Carlo, reports) is the **validation engine** behind the kitchen.

### Modular, manifest-driven system (engineering direction)

The kitchen must evolve as a **modular, manifest-driven** strategy system: **core engine stable**, **plug-ins** (factors, signals, regime, risk, execution templates) **registered**, **strategy runs defined by manifest**. New behavior is added via plug-ins and catalog entries — not by forking replay. **Permanent spec:** [`quant_research_kitchen_modularity_v1.md`](quant_research_kitchen_modularity_v1.md) (registry, manifest schema, examples, integration plan).

---

## 2. System identity

The platform is a **research kitchen** where users can, within governance:

- Assemble strategy **recipes** (bounded, not arbitrary code-from-browser).
- Run **deterministic backtests** (authoritative).
- Run **Monte Carlo** stress tests (shuffle, bootstrap; not primary truth).
- Analyze results, **compare to the locked baseline**, **export** outputs, and iterate **reproducibly**.

**Implementation surface (v1):** `UIUX.Web/dashboard.html` (workbench view), `UIUX.Web/api_server.py` (Renaissance API routes), `renaissance_v4/ui_api.py`, `renaissance_v4/research/robustness_runner.py`. Operator doc: [`renaissance_v4/WORKBENCH_V1.md`](../../renaissance_v4/WORKBENCH_V1.md).

---

## 3. Core subsystems (architectural map)

### 3.1 Data fabric

- Historical OHLCV and related bars (e.g. Binance ingestion into SQLite where applicable).
- Live reference feeds — **Pyth** remains part of the standard data layer for operational BlackBox surfaces.
- **Direction:** extensible symbols and time ranges; expansion is **intentional and documented** (storage allows growth; ingestion must stay governed).

### 3.2 Factor / signal library

- Reusable factors (trend, volatility, mean reversion, structure, volume) — **selectable and composable** in principle.
- **Governed:** no arbitrary user code from the browser; changes flow through **bounded experiments** and harness paths, not ad hoc mutation.

### 3.3 Replay + execution engine

- **Deterministic replay** is authoritative for trade generation and outcome tracking.
- **No divergence** from the locked baseline logic path for baseline validation; experiments are **separate** runs with declared scope.

### 3.4 Robustness layer

- **Monte Carlo** (shuffle + bootstrap) over closed-trade PnL sets; clearly labeled (no “MC” shorthand in operator copy).
- **Direction:** sensitivity testing, drawdown and distribution analysis; parameter sweeps and rolling windows as **near-term** harness work where directed.

### 3.5 Workbench UI

- Baseline visibility, **Monte Carlo** reference status, **approved experiment** launcher, **experiment queue**, **detail + comparison vs baseline**, **report links** (markdown artifacts), **CSV export** from **stored artifacts** (not recomputed ad hoc at click time).

---

## 4. Operator / SME model

**May:** access via web, inspect baseline, run **approved** experiments, analyze results, export data.

**Must not:** mutate baseline logic, inject arbitrary code, bypass validation gates, or promote baselines from the UI. **Architect approval** remains outside the browser for promotion.

---

## 5. Experiment lifecycle (normative)

```
baseline → experiment → validation → comparison → recommendation → optional promotion (governed, not in UI v1)
```

**Rules:**

- Baseline is **immutable**.
- Experiments are **bounded**; prefer **one subsystem change** per experiment where practical.
- Runs must be **reproducible**; results **persisted** (JSON, markdown, index).

---

## 6. Version 1 scope (strict)

Included: baseline inspection (metrics + links), Monte Carlo clearly spelled out, queue + detail, approved launcher, CSV exports, markdown report access.

**Not v1:** arbitrary strategy builder UI, freeform prompt strategy creation, **baseline promotion in UI**, **live trading** from this surface, **uncontrolled ML** experimentation.

**XLSX:** optional after CSV if justified.

---

## 7. Quant toolset (orientation)

| Horizon | Examples |
|--------|------------|
| **Immediate** | Deterministic replay, Monte Carlo, signal/regime breakdowns, risk-tier breakdowns, stop vs target analysis (as harness exposes) |
| **Near-term** | Parameter sweeps, sensitivity analysis, rolling windows, contribution analysis |
| **Future** | Clustering / regime discovery, anomaly detection, ML-assisted ranking, walk-forward validation |

All tools must **pass through governed validation** (replay + Monte Carlo where applicable).

---

## 8. Machine learning policy

ML is approved as a **future subsystem** only when:

- **Governed** and **validated** through replay + Monte Carlo (and project proof standards).
- Treated as a **feature / ranking layer**, not a substitute for validation discipline.
- **No** ML-driven strategy promotion without full validation and architect process.

---

## 9. Exports (non-negotiable)

Per completed experiment (when artifacts exist): trade list CSV, summary metrics CSV, Monte Carlo summary CSV, markdown report access. **Sources:** stored artifacts on disk, not recomputed on demand.

---

## 10. Non-goals (do not implement in v1)

See §6 and project governance: no freeform strategy builder, no browser code editing, no baseline promotion controls, no live execution from this workbench.

---

## 11. Success criteria (this thesis)

- Dashboard shows **Quant Research Kitchen V1**; SME reaches it via the existing route.
- Baseline is visible and inspectable; experiments launchable and trackable; results viewable and exportable; system **governed** and **reproducible**.

---

## 12. Strategy Research Agent (SRA)

A **first-class architectural role** — the governed **research conductor** for the kitchen (not the strategy itself). She will assemble **candidate manifests** from approved modules, launch **approved experiments**, read **baseline + artifacts**, compare candidates to baseline, and emit **recommendations** for **human** review. She **must not** mutate the locked baseline, bypass replay or Monte Carlo, self-promote, or run arbitrary code.

**Full definition:** [`strategy_research_agent_v1.md`](strategy_research_agent_v1.md) — purpose, limits, interfaces, artifact model, approval boundary.

---

## 13. Related

- [`renaissance_v4/WORKBENCH_V1.md`](../../renaissance_v4/WORKBENCH_V1.md) — product/API v1 detail.
- [`renaissance_v4/ROBUSTNESS.md`](../../renaissance_v4/ROBUSTNESS.md) — robustness runner usage.
- [`development_plan.md`](development_plan.md) — BlackBox phase plan (engine spine and directives).
