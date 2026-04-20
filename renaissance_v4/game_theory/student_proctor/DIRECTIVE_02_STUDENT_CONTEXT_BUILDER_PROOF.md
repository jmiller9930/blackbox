# Directive 02 — Student Context Builder (engineering proof)

## Objective met

- **`student_decision_packet_v1`** — versioned envelope + `bars_inclusive_up_to_t` (causal OHLCV only).
- **Causal state** — SQLite `market_bars_5m`: `WHERE symbol = ? AND open_time <= decision_open_time_ms`, capped with `ORDER BY open_time DESC LIMIT N` then chronological for reading.
- **No reveal logic** — builder does not join trades, PnL, or `OutcomeRecord`.
- **No execution influence** — read-only DB access; no replay/fusion changes.

## How causal state is obtained

1. Caller provides **`decision_open_time_ms`** (the simulated “now” bar open time on the tape).  
2. **`fetch_bars_causal_up_to`** returns at most **`max_bars_in_packet`** rows, all with `open_time <= decision_open_time_ms`.  
3. **`build_student_decision_packet_v1`** wraps rows in **`student_decision_packet_v1`** and runs **`validate_pre_reveal_bundle_v1`** before returning; internal inconsistency aborts with error string.

## Tests (reproducible)

```bash
PYTHONPATH=. python3 -m pytest renaissance_v4/game_theory/tests/test_student_context_builder_v1.py -v
```

Coverage:

| Test | Proof |
|------|--------|
| `test_fetch_causal_multiple_timesteps` | Different `decision_open_time_ms` → different bar counts (3 vs 7). |
| `test_no_future_bars_causal_boundary` | Every bar `open_time <= decision_open_time_ms`. |
| `test_build_packet_passes_validate_and_pre_reveal` | Built packet passes `validate_student_decision_packet_v1` and pre-reveal scan. |
| `test_packet_schema_enforced_reject_bad_schema` | Wrong `schema` → validation errors. |
| `test_manual_injected_flashcard_field_fails_pre_reveal` | Injected `pnl` → validators fail. |
| `test_builder_never_emits_forbidden_keys` | Builder output contains no `{pnl,mfe,mae,wins,losses,exit_*}` keys at top level or nested in known structure. |
| `test_empty_db_returns_error_not_crash` | Bad DB path handled without crash. |

## Files

- `student_proctor/student_context_builder_v1.py` — implementation  
- `tests/test_student_context_builder_v1.py` — proof tests (synthetic in-memory DB fixture)

## Operational closeout

**Commit (Directive 02 implementation):** `f25c43086c839ab39ffc31680cc784fa68a4b870` (`f25c4308` on `main`)

**git push (local → `origin/main`):**

```text
To https://github.com/jmiller9930/blackbox.git
   964f73f..f25c430  main -> main
```

**Target server:** `jmiller@clawbot.a51.corp` — `~/blackbox`

- **`git pull`:** fast-forward to **`f25c4308`** — HEAD matches pushed commit.  
- **Flask restart:** `bash scripts/pattern_game_remote_restart.sh` — new PID **985625** (session log line).  
- **Health:** `curl http://127.0.0.1:8765/` → **HTTP 200**.
