# RenaissanceV4 (BlackBox)

Research foundation through **Phase 3**: data → features → regime → **four signal hypotheses** (still **no trades**, no fusion). Architect sources: **`phase1_code_pack.md`**, **`phase2_code_pack.md`**, **`phase3_code_pack.md`**.

**Implementation note:** `utils/db.py` resolves the SQLite path from the package location (not the process cwd), so `python -m renaissance_v4.data.init_db` works from any directory. `init_schema.py` is a thin alias for `init_db.py`.

## Layout

- **Phase 1:** `data/`, `utils/db.py`, `core/decision_contract.py` — `phase1_code_pack.md` §3.
- **Phase 2:** `utils/math_utils.py`, `core/market_state.py`, `feature_set.py`, `market_state_builder.py`, `feature_engine.py`, `regime_classifier.py` — `phase2_code_pack.md` §3.
- **Phase 3:** `signals/signal_result.py`, `base_signal.py`, `trend_continuation.py`, `pullback_continuation.py`, `breakout_expansion.py`, `mean_reversion_fade.py` — `phase3_code_pack.md` §3.

`config/` and `tests/` remain for later phases.

## Run from repository root

```bash
cd /path/to/blackbox
export PYTHONPATH=.
```

### Phase 1

1. **Create tables** — `python3 -m renaissance_v4.data.init_db`
2. **Ingest** — `python3 -m renaissance_v4.data.binance_ingest`
3. **Validate** — `python3 -m renaissance_v4.data.bar_validator`

### Phase 2 + 3 replay

After at least 50 bars exist in `market_bars_5m`:

```bash
python3 -m renaissance_v4.research.replay_runner
```

**v3.0** evaluates all four signals each bar; `DecisionContract.reason_trace.phase` = `phase_3_signal_architecture`, with `active_signals` and `suppressed_signals` lists.

**Logging:** Phase 2 still prints builder + features + regime every bar; Phase 3 adds **four signal lines** per bar. Full-history replays are extremely verbose—redirect logs or trim locally for debugging.

SQLite file: `renaissance_v4/data/renaissance_v4.sqlite3`.

## Proof

- **Phase 1:** `phase1_code_pack.md` §7.
- **Phase 2:** `phase2_code_pack.md` §10.
- **Phase 3:** `phase3_code_pack.md` §10 — all four signals evaluated; active vs suppressed visible in logs and in `reason_trace`.
