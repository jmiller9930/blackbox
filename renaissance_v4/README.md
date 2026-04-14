# RenaissanceV4 (BlackBox)

Research foundation through **Phase 4**: data → features → regime → signals → **fusion** (`long` / `short` / `no_trade`). Still **no risk sizing or execution**. Architect sources: **`phase1_code_pack.md`** … **`phase4_code_pack.md`**.

**Implementation note:** `utils/db.py` resolves the SQLite path from the package location (not the process cwd), so `python -m renaissance_v4.data.init_db` works from any directory. `init_schema.py` is a thin alias for `init_db.py`.

## Layout

- **Phase 1:** `data/`, `utils/db.py`, `core/decision_contract.py` — `phase1_code_pack.md` §3.
- **Phase 2:** `utils/math_utils.py`, `core/market_state.py`, `feature_set.py`, `market_state_builder.py`, `feature_engine.py`, `regime_classifier.py` — `phase2_code_pack.md` §3.
- **Phase 3:** `signals/*` — `phase3_code_pack.md` §3.
- **Phase 4:** `core/fusion_result.py`, `signal_weights.py`, `fusion_engine.py` — `phase4_code_pack.md` §3.

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

### Replay (Phases 2–4)

After at least 50 bars exist in `market_bars_5m`:

```bash
python3 -m renaissance_v4.research.replay_runner
```

**v4.0** runs fusion after signals; `DecisionContract.direction` is the fused outcome (`long`, `short`, or `no_trade`); `reason_trace.phase` = `phase_4_fusion_logic`; `confidence_score` / `edge_score` derive from fusion scores (still `execution_allowed=False`).

**Logging:** Extremely verbose (per-bar builder, features, regime, four signals, fusion). Redirect output for full-history runs.

SQLite file: `renaissance_v4/data/renaissance_v4.sqlite3`.

## Proof

- **Phase 1:** `phase1_code_pack.md` §7.
- **Phase 2:** `phase2_code_pack.md` §10.
- **Phase 3:** `phase3_code_pack.md` §10.
- **Phase 4:** `phase4_code_pack.md` §10 — fusion scores, conflict, overlap penalty, threshold visible in logs and `reason_trace`.
