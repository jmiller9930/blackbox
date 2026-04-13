# BLACKBOX — System usage (current state)

## Purpose

This document explains how the BLACKBOX system works **as built today**, what is functional, and how to interact with it.

This is **not future design** — this is **current operational reality**. Roadmap (including Phase 5+) is in [`blackbox_master_plan.md`](blackbox_master_plan.md).

**Scope note:** This file uses the **Layer 1–4** lens (Playground, **legacy** operator dashboard under `scripts/runtime/operator_dashboard/`, approval UI). The lab **operator web** stack (**`UIUX.Web/`**, Docker on clawbot, **Anna training / bundle** APIs) is **separate** and is described in the master plan (*Operator web dashboard*) and in [`architect/PROJECT_SYSTEM_SPECIFICATION.md`](architect/PROJECT_SYSTEM_SPECIFICATION.md) under **Where the “whole system” is documented**. Read both if you need the full “what is installed where” picture.

---

## 1. System overview

BLACKBOX currently consists of a **control framework**, not a fully wired trading engine.

### Core components

- **Anna (strategy / analyst brain)** — conversational and analysis surfaces; not a live trading loop by itself.
- **Layer 1 — Playground** — sandbox pipeline execution (CLI).
- **Layer 2 — Operator dashboard** — read-only visibility (local web UI).
- **Layer 3 — Approval interface** — approve / reject / defer (CLI + UI).
- **Layer 4 — Execution** — **designed only** — **not implemented** for controlled remediation execution (see [`architect/layer_4_execution_interface_design.md`](architect/layer_4_execution_interface_design.md)).

---

## 2. What the system can do today

### 2.1 Run sandbox pipelines (Layer 1)

The system can:

- Run **sandbox** DATA pipelines (not live market-driven).
- Generate **validation** artifacts and structured outputs across stages (e.g. detection through simulation).

**Entrypoint:** [`scripts/runtime/playground/run_data_pipeline.py`](../scripts/runtime/playground/run_data_pipeline.py) — requires `--sandbox-db`; rejects non-sandbox production paths.

---

### 2.2 View system state (Layer 2 dashboard)

A basic **local** dashboard exists.

**What it shows (read-only):**

- Pipeline runs (stages synthesized per remediation)
- Validation runs
- Patterns
- Simulations
- Approvals (status **display** only)

**Important:**

- Read-only only — no writes, no execution, no pipeline control from the UI.
- Not a polished product UI — operational glass pane.

**Location:** [`scripts/runtime/operator_dashboard/`](../scripts/runtime/operator_dashboard/) — WSGI app + `static/index.html`.

**How it runs:** Local HTTP server (default bind `127.0.0.1:8765`). Example: `cd scripts/runtime && python3 -m operator_dashboard --sandbox-db /path/to/sandbox.db`

---

### 2.3 Approve / reject / defer (Layer 3)

You can:

- List and inspect approval artifacts and read-only context.
- **Approve**, **reject**, or **defer** via **decision token** (Bearer / `X-Approval-Token`).
- Track lifecycle and audit decisions in sandbox SQLite.

**Interfaces:**

- **CLI:** [`scripts/runtime/approval_cli.py`](../scripts/runtime/approval_cli.py)
- **UI:** [`scripts/runtime/approval_interface/`](../scripts/runtime/approval_interface/) — WSGI + `static/index.html` (default bind `127.0.0.1:8766`).

**Important:**

- Approvals **do not** trigger **Layer 4** remediation execution — that layer is **not built** yet.
- Approvals are stored in **`approvals`** (and related) rows in the **sandbox** DB you pass in.

---

## 3. What the system cannot do yet

The following are **not** implemented in the sense of **production trading**:

- No **live** market data feed wired as the engine for **Pyth** (or equivalent) in a Phase 5 **core trading engine** sense.
- No **strategy engine** driving **real** venue execution end-to-end.
- No **execution** to **Coinbase** or any exchange **as the Layer 4 + Phase 5 path** describes.
- No **wallet-based** live execution path through this stack.
- No **outcome tracking** from **real** trades through the approved execution layer (mock execution plane exists for lab; not the Layer 4 production contract).

---

## 4. Current data flow (simulated)

End-to-end today is **sandbox / simulated** pipeline and approval **artifacts**. There is **no** connection to **real markets** or **real trades** through the Phase 5 engine path — that is **roadmap**, not current runtime.

---

## 5. Architectural roles

### Anna (strategy / analyst)

- Produces analysis and structured outputs in the **implemented** runtime paths (e.g. Telegram, learning visibility).
- **Not** connected to a **live** Phase 5 **market ingestion → strategy → execution** loop yet.

### Billy (execution role)

- Described in architecture and master plan; **not** implemented as a runtime execution agent in this repo **today**.

### System

- Enforces **sandbox** boundaries, **read-only** dashboard, **approval** decisions, and **audit** of what is implemented — **no** production Layer 4 execution.

---

## 6. Storage

- **SQLite** is used for sandbox and runtime artifacts.
- **Sandbox** and **production** runtime DBs must stay **separate** by policy (Playground / dashboard / approval paths **assert** non-production paths where applicable).
- Current data is primarily **pipeline** outputs, **approval** rows, and **system_events**-style feedback (where implemented).

---

## 7. How to use the system (current)

1. **Run pipelines** — Playground CLI with a **sandbox** DB; inspect stages and artifacts.
2. **Review data** — Operator dashboard (read-only) or logs / CLI queries.
3. **Decide** — Approval interface or CLI: approve / reject / defer.

**Result today:** Decisions are **recorded** and **audited** in the sandbox model; **no** automated **Layer 4** execution **follows** approval.

---

## 8. What is being built next

**Phase 5 — Core trading engine** (see [`blackbox_master_plan.md`](blackbox_master_plan.md) and [`architect/development_plan.md`](architect/development_plan.md)):

1. Pyth (or chosen) **market data ingestion**
2. **Normalized** market snapshot **storage**
3. **Anna** strategy on **real** data (deterministic first slice)
4. **Approval binding** to real **candidate** signals
5. **Execution intent** aligned with Layer **4** design
6. **Billy** / **execution adapter** (e.g. Coinbase sandbox first)
7. **Outcome** capture

---

## 9. Key limitation (important)

The system today is a **structured decision and approval stack** on **simulated / sandbox** data, with **Layer 4 execution not implemented**.

**It has:**

- Decision structure (pipelines, artifacts, approvals)
- Approval control (Layer 3)
- Read-only visibility (Layer 2)

**It does not have:**

- Live market data as the **core engine** (Phase 5)
- Real execution through the **Layer 4** production contract
- End-to-end **live** trade outcomes in that sense

---

## 10. One-line summary

BLACKBOX today is a **fully structured decision and approval engine running on simulated data**; **Phase 5** will connect the roadmap to **real markets and execution** per the master plan.
