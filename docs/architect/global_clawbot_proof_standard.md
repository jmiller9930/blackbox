# Global directive — mandatory clawbot proof standard (all phases)

**Date:** 2026-03-23

## Purpose

This directive establishes a **non-negotiable** proof standard for **all** future phases.

No phase is considered complete without:

- clawbot execution  
- persisted evidence  
- structured proof output  

This overrides any prior implicit or informal proof behavior.

---

## Required execution flow (every phase)

The following must be performed **in order**:

1. Implement code  
2. Commit + push to Git  
3. SSH / remote into **clawbot**  
4. Pull latest code:  
   `cd ~/blackbox`  
   `git pull origin main`  
5. Confirm HEAD:  
   `git rev-parse HEAD`  
6. Execute **all** required runtime commands **on clawbot**  
7. Capture outputs  
8. Capture persistence proof (DB or file)  
9. Return structured proof package  

**Do not stop before step 9.**

---

## Required proof package (mandatory)

Every proof **must** include **all** sections below.

### 1. Commands executed (exact)

Exact commands run on clawbot. No summaries. No paraphrasing.

### 2. Clawbot commit verification

Example:

`git rev-parse HEAD:` `<commit_hash>`

Must match or exceed expected commit.

### 3. Runtime output (trimmed JSON)

Trimmed JSON for all required test paths. Must include:

- `kind` (where applicable)  
- key functional fields relevant to the phase  
- **not** full dumps  

### 4. Persistence proof (critical)

You **must** prove data was written.

**If DB-based:**

- `stored_task_id`  
- row verification (id, title, state)  

**If file-based:**

- file path  
- proof content exists in file  
- correct updated values (e.g., status, version)  

This is **required**. “No errors” is **not** proof.

### 5. Behavior validation

Explicitly confirm:

- expected behavior occurred  
- edge / null cases handled correctly (if applicable)  

### 6. Constraint confirmation

Explicit list, for example:

- no schema changes (unless instructed)  
- no unauthorized modules added  
- no registry mutation (if restricted)  
- no Telegram / execution / ML unless specified  

---

## Failure conditions

A phase is **not** complete if **any** of the following are missing:

- no clawbot run  
- no commit verification  
- no persistence proof  
- only local execution  
- vague summaries instead of real output  

---

## Acceptance rule

A phase is **CLOSED** only when:

- all required commands ran on clawbot  
- outputs are correct  
- persistence is proven  
- constraints are respected  

---

## Standard enforcement

This directive applies to:

- all runtime phases  
- all future directives  
- all verification steps  

**Assumption:** proof is incomplete unless clawbot evidence is returned.

---

## Stop condition

After returning the full proof package: stop; wait for architect validation.
