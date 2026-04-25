# GT_DIRECTIVE_024D — Student Full Control Execution Lane

**Status:** **IMPLEMENTED (v1)** — code + contract + tests  
**Parent:** `GT_DIRECTIVE_024_series_student_execution_authority_v1.md`  
**Prerequisite:** GT-024C closed as **baseline-gated** only.

## One-line summary

**Full Student control** means the Student lane can admit entries on the **fusion veto** path (fusion `no_trade` while a **directional signal** matches `student_execution_intent_v1`), still **flat** and **risk-gated** — not “trade every bar,” and not silent relabeling of baseline.

---

## Problem (solved in v1)

024C could not open when `fusion_result.direction == no_trade`, even if signals and Student agreed. Product needed an explicit, opt-in mode with separate `execution_authority_v1` and trace copy.

## Vocabulary (frozen)

| `execution_authority_v1` | Meaning |
|--------------------------|--------|
| `baseline_control` | Main batch row: Referee / manifest control. |
| `baseline_gated_student` | 024C: intent applies only when a baseline entry would already open (fusion long/short + risk). |
| `student_full_control` | 024D: includes **full_control_024d_fusion_veto** path below. |

## Engine semantics (v1)

### A — Baseline-gated (024C), unchanged

When `student_full_control_lane_v1` is **false** (default for `run_manifest_replay`):

- Same as 024C: if fusion is directional and risk allows, `student_execution_intent_v1` may **override direction** or **no_trade** to suppress.

### B — Full-control fusion veto (024D)

When `student_full_control_lane_v1` is **true** and `student_execution_intent_v1` is set:

- If **(flat ∧ risk.allowed ∧ fusion = no_trade ∧ at least one active signal direction matches intent enter_long/enter_short)**, open in that direction.
- If fusion is **already** directional, **A** applies first (024C path); veto path does not apply on the same bar.
- **No** entry without a matching active directional **signal** (no naked Student).

### Risk and position state

- **Risk governor** must still `allow` (same as baseline entries).
- **Flat** only (no pyramiding in this v1 table).

## Contract surface

- `exam_run_contract_v1` / `exam_run_contract_request_v1`:  
  - `student_controlled_execution_v1` (memory/LLM profiles)  
  - `student_execution_mode_v1`: `baseline_gated` \| `student_full_control` (parsed only when controlled execution is on)  
  - `student_full_control_v1`: `not_implemented` \| `enabled` (enabled when mode is `student_full_control`)
- `student_lane_authority_truth_v1` — non-ambiguous copy on scorecard.

## Code map (proof)

| Piece | Location |
|-------|----------|
| Entry decision | `renaissance_v4/research/replay_runner._compute_student_lane_entry_v1` |
| Replay loop + audit | `run_manifest_replay(..., student_full_control_lane_v1=...)` → `student_full_control_replay_audit_v1` on return dict |
| Orchestration + authority tag | `renaissance_v4/game_theory/student_controlled_replay_v1.attach_student_controlled_replay_v1` (`student_full_control_lane_v1` on scenario) |
| Exam automation | `apply_automated_student_lanes_from_exam_contract_v1` sets scenario flag from `student_execution_mode_v1` |
| Contract parse + line meta | `renaissance_v4/game_theory/exam_run_contract_v1` |
| UI | Pattern Machine: `#examStudentExecutionModePick` in `web_app` |

## Tests

- `renaissance_v4/game_theory/tests/test_student_lane_entry_024d_v1.py` — decision table.  
- `test_student_controlled_replay_v1` — `attach` passes `student_full_control_lane_v1` to replay.  
- `test_gt_directive_015_exam_run_contract_v1` — parse + scorecard line for full control.

## Proof bar (closure)

- [x] Engine path for fusion veto with documented guards (signal + risk + flat).  
- [x] `student_full_control_v1: enabled` only when mode + engine match.  
- [x] Trace and `student_controlled_replay_v1` payload carry `execution_authority_v1` and audit.  
- [x] L1 / L3 / debug fields remain distinguishable (no silent mix with 024C-only runs).  

## Deferred (not v1)

- Pyramiding, risk override, or entries **without** any directional signal.  
- Per-bar or per-trade intent in replay (single intent object per scenario today).  
