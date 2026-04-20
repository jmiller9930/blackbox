# Directive 07 — Cross-run behavioral proof (acceptance)

## Objective

Demonstrate in **automated tests** that prior ``student_learning_record_v1`` rows, once retrieved into the legal pre-reveal packet, **change observable Shadow Student fields** versus the same causal decision point without retrieval, and that **reset** (no matching retrieval) restores the baseline output.

## Mechanism (observable, no execution authority)

``emit_shadow_stub_student_output_v1`` inspects ``retrieved_student_experience_v1`` (Directive 06). When non-empty:

- appends recipe id ``cross_run_retrieval_informed_v1``;
- raises ``confidence_01`` (bounded);
- updates ``student_decision_ref`` (UUIDv5 seed includes retrieval count);
- extends ``reasoning_text`` with a Directive 07 marker.

Referee / fusion / replay are unchanged; proof is confined to Student-side artifacts.

## Automated proof

**Module:** ``renaissance_v4/game_theory/tests/test_directive_07_cross_run_proof_v1.py``

| Step | Test assertion |
|------|----------------|
| Run 1 — append learning row | ``_make_and_store_prior_run`` |
| Run 2a — baseline packet, shadow emit | ``o0`` |
| Run 2b — enriched packet + shadow emit | ``o1`` — differs from ``o0`` on recipes, confidence, ref, reasoning |
| Reset — empty retrieval (wrong key) | ``o2`` matches ``o0`` |
| Hot-path isolation | ``test_replay_runner_does_not_import_student_path`` |

## Operational closeout

Commit → ``git push origin main`` → SSH clawbot ``~/blackbox`` → ``git pull`` → ``bash scripts/pattern_game_remote_restart.sh`` → ``curl`` ``http://127.0.0.1:8765/`` → **200**; record ``git rev-parse HEAD`` and curl in engineering proof.
