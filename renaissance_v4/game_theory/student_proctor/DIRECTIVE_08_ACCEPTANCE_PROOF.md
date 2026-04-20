# Directive 08 — UI / API truth separation (acceptance proof)

## Objective

Operators can see **what** each destructive or clearing action affects: batch scorecard log, engine memory (experience / recall / bundles), vs **Student Proctor** append-only learning JSONL — without hidden coupling.

## Backend

- **Module:** ``student_learning_operator_v1.py`` — ``student_learning_store_status_v1()``, ``clear_student_learning_store_v1`` (typed confirm ``RESET_STUDENT_PROCTOR_LEARNING_STORE``).
- **Clarified docs:** ``pattern_game_operator_reset.py`` — engine reset does **not** truncate the Student Proctor store.
- **Flask**
  - ``GET /api/student-proctor/learning-store`` — read-only path + line count.
  - ``POST /api/student-proctor/learning-store/clear`` — truncates that JSONL only (confirm phrase).
  - ``POST /api/batch-scorecard/clear`` — response includes ``student_proctor_learning_store_unchanged`` + path/line snapshot.
  - ``POST /api/pattern-game/reset-learning`` — response includes ``student_proctor_learning_store_unchanged`` + snapshot.

## UI (pattern-game ``web_app``)

- Score card panel: **Student Proctor learning store** callout + status line + **Clear Student Proctor store…** (separate confirm).
- Confirm copy for **Clear Card** and **Reset Learning State** explicitly states Student Proctor store is **not** cleared by those actions.

## Automated tests

``tests/test_web_app_student_proctor_truth_separation.py`` — scorecard clear and engine reset leave store bytes unchanged; dedicated clear truncates store; GET status; wrong confirm rejected.

## Operational closeout

Commit → ``git push origin main`` → SSH clawbot ``~/blackbox`` → ``git pull`` → ``bash scripts/pattern_game_remote_restart.sh`` → ``curl`` ``http://127.0.0.1:8765/`` → **200**; record ``HEAD`` and curl in engineering proof.
