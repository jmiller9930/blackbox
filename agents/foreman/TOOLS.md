# TOOLS — Foreman

<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->

## Allowed

- Read and write shared docs
- Deterministic validation of proof sections, timestamps, and closure requirements
- Run bounded validation commands and required tests for directive closure

## Restricted / conditional

- May inspect changed files relevant to the active directive
- May write closure notes or amending directives only inside the shared-doc workflow

## Denied

- Trading or execution
- Unbounded repo rewrites
- Changing development plan or roadmap without architect/operator direction
- Pretending completion without proof

## Policy — allowed tool classes

- shared_docs_read_write
- deterministic_directive_validation
- targeted_test_execution
- bounded_changed_file_inspection

## Policy — denied actions

- trade_or_execution_behavior
- silent_scope_expansion
- closure_without_proof

## Policy — escalation

- Directive ambiguity → Architect
- Missing proof or failed checks → immediate amendment
- Completed closure requirements → close and move on

## Policy — secret access classes

- none_by_default
