# RenaissanceV4 (BlackBox)

Research foundation through **Phase 6**: **paper execution simulation** — ATR stop/target (1.6× / 4.0×), SL-first same-bar rule, PnL scaled by risk notional fraction. Still **not live trading**. Architect sources: **`phase1_code_pack.md`** … **`phase6_code_pack.md`**.

**Implementation note:** `utils/db.py` resolves the SQLite path from the package location (not the process cwd), so `python -m renaissance_v4.data.init_db` works from any directory. `init_schema.py` is a thin alias for `init_db.py`.

## Layout

- **Phase 1:** `data/`, `utils/db.py`, `core/decision_contract.py` — `phase1_code_pack.md` §3.
- **Phase 2:** `utils/math_utils.py`, `core/market_state.py`, `feature_set.py`, `market_state_builder.py`, `feature_engine.py`, `regime_classifier.py` — `phase2_code_pack.md` §3.
- **Phase 3:** `signals/*` — `phase3_code_pack.md` §3.
- **Phase 4:** `core/fusion_result.py`, `signal_weights.py`, `fusion_engine.py` — `phase4_code_pack.md` §3.
- **Phase 5:** `core/risk_decision.py`, `position_sizer.py`, `risk_governor.py` — `phase5_code_pack.md` §3.
- **Phase 6:** `core/trade_state.py`, `execution_manager.py`, `pnl.py` — `phase6_code_pack.md`.

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

### Replay (through Phase 6)

After at least 50 bars exist in `market_bars_5m`:

```bash
python3 -m renaissance_v4.research.replay_runner
```

**v6.0** manages at most one open simulated position: each bar, **exit checks first** (high/low vs stop/target, stop before target for pessimistic same-bar rule), then **open** if flat and risk allows a directional fusion. Entry price = **current bar close**; ATR = `features.atr_proxy_14`; size = `risk_decision.notional_fraction`.

`reason_trace.phase` = `phase_6_execution_simulation`; includes `execution` (exits, opens, cumulative PnL).

**Drawdown:** replay uses `drawdown_proxy = 0.0` (Phase 5 placeholder).

**Logging:** Extremely verbose — redirect for full-history runs.

SQLite file: `renaissance_v4/data/renaissance_v4.sqlite3`.

## Proof

- **Phase 1:** `phase1_code_pack.md` §7.
- **Phase 2:** `phase2_code_pack.md` §10.
- **Phase 3:** `phase3_code_pack.md` §10.
- **Phase 4:** `phase4_code_pack.md` §10.
- **Phase 5:** `phase5_code_pack.md` §10.
- **Phase 6:** `phase6_code_pack.md` §9 — deterministic opens/closes, PnL logs, same data → same run.
