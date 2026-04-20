# Directive 04 — Reveal layer (acceptance proof)

## Objective

Structured ``reveal_v1`` join of validated ``student_output_v1`` and Referee truth from :class:`~renaissance_v4.core.outcome_record.OutcomeRecord`, with no Referee mutation and no execution-path coupling.

## Implementation

- **Module:** ``renaissance_v4/game_theory/student_proctor/reveal_layer_v1.py``
  - ``outcome_record_to_referee_truth_v1`` — maps ``OutcomeRecord`` → ``referee_truth_v1`` (Referee fields only).
  - ``build_comparison_v1`` — Referee-grounded comparison dict (direction match, referee PnL sign).
  - ``build_reveal_v1_from_outcome_and_student`` — validates Student snapshot, enforces ``graded_unit_id == trade_id``, runs ``validate_reveal_v1``.

## Required tests (evidence)

| Concern | Test |
|--------|------|
| Join validates | ``test_build_reveal_validates_and_joins`` |
| Graded unit must match | ``test_mismatched_graded_unit_fails`` |
| Referee mapping | ``test_referee_truth_maps_outcome_fields`` |
| Pre-reveal vs reveal separation | ``test_reveal_is_not_a_pre_reveal_packet`` — ``validate_pre_reveal_bundle_v1(reveal)`` is non-empty while ``validate_reveal_v1(reveal)`` is empty |
| Comparison logic | ``test_comparison_direction_match_false_when_student_differs`` |
| E2E (packet → shadow → reveal) | ``test_e2e_packet_shadow_reveal_chain`` |
| No execution import | ``test_execution_stack_does_not_import_reveal_layer`` |
| Example JSON | ``test_examples_reveal_v1_layer_built_json_validates`` |

## Example artifact

- ``renaissance_v4/game_theory/examples/reveal_v1_layer_built_example.json`` — produced by the builder; passes ``validate_reveal_v1``.

## Forbidden scope (honored)

- Referee numbers are copied from ``OutcomeRecord``, not recomputed or overwritten.
- Reveal builder is not imported by ``replay_runner``, ``pattern_game``, ``web_app``, or ``renaissance_v4/core`` (see isolation test).

## Operational closeout

After merge: commit → ``git push origin main`` → SSH clawbot ``~/blackbox`` → ``git pull`` → ``bash scripts/pattern_game_remote_restart.sh`` → ``curl`` ``http://127.0.0.1:8765/`` → HTTP 200; record SHA and curl proof in the engineering response.
