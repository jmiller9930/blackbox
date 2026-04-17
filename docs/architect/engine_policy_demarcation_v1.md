# Engine vs policy — demarcation contract (v1)

**Status:** Normative for SeanV3 Node runtime and policy artifact loading.  
**Implements:** Separation of a **generic execution engine** from **policy artifacts** produced and validated by Kitchen.

---

## 1. Two layers (non-negotiable)

### Engine (execution layer)

The engine is a **separate system entity** from policy. It is responsible only for:

- Ingesting market/runtime data  
- Normalizing state  
- Computing canonical features needed for decisions  
- Enforcing risk and lifecycle rules  
- **Loading the assigned policy artifact** through a **standard contract** (not by becoming a named strategy)  
- Executing the returned decision (open, hold, exit, no-trade)  
- Logging deterministic proof of what happened (ledger, bar decisions, metadata)

The engine **must not** contain embedded strategy logic (no “if jup_v4 then …” strategy trees, no static imports of strategy modules in the runtime hot path).

### Policy (artifact layer)

Policy is responsible only for:

- Consuming the engine’s **standard input contract** (OHLC-derived inputs passed by the engine)  
- Returning a **standard decision output** (signals, diagnostics)  
- Carrying **its own** identity, version, and artifact metadata (via Kitchen intake + deployment manifest binding)

The policy **must not** own runtime orchestration (bar scheduling, DB writes for positions except through engine APIs, funding gates, etc.).

### Runtime rules

- **No blended runtime:** engine identity ≠ policy identity.  
- **No aliasing** that collapses “which policy artifact” into “which engine build” as a single string.  
- **Assigned policy = artifact the engine loads** — not a mode the engine becomes (no `switch(policyId)` to hardwired modules in production code).

### Short form

The **engine runs** policies. The **engine is not** the policy. Policy **plugs in** through a standard contract. **No** hidden strategy inside the engine.

---

## 2. SeanV3 Node — file map (where the boundary lives)

| Role | Location | Notes |
|------|-----------|--------|
| **Engine loop (hot path)** | `vscode-test/seanv3/sean_engine.mjs` | Calls `loadActivePolicyContext` only; does **not** import `legacy_policies/`. |
| **Policy resolution + manifest** | `vscode-test/seanv3/jupiter_policy_runtime.mjs` | Resolves deployment id → manifest binding → loader; no static strategy modules. |
| **Artifact load + contract** | `vscode-test/seanv3/engine/artifact_policy_loader.mjs` | `import()` of Kitchen `evaluator.mjs` only; verifies optional SHA256. |
| **Math shared (non-strategy)** | `vscode-test/seanv3/engine/atr_math.mjs` | ATR helper; not policy semantics. |
| **Lifecycle / exits (engine)** | `vscode-test/seanv3/sean_lifecycle.mjs` | Stops, targets, ATR-from-window — not candidate strategy selection. |
| **Orchestration** | `vscode-test/seanv3/app.mjs` | Schedules `processSeanEngine`; must not import strategy modules. |
| **HTTP / operator** | `vscode-test/seanv3/jupiter_web.mjs` | Writes `jupiter_active_policy`; validates against deployment manifest. Status strip: **Engine** = execution loop (`BBT_v1` / `SEAN_ENGINE_DISPLAY_ID`), **Deployment** = assigned policy id (manifest), not interchangeable. |
| **BlackBox control plane** | `renaissance_v4/blackbox_policy_control_plane.py` + `UIUX.Web/api_server.py` | Same model: **allowed** deployment ids = `kitchen_policy_deployment_manifest_v1` entries for `execution_target` **blackbox**; POST requires manifest row; state file holds active id + submission/hash; GET includes `engine_display_id` / `engine_online` (`BLACKBOX_ENGINE_DISPLAY_ID` / `BLACKBOX_ENGINE_SLICE`). |

### BlackBox (Python API)

- **Not** a registry slot switchboard: `kitchen_policy_registry_v1.json` `runtime_policies.blackbox` is **not** the allowlist for POST (manifest is).
- Optional env: `BLACKBOX_ENGINE_DISPLAY_ID` (default `BBT_v1`), `BLACKBOX_ENGINE_SLICE` (default on).
| **Quarantined legacy strategies** | `vscode-test/seanv3/legacy_policies/*.mjs` | **Not** part of the production engine path; tests/reference only unless explicitly imported from tests. |

**Deployment binding (repo config):**  
`renaissance_v4/config/kitchen_policy_deployment_manifest_v1.json` — lists Jupiter `deployed_runtime_policy_id` → `submission_id` (+ hash fields). Empty manifest means no approved deployment ids until operations populate it.

---

## 3. Forbidden patterns (do not reintroduce)

1. **Static imports** of `legacy_policies/*` or `jupiter_*_sean_policy.mjs` from `app.mjs`, `sean_engine.mjs`, `jupiter_policy_runtime.mjs`, `sean_lifecycle.mjs`, or `engine/*.mjs`.  
2. **`resolveJupiterPolicy`-style** switchboards that map ids → bundled `.mjs` modules in the engine loop.  
3. **Treating SQLite `jupiter_active_policy`** as “which shipped module” without a manifest row tying it to a **submission artifact**.  
4. **Collapsing** engine tags and policy tags in observability (display both where operators need proof).

**Enforcement:** `vscode-test/seanv3/test/engine_policy_boundary_guard.test.mjs` fails CI if the hot-path files regress.

---

## 4. Relationship to other docs

- **`ARCH-kitchen-execution-engine-policy-artifact-binding.md`** — historical Kitchen/runtime analysis and migration notes; **§3 Jupiter** “module switchboard” description is **superseded** for the Node path by this document and the files in §2.  
- **Kitchen Python** (`renaissance_v4/kitchen_runtime_assignment.py`, `policy_intake/candidates_registry.py`) — control-plane reconciliation may still have legacy fallbacks; tightening that is **separate** from the Node engine boundary but must align with §1 for end-to-end proof.

---

*End — engine_policy_demarcation_v1*
