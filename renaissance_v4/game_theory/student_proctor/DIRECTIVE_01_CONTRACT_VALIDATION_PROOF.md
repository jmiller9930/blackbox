# Directive 01 — Contract validation & leakage proof (engineering)

**Status:** Supplement to architect review — evidence that validators enforce **structure** and **pre-reveal** boundaries.

**Run tests (reproducible):**

```bash
cd /path/to/blackbox
PYTHONPATH=. python3 -m pytest \
  renaissance_v4/game_theory/tests/test_student_proctor_directive_01_proof.py \
  renaissance_v4/game_theory/tests/test_student_proctor_contracts_v1.py -v
```

**Expected:** all tests **passed** (17 as of last engineering run).

---

## 1. Contract validation — valid / invalid per schema

| Artifact | Valid (passes) | Invalid (fails) — proves structure enforcement |
|----------|----------------|-----------------------------------------------|
| **student_output_v1** | `student_output_v1_valid_proof()` — `contract_proof_fixtures_v1.py` | **Wrong `contract_version`** (99) — rejects with `contract_version must be 1` |
| **reveal_v1** | `reveal_v1_valid_proof()` — minimal `referee_truth_v1` with `trade_id`, `symbol`, `pnl` | **Missing `pnl`** under `referee_truth_v1` — rejects with message requiring `pnl` |
| **student_learning_record_v1** | `student_learning_record_v1_valid_proof()` | **`alignment_flags_v1` is a list** — rejects (must be `dict`) |

**Implementation:**  
- Validators: `validate_student_output_v1`, `validate_reveal_v1`, `validate_student_learning_record_v1` in `contracts_v1.py`  
- Proof tests: `test_student_proctor_directive_01_proof.py`  
- Named fixtures: `contract_proof_fixtures_v1.py`

Invalid cases are **not** “empty dict” acceptance tests — they are documents that are **almost legal** but violate **one required structural rule** each.

---

## 2. Leakage — pre-reveal boundary

| Proof | What it shows |
|-------|----------------|
| `illegal_pre_reveal_bundle_example_v1()` contains **`pnl`** | `validate_pre_reveal_bundle_v1` **rejects** with `forbidden pre_reveal key 'pnl'` |
| Nested **`mae`** under `context.nested` | Recursive key scan **rejects** |
| **`student_output_v1` with `win_rate` added** | Student validator runs pre-reveal scan on full doc — **rejects** (flashcard field) |
| **Legal packet** (bars + indicators only, no forbidden keys) | **Accepts** — `test_proof_leakage_legal_pre_reveal_style_packet_accepted` |

**Forbidden key set (v1):** `PRE_REVEAL_FORBIDDEN_KEYS_V1` in `contracts_v1.py`.

---

## 3. Files changed for this proof pass

- `student_proctor/contract_proof_fixtures_v1.py` — named valid/invalid fixtures  
- `tests/test_student_proctor_directive_01_proof.py` — architect-facing proof tests  
- This document — `DIRECTIVE_01_CONTRACT_VALIDATION_PROOF.md`

---

*Engineering — submit test output + this file as Directive 01 contract validation proof.*
