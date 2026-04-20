# Directive 05 — Student learning store (acceptance proof)

## Objective

Append-only, versioned persistence of ``student_learning_record_v1`` with read paths that do not require an LLM. No coupling to engine memory (fusion / DCR bundles) or execution/Referee mutation.

## Implementation

- **Module:** ``renaissance_v4/game_theory/student_proctor/student_learning_store_v1.py``
- **Default path:** ``<pml_runtime_root>/student_learning/student_learning_records_v1.jsonl`` (see ``default_student_learning_store_path_v1``; ``BLACKBOX_PML_RUNTIME_ROOT`` respected).
- **Append:** ``append_student_learning_record_v1`` — validates before write; optional duplicate ``record_id`` rejection (default on).
- **Read:** ``load_student_learning_records_v1``, ``get_student_learning_record_by_id``, filters by ``run_id``, ``graded_unit_id``, ``context_signature_v1["signature_key"]``.
- **Projection:** ``build_student_learning_record_v1_from_reveal`` — builds a learning row from a validated ``reveal_v1`` (no replay side effects).

## Tests (``test_student_learning_store_v1.py``)

| Requirement | Coverage |
|-------------|----------|
| Append + schema validation | ``test_append_rejects_invalid_record`` |
| Append + reload + get-by-id | ``test_append_load_roundtrip`` |
| Duplicate ``record_id`` | ``test_duplicate_record_id_forbidden`` |
| Durability (fresh read) | ``test_persistence_new_process_simulated_by_fresh_read`` |
| Query run / graded unit / signature | ``test_query_by_run_graded_unit_signature`` |
| Reveal → row → store | ``test_build_from_reveal_and_store`` |
| Malformed line handling | ``test_malformed_jsonl_line_skipped_on_load`` |
| Isolation from execution stack | ``test_execution_stack_does_not_import_learning_store`` |
| Default path layout | ``test_default_store_path_is_under_runtime`` |

## Forbidden scope

- Store is separate from harness ``memory_bundle`` / DCR JSONL; no automatic merge into fusion.
- ``replay_runner`` / ``pattern_game`` / ``web_app`` / ``renaissance_v4/core`` do not import the store (see test).

## Operational closeout

Commit → ``git push origin main`` → SSH clawbot ``~/blackbox`` → ``git pull`` → ``bash scripts/pattern_game_remote_restart.sh`` → ``curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/`` → expect **200**; record ``HEAD`` and curl in engineering proof.
