# JUPv4 — Grok prompt for fully documented policy delivery

**Purpose:** When Sean’s **JUPv4** policy spec is implemented via **Grok**, use the prompt below so the emitted code ships with **exhaustive docstrings** — every constant, function, gate, and diagnostic field explained so engineering can integrate without guesswork.

**Context:** JUPv3 is documented in [`JUPv3.md`](JUPv3.md); canonical Python policy lives in `modules/anna_training/jupiter_3_sean_policy.py`. JUPv4 will need its own module(s), constants, and wiring per governance — Grok should **not** invent trading intent; it should **encode Sean’s spec** with **maximum inline documentation**.

---

## Paste this into Grok (system or first user message)

You are implementing **Jupiter V4 (JUPv4)** trading policy code for the BLACK BOX repo from **Sean’s written specification** (pasted below or attached).

**Non‑negotiable documentation requirements**

1. **Module docstring** — What JUPv4 is, how it differs from JUPv3 if applicable, catalog/policy IDs, and **paper vs live** stance. Name every **external input** (e.g. OHLCV source, symbol, timeframe).

2. **Every top-level constant** — Each must have a comment or docstring block explaining: **numeric value**, **why that value**, **units** (USD, ratio, bars, ms), and **what breaks** if it is changed.

3. **Every public function** — Google-style or NumPy-style docstring with: **Args**, **Returns** (types and semantics), **Raises**, and **Side effects** (e.g. “mutates nothing”, “reads SQLite”).

4. **Every gate / rule / boolean** — If the policy defines long/short “gates” (like JUPv3’s `jupiter_v3_gates`), document **each gate**: label, exact predicate, symmetry (long vs short), and dependency order if order matters.

5. **Diagnostics / return dict** — If the evaluator returns a structured dict (RSI, ATR, volume spike flags, etc.), **document every key**: type, meaning, and how the dashboard or ledger should interpret it.

6. **Edge cases** — Document behavior for: insufficient bars, NaN, missing volume, flat market, and tie-break rules (e.g. long vs short priority).

7. **Parity** — If a Node/TS mirror is required (as for JUPv3), state explicitly what must match and point to filenames; if Python-only, say so.

8. **No silent magic** — No unexplained thresholds; if Sean’s spec leaves ambiguity, add a `NOTE:` in docstrings listing assumptions and recommend architect confirmation.

**Code quality**

- Type hints on public APIs.
- Keep constants in one obvious block (same style as `jupiter_3_sean_policy.py`).
- Prefer pure functions for signal math; isolate I/O.

**Output format**

- Deliver **complete file contents** ready to drop into `modules/anna_training/` (and mirror path if required), not pseudocode.
- After the code, deliver a short **“Integration checklist”** markdown list: files to touch, ledger `signal_mode` string, dashboard bundle hooks — so Cody can wire without re-deriving intent.

---

## Sean’s specification (fill in before sending)

Paste Sean’s JUPv4 policy text, constants table, or attachment **below** this section when you run Grok.

```
[PASTE SEAN SPEC HERE]
```

---

## After Grok returns

- Review docstrings for **every** item in the **Integration checklist**.
- Align with [`development_governance.md`](../development_governance.md) and phase scope before merging.
- If JUPv4 adds a new policy slot, see [`JUPv3.md`](JUPv3.md) § on new slots (constants, valid set, bridge, evaluator).
