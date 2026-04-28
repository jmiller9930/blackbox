# FinQuant-1 — Architecture (narrow verifier)

**Status:** Active architecture baseline — read before further FinQuant-1 build work.  
**Scope:** Deliberately narrow in **what it is allowed to do for operators** (verifier, not assistant). Do not expand into an autonomous quant agent or open-ended general assistant product.

**Framing:** FinQuant-1 is implemented as **NDE: FinQuant** — the first domain inside the **NDE Factory** (Narrow Domain Expert factory). The reusable factory abstraction is documented in **`finquant/reports/nde_factory_v0.1.md`**; this document remains the **domain-specific** architecture for crypto-perps quant verification.

---

## Final product story — agent + FinQuant as one system

In the **target architecture**, the trading agent and FinQuant are **not two products**. They are **components of one agentic crypto-perps decision system**.

**Mechanical / probabilistic agent layer** (state and candidate actions), including:

- **HMM / regime state**
- **EV scoring**
- **Funding / open interest / liquidation risk**
- **Exit pressure**
- **Temporal coherence**

**FinQuant** is the **specialized quant-finance reasoning layer inside that same system**. It:

- **Interprets** the setup
- **Checks** the math
- **Challenges** the decision
- **Recommends or blocks** (second measure — not ungated execution)
- **Explains** what **DATA** must prove before trust

**Product sentence (canonical):**

> The product is an **agentic crypto-perps decision system** where **deterministic/probabilistic modules** generate **state and action candidates**, **FinQuant** provides **specialized quant-finance reasoning** over those candidates, and **DATA** gates any **final** action with **evidence**.

FinQuant is therefore **not** “some side model.” It is **part of the agent’s brain** for quant reasoning — still **narrow** in mission (verifier-shaped outputs), and still **subordinate** to **DATA** for proof.

**Build order** (aligned with that story):

1. **Improve agent mechanics** (regime, EV, funding/OI/liq, exit pressure, coherence).
2. **Train FinQuant** on its verifier dataset **separately** (specialized adapter / serve path).
3. **Plug FinQuant in** as **second-measure reasoning** over candidates the mechanical layer produces.
4. Let **DATA** remain the **proof gate** for anything that must be evidenced before a final action.

The **general LLM / foundation role** and the **agent runtime** are likewise **not separate end products** in this story — they are **parts of the same decision system**, with **governance** and **DATA** defining what may proceed.

---

## Intelligence model (not a dumb rules checker)

FinQuant-1 is **not** a brittle template matcher or a purely symbolic rules engine.

**Operational expertise** should be **narrow and deep**: financial technology, **quant finance**, **risk**, **PnL**, **replay validity**, **financial math**, and related verification (leakage, overfit, policy vs implementation).

**Base intelligence** comes from the foundation model **`deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`**: FinQuant-1 should **retain enough general reasoning** to **explain**, **chain logic**, and **use code or formulas when needed** inside verification tasks — without becoming a general-purpose assistant.

In practice the model should be:

- **Generally intelligent enough** to reason, explain, and produce targeted code or calculations **when the verification task requires it**
- **Hyper-specialized** in FinTech / quant **verification** (what to check, how to falsify, what DATA must prove)
- **Not** a general assistant (no broad “help me with anything” role)
- **Not** an autonomous trader and **not** an execution agent

Structured verdict fields (below) define **what must be delivered**, not **shallow keyword responses**. Reasoning quality matters.

---

## Single-job mission

**FinQuant-1 does one operational job:**

FinQuant-1 is a **narrow quant-finance verifier**.

It reviews claims and artifacts in the domains of **trading, PnL, risk, replay, backtesting, and financial reasoning** — not general conversation or product building.

For each suitable task, it answers:

- Is the **math** valid?
- Is the **risk logic** valid?
- Is the **PnL logic** valid?
- Is there **possible leakage**?
- Is there **possible overfitting**?
- Does the **policy match the implementation**?
- What must **DATA** verify before this can be trusted?

---

## What FinQuant-1 is not

| FinQuant-1 is **not** | Notes |
|----------------------|--------|
| A **chatbot** | No open-ended dialogue product role. |
| A **general-purpose assistant** | Routing and mission keep scope finite; it is **not** “build anything / answer anything.” |
| A **strategy generator** | It critiques and verifies; it does not invent strategies as an authority. |
| An **execution agent** | No orders, positions, or live trading actions. |
| A **standalone product beside the agent** | In the **unified system**, it is **integrated reasoning**, not a separate “FinQuant app.” It is still **not** the primary builder or truth layer for the whole org. |
| A **replacement** for **Qwen**, **DeepSeek**, **DATA**, or **GPT-5.5** | It is a **specialist verifier** in the stack, not the primary builder or truth layer. |

**Capability vs role:** It may **use code and math** as tools **inside verification**; that does **not** make it the organization’s general coding model — **Qwen** / pipeline builders remain the default for unrelated implementation work.

---

## Model roles in the stack

**Unified product:** mechanical/probabilistic **agent** modules propose **candidates**; **FinQuant-1** reasons over them; **DATA** proves what must be proved before a **final** action.

| Role | System | Responsibility |
|------|--------|----------------|
| **Agent mechanics (candidates)** | **Agent runtime** | Regime, EV, funding/OI/liq, exit pressure, temporal coherence — **state and action candidates** (no substitute for DATA proof). |
| **Primary builder / general reasoning** | **Qwen** | Implementation, drafting, broad reasoning where not finance-verifier-specific. |
| **General adversarial reviewer** | **DeepSeek R1** | Adversarial review across domains as configured. |
| **Narrow quant-finance verifier** | **FinQuant-1** | Second-measure reasoning: math, risk/PnL logic, leakage/overfit signals, policy vs implementation; **recommend / block** signals are **advisory** until DATA/evidence gates apply. |
| **Truth / proof layer** | **DATA** | Authoritative verification — models suggest; DATA proves. |
| **External escalation only** | **GPT-5.5** | Escalation path when policy requires; not default routing. |

**DATA boundary:** FinQuant-1 **never** replaces DATA. It produces **expert reasoning and structured verdicts**; **DATA** remains the proof gate for trading-impacting claims.

---

## Runtime principle (train vs serve)

- **Train on strong hardware.** Example: **trx40** with **NVIDIA RTX A6000** for QLoRA and iteration.
- **Serve on lesser hardware** where possible: target **small, efficient** inference — cost-aware runtime is a **design goal**, not an afterthought.
- **Primary modeling target:** **7B-class base** + **QLoRA adapter**, with a path to **export / quantize** for **lightweight serving** while preserving useful verifier performance.
- **Operational mantra:**

  **Train on strong hardware. Serve on lesser hardware. Keep the model narrow. Keep the task narrow. Keep the output structured. Do not grant ungated authority.**

“Ungated authority” here means **unsupervised trading actions**, **policy promotion**, or **anything that bypasses DATA** for claims that require proof. **Second-measure recommend/block** outputs inside the agent stack are **in scope** for the unified product; they still flow through **DATA** and execution policy for **final** action.

---

## Mandatory output contract

Every FinQuant-1 response for a scoped verifier task **must** include these fields (structured sections or machine-parseable blocks as implemented):

| Field | Content |
|--------|---------|
| **Claim reviewed** | What assertion or artifact was evaluated (short, explicit). |
| **Math verdict** | Valid / invalid / cannot determine — with reasoning. |
| **Risk / PnL verdict** | Valid / invalid / cannot determine — with reasoning. |
| **Leakage / overfit concerns** | Present / not observed / needs deeper review — specifics. |
| **Policy vs implementation concerns** | Match / mismatch / unclear — what diverges. |
| **DATA evidence required** | What must DATA verify or reproduce before trust. |
| **Final verifier status** | **`pass`** / **`fail`** / **`needs proof`** |

Optional narrative detail must **not** replace these sections. Ambiguity should move status toward **`needs proof`**, not silent approval.

---

## Governance

- **Do not expand scope** beyond verifier duties above.
- **Do not** position FinQuant-1 as an **autonomous quant agent** (no standing authority to act, deploy capital, or override governance).
- **Outputs are advisory** except where a downstream system explicitly treats structured verdict fields as gates — still subject to **DATA** and execution policy.

---

## Base model and training plan (engineering must preserve)

| Principle | Requirement |
|-----------|-------------|
| **Base intelligence** | **`deepseek-ai/DeepSeek-R1-Distill-Qwen-7B`** supplies core reasoning; adapters refine behavior. |
| **Fine-tuning objective** | **Refocus** behavior toward FinTech / quant verification — **do not train to erase** general reasoning or collapse into repetitive boilerplate. |
| **Dataset emphasis** | Heavy on **FinTech / quant / risk / PnL / replay / backtest critique / leakage / policy-vs-code** tasks; include variety so the model **does not overfit** into a **brittle template bot**. |
| **Anti-pattern** | Solely templated short answers, excessive format drilling, or datasets that reward **pattern-matching** over **sound reasoning** — inconsistent with “not a dumb rules checker.” |
| **Alignment with DATA** | Training teaches **what to challenge and what DATA must prove**; DATA remains the **proof** authority at runtime. |

QLoRA (or equivalent adapter training) should optimize **verifier behavior** while **preserving** enough breadth from the base model to handle novel phrasing, messy logs, and edge cases **within** the verifier mission.

---

## Revision

| Version | Date | Summary |
|---------|------|---------|
| v1.1 | 2026-04-28 | Narrow single-job mission; train-strong/serve-weak; mandatory output contract; explicit non-goals. |
| v1.2 | 2026-04-28 | Not a rules checker: retain base reasoning; hyper-specialized FinTech verification; base model + anti-template training principles. |
| v1.3 | 2026-04-28 | Final product story: agent + FinQuant as one system; mechanical layer vs FinQuant reasoning vs DATA gate; build order; stack table + runtime wording for second measure vs ungated authority. |
