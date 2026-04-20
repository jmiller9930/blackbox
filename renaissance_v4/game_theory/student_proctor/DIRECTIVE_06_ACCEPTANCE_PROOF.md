# Directive 06 — Cross-run retrieval (acceptance proof)

## Objective

Load prior ``student_learning_record_v1`` rows and attach **pre-reveal-safe** slices into a legal ``student_decision_packet_v1`` only via ``retrieved_student_experience_v1``, without engine-memory relabeling, execution influence, or forbidden-key leakage.

## Implementation

- **Contracts:** ``SCHEMA_STUDENT_RETRIEVAL_SLICE_V1``, ``FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1`` in ``contracts_v1.py``.
- **Module:** ``cross_run_retrieval_v1.py``
  - ``project_student_learning_record_to_retrieval_slice_v1`` — strips referee outcome fields that use forbidden key names for pre-reveal; keeps prior ``student_output`` + ids + optional ``prior_symbol_hint`` (symbol is not a forbidden key).
  - ``build_student_decision_packet_v1_with_cross_run_retrieval`` — causal bars + slices matched by ``context_signature_v1.signature_key`` via the Student Learning Store.
- **Packet validation:** ``validate_student_decision_packet_v1`` enforces slice schema/version and runs full-tree ``validate_pre_reveal_bundle_v1``.

## Tests (``test_cross_run_retrieval_v1.py`` + context builder suite)

| Concern | Test |
|---------|------|
| Two prior rows → two slices, packet validates | ``test_retrieval_slices_injected_into_legal_packet`` |
| No ``pnl`` substring in serialized packet JSON | same (forbidden-key guard) |
| Wrong signature → empty list, still valid | ``test_wrong_signature_yields_empty_retrieval`` |
| Projection omits referee PnL branch | ``test_projection_drops_referee_pnl_branch`` |
| Isolation (replay/pattern_game/web/core) | ``test_execution_stack_no_cross_run_import`` |
| Backward compatibility | Existing ``test_student_context_builder_v1`` — packets without retrieval unchanged |

## Operational closeout

``git push origin main`` → SSH clawbot ``~/blackbox`` → ``git pull`` → ``bash scripts/pattern_game_remote_restart.sh`` → ``curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/`` → **200**; capture ``git rev-parse HEAD`` and curl proof.
