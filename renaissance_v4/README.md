# RenaissanceV4 (BlackBox)

Phase 1 research foundation per **`phase1_code_pack.md`** (architect) and the earlier implementation pack. This is data → validation → deterministic replay with a **no-trade decision shell**, not live trading.

**Implementation note:** `utils/db.py` resolves the SQLite path from the package location (not the process cwd), so `python -m renaissance_v4.data.init_db` works from any directory. `init_schema.py` is a thin alias for `init_db.py`.

## Layout (Phase 1)

See `phase1_code_pack.md` §3. The repo may also contain extra packages (`config/`, `signals/`, `tests/`) reserved for later phases.

## Run from repository root

```bash
cd /path/to/blackbox
export PYTHONPATH=.
```

1. **Create tables**

   ```bash
   python3 -m renaissance_v4.data.init_db
   ```

   (Equivalent: `python3 renaissance_v4/data/init_db.py` when run from repo root.)

2. **Ingest Binance 5m bars** (network; ~2 years SOLUSDT by default)

   ```bash
   python3 -m renaissance_v4.data.binance_ingest
   ```

3. **Validate bars**

   ```bash
   python3 -m renaissance_v4.data.bar_validator
   ```

4. **Replay** (placeholder `DecisionContract` per bar — Phase 1 shell)

   ```bash
   python3 -m renaissance_v4.research.replay_runner
   ```

SQLite file: `renaissance_v4/data/renaissance_v4.sqlite3` (created on first connection).

## Phase 1 proof

See `phase1_code_pack.md` §7 — DB created, schema applied, ingest + validator clean, replay completes over the full dataset.
