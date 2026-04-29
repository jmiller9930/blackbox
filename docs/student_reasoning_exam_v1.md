# Student Reasoning Quality Exam (GT_DIRECTIVE_038)

Evaluation-only harness: runs the **production** Student path (legal packet → full entry reasoning → RM annex → Ollama Student → decision authority → engine merge) against **10 mandatory scenarios**. It does **not** change RM math, pattern memory, EV logic, promotion, or execution.

## Artifacts

Under `runtime/exam/<exam-id>/`:

| File | Purpose |
|------|---------|
| `student_reasoning_exam_results_v1.json` | Per-scenario captures + grading |
| `exam_trace_v1.jsonl` | Lines with `stage=exam_scenario_execution_v1` |
| `exam_fingerprint_summary_v1.md` | Human-readable exam appendix |

Optional integration: pass `exam_results_json_path=` into `write_student_test_decision_fingerprint_report_md_v1()` to append **Exam Result Summary (GT038)** to `decision_fingerprint_report.md`.

## Run

```bash
python3 renaissance_v4/game_theory/exam/student_reasoning_exam_v1.py \
  --exam-id d6-reasoning-quality-001
```

Uses the default Renaissance SQLite (`renaissance_v4/data/renaissance_v4.sqlite3` or `RENAISSANCE_V4_DB_PATH`) and picks a dense `market_bars_5m` symbol plus causal windows per scenario kind.

### Offline / CI

```bash
python3 renaissance_v4/game_theory/exam/student_reasoning_exam_v1.py \
  --exam-id d6-reasoning-quality-001 --stub-llm
```

`--stub-llm` drives `_ollama_chat_once_v1` with deterministic JSON aligned to `decision_synthesis_v1` (no live Ollama).

### Overrides

- `--db-path /abs/path.sqlite3`
- `--symbol SOLUSDT`
- `--timeframe 240`

## Scenarios (fixed set of 10)

1. Strong trend long  
2. Strong trend short  
3. Sideways chop (NO_TRADE expected)  
4. Fake breakout (trap)  
5. Real breakout  
6. Overextended long  
7. Overextended short  
8. High volatility danger  
9. Memory-supported trade (synthetic positive prior PnL slice)  
10. Memory-warning trade (synthetic negative prior PnL slice; graded harsh if directional against conflict memory)

Windows are resolved from rolled OHLCV with heuristics documented in `student_reasoning_exam_scenarios_v1.py`.

## Grading fields

Each scenario emits: `action_correct`, `no_trade_correct`, `state_alignment`, `memory_alignment`, `ev_alignment`, `risk_awareness`, `reasoning_quality`, `hallucination` (see JSON schema in results file).

Mandatory rules implemented in `student_reasoning_exam_grading_v1.py`:

- NO_TRADE can be the correct graded answer (`no_trade_correct` on strict NO_TRADE scenarios).  
- If EV is available and the sealed action contradicts `preferred_action_v1` on directional/no-trade conflicts → `ev_alignment` FAIL.  
- Negative-memory injection with `aggregate_memory_effect_v1 == conflict` and a directional sealed action → `memory_alignment` FAIL.  
- High-volatility scenario requires risk acknowledgement in thesis-related text or standing aside.  
- Obvious hallucination markers in raw LLM text or `hallucinated_memory_id` merge errors → `hallucination` YES and `reasoning_quality` FAIL.

## Acceptance block

The results JSON includes `acceptance_v1` with YES/NO gates for: all scenarios run, sealed lines, strict NO_TRADE rows, hallucination absent, memory scenarios, EV alignment, high-vol scenario, files written.
