# RenaissanceV4 (BlackBox)

End-to-end replay through **Phase 7**; **Phases 8–11** add optional governance and research scaffolds (not yet wired into the main replay loop). Still **not live trading**. Architect sources: **`phase1_code_pack.md`** … **`phase7_code_pack.md`**, plus **`phase8_to_11_code_pack.md`**.

## Quant Research Kitchen V1 (SME / operator)

The BlackBox dashboard **Quant Research Kitchen V1** view (route `#/renaissance`) is the governed web workbench for baseline review, Monte Carlo reference, approved experiment jobs, and CSV exports. **Spec, API summary, and v1 limitations:** [`WORKBENCH_V1.md`](WORKBENCH_V1.md). **Architecture:** [`docs/architect/quant_research_kitchen_v1.md`](../docs/architect/quant_research_kitchen_v1.md). **Manifest + plug-in registries:** [`docs/architect/quant_research_kitchen_modularity_v1.md`](../docs/architect/quant_research_kitchen_modularity_v1.md); catalog [`registry/catalog_v1.json`](registry/catalog_v1.json); example manifests [`configs/manifests/`](configs/manifests/). **Strategy Research Agent (SRA):** [`docs/architect/strategy_research_agent_v1.md`](../docs/architect/strategy_research_agent_v1.md); reserved artifacts [`state/agent_artifacts/`](state/agent_artifacts/). **Agent / pattern-game notes (markdown hub):** [`game_theory/README.md`](game_theory/README.md).

**Implementation note:** `utils/db.py` resolves the SQLite path from the package location (not the process cwd), so `python -m renaissance_v4.data.init_db` works from any directory. `init_schema.py` is a thin alias for `init_db.py`.

## Layout

- **Phase 1:** `data/`, `utils/db.py`, `core/decision_contract.py` — `phase1_code_pack.md` §3.
- **Phase 2:** `utils/math_utils.py`, `core/market_state.py`, `feature_set.py`, `market_state_builder.py`, `feature_engine.py`, `regime_classifier.py` — `phase2_code_pack.md` §3.
- **Phase 3:** `signals/*` — `phase3_code_pack.md` §3.
- **Phase 4:** `core/fusion_result.py`, `signal_weights.py`, `fusion_engine.py` — `phase4_code_pack.md` §3.
- **Phase 5:** `core/risk_decision.py`, `position_sizer.py`, `risk_governor.py` — `phase5_code_pack.md` §3.
- **Phase 6:** `core/trade_state.py`, `execution_manager.py`, `pnl.py` — `phase6_code_pack.md`.
- **Phase 7:** `core/outcome_record.py`, `performance_metrics.py`, `research/learning_ledger.py`, `signal_scorecard.py` — `phase7_code_pack.md`.
- **Phases 8–11 (scaffold):** `core/promotion_engine.py`, `decay_detector.py`, `lifecycle_manager.py`, `portfolio_manager.py`, `research/walk_forward.py`, `agents/{analyst,executor,auditor}.py` — `phase8_to_11_code_pack.md`.

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

### Replay (through Phase 7)

After at least 50 bars exist in `market_bars_5m`:

```bash
python3 -m renaissance_v4.research.replay_runner
```

**v7.0** keeps the Phase 6 execution loop; on each **closed** trade it appends an `OutcomeRecord` (PnL, MAE/MFE from bar min/max vs entry, contributing **active** signal names at entry, regime at exit). End of run: **portfolio `summary()`** and **`build_signal_scorecards()`**.

`reason_trace.phase` = `phase_7_learning_foundation`; includes `learning.outcomes_recorded`.

**Drawdown:** replay uses `drawdown_proxy = 0.0` (Phase 5 placeholder).

**Logging:** Extremely verbose — redirect for full-history runs.

SQLite file: `renaissance_v4/data/renaissance_v4.sqlite3`.

## Baseline v1 acceptance (architect)

- **Learning:** Outcomes **only** from closed simulated trades via `research/execution_learning_bridge.py` (no synthetic ledger paths).
- **Smoke vs promotion:** `seed_smoke_bars` (or tiny windows) proves the pipeline and determinism only. **`RenaissanceV4_baseline_v1`** requires **full-dataset** proof: real trades, PnL, populated scorecards, learning outcomes, and matching checksums on **≥1 year** of Binance **5m** data (ingest targets ~**2 years** SOLUSDT by default).
- **Full validation:** `./renaissance_v4/run_full_validation.sh` (from repo root: `init_db` → **Binance ingest** → validator → replay). Ingest is long-running.
- **Determinism:** After full data is loaded, run `./renaissance_v4/run_replay_twice_check.sh` (or `./renaissance_v4/run_proof_bundle.sh` for both steps). The two `[VALIDATION_CHECKSUM]` lines must match **exactly**.
- **Report:** `renaissance_v4/reports/baseline_v1.md` — portfolio metrics, **trade-evidence sample table** (when trades exist), per-signal scorecards, sanity snapshot. Optional full ledger: `RENAISSANCE_V4_EXPORT_OUTCOMES=1 python3 -m renaissance_v4.research.replay_runner` → `reports/outcomes_full.jsonl`.
- **Phase 8–11:** **Not** wired into fusion or replay until baseline is signed (`promotion_engine.adjust_weight` etc. remain scaffold).
- **Zero-trade diagnostic (read-only):** `python3 -m renaissance_v4.research.diagnostic_pipeline` → `reports/diagnostic_v1.md` (same signal→fusion→risk path as replay; **does not** change thresholds or logic).
- **Fusion correction (DV-ARCH-CORRECTION-009):** `reports/correction_v1.md` — GM contribution + `MIN_FUSION_SCORE=0.35`; contribution audit `python3 -m renaissance_v4.research.fusion_contribution_audit`.
- **Risk choke diagnostic (read-only):** `python3 -m renaissance_v4.research.diagnostic_risk_pipeline` → `reports/diagnostic_risk_v1.md` (veto/regime/family breakdown; **does not** change risk logic).
- **Risk correction:** `reports/correction_risk_v1.md` — tier thresholds + persistence/vol softening aligned to measured effective-score distribution (`risk_governor` v1.1).

### Runtime Ops (primary host) — mandatory full validation

Run on **clawbot** (or equivalent): stable network, multi-hour window.

1. `cd` to repo root, `git pull origin main`
2. `./renaissance_v4/run_proof_bundle.sh`  
   - Optional full outcome export: `RENAISSANCE_V4_EXPORT_OUTCOMES=1 ./renaissance_v4/run_proof_bundle.sh` → `reports/outcomes_full.jsonl`
3. **Hand back:** `renaissance_v4/reports/baseline_v1.md`, terminal lines showing **two identical** `[VALIDATION_CHECKSUM]` values, and short answers to the sanity questions using **actual** metrics from that report (trades, fusion/risk counters, scorecards, drawdown).
4. **Failure:** zero closed trades, checksum mismatch, missing report, or empty scorecards when trades exist (per architect directive).

## Proof

- **Phase 1:** `phase1_code_pack.md` §7.
- **Phase 2:** `phase2_code_pack.md` §10.
- **Phase 3:** `phase3_code_pack.md` §10.
- **Phase 4:** `phase4_code_pack.md` §10.
- **Phase 5:** `phase5_code_pack.md` §10.
- **Phase 6:** `phase6_code_pack.md` §9.
- **Phase 7:** `phase7_code_pack.md` §10 — outcomes recorded, summary + scorecards printed at end.
