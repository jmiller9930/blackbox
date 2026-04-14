# RenaissanceV4 (BlackBox)

Research foundation: **Phase 1** = data → validation → replay shell; **Phase 2** = `MarketState` → `FeatureSet` → regime classifier (still **no trades**). Architect sources: **`phase1_code_pack.md`**, **`phase2_code_pack.md`**.

**Implementation note:** `utils/db.py` resolves the SQLite path from the package location (not the process cwd), so `python -m renaissance_v4.data.init_db` works from any directory. `init_schema.py` is a thin alias for `init_db.py`.

## Layout

- **Phase 1:** `data/`, `utils/db.py`, `core/decision_contract.py`, `research/replay_runner.py` — see `phase1_code_pack.md` §3.
- **Phase 2:** `utils/math_utils.py`, `core/market_state.py`, `feature_set.py`, `market_state_builder.py`, `feature_engine.py`, `regime_classifier.py` — see `phase2_code_pack.md` §3.

Extra packages (`config/`, `signals/`, `tests/`) are reserved for later phases.

## Run from repository root

```bash
cd /path/to/blackbox
export PYTHONPATH=.
```

### Phase 1

1. **Create tables** — `python3 -m renaissance_v4.data.init_db`
2. **Ingest** — `python3 -m renaissance_v4.data.binance_ingest`
3. **Validate** — `python3 -m renaissance_v4.data.bar_validator`

### Phase 2 (after Phase 1 data exists)

Replay builds a 50-bar window, computes features, classifies regime, and attaches a `DecisionContract` with `reason_trace.phase` = `phase_2_market_interpretation`:

```bash
python3 -m renaissance_v4.research.replay_runner
```

**Logging:** Phase 2 prints market state, feature summary, and regime **on every bar** after the first 50 (architect pack). Full-history replays are very verbose; use shorter datasets or redirect logs if needed.

SQLite file: `renaissance_v4/data/renaissance_v4.sqlite3`.

## Proof

- **Phase 1:** `phase1_code_pack.md` §7.
- **Phase 2:** `phase2_code_pack.md` §10 — end-to-end run, features and regimes visible in logs.
