# Directive DEV-BBX-SMS-001 — Operator SMS workspace panel (UI + API)

**Status:** Issued — **developer-owned** (backend + UI API).  
**Issued:** 2026-04-02  
**Governance:** [`../development_governance.md`](../development_governance.md); template alignment: [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md).

**Authorization boundary:** This package authorizes **control-surface wiring only** — notification distro management and test sends. It **does not** lift Pillar 1 intake gates, **does not** change trading logic, execution, approvals, or kill-switch behavior, and **does not** replace or satisfy **CANONICAL #041** (architect-owned). If `docs/working/developer_handoff.md` conflicts, the handoff file’s **Additional authorized work** pointer to this directive controls for this scope.

**Technical source of truth (implementation):**

- Python: [`modules/notification_gateway/`](../../../modules/notification_gateway/) — `notify_system`, `notify_trade`, `notify_training_milestone`, `resolve_recipient_targets`, `normalize_to_e164`, `parse_sms_allowed_tiers`, tier gating.
- CLI reference behavior: [`scripts/runtime/tools/send_notification_test.py`](../../../scripts/runtime/tools/send_notification_test.py) — `--ping`, `--who`, `--kind`, `--dry-run`.
- Operator notes: [`scripts/runtime/README.md`](../../../scripts/runtime/README.md) — section **Phone / SMS notifications** and **Backend / workspace panel**.

---

## Scope & objectives

**Requirement:** Deliver an **operator-facing workspace panel** (internal portal) plus **HTTP JSON API** so an authorized operator can:

1. **View** the SMS distribution list (names + **masked** phone display in UI; full E.164 only in secure edit flows).
2. **Create / update / delete** recipients with **E.164 validation** using `normalize_to_e164` (or equivalent server-side validation); persist to **SQLite** (preferred) or atomic file write to a **server-only** path (e.g. under repo or `/etc/blackbox/` — **never** commit secrets).
3. **Send test notifications** equivalent to the CLI: at minimum **`ping`** (same summary string as CLI `PING_SUMMARY`: *“This is a system test from the BLACK BOX engine.”*), and optionally **`system`**, **`trade`**, **`training`** with the same semantics as `send_notification_test.py`.
4. **Respect** `BLACKBOX_NOTIFY_SMS_TIERS` and existing tier behavior (T1/T2/T3); surface tier in UI where useful.
5. **AuthZ:** same **internal staff** gate as other portal control surfaces (match existing session/role checks in [`UIUX.Web/app.js`](../../../UIUX.Web/app.js) / API patterns in [`UIUX.Web/api_server.py`](../../../UIUX.Web/api_server.py)); **no** anonymous or consumer access to SMS APIs.

**Why:** Operators must test SMS and manage distro **without SSH**; backend must delegate to existing gateway code — **no** second Twilio client implementation in JS.

**Non-negotiable for directive issuance:** Yes.

### Out of scope

- Changing Twilio account ownership or production secrets policy (operator/env provides `TWILIO_*` on the host that performs sends).
- SMS content marketing, arbitrary user-defined message bodies from untrusted roles (test sends use **fixed** templates or the existing gateway formatters only).
- Moving canonical hashtag / Slack vocabulary docs into this panel (link only).

### Suggested API shape (contractual minimum)

Implement under **`/api/v1/notify/`** (or equivalent namespaced path consistent with `api_server.py`):

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/api/v1/notify/recipients` | List recipients; mask phone for display (`…1234`). |
| `PUT` | `/api/v1/notify/recipients` | Replace full list; validate E.164; persist. |
| `GET` | `/api/v1/notify/settings` (optional) | Read-only or admin: `BLACKBOX_NOTIFY_SMS_TIERS`, mode hints. |
| `POST` | `/api/v1/notify/test` | Body: `{ "to": "john" \| "all" \| "recipient1", "kind": "ping" \| "system" \| "trade" \| "training" }`; returns `{ "ok": bool, "detail": str }` from gateway. |

**Process:** SMS delivery must run where **`BLACKBOX_NOTIFY_MODE=twilio`** (or webhook) and **`TWILIO_*`** are available — typically **clawbot** / primary host per [`docs/runtime/execution_context.md`](../../runtime/execution_context.md). If the UI API container lacks secrets, use a **documented** pattern: subprocess on host, SSH one-shot, or shared env on the same machine as today’s CLI proof.

### UI shape (contractual minimum)

- **Panel** in **operator internal workspace** (e.g. [`UIUX.Web/internal.html`](../../../UIUX.Web/internal.html) or dedicated route): table + Save + **Send test (ping)** + optional kind selector; link to docs for Slack vs SMS.
- **Errors:** show gateway `detail` string; never log full phone numbers server-side in shared logs.

---

## Documentation / Status Synchronization (Mandatory)

On **closure** of this directive: update **`docs/blackbox_master_plan.md`** and **`directive_execution_log.md`** in the **same change set** with matching status. *(Issuance does not require master-plan edit if no plan row exists yet; add one on closeout.)*

---

## Closeout / return summary (Mandatory)

Closeout must include the literal line:

`Plan/log status sync: PASS`

---

## Developer verification checklist (before return) (Mandatory)

- [ ] Panel + API merged; internal-staff auth enforced.
- [ ] `PUT` recipients persists and `GET` reflects data; validation uses gateway helpers or equivalent.
- [ ] `POST` test delegates to `modules/notification_gateway` (or calls the CLI script as a subprocess — second choice).
- [ ] `python3 -m pytest tests/test_notification_gateway.py` passes; add API tests if new routes exist.
- [ ] Proof on **primary host** when [`execution_context.md`](../../runtime/execution_context.md) requires clawbot (document SHA).

---

## Git commit and remote sync (Mandatory for implementation closes)

Record full commit SHA, branch, push, and **primary-host SHA** when applicable.

---

## Documentation mismatch failure rule (Mandatory)

Per template — no closure with plan/log mismatch.

---

## Proof & evidence (Mandatory for closure)

| Criterion | Evidence |
|-----------|----------|
| Automated | `pytest` for notification module + any new API tests; capture command + exit code. |
| Primary host | If execution context mandates clawbot: `git rev-parse HEAD` on clawbot after pull; run test send or dry-run path documented. |
| Operator | Optional: operator confirms receipt of **ping** on at least one handset (not a substitute for automated proof). |

Closeout must include **`Plan/log status sync: PASS`** and filled **Git commit and remote sync**.

---

## Notes

- README table in `scripts/runtime/README.md` may be extended but must stay consistent with this directive.
