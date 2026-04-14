# RenaissanceV4 (BlackBox)

Research foundation through **Phase 5**: fusion → **risk governor** (size tiers, compression, vetoes). **`execution_allowed`** can be true when risk approves a non-zero tier; still **no order execution or simulation** (Phase 6+). Architect sources: **`phase1_code_pack.md`** … **`phase5_code_pack.md`**.

**Implementation note:** `utils/db.py` resolves the SQLite path from the package location (not the process cwd), so `python -m renaissance_v4.data.init_db` works from any directory. `init_schema.py` is a thin alias for `init_db.py`.

## Layout

- **Phase 1:** `data/`, `utils/db.py`, `core/decision_contract.py` — `phase1_code_pack.md` §3.
- **Phase 2:** `utils/math_utils.py`, `core/market_state.py`, `feature_set.py`, `market_state_builder.py`, `feature_engine.py`, `regime_classifier.py` — `phase2_code_pack.md` §3.
- **Phase 3:** `signals/*` — `phase3_code_pack.md` §3.
- **Phase 4:** `core/fusion_result.py`, `signal_weights.py`, `fusion_engine.py` — `phase4_code_pack.md` §3.
- **Phase 5:** `core/risk_decision.py`, `position_sizer.py`, `risk_governor.py` — `phase5_code_pack.md` §3.

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

### Replay (Phases 2–5)

After at least 50 bars exist in `market_bars_5m`:

```bash
python3 -m renaissance_v4.research.replay_runner
```

**v5.0** runs `evaluate_risk()` after fusion; `risk_budget` = notional fraction; `execution_allowed` = risk approval (non-zero tier). `reason_trace.phase` = `phase_5_risk_governance`; nested `risk` block includes tier, compression, vetoes.

**Drawdown:** replay uses `drawdown_proxy = 0.0` (placeholder per pack).

**Logging:** Extremely verbose — redirect for full-history runs.

SQLite file: `renaissance_v4/data/renaissance_v4.sqlite3`.

## Proof

- **Phase 1:** `phase1_code_pack.md` §7.
- **Phase 2:** `phase2_code_pack.md` §10.
- **Phase 3:** `phase3_code_pack.md` §10.
- **Phase 4:** `phase4_code_pack.md` §10.
- **Phase 5:** `phase5_code_pack.md` §10 — risk tier, compression, veto reasons in logs and `reason_trace`.
