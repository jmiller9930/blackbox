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

### Items still expected to tighten later

- exact structured template fields for Bachelor human training directives
- exact pass/fail packet shape for each training fork
- exact downgrade/fail-closed behavior when pre-work is incomplete
- exact relationship between Bachelor micro-live eligibility and `#train #trade`
- exact reward-marker and reset mechanics
- exact interaction grammar beyond the initial small command set
- exact confirmation prompt wording for "stage this as training?"
- exact output wording when Anna thinks a human training suggestion is counterproductive or incorrect
- exact approved internal research surfaces for first-pass training judgments
- exact confirmation prompt wording for the compact `v1` packet
- exact minimum schema for training-intake and decision artifacts
- exact downstream review and promotion artifact linkage fields
- exact human-facing wording for the four state labels in Slack and other interfaces
- exact compact header wording for Slack and non-Slack surfaces
