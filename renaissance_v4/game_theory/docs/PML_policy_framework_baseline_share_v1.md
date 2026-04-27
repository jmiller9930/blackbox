# PML — policy, policy framework, and baseline strategy (share sheet)

**Purpose:** Single document for sharing how **Pattern Machine Learning (PML)** relates to the **learning goal (`goal_v2`)**, the **policy framework** (bounded exploration surface), and the **baseline execution manifest** (catalog-backed strategy).

**Source of truth in repo:** paths below are relative to the repository root unless noted.

---

## 1. How the three layers fit together

| Layer | Role | Repo file(s) |
|--------|------|----------------|
| **PML (operator recipe)** | UI recipe `pattern_learning`: loads **one** curated scenario batch, attaches **`goal_v2`**, wires **manifest + policy framework** for operator harness runs. | `renaissance_v4/game_theory/operator_recipes.py` (`recipe_id: pattern_learning`), scenario batch `renaissance_v4/game_theory/examples/tier1_twelve_month.example.json` |
| **Policy framework** | Declares **what may change** (tunable surface, memory-bundle keys), **context model**, **non-goals**, and **constraints**. Does not replace the execution manifest. | `renaissance_v4/configs/manifests/baseline_v1_policy_framework.json` |
| **Baseline strategy (manifest)** | **Execution** definition: `strategy_id`, symbol, timeframe, signal modules, fusion, risk, execution template, experiment type, etc. Candidate search and learning operate **on top of** this manifest inside the framework. | `renaissance_v4/configs/manifests/baseline_v1_recipe.json` |

**PML default scenario batch** points each row at the same execution manifest:

- `renaissance_v4/game_theory/examples/tier1_twelve_month.example.json` → `manifest_path`: `renaissance_v4/configs/manifests/baseline_v1_recipe.json`

The recipe also sets `policy_framework_path` to the framework JSON for every scenario built from the catalog.

---

## 2. PML operator recipe (summary)

- **Recipe id:** `pattern_learning`  
- **Operator label:** Pattern Machine Learning (PML)  
- **Execution manifest (catalog):** `renaissance_v4/configs/manifests/baseline_v1_recipe.json`  
- **Policy framework:** `renaissance_v4/configs/manifests/baseline_v1_policy_framework.json`  
- **Scenario batch file:** `renaissance_v4/game_theory/examples/tier1_twelve_month.example.json` (default **1** scenario, e.g. `tier1_twelve_month_default`)  
- **Harness:** Runs `operator_test_harness_v1` — **control (baseline) replay** plus **bounded candidate search** vs control; scorecard **Cand / Learn** fields reflect harness output.

**Operator-facing goal summary (from catalog):**

- **Title:** Pattern Outcome Quality  
- **Goal name:** `pattern_outcome_quality`  
- **Primary metric:** `expectancy_per_trade`  
- **Constraints line:** Minimum 5 trades; max drawdown threshold unset.  
- **Note:** Bounded candidate search vs control on the baseline manifest inside the policy framework tunable surface.

---

## 3. PML `goal_v2` (pattern outcome quality)

This object is attached to each PML scenario in code (`operator_recipes._GOAL_V2_PATTERN_OUTCOME_QUALITY`):

```json
{
  "goal_name": "pattern_outcome_quality",
  "objective_type": "outcome_quality",
  "primary_metric": "expectancy_per_trade",
  "secondary_metrics": [
    "avg_win_size",
    "avg_loss_size",
    "win_loss_size_ratio",
    "exit_efficiency"
  ],
  "constraints": {
    "minimum_trade_count": 5,
    "maximum_drawdown_threshold": null
  },
  "notes": {
    "intent_plain": "Improve pattern recognition so trade outcomes are higher quality — not maximizing raw win count or a fixed PnL.",
    "emphasis": "Outcome quality from pattern-aware behavior; engine stays neutral."
  }
}
```

---

## 4. Policy framework (`baseline_v1_policy_framework`)

**Path:** `renaissance_v4/configs/manifests/baseline_v1_policy_framework.json`

Full document (as in repo):

```json
{
  "schema": "policy_framework_v1",
  "framework_id": "baseline_v1_policy_framework",
  "framework_version": "1.0.0",
  "display_name": "Baseline v1 — bounded exploration for pattern outcome quality",
  "documentation": "Defines the constrained behavior space for learning. It does not prescribe winning patterns. Execution still uses execution_manifest_path (catalog-backed manifest).",
  "execution_manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
  "learning_goal_alignment": {
    "operator_goal_model": "pattern_outcome_quality",
    "emphasis": [
      "expectancy_per_trade",
      "avg_win_size",
      "avg_loss_size",
      "win_loss_size_ratio",
      "exit_efficiency"
    ],
    "non_goals": [
      "raw_pnl_maximization",
      "raw_win_count_maximization"
    ],
    "design_intent": "Support tuning and memory-driven adaptation that improve trade outcome quality within the framework — not unrestricted strategy search."
  },
  "context_model": {
    "regime_families": [
      "trend_up",
      "trend_down",
      "range",
      "volatility_compression",
      "volatility_expansion"
    ],
    "fusion_state": {
      "conflict": "High vs low conflict score across fused signals (bounded fusion thresholds in manifest / memory bundle).",
      "directional_alignment": "Aligned vs countertrend directional bars (pattern_context_v1 aggregates)."
    },
    "volatility_buckets": ["compressed", "neutral", "expanding"],
    "notes": "Agent observes regime + fusion context produced by the engine; no hidden parallel world state."
  },
  "signal_families": [
    {
      "id": "trend_continuation",
      "catalog_module": "trend_continuation",
      "role": "Trend-following continuation signals within catalog parameters."
    },
    {
      "id": "pullback_continuation",
      "catalog_module": "pullback_continuation",
      "role": "Pullback entry in trend context."
    },
    {
      "id": "breakout_expansion",
      "catalog_module": "breakout_expansion",
      "role": "Volatility expansion / breakout participation."
    },
    {
      "id": "mean_reversion_fade",
      "catalog_module": "mean_reversion_fade",
      "role": "Mean-reversion / fade lane."
    }
  ],
  "allowed_adaptations": {
    "categories": [
      "fusion_threshold_tuning",
      "signal_confidence_threshold_tuning",
      "signal_family_favoring_or_suppression",
      "module_disablement_within_catalog",
      "execution_geometry_atr_tuning"
    ],
    "tunable_surface": {
      "identifier": "baseline_v1_tunable_surface_v1",
      "summary": "Keys whitelisted for memory-bundle merge, plus per-scenario ATR overrides; bounded DCR v2 multipliers in code constants.",
      "memory_bundle_apply_keys": [
        "atr_stop_mult",
        "atr_target_mult",
        "fusion_min_score",
        "fusion_max_conflict_score",
        "fusion_overlap_penalty_per_extra_signal",
        "mean_reversion_fade_min_confidence",
        "mean_reversion_fade_stretch_threshold",
        "trend_continuation_min_confidence",
        "trend_continuation_min_regime_fit",
        "pullback_continuation_min_confidence",
        "pullback_continuation_volatility_threshold",
        "breakout_expansion_min_confidence",
        "disabled_signal_modules"
      ],
      "scenario_level_keys": ["atr_stop_mult", "atr_target_mult"],
      "decision_context_recall": {
        "note": "Optional replay-time recall + bounded fusion/signal bias (renaissance_v4.game_theory.decision_context_recall). Tuning is via memory matches and manifest-scoped bias — not free-form policy swap.",
        "bounded_constants_reference": "decision_context_recall.DCR_V2_MULT_SOFT_MIN / DCR_V2_MULT_SOFT_MAX and rule thresholds"
      },
      "batch_and_search": {
        "hunter_planner": "Suggests distinct parallel scenarios from scorecard + retrospective (no Referee oracle).",
        "catalog_batch_builder": "ATR sweep batches share one manifest; geometry only within declared grids.",
        "optimizer_note": "Any automated search must respect catalog modules and whitelisted apply keys only."
      }
    }
  },
  "non_tunable_constraints": [
    "No arbitrary new indicators outside catalog + PolicySpec where applicable.",
    "No free-form execution semantics bypassing ExecutionManager / manifest execution_template.",
    "No bypass of manifest + framework layer for production replay paths.",
    "No hidden policy switching: strategy_id and modules must remain catalog-validated.",
    "No additional signal modules beyond those declared on the execution manifest unless manifest is formally replaced."
  ],
  "agent_visibility": {
    "market_data": "Historical OHLCV bars provided by replay (e.g. market_bars_5m) within evaluation window slicing.",
    "structured_context": "Regime, fusion, risk, and pattern_context_v1 aggregates echoed per run — not raw future peeking.",
    "memory_channels": "Promoted memory bundles (whitelisted keys), Groundhog bundle when armed, context-signature memory for DCR when enabled."
  }
}
```

---

## 5. Baseline execution manifest (`baseline_v1_recipe`)

**Path:** `renaissance_v4/configs/manifests/baseline_v1_recipe.json`

This is the **strategy manifest** used for replay (signals, fusion, risk, execution template, etc.):

```json
{
  "schema": "strategy_manifest_v1",
  "manifest_version": "1.0",
  "strategy_id": "renaissance_baseline_v1_stack",
  "strategy_name": "RenaissanceV4 locked baseline — full-history replay stack",
  "baseline_tag": "RenaissanceV4_baseline_v1",
  "symbol": "SOLUSDT",
  "timeframe": "5m",
  "start_date": null,
  "end_date": null,
  "factor_pipeline": "feature_set_v1",
  "signal_modules": [
    "trend_continuation",
    "pullback_continuation",
    "breakout_expansion",
    "mean_reversion_fade"
  ],
  "regime_module": "regime_v1_default",
  "risk_model": "risk_governor_v1_default",
  "fusion_module": "fusion_geometric_v1",
  "execution_template": "execution_manager_v1_default",
  "stop_target_template": "none",
  "monte_carlo_config": {
    "seed": 42,
    "modes": ["shuffle", "bootstrap"],
    "n_simulations": 10000
  },
  "experiment_type": "replay_full_history",
  "notes": "Matches current replay_runner.py signal list and pipeline wiring. Future replay should consume this manifest instead of hardcoding classes."
}
```

---

## 6. Default PML scenario row (curated example)

**Path:** `renaissance_v4/game_theory/examples/tier1_twelve_month.example.json`

Illustrative first row (evaluation window and narrative fields may be overridden by the operator UI merge):

```json
[
  {
    "scenario_id": "tier1_twelve_month_default",
    "tier": "T1",
    "evaluation_window": {
      "calendar_months": 12,
      "referee_note": "Declarative T1 / 12-month contract; full replay uses current SQLite bar range until optional date slicing lands."
    },
    "game_spec_ref": "GAME_SPEC_INDICATOR_PATTERN_V1.md",
    "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
    "training_trace_id": "tier1_batch_v1",
    "agent_explanation": {
      "hypothesis": "Full-history baseline v1 stack on ingested SOLUSDT 5m yields positive expectancy vs strict binary trade scorecard under outcome_rule_v1 (testable vs this replay only).",
      "why_this_strategy": "Runnable preset; replace with partner narrative.",
      "indicator_values": {},
      "learned": "",
      "behavior_change": ""
    }
  }
]
```

---

## 7. Change control

If you edit **policy intent** vs **tunable keys** vs **execution wiring**, update the matching file and keep this share sheet in sync (or regenerate from repo). **Framework** and **manifest** are versioned JSON; **PML** wiring and **`goal_v2`** live in `operator_recipes.py` until moved to external config.

---

*Document: `renaissance_v4/game_theory/docs/PML_policy_framework_baseline_share_v1.md`*
