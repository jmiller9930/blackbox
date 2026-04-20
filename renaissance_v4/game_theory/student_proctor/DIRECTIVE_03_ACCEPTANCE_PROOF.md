# Directive 03 — Final acceptance proof (Shadow Student Output)

## 1. Batch path: schema-valid artifacts only; no silent invalid rows

**Code:** `shadow_stub_student_outputs_for_outcomes` calls `emit_shadow_stub_student_output_v1`, which runs `validate_student_output_v1` before returning success. After emit returns `(doc, [])`, the batch path runs **`validate_student_output_v1` again**; non-empty validation → append to `errors`, **no** append to `outputs` (`post_emit_schema_gate` prefix).

**Tests:** `renaissance_v4/game_theory/tests/test_shadow_student_output_v1.py`

- `test_shadow_outputs_for_outcome_records` — every batch item passes `validate_student_output_v1`.
- `test_batch_path_never_appends_invalid_student_output` — monkeypatched emit returns an invalid dict with a fake empty error list; batch lists **empty outputs** and **errors** containing `post_emit_schema_gate`.
- `test_emit_rejects_illegal_decision_packet` — illegal packet → `(None, errors)`, not a silent object.

## 2. End-to-end chain (one legal packet → one valid `student_output_v1`)

**Test:** `test_e2e_legal_decision_packet_to_valid_student_output`

Sequence:

1. `build_student_decision_packet_v1(db_path, symbol, decision_open_time_ms)` → `student_decision_packet_v1`.
2. `validate_student_decision_packet_v1(packet) == []`.
3. `emit_shadow_stub_student_output_v1(packet, graded_unit_id=..., decision_at_ms=...)` → `student_output_v1`.
4. `validate_student_output_v1(output) == []`.

**Committed example artifact:** `renaissance_v4/game_theory/examples/student_output_v1_shadow_stub_example.json` (validated in `test_committed_example_json_validates`).

## 3. Isolation — no execution-facing path consumes `student_output_v1` (Directive 03)

**Statement:** In this directive, `student_output_v1` is produced only inside `student_proctor` for shadow / analytic use. **Referee execution** (replay, fusion, manifest execution, Flask UI request handling) has **no** import or use of `emit_shadow_stub_student_output_v1`, `shadow_stub_student_outputs_for_outcomes`, or `student_output_v1` as an order or fusion input.

**Evidence:**

- Repository tests assert the absence of shadow symbols in `renaissance_v4/core/**`, `replay_runner.py`, `pattern_game.py`, and that `web_app.py` does not reference `student_output_v1` / `emit_shadow_stub` (`test_execution_facing_modules_do_not_reference_shadow_student_outputs`, `test_referee_codepath_does_not_depend_on_shadow_student`).
- Architectural fact: `student_output_v1` is not passed into `run_manifest_replay`, `FusionEngine`, or execution templates; Referee math is unchanged because the Shadow path is **not on the runtime order path**.

Directive 04 (reveal join) remains blocked until the architect accepts this proof package.
