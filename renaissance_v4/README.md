# RenaissanceV4 (BlackBox)

Implementation scaffold per **RenaissanceV4 — Implementation Pack v1.0**. This is research infrastructure (data → replay → contracts), not a trading strategy runtime.

## Layout

See the implementation pack for the full folder map: `config/`, `data/`, `core/`, `signals/`, `research/`, `utils/`, `tests/`.

## Run from repository root

```bash
cd /path/to/blackbox
export PYTHONPATH=.
```

1. **Create tables**

   ```bash
   python -m renaissance_v4.data.init_schema
   ```

2. **Ingest Binance 5m bars** (network; ~2 years SOLUSDT by default)

   ```bash
   python -m renaissance_v4.data.binance_ingest
   ```

3. **Validate bars**

   ```bash
   python -m renaissance_v4.data.bar_validator
   ```

4. **Replay placeholder** (bar loop only until pipeline is wired)

   ```bash
   python -m renaissance_v4.research.replay_runner
   ```

SQLite file: `renaissance_v4/data/renaissance_v4.sqlite3` (created on first connection).
