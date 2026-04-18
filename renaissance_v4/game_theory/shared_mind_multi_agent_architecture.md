# Shared-Mind Multi-Agent Architecture
## Detailed build document for a two-agent trading research system that operates as one cognitive system

---

# 1. Purpose

This document defines a **shared-mind multi-agent architecture** for a trading research and paper-trading system.

The goal is to support at least two specialized agents:

1. **Event Watcher Agent**
2. **Cook / Research Agent**

These agents must remain **functionally separate** while behaving **as if they were of one mind**.

That means:

- separate jobs
- separate execution paths
- shared vocabulary
- shared memory
- shared context
- shared objective function
- shared evidence standards

This document is written so a developer can implement the system directly without having to invent missing architecture.

---

# 2. Why split the agents at all

A single giant agent is the wrong architecture for this problem.

The jobs are materially different:

## 2.1 Event Watcher job
This job is:

- real-time
- streaming
- narrow in purpose
- detection/classification oriented
- high frequency
- fact-emitting

## 2.2 Cook / Research job
This job is:

- batch and cycle oriented
- memory heavy
- search and testing oriented
- policy generation oriented
- evaluation oriented
- slower than the watcher
- dependent on experiment history

Combining them into one giant agent causes:

- unclear boundaries
- poor debuggability
- harder evaluation
- mixed incentives
- harder scaling
- muddy state handling

The correct model is:

> separate specialists, unified cognition

---

# 3. High-level design truth

The system must be built on this rule:

> **Different bodies, one mind**

That means the agents do not need to be the same process, but they must share:

- the same canonical event vocabulary
- the same canonical policy vocabulary
- the same context store
- the same experiment ledger
- the same objective function
- the same scoring rules
- the same evidence standards

If those are not shared, the agents will drift and stop acting like one system.

---

# 4. Core system roles

---

## 4.1 Event Watcher Agent

### Mission
Continuously watch live market streams and detect structural market events.

### It does NOT:
- directly trade
- directly promote policies
- directly override baseline
- make production decisions

### It DOES:
- detect events
- classify events
- score event confidence
- publish structured facts
- write event records into shared memory

### Example event classes
- short squeeze risk
- long squeeze risk
- stop-run up
- stop-run down
- liquidity vacuum
- volatility expansion
- volatility shock
- abnormal acceleration
- mean-reversion setup after forced move
- order-book dislocation
- funding imbalance event
- open-interest flush

### Output type
Structured event records, not prose.

---

## 4.2 Cook / Research Agent

### Mission
Use the policy vocabulary, market history, current baseline, and watcher outputs to generate, test, rank, and refine candidate policies.

### It does NOT:
- invent arbitrary undefined indicators
- bypass validation
- bypass promotion gates
- directly replace production baseline

### It DOES:
- read baseline policy
- read candidate history
- read event watcher records
- create policy variants
- schedule tests
- interpret results
- search around winners
- kill weak branches

### Output type
Structured policy candidates, test plans, rankings, and summaries.

---

## 4.3 Execution / Promotion Layer

This is not a free-thinking agent.

It is a controlled operational layer.

### Mission
Accept only proven policies and enforce capital/risk controls.

### It does:
- accept only approved bankroll candidates
- deploy constrained capital
- monitor live behavior
- trigger kill switches
- retire degraded strategies

### It does NOT:
- experiment
- invent
- search
- improvise

This layer must remain boring and strict.

---

# 5. Required shared layers

The agents only behave like one mind if these shared layers exist.

---

## 5.1 Canonical Event Registry

This is the single source of truth for market event names and meanings.

### Purpose
Prevent naming drift and interpretation drift between agents.

### Required fields
Each event definition should include:

- `event_type`
- `event_version`
- `description`
- `required_features`
- `optional_features`
- `default_confidence_rules`
- `severity_scale`
- `intended_usage`
- `status` (active/deprecated/research)

### Example
```json
{
  "event_type": "short_squeeze_risk",
  "event_version": "v1",
  "description": "Elevated probability of forced upward move caused by crowded short positioning and cascading stop/liquidation behavior.",
  "required_features": [
    "price_acceleration_up",
    "volume_spike",
    "open_interest_shift"
  ],
  "optional_features": [
    "funding_skew_negative",
    "liquidation_cluster_above"
  ],
  "severity_scale": "0_to_1",
  "intended_usage": [
    "policy_filter",
    "regime_label",
    "risk_modifier"
  ],
  "status": "active"
}
```

### Developer rule
No code path should use an event label that is not present in this registry.

---

## 5.2 Canonical Policy Vocabulary

This is the shared language of strategy construction.

### Purpose
Ensure both humans and agents use the same policy grammar.

### Required categories
- indicators
- derived features
- event conditions
- comparison operators
- logical operators
- risk controls
- execution directives
- parameter range definitions

### Example categories
Indicators:
- ema200
- rsi14
- atr14
- supertrend

Event conditions:
- short_squeeze_risk
- long_squeeze_risk
- volatility_expansion
- liquidity_vacuum

Risk controls:
- stop_atr
- target_atr
- max_trades_per_day
- risk_pct
- leverage_cap

### Developer rule
The cook must only generate policies from this vocabulary unless explicitly placed into a higher-risk experimental namespace.

---

## 5.3 Shared Context Store

This is the living “current mind” of the system.

### Purpose
Hold the current market context, active events, baseline status, and recent experiment state in one queryable place.

### It should contain
- current market state snapshot
- recent event detections
- recent baseline behavior
- active candidate behaviors
- regime classification
- research cycle metadata
- rolling performance summaries

### Example object
```json
{
  "symbol": "SOL-PERP",
  "timestamp": "2026-04-17T18:25:00Z",
  "market_regime": "high_volatility_trend",
  "active_events": [
    {
      "event_type": "short_squeeze_risk",
      "confidence": 0.81
    },
    {
      "event_type": "volatility_expansion",
      "confidence": 0.74
    }
  ],
  "baseline_state": {
    "policy_id": "baseline_v1",
    "recent_pnl": 123.4,
    "recent_drawdown": 0.03,
    "recent_trade_quality": "degrading"
  },
  "research_state": {
    "active_generation_batch": "gen_2026_04_17_01",
    "candidate_count": 45
  }
}
```

### Developer rule
Both watcher and cook must read from and write to the same shared context store, even if one of them also has private local state.

---

## 5.4 Shared Experiment Ledger

This is the long-term memory of the system.

### Purpose
Store all policy experiments, event annotations, mutation history, pass/fail decisions, and outcomes.

### It should answer questions like
- What has already been tested?
- Which policy families failed?
- Which event conditions improved or degraded results?
- Which candidate branches should not be revisited?
- When did a policy become bankroll-eligible?
- Which event regimes correlated with drawdown spikes?

### Required record types
- policy lineage records
- candidate generation records
- backtest result records
- cross-window validation records
- live paper shadow records
- promotion decisions
- retirements
- event performance associations

### Developer rule
Nothing important may happen without a ledger record.

---

## 5.5 Shared Objective Function

Both agents must work toward the same definition of success.

### Purpose
Prevent one agent from maximizing noisy activity while the other is maximizing stability.

### Recommended objective priorities
1. risk-controlled improvement
2. baseline-relative performance
3. stable expectancy
4. low drawdown
5. robustness across windows/regimes
6. controlled trade count
7. low false-discovery rate

### Developer rule
The watcher is not rewarded for “interesting detections.”
The watcher is rewarded only if its detections become useful features for improving policies or reducing risk.

---

# 6. Architecture diagram in words

The clean flow is:

**Market Data Ingest**
↓
**Event Detection Layer**
↓
**Shared Context Store**
↓
**Cook / Research Layer**
↓
**Testing + Scoring Pipeline**
↓
**Promotion Controller**
↓
**Execution / Paper / Production Lanes**

This is the correct order of dependency.

---

# 7. Detailed subsystem design

---

## 7.1 Market Data Ingest Layer

### Purpose
Provide normalized market and market-adjacent data to all downstream systems.

### Typical inputs
- candles / bars
- trades / ticks
- order book snapshots if available
- open interest
- funding rate
- liquidation feed if available
- mark/index price
- derived indicators
- external context feeds if approved

### Responsibilities
- normalize timestamps
- standardize symbol naming
- guarantee ordering
- persist raw feed snapshots if needed
- compute or attach derived features
- publish clean data into shared infrastructure

### Developer requirement
No detector or research component should directly scrape raw external feeds independently if you can centralize the ingest.
Centralize ingestion to avoid inconsistent interpretations.

---

## 7.2 Event Detection Layer

This can be one service with multiple detectors or multiple services.

### Recommended design
One event framework, multiple detector modules.

### Example detector modules
- squeeze_detector
- stop_run_detector
- volatility_shock_detector
- liquidity_vacuum_detector
- funding_imbalance_detector
- open_interest_flush_detector

### Input
Normalized market data + optional order book/open interest/funding context

### Output
Structured event records

### Event record schema
```json
{
  "event_id": "evt_20260417_001",
  "symbol": "SOL-PERP",
  "timestamp": "2026-04-17T18:25:00Z",
  "event_type": "short_squeeze_risk",
  "event_version": "v1",
  "confidence": 0.81,
  "severity": 0.72,
  "supporting_features": {
    "price_acceleration_up": 2.1,
    "volume_spike": true,
    "oi_shift": -0.9,
    "funding_skew_negative": true
  },
  "time_horizon_hint": "short",
  "status": "active"
}
```

### Developer requirement
Detectors must emit facts, not opinions.

Bad:
- “Maybe this looks bullish.”

Good:
- structured event record with confidence and supporting features

---

## 7.3 Shared Context Store

### Purpose
Serve as the “active consciousness” of the system.

### Storage model
This can be:
- Redis for fast current-state access
- a structured state document store
- or a combined cache + persistent store

### It should support
- latest event lookup by symbol
- active event set by time window
- current baseline metrics
- current market regime
- active candidate summaries
- experiment generation metadata

### Context package generation
The store should be able to produce a packaged context object for any consumer.

Example:
```json
{
  "symbol": "SOL-PERP",
  "as_of": "2026-04-17T18:25:00Z",
  "active_events": [
    {"event_type": "short_squeeze_risk", "confidence": 0.81},
    {"event_type": "volatility_expansion", "confidence": 0.74}
  ],
  "baseline_state": {
    "policy_id": "baseline_v1",
    "recent_drawdown": 0.03,
    "recent_signal_quality": "degrading"
  },
  "regime": "high_volatility_trend",
  "research_focus": "reduce short-side false entries"
}
```

This lets every agent see the same battlefield.

---

## 7.4 Policy Registry

### Purpose
Hold all policy definitions and status.

### Required fields
- `policy_id`
- `parent_policy_id`
- `origin_type`
- `policy_family`
- `market`
- `timeframe`
- `entry_long_conditions`
- `entry_short_conditions`
- `filters`
- `risk_rules`
- `execution_semantics_version`
- `mutation_summary`
- `status`
- `version`
- `created_at`

### Status values
- draft
- compile_failed
- compile_passed
- backtest_pending
- backtest_failed
- backtest_passed
- validation_pending
- validation_failed
- validation_passed
- paper_pending
- paper_failed
- paper_passed
- bankroll_candidate
- production_active
- retired

### Developer requirement
A policy without state should not exist.

---

## 7.5 Policy Builder / Compiler

### Purpose
Convert structured policy definitions into executable form.

### Responsibilities
- validate syntax
- validate vocabulary usage
- validate parameter ranges
- detect contradictions
- attach execution semantics version
- produce executable policy object

### Example contradictions to reject
- `rsi14 > 60` and `rsi14 < 40` in same always-on branch
- unknown event type
- missing stop/target rule if policy class requires it
- empty entry conditions

### Developer requirement
Nothing goes into backtest without successful compilation.

---

## 7.6 Mutation Engine

### Purpose
Mechanically create child policies from parent policies.

### Inputs
- parent policy
- search intent
- mutation budget
- allowed mutation families
- policy vocabulary constraints

### Example mutation families
- threshold tightening
- threshold loosening
- add event filter
- remove event filter
- add volatility gate
- add frequency cap
- tighten exit
- loosen exit
- shift asymmetry between long/short
- add no-trade regime block

### Output
Child policy with:
- full rule set
- exact mutation summary
- lineage metadata

### Example mutation record
```json
{
  "policy_id": "cand_20260417_014",
  "parent_policy_id": "baseline_v1",
  "mutations": [
    {
      "type": "threshold_adjustment",
      "target": "rsi14_long_entry",
      "from": 52,
      "to": 56
    },
    {
      "type": "add_event_filter",
      "target": "short_entry_block",
      "value": "short_squeeze_risk >= 0.7"
    }
  ]
}
```

### Developer requirement
Mutation types must be explicit and enumerable, not free-form prose.

---

## 7.7 AI Search Orchestrator

### Purpose
Decide where to search next.

### This is where the “mind” feels unified.
It reads:
- active event history
- baseline weakness
- prior experiment outcomes
- candidate family performance
- paper-lane degradation

Then it decides:
- which parent policies to mutate
- which mutation families to emphasize
- whether to explore or exploit
- whether event-derived features are worth testing more heavily

### Inputs
- context store
- experiment ledger
- policy registry
- active event statistics

### Outputs
- search intent
- mutation family weighting
- candidate batch size
- search priority queue

### Example search intent
```json
{
  "search_intent_id": "intent_20260417_003",
  "goal": "reduce short-side drawdown during squeeze-risk conditions",
  "preferred_parent_policies": ["baseline_v1", "cand_20260416_021"],
  "preferred_mutation_families": [
    "add_event_filter",
    "threshold_tightening",
    "frequency_reduction"
  ],
  "candidate_budget": 40
}
```

### Developer requirement
The orchestrator does not write policies directly.
It directs mutation and testing systems.

---

## 7.8 Historical Backtest Engine

### Purpose
Test policies under controlled historical conditions.

### Responsibilities
- load same windows for comparable runs
- use fixed execution semantics
- produce comparable metrics
- support policy-vs-baseline evaluation

### Required outputs
- net pnl
- gross pnl
- max drawdown
- average drawdown
- expectancy
- profit factor
- trade count
- long-only performance
- short-only performance
- time in market
- regime-tagged performance if available

### Developer requirement
The backtester must support baseline-relative comparison, not just absolute metric output.

---

## 7.9 Cross-Window Validation Layer

### Purpose
Prevent promoting lucky one-window winners.

### Required behavior
For candidates surviving primary backtest:
- test on out-of-sample windows
- test on alternate windows
- test across different volatility/trend regimes if possible

### Developer requirement
A candidate cannot become a serious contender based on one great backtest alone.

---

## 7.10 Live Paper Shadow Engine

### Purpose
Run surviving policies on live data with no real capital.

### Responsibilities
- subscribe to live market feed
- evaluate signals in real time
- simulate entries/exits
- record hypothetical outcomes
- compare live paper behavior to expected behavior
- compare to house baseline

### Required metrics
- rolling paper pnl
- rolling drawdown
- signal rate
- divergence from backtest profile
- event-conditioned behavior
- degradation score

### Developer requirement
This must be close to production semantics even though it is paper.

---

## 7.11 Scoring and Culling Engine

### Purpose
Apply pass/fail gates and rank candidates.

### Required gate families
1. structural gate
2. performance gate
3. stability gate
4. forward-behavior gate
5. promotion gate

### Each gate must emit
- gate_name
- result
- thresholds used
- actual values
- reason_code

### Example reason codes
- `compile_unknown_indicator`
- `compile_contradictory_conditions`
- `backtest_pnl_below_baseline`
- `backtest_drawdown_above_limit`
- `validation_window_instability`
- `paper_forward_degradation`
- `promotion_trade_count_insufficient`

### Developer requirement
No candidate should fail silently.

---

## 7.12 Promotion Controller

### Purpose
Move policies from research success to bankroll eligibility, then controlled deployment.

### Required responsibilities
- verify all gate requirements passed
- create promotion evidence bundle
- optionally require human approval
- stage constrained capital allocation
- monitor post-promotion behavior
- retire degraded policies

### Cookie definition
A “cookie” should mean:

> A policy that has passed all research-lane gates and is now eligible for constrained bankroll deployment.

Not every survivor is a cookie.
Only the proven survivors are.

---

# 8. How the two agents actually work together

This section is the core of your requirement.

---

## 8.1 Event Watcher responsibilities in the shared mind

The watcher continuously answers:

- What structural event may be happening?
- How confident are we?
- What features support the classification?
- What time horizon is relevant?
- Is this event active, decaying, or ended?

It writes structured records to:
- event registry-compliant store
- shared context store
- experiment ledger if needed

---

## 8.2 Cook responsibilities in the shared mind

The cook continuously asks:

- Are current baseline losses associated with particular event classes?
- Do event conditions explain drawdown clusters?
- Should current policy block trades under event X?
- Should policy family Y add event filter Z?
- Are there search directions suggested by watcher outputs?

Then it generates candidate policies that explicitly reference those event facts.

### Example policy use
- block shorts when `short_squeeze_risk >= 0.7`
- only allow breakout long when `volatility_expansion >= 0.6`
- reduce trade frequency during `liquidity_vacuum`
- tighten exits under `abnormal_acceleration`

This is how the event watcher becomes useful to the cook.

---

## 8.3 Shared cognition loop

The shared-mind loop is:

1. watcher detects event
2. event written to shared context
3. cook reads event + baseline behavior + experiment history
4. cook generates candidate policies using event facts
5. backtester evaluates candidates
6. ledger records whether those event-aware policies actually improved results
7. watcher signals become more or less valuable based on evidence
8. orchestrator updates future search priorities

This is how the system acts like one mind instead of two separate bots.

---

# 9. Message and data contracts

Do not let these agents speak loose prose to each other.

Use structured contracts.

---

## 9.1 Watcher → Context message
```json
{
  "message_type": "event_detection",
  "symbol": "SOL-PERP",
  "timestamp": "2026-04-17T18:25:00Z",
  "events": [
    {
      "event_type": "short_squeeze_risk",
      "confidence": 0.81,
      "severity": 0.72,
      "supporting_features": {
        "price_acceleration_up": 2.1,
        "volume_spike": true,
        "oi_shift": -0.9
      }
    }
  ]
}
```

---

## 9.2 Context → Cook package
```json
{
  "message_type": "research_context",
  "symbol": "SOL-PERP",
  "as_of": "2026-04-17T18:25:00Z",
  "baseline_policy_id": "baseline_v1",
  "active_events": [
    {"event_type": "short_squeeze_risk", "confidence": 0.81}
  ],
  "baseline_metrics": {
    "recent_pnl": 123.4,
    "recent_drawdown": 0.03,
    "weakness_label": "short_side_degrading"
  },
  "research_goal": "reduce losses during squeeze conditions"
}
```

---

## 9.3 Cook → Mutation/Testing job
```json
{
  "message_type": "candidate_generation_job",
  "parent_policy_ids": ["baseline_v1"],
  "search_intent": "reduce short-side losses during squeeze risk",
  "mutation_families": [
    "add_event_filter",
    "threshold_tightening"
  ],
  "candidate_budget": 40
}
```

---

## 9.4 Testing → Ledger result
```json
{
  "message_type": "candidate_test_result",
  "policy_id": "cand_20260417_014",
  "baseline_policy_id": "baseline_v1",
  "metrics": {
    "net_pnl": 141.2,
    "max_drawdown": 0.021,
    "trade_count": 84,
    "expectancy": 0.18
  },
  "comparison": {
    "pnl_delta_vs_baseline": 18.5,
    "drawdown_delta_vs_baseline": -0.009
  },
  "event_condition_effects": {
    "short_squeeze_risk_filter": "positive"
  },
  "status": "backtest_passed"
}
```

---

# 10. Required state machines

This should not be implicit.

---

## 10.1 Event lifecycle
Events should have states:
- detected
- active
- decaying
- ended
- invalidated

This matters because some policies may care about event onset while others care about post-event decay.

---

## 10.2 Policy lifecycle
Policies should have states:
- draft
- compile_failed
- compile_passed
- backtest_pending
- backtest_failed
- backtest_passed
- validation_pending
- validation_failed
- validation_passed
- paper_pending
- paper_failed
- paper_passed
- bankroll_candidate
- production_active
- retired

---

# 11. What must be logged

Every major action needs a record.

---

## 11.1 On event detection
- detector name
- event type
- confidence
- supporting features
- status transition

## 11.2 On candidate creation
- parent policy
- search intent
- exact mutations
- batch id

## 11.3 On compilation
- pass/fail
- rejection reasons

## 11.4 On backtest
- window
- metrics
- baseline comparison
- gate results

## 11.5 On validation
- cross-window stability
- regime behavior

## 11.6 On paper shadow
- rolling metrics
- anomalies
- degradation alerts

## 11.7 On promotion or retirement
- evidence bundle
- reason codes
- timestamp
- human approver if applicable

Without this, there is no shared memory worth trusting.

---

# 12. Build order for developers

---

## V1 — Shared language and storage
Build first:
- canonical event registry
- canonical policy vocabulary
- policy registry
- shared context store
- experiment ledger

Without these, there is no shared mind.

---

## V2 — Functional bodies
Build next:
- market ingest
- event detectors
- policy compiler
- mutation engine
- backtester
- scoring/culling engine

Without these, the agents cannot act.

---

## V3 — Shared cognition
Build next:
- AI search orchestrator
- context packaging
- event-aware policy generation
- cross-window validation
- live paper shadow engine

Without these, the system is mechanical but not intelligent.

---

## V4 — Promotion discipline
Build last:
- promotion controller
- constrained bankroll activation
- degradation monitoring
- retirement logic

Without these, the system cannot safely move from paper to money.

---

# 13. Failure modes if you ignore this architecture

If you skip the shared layers, you get:
- naming drift
- inconsistent features
- duplicated work
- agents arguing via incompatible concepts
- impossible debugging
- fake “AI cooperation”

If you skip structured data contracts, you get:
- vague prose between agents
- fragile orchestration
- unreliable evaluation
- impossible automation

If you skip the ledger, you get:
- no memory
- repeated bad experiments
- no accountability
- no audit trail

If you skip the objective function lock, you get:
- watcher optimizing for noise
- cook optimizing for paper vanity metrics
- no real improvement

---

# 14. Final implementation truth

To make two agents work together as if they were one mind, you do not merge them into one process.

You give them:

- one language
- one memory
- one context
- one success definition
- one evidence standard

That is the shared mind.

---

# 15. One-sentence definition

The agents are functionally separate but cognitively unified through a canonical event registry, canonical policy vocabulary, shared context store, shared experiment ledger, and common objective function, allowing them to operate as one coordinated research intelligence rather than two disconnected bots.
