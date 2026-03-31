# BLACK BOX Web UI — Required Context

**Status:** Active context document for web/UI development  
**Folder authority:** `UIUX.Web/`  
**Purpose:** Explain why the BLACK BOX UI is required, what role it serves in the platform, and why it is not optional polish.

## 1. Why this document exists

The BLACK BOX web UI can be misunderstood as a cosmetic layer or a convenience dashboard.

That is incorrect.

The UI is required because BLACK BOX is not only an internal Slack conversation. It is a platform with:

- internal operator workflows
- consumer-facing account workflows
- PiBot onboarding and recovery flows
- runtime visibility requirements
- control surfaces that must be available outside Slack
- a non-custodial portal model

This document exists so a developer understands that the UI is part of the product contract, not a decorative afterthought.

## 2. Core statement

The BLACK BOX UI is required because the platform needs a stable human-facing portal for:

- access
- routing
- visibility
- control
- onboarding
- recovery
- governed interaction with the engine

Without the UI, key parts of the product become ambiguous, hidden, or non-usable for normal users.

## 3. How BLACK BOX fits together with the UI

BLACK BOX is a multi-part platform, and the UI makes that platform intelligible and usable.

The required system model is:

- **BLACK BOX portal UI** = human-facing shell
- **BLACK BOX engine core** = source of truth, orchestration, decision surfaces, status surfaces, and governed control handling
- **Anna** = strategist / analyst intelligence surfaced through the engine
- **Billy** = execution bot / market connector surfaced through the engine
- **PiBot** = user-owned edge execution device that holds secrets locally
- **API boundary** = the approved contract between the UI and the engine

The relationship is:

- the UI does not replace BLACK BOX
- the UI is how humans enter and use BLACK BOX
- the engine core does not become the UI
- the engine core exposes truth and actions through the API
- PiBot does not become the portal
- PiBot remains the edge device that proves identity, holds secrets, and executes locally

In plain terms:

- BLACK BOX is the system
- the UI is the front door and control surface for that system
- the engine is the operational brain behind that door
- PiBot is the edge extension of the system that stays under user/local control

Without this UI layer:

- BLACK BOX is harder to access
- BLACK BOX is harder to explain
- BLACK BOX is harder to operate
- PiBot workflows become awkward or hidden
- operator and consumer experiences blur together

Therefore the UI is not an add-on to BLACK BOX.

It is the required portal surface through which BLACK BOX is presented and used.

## 4. What problem the UI solves

The UI solves these platform problems:

### A. Human access to the platform

BLACK BOX needs a recognizable front door.

Users and operators need:

- a website to enter
- a login path
- role-based routing
- a clear separation between internal and consumer surfaces

Slack alone does not satisfy that requirement.

### B. Internal operator usability

The internal team needs a web surface to:

- see current runtime state
- see Anna state
- see Billy / exchange state
- view training state
- inspect strategy inventory
- access development-plan visibility
- eventually operate runtime controls through the approved API boundary

This is required because operational visibility must not depend only on remembering chat commands.

### C. Consumer usability

Consumers need a simpler controlled surface to:

- sign in
- confirm whether their PiBot is connected
- view safe status information
- manage limited consumer-safe actions

Without a UI, the consumer experience is either missing or pushed into the wrong channel.

### D. PiBot onboarding and recovery

The platform requires a portal-driven process for PiBot lifecycle actions such as:

- first connection
- pairing
- identity binding
- reconnect / recovery when the device still exists
- restart-from-scratch when a device is wiped or reimaged

This is especially important because BLACK BOX is non-custodial:

- PiBot holds secrets
- BLACK BOX does not
- the website must therefore own the user-facing pairing and status flow

### E. Separation of concern

The UI provides the correct separation between:

- the human-facing shell
- the engine core
- the edge device

The required model is:

- portal for interaction
- engine for truth and decisions
- PiBot for local secrets and edge execution

Without the UI, those roles blur together and the platform becomes harder to explain, build, and govern.

## 5. Why Slack is not enough

Slack may remain useful for operator interaction, but it is not enough to define the product surface.

Slack is insufficient for the following reasons:

- it is not the canonical public front door
- it is not the right place for ordinary consumer onboarding
- it is not the right place for PiBot pairing and recovery UX
- it is not the right place for stable role-based navigation
- it is not the right place for a long-lived portal identity model
- it is not the right place for a branded platform experience

Therefore:

- Slack is an approved operator interaction channel
- the web UI is the required portal interaction channel

Both may coexist, but the web UI is not optional.

## 6. Why the UI matters to the engine

The UI is required because the engine cannot be treated as a hidden black box that only developers touch.

The engine needs a stable external interaction shell for:

- status reads
- control requests
- event visibility
- user-safe acknowledgement
- future onboarding and pairing flows

The UI does **not** replace the engine. It exposes governed access to it.

The required relationship is:

- the engine remains the source of truth
- the UI remains the client shell
- the API remains the contract boundary

## 7. Why the UI matters to the non-custodial model

BLACK BOX is being positioned as a conductor, not a custodian.

That means:

- users come to BLACK BOX for intelligence, orchestration, status, and workflow
- users do **not** come to BLACK BOX to hand over wallet secrets
- PiBot or other edge bots keep secret data locally

This creates a requirement for a portal because users still need a place to:

- register access
- view account/bot state
- pair devices
- recover device bindings
- see system state relevant to them

The UI is therefore required to make the non-custodial model usable.

## 8. Why the UI matters to governance

The UI is also required for governed development.

Why:

- web work must be testable
- control surfaces must be explicit
- visible actions must be honest
- API-backed actions must fail closed
- user-facing states must be inspectable

Without the UI, many later requirements remain abstract and cannot be validated as real user workflows.

The UI therefore provides proof surfaces for:

- loading states
- error states
- routing behavior
- button/control integrity
- API acknowledgements
- role separation

## 9. Minimum platform outcomes that require a UI

The following platform outcomes require the UI:

- public landing page
- login and routing
- internal portal
- consumer portal
- structured system guide page for humans using the platform
- PiBot connection flow
- PiBot reconnect / recovery flow
- controlled runtime status and control surfaces
- development-plan and progress visibility for the internal team

These are not separate mini-products.

They are the human-facing pieces of how BLACK BOX operates as one system.

If those outcomes are required, the UI is required.

## 10. What the developer should conclude

A developer reading this document should conclude:

- the web layer is a product requirement
- the web layer is not optional polish
- the web layer is not only for aesthetics
- the web layer is part of how BLACK BOX is accessed and operated
- the web layer is how the rest of the BLACK BOX system is made usable to humans
- the web layer must be built to contract, not improvised

## 11. Binding interpretation

The UI is required because BLACK BOX needs a governed, branded, non-custodial, human-facing portal for both operators and users.

That requirement is not implied fluff.

It is a platform necessity.
