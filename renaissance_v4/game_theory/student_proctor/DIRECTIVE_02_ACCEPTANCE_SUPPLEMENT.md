# Directive 02 — Acceptance supplement (field inventory, causal rule, recursive leak)

## 1. Real `student_decision_packet_v1` example (artifact)

**File:** `renaissance_v4/game_theory/examples/student_decision_packet_v1_real_db_example.json`

- Built from **this repo’s** `renaissance_v4/data/renaissance_v4.sqlite3` (SOLUSDT fixture rows).
- Wrapper keys: `_comment`, `db_path_note`, `decision_open_time_ms`, and **`packet`** (the actual contract object).

### 1.1 Every field on `packet` (top level)

| Field | Present now? | Meaning |
|------|----------------|---------|
| `schema` | **Yes** | Always `student_decision_packet_v1`. |
| `contract_version` | **Yes** | `1` (Directive 01 contract epoch). |
| `symbol` | **Yes** | Instrument (e.g. `SOLUSDT`). |
| `table` | **Yes** | Always `market_bars_5m` for v1. |
| `decision_open_time_ms` | **Yes** | Simulated decision clock *t* = bar open time (ms) on the tape. |
| `graded_unit_type_hint` | **Yes** | String `closed_trade` — **hint only** for v1 semantics (not a Referee bind). |
| `bars_inclusive_up_to_t` | **Yes** | List of OHLCV row dicts (see §1.2). |
| `bar_count` | **Yes** | `len(bars_inclusive_up_to_t)` (redundant for convenience / audits). |
| `builder_notes` | **Optional** | Only if caller passed `notes=` into `build_student_decision_packet_v1` — omitted in the real example. |

### 1.2 Every field on each element of `bars_inclusive_up_to_t`

| Field | Present? | Meaning |
|-------|------------|---------|
| `open_time` | **Yes** | Bar open (ms), primary causal ordering key. |
| `symbol` | **Yes** | Repeated per row (matches query). |
| `open`, `high`, `low`, `close`, `volume` | **Yes** | Causal OHLCV **as of** that bar’s close in DB (same columns replay reads). |

**Intentionally **not** in the packet (deferred to later directives or other subsystems):**

| Deferred | Where it lands later / why not D02 |
|----------|-------------------------------------|
| `pattern_context_v1` / regime fusion snapshots | Replay + harness emit these; D02 is **bars-only** pre-reveal envelope. **Directive 03+** may merge structured context into the packet **without** flashcards. |
| `student_output_v1` | **Directive 03** (shadow Student). |
| `reveal_v1`, `OutcomeRecord` fields | **Reveal** is post-decision — **forbidden** pre-reveal. |
| Retrieved `student_learning_record_v1` rows | **Directive 06** — retrieval into **legal** packet only after merge rules are defined. |
| Full indicator / feature pipeline vectors | Not duplicated here; engine computes during replay. D02 does **not** replace fusion — it gives the **raw causal tape slice** the Student view can anchor to. |

---

## 2. Causal boundary at time *t* (graded unit v1 = `closed_trade`)

**Rule:** include only rows with `open_time <= decision_open_time_ms` (SQL + sort oldest→newest).

**Why this does not leak “not-yet-knowable” market information:**

- Each **5m bar** in the table is **historical**: commit time of bar *t* in the DB is the **last** time price/volume for that interval are fixed in the record.
- **No row** with `open_time` **strictly after** `decision_open_time_ms` is selected — so **future intervals** on the tape are excluded.
- **Closed-trade** graded units are **graded after** the Referee has entries/exits; the **packet at bar *t*** deliberately **excludes** any trade outcome — it only carries **public** OHLCV **known once that bar exists** in history. Anything **unknowable at *t*** (later bars, exit fill, PnL) is **not** in the builder path.

**What *t* is:** the **bar open time** the operator (or future harness) designates as “now” for a Student decision — aligned with replay using the same `open_time` key as ordering.

**Cap:** `max_bars_in_packet` keeps the **most recent** N bars still satisfying the cutoff — no future leakage; only **depth** is bounded.

---

## 3. Recursive no-leak proof on the **built packet** tree

**Mechanism:** `validate_pre_reveal_bundle_v1` in `contracts_v1.py` walks **all** dict/list nesting via `_collect_string_keys` and rejects any string key whose **name** (case-insensitive) is in `PRE_REVEAL_FORBIDDEN_KEYS_V1` (e.g. `pnl`, `mfe`, `wins`, `referee_truth`, `validation_checksum`, …).

**`validate_student_decision_packet_v1`** also checks causal `open_time <= decision_open_time_ms` per row and **calls** `validate_pre_reveal_bundle_v1` on the **whole** packet.

**Automated proof (built packet clone + poison):**  
`test_recursive_forbidden_key_anywhere_in_tree_rejected` in `tests/test_student_context_builder_v1.py` — five nests:

1. `a → b → pnl`
2. `bars_inclusive_up_to_t[0].layer.mfe`
3. `h[0].wins`
4. root `referee_truth`
5. `m → m2 → m3 → validation_checksum`

Each case: **non-empty** errors from `validate_pre_reveal_bundle_v1` **and** from `validate_student_decision_packet_v1`.

**Limitation (documented):** validation is **key-name** based, not **value** semantics — e.g. prose in `builder_notes` could mention “pnl” as text; **keys** remain the enforced boundary per Directive 01 freeze.

---

## 4. Re-run tests

```bash
PYTHONPATH=. python3 -m pytest renaissance_v4/game_theory/tests/test_student_context_builder_v1.py -v
```

---

## 5. Operational closeout (supplement push)

| Step | Result |
|------|--------|
| **Commit** | `4bb41e25f464746c1813237adbfaa153e7bcc095` |
| **git push** | `a09ac6b..4bb41e2` → `origin/main` |
| **Server** `jmiller@clawbot.a51.corp` `~/blackbox` | **Fast-forward** to `4bb41e25`; `HEAD` matches |
| **Flask restart** | `pattern_game_remote_restart.sh` — PID **986939** (session after supplement pull) |
| **Health** | `curl http://127.0.0.1:8765/` → **200** |

*End — Directive 02 acceptance supplement.*
