# SecOps CMMC v0.1 verifier dataset — plan

**Artifact (repo):** `nde/secops/datasets/staging/secops_cmmc_v0.1.jsonl`  
**Deploy mirror:** `/data/NDE/secops/datasets/staging/secops_cmmc_v0.1.jsonl`  
**Generator:** `nde/secops/scripts/generate_secops_cmmc_v0_1_jsonl.py`  
**Seed:** `88001`

## Sources used (conceptual alignment)

| Source | Use in this dataset |
|--------|---------------------|
| **CMMC** | Verifier-shaped claims about practices that must map to CMMC practices / assessment expectations (synthetic paraphrases; not copied text). |
| **NIST SP 800-171** | Control families cited in DATA lines (e.g., AC, AU, IA, SC, SI, IR, CM) as **control ID exemplars** for evidence requests. |
| **CIS Controls** | Informal alignment with logging, inventory, secure config, and vuln management themes in adversarial/clean scenarios (synthetic). |

This patch is **synthetic verifier training data** for structure and substance cues—not a substitute for official CMMC or NIST publications.

## Dataset metrics

| Metric | Value |
|--------|--------|
| Rows | 200 |
| Adversarial | 140 (70%) |
| Fields | `instruction`, `input`, `output` (+ metadata for traceability) |

## Output format

Four labeled sections in order:

1. `Claim reviewed:`
2. `Math verdict:`
3. `DATA evidence required:`
4. `Final verifier status:`

Wrong security claims → **Incorrect** in Math verdict and **FAIL** in Final status (adversarial rows).

## Coverage map (minimum themes)

| Theme | Present in templates |
|-------|----------------------|
| Access control (least privilege, MFA) | Yes — VPN/MFA, shared accounts, VIP exemptions, Domain Admin |
| Logging / monitoring | Yes — log waiver, email-only monitoring, AU-6 vs dashboards |
| Patching / vuln mgmt | Yes — quarterly-only, CVE chains, container scans |
| Encryption (at rest / in transit) | Yes — at-rest vs TLS, backup timing |
| Incident response | Yes — tabletops, contractor scope |
| Asset inventory | Yes — stale CMDB |
| Identity lifecycle | Yes — slow deprovisioning |
| Network segmentation | Yes — VLAN vs enforcement, default deny |

## DATA evidence elements (required themes in rows)

Each reference answer includes bullets touching:

- Control ID examples (e.g., AC-2, IA-5, AU-2, SC-8, SI-2, IR-4)
- Logs (timestamps, sources)
- IAM (roles, MFA state)
- Patch levels / CVE references
- Audit artifacts (reviews, POA&M, assessor responses)

## Ten sample records (abbreviated)

1. **Adv — VPN = secure, MFA optional:** Incorrect + FAIL; DATA cites IA-2(1), AC-2, VPN logs, MFA enrollment.
2. **Adv — No incidents ⇒ no logs:** Incorrect + FAIL; AU-2, AU-6, SIEM sources, sample log lines.
3. **Adv — Quarterly patching enough:** Incorrect + FAIL; SI-2, RA-5, CVE mapping to hosts.
4. **Adv — Encryption at rest enough without TLS:** Incorrect + FAIL; SC-8, SC-13, TLS inventory.
5. **Adv — Shared admin accounts OK internally:** Incorrect + FAIL; IA-5, AC-2, PAM logs.
6. **Adv — Flat VLAN = segmentation:** Incorrect + FAIL; SC-7, AC-4, firewall rules, east-west logs.
7. **Clean — MFA enforced for remote privileged:** PASS; IA-2(1), conditional access exports.
8. **Clean — Centralized logging + retention:** PASS; AU-2/AU-6, ingestion evidence.
9. **Clean — CVE SLA with changes:** PASS; SI-2/RA-5, ticket/CVE chain.
10. **Clean — IR exercised annually:** PASS; IR-4/IR-8, tabletop artifacts.

Full rows: see `nde/secops/datasets/staging/secops_cmmc_v0.1.jsonl`.

## Training

**Not run** for this directive (dataset + plan only).
