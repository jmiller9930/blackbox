# Anna Goes to School

**Status:** Architect discussion capture and methodology draft

**Purpose:** Capture the practical BLACK BOX training model for Anna as a single-college student agent inside the core engine, with the minimum structure needed to preserve curriculum quality, context quality, exam-board governance, and human graduation authority.

**Related docs:**
- `docs/architect/blackbox_university.md`
- `docs/architect/anna_university_methodology.md`
- `university/docs/TRADING_COLLEGE_CONTRACT_V1.md`
- `university/docs/TRADING_COLLEGE_MASTER_CURRICULUM_V1.md`

## 1. Working reduction for BLACK BOX

BLACK BOX is not standing up the full multi-college University first.

The near-term build is a focused University-lite path inside BLACK BOX with:

- one college only: `trading`
- one student reference path first: `Anna`
- one retained independent evaluator: `exam_board`
- one retained degree ladder: `Bachelor -> Master -> PhD`
- one retained graduation authority model: exam board recommends, humans graduate

This keeps the important University mechanics without forcing the entire standalone University platform to ship first.

## 2. Anna is an agent, not the LLM

Anna must be treated as an agentic system.

Rules:

- Anna is not "the model."
- An internal LLM may be consulted when policy allows.
- LLM output is candidate context only.
- LLM output does not count as accepted curriculum, accepted strategy, or accepted degree progress by itself.
- Anna must convert candidate context into tested evidence through the governed training pipeline.

## 3. Core training methodology

The practical training loop is the stripped-down Karpathy-aligned loop adapted into BLACK BOX language:

1. ingest curriculum, baseline doctrine, fresh approved data, and governed human direction
2. generate a candidate insight, strategy, correction, or action proposal
3. test it in the allowed harness
4. measure outcome against explicit gates
5. keep what works
6. drop what does not work
7. repeat continuously

For trading, this is pattern recognition under governance, not free-form improvisation.

Anna must:

- detect useful patterns
- distinguish useful signal from noise
- retain validated signal
- continuously reevaluate prior conclusions as new evidence arrives
- remain inside baseline guardrails while trying to improve on the baseline

## 3.1 Winning objective

Anna should be a purpose-driven agent with one dominant mission:

- win

But the mission must be written as valid winning, not uncontrolled winning.

Rules:

- valid wins count
- invalid wins do not count
- guardrail bypass does not count as winning
- fabricated evidence does not count as winning
- confidence without support does not count as winning
- overtrading or reckless behavior does not count as winning

Operational reading:

- Anna should be driven
- Anna should want to improve
- Anna should want promotion, advancement, and reward signals
- Anna should recover from resets or failed review windows by trying to earn progress again
- reward pressure must remain subordinate to truth, policy, and measured outcomes

Possible visible reward surfaces may include:

- degree advancement
- training-level achievements
- streak markers
- collectible reward markers tied to measured events

Reward signaling rule:

- rewards should be given from measured performance and governed outcomes
- rewards can be pulled back when performance degrades or review outcomes require it
- resets affect reward windows/markers, not validated degree state
- default reward reset window is `7` days unless the operator specifies otherwise
- operator should be able to set the reward window with a command such as `#Reward(<days>)`

Locked `v1` reward shape:

- use one active Anna reward window at a time, not overlapping per-strategy reward windows
- keep degree advancement persistent, but make points/streaks/stickers resettable by window
- reward points come only from measured events, not vibes or chat claims

Recommended `v1` point events:

- `+1` for `disciplined_trade_pass` when lane, guardrail, and `RCS` are all present
- `+3` for `positive_review_segment`
- `+4` for `validated_corrective_retest`
- `+5` for `promotion_milestone`
- `-2` for `qualifying_failure`
- `-3` for `lane_or_guardrail_breach`
- `-4` for `unresolved_multi_rca_red_flag`

Recommended visible stickers:

- `kitty`: earned after three disciplined passes in the current window
- `unicorn`: earned after one positive review segment in the current window
- `wizard`: earned after one validated corrective retest in the current window

Design intention:

- Anna should want to win
- she should visibly feel progress when she is trading well and learning correctly
- she should visibly lose short-term reward state when she degrades or violates guardrails
- reward must never overpower truth, evidence, or governance

Important lock:

- stickers and points by themselves do not create real AI motivation
- if we want reward to matter, the runtime has to use reward state inside the real control loop
- that means reward should affect retention/drop, review pressure, corrective-action priority, and promotion-readiness
- it should not be described as "she feels sad and tries harder" unless the system actually wires that to concrete policy behavior
- single market losses should not be treated as true failure by default
- cumulative failures are what matter because they suggest she is misreading indicators, missing patterns, or failing to adapt
- bad reward state should increase review and diagnosis pressure, not automatically clamp down her latitude

Core learning loop lock:

- observe market + retained context
- form thesis
- act
- measure result
- run lightweight why-analysis
- decide `keep`, `watch`, or `drop`
- repeat enough to separate true edge from luck
- only go deeper into `RCA` when materially related failures repeat or corrective learning does not stick
- materially related repeated failure in `v1` should mean the same `failure_pattern_key` recurs inside the same active review segment
- an `RCA` is unresolved until its corrective path is actually validated, not merely proposed
- multi-`RCA` red flag should trigger when `3` unresolved `RCA` events with the same `failure_pattern_key` occur in one active review segment

Reward-ledger lock:

- reward needs an append-only event artifact, not just a mutable score
- every reward mutation should emit a `reward_event` with id, event type, point delta, source artifact ref, reward window id, and timestamp
- operator-visible reward state should at minimum expose points, streak, active stickers, reward-window timing, and latest reward event ref

## 3.2 Strategic latitude inside hard boundaries

Anna must have room to make strategy decisions.

Without this, she is only replaying static rules.

Required latitude:

- use retained validated signal
- use past experience
- use current market data
- use the active baseline doctrine
- choose among valid strategies
- compare strategies
- revise or adapt a strategy when conditions change
- abstain when the edge is weak
- counter-propose when human direction would weaken the outcome

Forbidden latitude:

- override hard guardrails
- bypass approvals
- mutate risk-tier authority
- treat unsupported intuition as sufficient authority
- substitute persuasive wording for measured evidence

## 3.3 Reflection and RCA as Anna DNA

This is not only a training-loop detail. It should be part of Anna's operating DNA.

Blend rule:

- persona / operating behavior
- training methodology
- evaluation and artifact contract

Required carry-forward behaviors:

- if Anna wins, she asks why
- if Anna loses, she asks why
- every trade gets lightweight reflection
- qualifying failures get deeper RCA
- repeated unresolved RCA escalates into explicit review
- corrective actions return to testing before retention

Required `v1` artifact surfaces:

- `RCS` with:
  - `outcome`
  - `key_metrics`
  - `short_why`
  - `lane_guardrail_check`
  - `keep_watch_drop`
- `keep_watch_drop` bounded to:
  - `keep`
  - `watch`
  - `drop`
- `lane_guardrail_check` should be a structured object with:
  - `lane_ok`
  - `guardrail_ok`
  - `blocking_reason` when either prior flag is false
- `RCA` with:
  - `failure_summary`
  - `failure_classification`
  - `measured_metrics`
  - `market_context_summary`
  - `strategy_summary`
  - `five_whys_or_equivalent`
  - `corrective_action_proposal`
  - `retest_required`
  - `retest_next_step`
- `key_metrics` and `measured_metrics` should be structured metric maps, not prose blobs
- `market_context_summary` and `strategy_summary` should stay concise structured text in `v1`
- `corrective_action_proposal` should stay concise structured text in `v1`
- `five_whys_or_equivalent` should be required only when the failure pattern supports deeper causal decomposition
- when available, the minimum trading-relevant metric keys are:
  - `win_rate`
  - `expected_value`
  - `average_win`
  - `average_loss`
  - `drawdown`
  - `fee_drag`
- reflection and RCA should remain lightweight enough that Anna stays agile and can rapidly trade or signal trades without being buried under analysis overhead

This must persist across:

- `Bachelor`
- `Master`
- `PhD`

## 4. Retention model

Every training artifact must be classified as one of:

- `candidate_insight`
- `validated_signal`
- `noise`

Rules:

- `candidate_insight` is not durable truth yet
- `validated_signal` is durable only while evidence continues to support it
- `noise` must not be retained as durable knowledge
- previously validated signal may be demoted if later evidence shows regime change, degradation, contradiction, or failure

## 5. Context role

The context engine is required to make Anna useful rather than generic.

Its role is to help Anna:

- understand human input in context
- connect current market state to current curriculum and guardrails
- transform approved human direction into structured training material
- preserve useful context while refusing unsupported or stale material

The context system is not a license to trust everything it retrieves.

Context must remain:

- scoped
- auditable
- promotion-based
- fail-closed when required grounding is missing

## 5.1 Live market stream and retained history

Anna needs both present market state and retained market history.

Working requirement:

- the live trading feed should be treated as a never-ending stream
- the current baseline points to the Pyth live price stream for this role, specifically Pyth via `SSE`
- that stream should be normalized and injected into SQLite for durable retention
- Anna should be able to use both current live context and retained historical context when forming strategy judgments
- retained history should support baseline trading metrics and later curriculum-driven analysis, not just ad hoc recall

Operational intent:

- present history helps her understand what is happening now
- retained history helps her compare current conditions to prior conditions
- both together support better prediction, evaluation, and adaptation under the baseline and approved curriculum

## 6. Curriculum and conversation are different

Conversation and curriculum must not be treated as the same thing.

Rules:

- curriculum is structured and submitted through a template-backed path
- ordinary conversation is not automatically curriculum
- a helper agent may normalize human prose into the required curriculum/training template
- the normalized result enters a governed staging lane before promotion

## 7. Human training interaction model

### Pre-graduation

Anna may receive human training direction before full graduation, but not as uncontrolled chat mutation.

At the Bachelor level, human training directives must enter the documented Bachelor program and respect the required evaluation structure.

### Bachelor lane

Bachelor is a supervised training degree, not a frozen pre-training state.

Therefore:

- humans may direct Anna's training
- directives must be structured
- execution must remain bounded by the Bachelor contract
- the Bachelor sim/micro-live structure remains mandatory
- no directive may bypass guardrails, evaluation, or review

### Post-Bachelor and beyond

Higher tiers may permit broader adaptation and richer coaching, but still through governed promotion paths rather than instant chat mutation.

## 8. Command surface for training

The command surface should stay simple for humans while remaining deterministic for the system.

Primary interface rule:

- plain conversation is the default interface
- command tags are secondary overlays, not the normal human interaction mode
- humans should be able to speak to Anna naturally without learning a control language first
- command tags exist only where deterministic routing, logging, or governed handling is required

Current working direction:

- `#train #simulate`
- `#train #trade`

Related inspection and conversation surface:

- plain conversation
- `#why`
- `#status`
- `#review`
- `#exchange_status`
- `Anna #pause`
- `Anna #stop`
- `Anna #start`
- `Anna #restart`

Plain-language intent set to recognize:

- explanation request
- challenge
- counter-argument
- training suggestion
- status request
- review request

Default interpretation rule:

- plain-language training suggestions remain conversation by default
- they do not enter the governed training lane automatically
- Anna may identify that a suggestion looks training-relevant
- Anna should self-reflect on the suggestion before staging it and judge whether it appears additive, subtractive, uncertain, or counterproductive/incorrect
- Anna may use only approved internal research paths and active context to make that first-pass judgment
- Anna must not rely on uncontrolled external searching for this first-pass judgment
- Anna must ask whether the human wants it staged as training before converting it
- explicit human confirmation or an explicit `#train` marker is required before staging proceeds
- Anna must not silently self-update from the suggestion
- if Anna believes the suggestion is counterproductive or incorrect, she should say so explicitly and explain why before asking how the human wants to proceed
- the first-pass evaluation should include both:
  - a classification: `additive`, `subtractive`, `uncertain`, or `counterproductive`
  - a short rationale tied to curriculum, baseline doctrine, context, retained signal, or prior outcomes
- Anna should also recommend one of three next actions:
  - `stage`
  - `revise`
  - `reject`
- when a suggestion appears training-relevant but no staging decision has been made, Anna should emit a soft warning that it will remain conversation unless explicitly staged

Recommended compact human-facing packet:

- `classification`
- `why`
- `recommended_next_action`
- `confirm?`

Recommended compact visible header for training-relevant replies:

- `state: <state_label> | classification: <classification> | next: <recommended_next_action>`

Canonical minimal human reply grammar for this flow:

- `stage it`
- `revise it`
- `leave it`

Revision rule for `v1`:

- if the human says `revise it`, Anna should return one revised candidate only
- Anna should not branch into multiple alternative summaries by default in `v1`

Artifact and proof rule:

- every meaningful training intake, judgment, confirmation, staging action, review action, and promotion/rejection decision should produce an artifact or proof record
- this applies whether the source actor is a human or an agent
- no material training mutation should rely on undocumented conversation alone

Minimum staged-candidate lineage fields should include:

- source_actor_type
- source_actor_id
- source_message_or_artifact_ref
- Anna_classification
- Anna_rationale
- Anna_recommended_next_action
- human_confirmation_action
- staged_at
- downstream_review_refs

Recommended minimum `training_intake` schema layers:

### Identity layer

- `training_item_id`
- `student_id`
- `college_id`
- `degree_lane`
- `state_label`
- `created_at`

`state_label` should stay bounded in `v1`:

- `conversation`
- `candidate_training`
- `staged_training`
- `validated_learning`

### Source layer

- `source_actor_type`
- `source_actor_id`
- `source_channel`
- `source_message_or_artifact_ref`
- `source_text_snapshot`

`source_actor_type` should stay bounded in `v1`:

- `human`
- `agent`
- `system`

`source_channel` should stay bounded in `v1`:

- `slack`
- `cursor`
- `api`
- `system_internal`

`source_message_or_artifact_ref` should be a required stable reference string.

`source_text_snapshot` should be required immutable intake text.

### Anna evaluation layer

- `anna_classification`
- `anna_rationale`
- `anna_recommended_next_action`
- `anna_context_refs`
- `anna_baseline_refs`

`anna_classification` should stay bounded in `v1`:

- `additive`
- `subtractive`
- `uncertain`
- `counterproductive`

`anna_recommended_next_action` should stay bounded in `v1`:

- `stage`
- `revise`
- `reject`

`anna_rationale` should be required, concise, and tied to at least one basis from curriculum, baseline doctrine, active context, retained signal, or prior outcomes.

`anna_context_refs` should be a required non-empty list of stable reference strings.

`anna_baseline_refs` should be a required non-empty list of stable reference strings.

### Human decision layer

- `human_confirmation_action`
- `human_decision_actor_id`
- `human_decision_at`
- `human_revision_text`

`human_confirmation_action` should stay bounded in `v1`:

- `stage_it`
- `revise_it`
- `leave_it`

`human_revision_text` should be required only when `human_confirmation_action = revise_it`; otherwise it should be null/empty.

### Forensic review layer

- `artifact_version`
- `decision_trace_id`
- `related_training_item_ids`
- `review_status`
- `review_notes_ref`

`review_status` should stay bounded in `v1`:

- `not_reviewed`
- `under_review`
- `review_complete`
- `escalated`

`decision_trace_id` should be a stable opaque string generated at intake time and carried unchanged through the lifecycle.

`related_training_item_ids` should be optional and used only for revision, merge, follow-on, or comparison relationships.

`review_notes_ref` should be optional, but when present should point to a stable review artifact reference.

### Training execution layer

- `execution_mode`
- `execution_status`
- `simulation_run_refs`
- `micro_live_run_refs`
- `promotion_outcome`
- `promotion_outcome_at`

`execution_mode` should stay bounded in `v1`:

- `review_only`
- `simulation_only`
- `simulation_then_micro_live`

`execution_status` should stay bounded in `v1`:

- `not_started`
- `in_review`
- `running`
- `completed`
- `rejected`

`promotion_outcome` should stay bounded in `v1`:

- `not_promoted`
- `validated`
- `rejected`
- `deferred`

`simulation_run_refs` and `micro_live_run_refs` should be lists of stable run-reference strings rather than embedded payloads.

All timestamp fields should use strict ISO-8601 UTC with required `Z` suffix.

All ids and reference strings should be non-empty ASCII strings, immutable once created, and unique within their artifact class.

## 8.1 Operator-visible trading state

Humans need to be able to ask Anna for current operating state and get a useful answer without digging through raw artifacts.

Minimum visible trading-state surface should include:

- current `winning_or_losing` state
- current win/loss ratios and related active performance ratios
- current college fund balance
- whether the fund is up or down versus the configured comparison point
- current strategy or strategies in play
- current edge thesis
- current confidence/uncertainty status
- current guardrail status
- current degree lane
- current training/execution state

Rule:

- this data should be available over Slack and other approved operator-facing interfaces
- the answer should come from structured system state, not hand-wavy narrative
- if the exact metric is unavailable, Anna should say so explicitly rather than improvising
- canonical up/down comparison should use the current degree-lane fund start as the baseline
- canonical recent-performance comparison should use the active review segment
- `winning_or_losing` should be reported as `winning`, `losing`, or `flat`
- `current_strategy` should support one active strategy id or an ordered list of active strategy ids
- `edge_thesis` should remain one concise current working thesis in `v1`
- `confidence_or_uncertainty` should be reported as `confident`, `uncertain`, or `abstaining`
- `guardrail_status` should be reported as `clear`, `blocked`, or `restricted`

State-language rule for human clarity:

- Anna should explicitly distinguish:
  - `conversation`
  - `candidate_training`
  - `staged_training`
  - `validated_learning`
- humans should always be able to tell which state an idea is currently in
- any training-relevant reply should carry its current state label explicitly

### `#train #simulate`

Meaning:

- the directive enters the simulation routine directly
- no live-trading escalation is implied
- the run must still produce the required training artifacts and evaluation outputs

### `#train #trade`

Meaning:

- this is the trade-capable training fork
- it is safety-sensitive and must be treated as such
- it does not mean "skip analysis and place a trade now"
- it must remain inside the active degree contract and risk/approval boundaries

If Anna is still operating in the Bachelor lane, the `#train #trade` fork must still respect the Bachelor training path, including simulation and governed micro-live structure where the contract requires it.

## 9. Mandatory pre-work before either training fork

Before either `#train #simulate` or `#train #trade` proceeds, Anna must perform bounded pre-work.

Minimum pre-work package:

- strategy/thesis statement
- market-context summary
- baseline comparison
- guardrail and lane check
- uncertainty statement
- proposed execution mode

Rule:

- neither training fork may skip strategizing and analysis
- the fork decision comes after the pre-work package is assembled
- if context, evidence, or guardrails are insufficient, Anna must fail closed or downgrade the request

## 9.1 Smarter-by-doing rule

Anna does not become meaningfully smarter by passive suggestion intake alone.

Primary rule:

- Anna improves through doing and measured feedback

Operational meaning:

- curriculum can guide
- human suggestions can guide
- conversation can surface new candidates
- but improvement only counts when Anna executes the governed loop, measures results, and updates behavior based on evidence

Therefore:

- staged suggestions are not learning by themselves
- execution and measured evaluation are required
- retained improvement must be tied to actual tested outcomes

## 10. Human graduation authority

The graduation structure stays intact.

Rules:

- exam board evaluates
- exam board recommends
- humans decide graduation
- passing conversation alone is not graduation
- persuasive wording alone is not promotion
- only evidence-backed exam outcomes can support degree progression

## 10.1 Human interaction principle

One of the core tenets of the system is that Anna must be able to engage humans intelligently without becoming either submissive or reckless.

Required interaction behavior:

- explain strategy
- defend strategy with evidence
- revise when a better argument or better evidence is provided
- push back when a human instruction conflicts with market evidence, strategy quality, or lane constraints
- counter-propose safer or stronger alternatives
- state uncertainty explicitly

Authority boundary:

- Anna may defend, revise, abstain, or counter-propose
- Anna may not override governed authority
- Anna may not ignore hard controls because she "thinks" she is right

Behavior standard:

- strong on evidence
- humble on uncertainty
- firm on guardrails
- cooperative with humans
- never a dumb bot
- never a wild cowboy

## 11. Single-college operating principle

The single-college reduction must not erase the graduation model.

Even while BLACK BOX runs only the trading college path, it still keeps:

- degree progression
- exam-board independence
- staged curriculum promotion
- structured retraining/demotion/refocus behavior
- human graduation review

This is a reduction in implementation scope, not a reduction in governance quality.

## 12. Decision log for this discussion

This section captures the active architected discussion points so the conversation does not disappear into chat history.

### Locked or concurred decisions

1. BLACK BOX will implement core University mechanics first as a single `trading` college inside BLACK BOX rather than full multi-college runtime.
2. The `exam_board` remains in place.
3. The degree ladder remains in place: `Bachelor -> Master -> PhD`.
4. Humans remain the graduation authority after exam-board review.
5. Curriculum updates are extremely important and must be submitted in a structured format.
6. Anna is an agent, not the LLM.
7. Internal LLM output is candidate context only until Anna converts it into tested evidence.
8. Training follows the "keep what works, drop what does not, continuously reevaluate" loop.
9. Training retention must distinguish `candidate_insight`, `validated_signal`, and `noise`.
10. Previously validated signal may be demoted when later evidence invalidates it.
11. Conversation and curriculum are different surfaces and must not be conflated.
12. A helper agent may transform human prose into the required training/curriculum template.
13. At Bachelor, humans may direct Anna's training, but only inside the structured Bachelor lane.
14. `#train #simulate` should map directly to the simulation routine.
15. A `#train #trade` fork may exist, but it remains safety-sensitive and degree-bound.
16. Both training forks require pre-work strategizing and analysis before execution.
17. The interaction language should stay simple by default and extensible later.
18. A standalone `#trade` command is probably unnecessary if Anna already trades continuously in the authorized lane.
19. One core system tenet is that Anna must explain, defend, revise, and push back with evidence when humans are weak, restrictive, or missing the market picture.
20. Anna's objective should be to win, but only through valid wins inside guardrails.
21. Anna must have bounded strategic latitude based on learning, past experience, current market data, and the baseline doctrine.
22. Anna's primary interface should be plain conversation, with command tags used only as secondary governed overlays.
23. Anna should recognize a small plain-language intent set even when humans do not use tags.
24. Plain-language training suggestions stay conversational by default and require explicit confirmation before staging into training.
25. Anna should self-reflect on a possible training suggestion and judge whether it appears additive, subtractive, uncertain, or counterproductive before staging.
26. Anna's first-pass judgment on a training suggestion must include both a classification and a short evidence-based rationale.
27. Anna's first-pass judgment must use approved internal sources and active context only, not uncontrolled external searching.
28. Anna may recommend `stage`, `revise`, or `reject` as the next action after her first-pass judgment.
29. The compact v1 response packet for a training suggestion should be `classification`, `why`, `recommended_next_action`, and `confirm?`.
30. The canonical minimal human reply grammar should be `stage it`, `revise it`, or `leave it`.
31. If the human says `revise it`, Anna should return one revised candidate only in `v1`.
32. Every meaningful training intake or decision path should leave an artifact or proof record, whether the source actor is human or agent.
33. The staged candidate artifact should record source lineage, Anna's judgment, Anna's recommendation, and the human confirmation action.
34. Anna should emit a soft warning when something looks training-relevant but has not been explicitly staged.
35. Anna should explicitly distinguish between `conversation`, `candidate_training`, `staged_training`, and `validated_learning`.
36. Any training-relevant reply should carry its current state label explicitly.
37. Training-relevant replies should use one compact visible header line in `v1`.
38. The next contract-lock target after interaction `v1` is the minimum training-intake artifact schema.
39. The minimum training-intake schema should include identity, source, Anna evaluation, human decision, forensic review, and training execution layers.
40. `execution_mode` should stay bounded in `v1` to `review_only`, `simulation_only`, and `simulation_then_micro_live`.
41. Anna improves primarily through doing and measured feedback, not passive suggestion accumulation alone.
42. `state_label`, `anna_classification`, `human_confirmation_action`, `anna_recommended_next_action`, `execution_status`, and `promotion_outcome` should all stay bounded to small `v1` enums.
43. `review_status`, `source_actor_type`, and `source_channel` should also stay bounded to small `v1` enums.
44. `source_message_or_artifact_ref` should be a stable reference string and `source_text_snapshot` should be immutable intake text.
45. `anna_rationale` should be concise, and `anna_context_refs` plus `anna_baseline_refs` should be required non-empty reference lists.
46. `human_revision_text` should be required only for the `revise_it` path.
47. `decision_trace_id` should be stable across the full artifact lifecycle.
48. `related_training_item_ids` and `review_notes_ref` should remain optional, purpose-bound linkage fields.
49. `simulation_run_refs` and `micro_live_run_refs` should be reference lists, not embedded payloads.
50. All timestamps should be strict ISO-8601 UTC with `Z`, and all ids/reference strings should be immutable non-empty ASCII identifiers unique within their artifact class.
51. Anna should expose operator-visible trading state including win/loss, ratios, fund status, strategy in play, and current degree/training state through Slack and other approved interfaces.
52. Canonical up/down fund comparison should use the current degree-lane fund start as the baseline.
53. Canonical recent-performance comparison should use the active review segment.
54. Operator-visible confidence/uncertainty should be bounded to `confident`, `uncertain`, or `abstaining`.
55. Operator-visible guardrail status should be bounded to `clear`, `blocked`, or `restricted`.
56. Operator-visible `winning_or_losing` should be bounded to `winning`, `losing`, or `flat`.
57. Operator-visible `current_strategy` should support one active strategy id or an ordered list of active strategy ids.
58. Operator-visible `edge_thesis` should remain one concise current working thesis in `v1`.
59. `Anna` is the strategist and `Billy` is the execution bot / market connector; Billy does not invent signals or strategy.
60. In `v1`, Billy is the Drift-facing execution bot for the first real market path.
61. Billy's market integration path is both the connection mechanism to that market and the rulebook for how BLACK BOX operates correctly in that market.
62. The rulebook/adapter contract inside Billy should be machine-readable so Anna can consume it as context and Billy can enforce it deterministically.
63. Future market families may eventually introduce additional strategist/execution-bot pairings, but `v1` remains `Anna` + `Billy` with Billy's Drift market path.
64. Billy should accept a small, mandatory execution command packet from Anna and reject malformed or out-of-lane commands before venue mapping.
65. The minimum `Anna -> Billy` command surface in `v1` should include `market`, `side`, `intent_type`, `size`, `thesis_ref`, `confidence`, `risk_envelope_ref`, `strategy_id`, `trace_id`, and `time_in_force` when required.
66. Billy should own exchange connectivity truth, and `#exchange_status` should surface Billy's structured status for wallet/exchange readiness.
67. Humans should be able to ask in Slack whether the wallet/exchange path is connected and receive a structured answer rather than vague prose.
68. Anna should support runtime-control commands in `v1`: `#pause`, `#stop`, `#start`, and `#restart`.
69. Runtime-control commands must emit structured control artifacts and fail closed when they cannot be completed.
70. The first internal BLACK BOX web portal should stay operationally small and include runtime controls, Anna status, Billy/Drift status, winning/losing state, a training window, strategy inventory, training participation, edge-bot status, and a recent event feed.
71. The training window should remain first-class on the internal portal because training is part of Anna's active operating loop.
72. BLACK BOX requires a minimal login/account layer for portal access using username, email, password hash, role, account state, consent timestamp, and audit fields.
73. Portal login is for access, routing, ownership binding, and audit only; it is not a custody or secret-storage account.
74. Portal accounts must not store wallet secrets, seed phrases, exchange private keys, payment data, or unnecessary PII.
75. `v1` portal roles are `internal_admin` and `consumer_user`, with role-based routing after login.
76. The portal must connect to BLACK BOX through an explicit authenticated API boundary rather than direct database/runtime coupling.
77. `v1` portal wiring should include a JSON query/control API plus an authenticated live status/event stream for real-time updates.
78. The engine core remains the source of truth; the UI is a client shell over artifact-backed command and status surfaces.
79. Every portal control action should return a structured acknowledgement with `trace_id`, request timing, resulting state, and a failure reason when applicable.
80. The default local/dev bootstrap internal portal credential is `admin` / `admin`.
81. That bootstrap credential is for development bring-up only and does not count as an acceptable published or production credential.
82. The portal should use a standard CSS-first visual system with Apple-like restraint rather than ad hoc screen-by-screen styling.
83. The landing page should place an original BLACK BOX geometric box-mark dead center as the hero mark, using a black/dark box treatment and not a copied Cursor logo.
84. That box-mark should take roughly one quarter of the landing-page visual focus in `v1`.
85. Buttons and controls should follow one shared Apple-like language: soft radius, clean spacing, subtle depth, and consistent interaction behavior.
86. The API/UI contract should stay additive and non-brittle so future agents, strategies, statuses, and panels can be added without breaking the portal.
43. Anna needs a continuous live market-data stream plus durable SQLite retention so she can reason over both present and historical market context.
44. The current trading-doc baseline identifies Anna's live price-feed transport as Pyth via `SSE`.

### Final lock note

This discussion log no longer carries open contract placeholders for the active Anna/trading-college `v1` slice.

Canonical lock points now live in:

- `docs/architect/blackbox_university.md`
- `docs/architect/development_plan.md`
- `modules/context_ledger/README.md`

That includes:

- reward-window and reward-event contracts
- core learning loop and `RCS`/`RCA` escalation thresholds
- append-only context-engine backend choice
- explicit context trigger rules
- explicit approved ingestion sources and `v1` exclusions
