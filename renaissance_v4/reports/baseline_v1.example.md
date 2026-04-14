# RenaissanceV4 — Baseline Report v1 (example shape)

This file shows the **structure** produced at `renaissance_v4/reports/baseline_v1.md` after a successful replay.

The real file is **gitignored**; run:

```bash
cd /path/to/blackbox
export PYTHONPATH=.
python3 -m renaissance_v4.data.seed_smoke_bars   # optional minimal data
python3 -m renaissance_v4.research.replay_runner
```

Then open `renaissance_v4/reports/baseline_v1.md`.

Sections: dataset size, portfolio metrics (trades, win rate, expectancy, max drawdown, MAE/MFE), validation checksum, per-signal scorecards, sanity counters.
