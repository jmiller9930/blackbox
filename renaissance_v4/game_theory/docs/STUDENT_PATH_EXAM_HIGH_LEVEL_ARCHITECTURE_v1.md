# High-level architecture — learning, exam, certification, engineering, UI splice

**Status:** v1.2 — adds mandatory **delivery closeout** (commit / push / restart / verify) per engineering directive and UI splice.

---

## 0. Scope fence (demarcation)

**Closed baseline (do not reopen):**  
The **Student panel UI refactor is complete for its role**:

- L1 run table  
- L2 run summary + trade-grain carousel  
- L3 `student_decision_record_v1`  
- batch / scorecard wiring  
- honest `data_gap`

This is the **execution truth layer (Referee-facing receipt system)**.

**Active workstream:**  
Define and implement the **exam system (moment truth layer)**:

- decision frames  
- deliberation  
- commitment  
- staged reveal  
- grading  

Then **splice those artifacts into the existing UI** (carousel becomes a **timeline of moments**).

---

## 1. Learning model (product definition)

Learning is defined as **operator-grade decision competence**, not rule memorization.

### Learning consists of:

1. **Literacy**
   - Indicators = defined transforms of price/volume  
   - Meaning must be understood in **context** (structure, regime, velocity)  
   - Anchored by:
     - `INDICATOR_KIND_VOCABULARY` (`renaissance_v4/policy_spec/indicators_v1.py`)
     - `TRADING_CONTEXT_REFERENCE_V1.md`

2. **Deliberation**
   - Student MUST evaluate **multiple hypotheses** (minimum count **`K`** published per exam pack; default **3** if unset).
   - Each hypothesis MUST include:
     - market interpretation  
     - indicator support  
     - resulting action (ENTER long / ENTER short / NO_TRADE)  
     - falsification condition (exam-legal; no future leakage)

3. **Evaluation (H4 — required)**
   - Student MUST compare hypotheses using:
     - indicator alignment  
     - context fit  
     - risk clarity (invalidation strength)  
   - Selection MUST NOT be arbitrary.

4. **Commitment (Decision A)**
   - Based on opening window only  
   - Student commits:
     - ENTER / NO_TRADE  
     - side (if ENTER)  
     - thesis  
     - invalidation  
     - horizon  
     - why (bounded)

5. **Path discipline (Decision B)**
   - After commitment, evaluate:
     - thesis validity over time  
     - mechanism adherence (stops, timing, exit)

6. **Memory (optional)**
   - Groundhog MAY influence Decision A  
   - MUST NOT leak future data  
   - MUST NOT override Referee truth  

**Note:** **H1–H3** = hypothesis generation; **H4** = comparative evaluation and **primary selection** (or explicit none-merit ENTER). **Phase A (§3) requires the full H1–H4 sequence.**

---

## 2. Decision Frame (canonical artifact)

**Decision Frame** is the **atomic unit of moment truth** for the exam: one checkpoint in time — what the Student saw (for that frame), what was evaluated, and (on frame 0) what was sealed as Decision A.

### Parent / child (non-ambiguous)

- **`exam_unit_id`** — parent: one exam session (one opening window + optional downstream path + grades).  
- **`decision_frame_id`** — child: **one** frame in the unit’s timeline.  

An **exam unit** **SHALL** contain an **ordered list** of `decision_frame` records:

- **Frame 0:** opening window snapshot (market + indicators) + hypothetical deliberation (**H1–H4**) + **sealed Decision A**.  
- **Frames 1…n** (if and only if Decision A was ENTER): downstream observations for **Decision B**, per **§7** termination rule.

**Rule:** All UI cards, slices, or checkpoints **MUST** resolve to a **`decision_frame_id`** (and thus to an **`exam_unit_id`**). The carousel is an **ordered view** of these frames, not a separate conceptual object.

### Trade record (link only)

A **trade record** (`trade_id` / execution truth) **MAY** link to the **exam unit** or to **frame 0** when a replayed position exists; it **MUST NOT** be confused with moment truth payload (see **§5**).

---

## 3. Exam structure (contractual flow)

### Phase A — Opening (Decision A)

**Student sees:**  
Only data up to the **end of the opening window** (v1 default: **one 5m bar** unless the exam pack states otherwise).

**Student MUST:**

- Generate hypotheses **H1–H3**  
- Perform **H4** — compare hypotheses and **select** primary branch (or justify **NO_TRADE** / no ENTER merit)  
- Seal **Decision A** (all required fields per **§1.4**)

### Phase B — Downstream (Decision B)

Triggered **only** if Decision A = **ENTER**.

**After Decision A is sealed:**

- Downstream data is revealed **incrementally or batched** per exam UX policy, but **only** after seal — **never** before.  
- Termination per **§7**.

**Student MUST evaluate:**

- Thesis validity (confirm / negate / noise)  
- Mechanism adherence (invalidation / horizon)

### Reveal ordering (strict)

1. Opening window shown  
2. **H1–H3** generated  
3. **H4** evaluation / selection completed  
4. **Decision A** sealed  
5. **Then** downstream revealed (if ENTER)  
6. **Then** Decision B evaluated  

**Violation of this ordering invalidates the exam unit.**

---

## 4. Keying model (non-optional)

- `exam_unit_id` → parent (session)  
- `decision_frame_id` → child (moment / checkpoint)  

Frames MUST be:

- ordered by **index** or **timestamp** (published rule per pack)  
- grouped under the parent unit  

---

## 5. Trade vs Decision separation

### Decision Frame (moment truth)

- what was seen (for that frame)  
- what was decided (on frame 0: sealed A)  
- why (bounded)  
- deliberation artifacts (**H1–H4**)

### Trade Record (execution truth)

- what happened  
- outcome  
- PnL  

These **MUST** remain **separate objects** but **MAY** be **linked** by stable IDs (`exam_unit_id`, `trade_id`, `scenario_id` as applicable).

---

## 6. NO_TRADE (first-class outcome)

NO_TRADE MUST be treated equally to ENTER for **process grading** and **UI presence**.

### NO_TRADE classifications (Referee MAY emit only if defined in exam pack)

- **Correct NO_TRADE** — per published rubric (e.g. no valid arm per Student’s declared rules).  
- **Missed opportunity** — **ONLY** if the exam pack defines **non-oracle** criteria (e.g. a **published** “armed signal” the Student’s **own** pre-declared policy would require to catch). **MUST NOT** label “missed” by hindsight alone without a published rule.

### Student MUST provide (NO_TRADE)

- why not entering  
- what would trigger entry (**defined without future facts**)

---

## 7. Downstream termination rules

The exam pack **MUST** define exactly **one** primary mode per unit:

- **fixed bar count** — default **5** five-minute bars if pack omits `D` (implementation SHOULD surface default in UI)  
- **until invalidation** — until Student’s declared invalidation triggers or session end  
- **volatility / regime threshold** — until ATR-scaled move or regime flip per published threshold, or cap bars elapsed  

---

## 8. Exam pack (versioned configuration)

Each **exam pack** **SHALL** publish (at minimum):

| Parameter | Role |
|-----------|------|
| `exam_pack_id` + `version` | Audit and drift control |
| `K` | Minimum hypotheses (H1–H3 count) |
| `opening_window` | e.g. one 5m bar |
| Termination mode + `D` / thresholds | §7 |
| Economic gates | `ε` expectancy and/or `φ` profit factor + `δ` drawdown cap (as chosen) |
| `p_min` | Minimum process score for PASS |
| `N_batch` | Certification batch size |
| **E mode** | replay PnL vs paper metric (must declare) |
| NO_TRADE sublabels | whether “missed opportunity” enabled + **definition** |

**Amendment rule:** Any change to the above **SHALL** bump **`exam_pack` version**; graders and UIs **MUST** log which pack graded each unit.

---

## 9. Grading system

Two **independent** dimensions:

### Economic (E)

Defined per batch (see exam pack):

- expectancy **OR**  
- profit factor + drawdown cap  

**Win rate:**

- MUST NOT be sole **E** PASS criterion  
- MAY be secondary or paired with published floor **only if** exam pack explicitly defines pairing (avoid “51% win rate only” as sole gate).

### Process (P)

Scored 0–1:

- **P1:** hypothesis completeness (**H1–H3**) + **H4** present  
- **P2:** decision consistency (thesis vs side vs invalidation vs A)  
- **P3:** mechanism adherence vs invalidation / horizon on downstream path  

### PASS condition

**PASS** = (**E** passes published thresholds) **AND** (**P** ≥ **`p_min`**).

---

## 10. Certification meaning

Certification means:

> The Student consistently produces **valid process** and **meets published economic thresholds** over **`N_batch`** exam units under a fixed **`exam_pack` version**.

It does **NOT** mean:

- omniscience  
- perfection  
- guaranteed profitability in live markets  

---

## 11. Engineering responsibilities

### Already complete (foundation)

- replay engine  
- Referee truth  
- batch execution (`parallel_runner` / scorecard job path)  
- storage  
- UI shell (L1 / L2 / L3)  
- indicator vocabulary  

### Must be built (each slice ends with **Delivery closeout** below)

#### 11.1 Exam state machine

Enforce **§3** ordering; invalidate unit on violation.

#### Delivery closeout (11.1 — mandatory)

```bash
cd /path/to/blackbox   # repo root
git status
git add -- <paths changed for 11.1 only>
git commit -m "feat(exam): state machine — enforce §3 ordering; invalidate on violation"
git pull origin main
git push origin main
# Restart all services used for game_theory / Student panel testing, e.g.:
# - Flask app hosting web_app (pattern game) — restart process or container
# - docker compose restart <relevant-service>   # if your stack uses Compose
# Verify (expect 200):
# curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:<PORT>/api/student-panel/runs"
```

---

#### 11.2 Deliberation capture

**H1–H4** exporter (non-placeholder); schema versioned.

#### Delivery closeout (11.2 — mandatory)

```bash
cd /path/to/blackbox
git status
git add -- <paths changed for 11.2 only>
git commit -m "feat(exam): deliberation capture — H1–H4 exporter + schema"
git pull origin main
git push origin main
# Restart Flask/web_app + Docker stack if applicable; verify Student panel APIs HTTP 200.
```

---

#### 11.3 Decision Frame schema

Parent unit + ordered frames (**§2**).

#### Delivery closeout (11.3 — mandatory)

```bash
cd /path/to/blackbox
git status
git add -- <paths changed for 11.3 only>
git commit -m "feat(exam): decision_frame schema — exam_unit + ordered frames"
git pull origin main
git push origin main
# Restart Flask/web_app + Docker stack if applicable; verify Student panel APIs HTTP 200.
```

---

#### 11.4 Downstream frame generator

Timeline per **§7**.

#### Delivery closeout (11.4 — mandatory)

```bash
cd /path/to/blackbox
git status
git add -- <paths changed for 11.4 only>
git commit -m "feat(exam): downstream frame generator — timeline per pack"
git pull origin main
git push origin main
# Restart Flask/web_app + Docker stack if applicable; verify Student panel APIs HTTP 200.
```

---

#### 11.5 Grading service

**E** + **P** from pack constants.

#### Delivery closeout (11.5 — mandatory)

```bash
cd /path/to/blackbox
git status
git add -- <paths changed for 11.5 only>
git commit -m "feat(exam): grading service — E and P from exam pack"
git pull origin main
git push origin main
# Restart Flask/web_app + Docker stack if applicable; verify Student panel APIs HTTP 200.
```

---

#### 11.6 API layer

Submit A / deliberation; fetch frames; fetch grades; pack metadata.

#### Delivery closeout (11.6 — mandatory)

```bash
cd /path/to/blackbox
git status
git add -- <paths changed for 11.6 only>
git commit -m "feat(exam): API layer — submit/fetch exam unit + frames + grades"
git pull origin main
git push origin main
# Restart Flask/web_app + Docker stack if applicable; verify new routes + /api/student-panel/runs → 200.
```

---

#### 11.7 UI splice (engineering slice)

Map frames → carousel; frame → drill-down (**§12**). *(May ship in same PR as 11.6 or immediately after; still requires its own closeout when merged.)*

#### Delivery closeout (11.7 — mandatory)

```bash
cd /path/to/blackbox
git status
git add -- <paths changed for 11.7 only>
git commit -m "feat(exam-ui): splice decision frames into carousel + drill-down"
git pull origin main
git push origin main
# Restart Flask/web_app + Docker stack if applicable; verify L2 carousel + L3 drill HTTP 200.
```

---

## 12. UI integration

Reuse existing UI shell.

### Carousel becomes:

- **timeline of Decision Frames** (ordered by `exam_unit_id`, frame index)

### Cards:

- **Card 0:** frame 0 — Decision A (entry moment + deliberation summary)  
- **Cards 1+:** downstream frames (Decision B), **ENTER** only  

### Drill-down:

- full **decision_frame** detail view (handle = `decision_frame_id`)

#### Delivery closeout (§12 UI splice — mandatory when this slice ships)

If §12 work ships **separately** from **§11.7**, run again after §12-only changes:

```bash
cd /path/to/blackbox
git status
git add -- <paths changed for §12 UI splice only>
git commit -m "feat(exam-ui): timeline carousel + frame drill-down per STUDENT_PATH_EXAM spec"
git pull origin main
git push origin main
# Restart Flask/web_app + Docker stack if applicable.
# Verify: L1 runs → L2 selected run → carousel frames → drill-down; Student panel APIs HTTP 200.
```

---

## 13. Risks

- **Data leakage** (any post–opening-window or post–A truth visible before seal) → **invalidates** exam unit.  
- **PnL-only grading** → promotes luck; **P** dimension is mandatory for v1 PASS.  
- **No hypothesis / H4 enforcement** → destroys reasoning contract.  
- **`parallel_runner` / parallel batch** — **MUST NOT** be treated as satisfying **H1–H4 deliberation** unless an **exam mode** explicitly defines that equivalence; they are **different mechanisms** (throughput vs pre-commitment cognitive trace).  

---

## 14. Final alignment statement

The system teaches:

- how to interpret the market (**Decision Frames**)  
- how to act (**Decision A**)  
- how decisions perform over time (**Decision B**)  
- how outcomes validate behavior (**Referee** / trade record)  

Certification is based on:

- economic performance (**E**)  
- process discipline (**P**)  

UI displays:

- a **timeline of decisions** (moment truth)  
- not only a list of trades (execution truth), though both remain **linkable**  

---

## 15. One-line product definition

This system is a **proctored decision-training and validation engine** that teaches how to make decisions and proves whether those decisions actually work — under **versioned exam packs**, **strict reveal order**, and **separate moment vs execution records**.

---

## 16. Operational closeout — canonical template (all **Delivery closeout** blocks)

**Rule:** Any directive in **§11** or **§12** that ships implementation **MUST** end with a **Delivery closeout**: full **local commit**, **remote sync**, **restart all web services** used for game-theory / Student panel testing, and **HTTP verification**.

### 16.1 Git (local + remote)

Replace `<BRANCH>` with your integration branch if not `main`. Scope `git add` to **only** files touched by that directive.

```bash
cd /path/to/blackbox   # repository root
git status
git add -- path/to/changed/files...
git commit -m "feat(exam): <directive id> — <complete sentence summary>"
git pull origin <BRANCH>
git push origin <BRANCH>
```

### 16.2 Restart services

Restart **every** process the team uses to manually test the Student panel and exam APIs, typically including:

- **Flask / `web_app`** (pattern game + Student panel routes) — however you run it locally (venv, `flask run`, systemd, or **Docker**).  
- **Docker Compose** (if applicable) — e.g. `docker compose restart` for the service(s) that front the same app or DB.

There is no single PID in this doc; operators **MUST** restart whatever matches their environment so **no stale code** serves requests.

### 16.3 Verify (testing)

After restart, confirm **HTTP 200** on at least:

- `GET /api/student-panel/runs`  
- Any **new exam** routes introduced by the directive (document the exact paths in the commit message or PR).

Example:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:<PORT>/api/student-panel/runs"
```

---

## Revision history

| Version | Summary |
|---------|---------|
| v1.0 | User draft (scope, learning, frames, flow, keying, NO_TRADE, grading, engineering, UI, risks). |
| v1.1 | H1–H4 in Phase A; `exam_unit` vs atomic `decision_frame`; exam pack table; NO_TRADE “missed opportunity” guard; win-rate pairing note; `parallel_runner` vs deliberation in risks; PASS/E copy tied to pack. |
| v1.2 | §11 split into 11.1–11.7 with per-directive **Delivery closeout** (commit, pull, push, restart, verify); §12 closeout; **§16** canonical template. |
