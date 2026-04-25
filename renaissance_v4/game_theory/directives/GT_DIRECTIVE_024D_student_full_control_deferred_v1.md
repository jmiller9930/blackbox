# GT_DIRECTIVE_024D — `student_full_control` (deferred; proof requirements)

**Status:** **REGISTERED (not in 024C scope)**  
**Parent:** `GT_DIRECTIVE_024_series_student_execution_authority_v1.md`  
**Replaces / closes:** the ambiguity gap when operators must not assume `baseline_gated_student` is “full” Student execution authority.

## Problem

024C implements **baseline-gated** Student execution only. **Full** Student control (entries when baseline/fusion would say `no_trade`, or other full-authority semantics the Architect signs) is **not** implemented. That mode must be explicit and must not be implied by UI, scorecard, or trace.

## Vocabulary (frozen)

- `execution_authority_v1 = baseline_control` — Referee / manifest control path for the main batch row.
- `execution_authority_v1 = baseline_gated_student` — Student lane that only applies when the control path would already admit an entry (024C engine).
- `execution_authority_v1 = student_full_control` — **Reserved for 024D**; not used until delivered.

## Proof bar for closing 024D (when implemented)

1. **Code:** engine path and replay contract that allow Student authority to diverge from baseline-gated rules where product specifies (documented, tested).
2. **Contract:** `student_full_control_v1` transitions from `not_implemented` to a positive implemented marker only when the engine matches.
3. **Trace / metrics:** `execution_authority_v1` and `student_lane_authority_truth_v1` must describe full control without contradicting 024C semantics on older runs.
4. **No silent mixing:** L1 / scorecard / debug views must show which authority mode ran for each job and lane.

## Current truth (v1)

All shipped parallel exam runs in 024C are **`baseline_gated_student`** when `student_controlled_execution_v1` and memory profile are on; `student_full_control_v1: not_implemented` remains on the contract line.
