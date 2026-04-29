#!/usr/bin/env python3
"""
Generate secops_cmmc_v0.1.jsonl — SecOps verifier dataset (CMMC / NIST 800-171 aligned).

Run from repo root:
  python3 nde/secops/scripts/generate_secops_cmmc_v0_1_jsonl.py

Output:
  nde/secops/datasets/staging/secops_cmmc_v0.1.jsonl

Deploy mirror:
  /data/NDE/secops/datasets/staging/secops_cmmc_v0.1.jsonl
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "datasets" / "staging"
OUT_JSONL = OUT_DIR / "secops_cmmc_v0.1.jsonl"

INSTR = (
    "You are a SecOps verifier for CMMC-aligned security controls. "
    "Answer using exactly four labeled sections in this order: "
    "Claim reviewed:, Math verdict:, DATA evidence required:, Final verifier status:. "
    "Be concise. Use FAIL when the claim contradicts least privilege, logging, patching, "
    "encryption, incident response, inventory, identity, or segmentation expectations."
)

TARGET_N = 200
ADV_FRAC = 0.70
SEED = 88001
FLAG = "secops_cmmc_v0.1"


def _snip(s: str, max_words: int = 36) -> str:
    w = s.replace("\n", " ").strip().split()
    if len(w) <= max_words:
        return " ".join(w)
    return " ".join(w[:max_words]) + "…"


def four_section(
    *,
    claim_summary: str,
    verdict: str,
    data_lines: list[str],
    final_status: str,
) -> str:
    body = "\n".join(f"- {x.strip()}" for x in data_lines if x.strip())
    return (
        f"Claim reviewed:\n{_snip(claim_summary)}\n\n"
        f"Math verdict:\n{verdict.strip()}\n\n"
        f"DATA evidence required:\n{body}\n\n"
        f"Final verifier status:\n{final_status.strip()}"
    )


# Each tuple: input_one_liner, adversarial bool implicit True, verdict Incorrect line, data bullets (must reference controls/logs/IAM/patch/audit themes)
ADV_TEMPLATES: list[tuple[str, str, list[str]]] = [
    (
        "[VERIFY] Claim: VPN alone equals secure access; MFA is optional for admins.",
        "Incorrect — remote privileged access requires strong authentication; VPN does not replace MFA for privileged users (see IA-2(1), AC-2).",
        [
            "Control ID mapping: IA-2(1), AC-2, AC-3 (policy excerpt)",
            "IAM config export: role assignments, MFA enrollment state per account",
            "VPN gateway logs with timestamps and source IPs correlated to user IDs",
            "Conditional access / IdP audit artifacts for privileged sessions",
            "Recent assessor finding / POA&M row if applicable",
        ],
    ),
    (
        "[VERIFY] Claim: Because we have had no incidents, centralized logging is unnecessary.",
        "Incorrect — absence of incidents does not waive AU-family controls; monitoring is preventive and detective (AU-2, AU-6).",
        [
            "Control ID: AU-2 (event types), AU-6 (review), AU-12 (protection)",
            "SIEM/log aggregator config: sources, retention, integrity protections",
            "Sample log lines with UTC timestamps covering authentication and admin actions",
            "Audit artifact: last periodic log review record",
        ],
    ),
    (
        "[VERIFY] Claim: Quarterly patching is sufficient for all production servers.",
        "Incorrect — patch cadence must match risk and vendor guidance; quarterly-only posture is unsupported as universally adequate (SI-2).",
        [
            "Control ID: SI-2, RA-5 (vuln scanning linkage)",
            "Patch compliance report: KB/CVE applied vs outstanding by asset ID",
            "CVE references tied to asset inventory rows (e.g., CVE-2024-xxxx)",
            "Change tickets / maintenance windows aligned to SLAs",
            "Audit artifact: vulnerability scan export dates",
        ],
    ),
    (
        "[VERIFY] Claim: Disk encryption at rest means we meet confidentiality requirements without TLS inside the VPC.",
        "Incorrect — encryption at rest does not satisfy data-in-transit protections where SC-8 applies to transmissions.",
        [
            "Control ID: SC-8 (transmission confidentiality), SC-13 (crypto)",
            "TLS/cipher inventory for APIs, DB links, management planes",
            "Network diagrams showing segmentation boundaries relevant to flows",
            "Configuration snapshots proving TLS versions and cert validity windows",
            "Audit artifact: SSL/TLS scan or config assessment excerpt",
        ],
    ),
    (
        "[VERIFY] Claim: Shared local administrator accounts are acceptable for internal maintenance.",
        "Incorrect — shared privileged accounts break accountability and conflict with IA-5 / AC-2 named-account expectations.",
        [
            "Control ID: IA-5 (authenticator mgmt), AC-2 (account mgmt), AC-6 (least privilege)",
            "IAM listing showing shared vs named admin accounts with last-login timestamps",
            "PAM/jump host logs tying actions to individuals where required",
            "Policy clause prohibiting shared credentials",
            "Audit artifact: account review attestation",
        ],
    ),
    (
        "[VERIFY] Claim: Least privilege means users may keep permanent Domain Admin if onboarding is faster.",
        "Incorrect — standing excessive privilege violates AC-6 and separation-of-duty expectations without compensating controls evidenced.",
        [
            "Control ID: AC-6, AC-5 (SoD as applicable)",
            "Role catalog vs actual group memberships (CSV + timestamp)",
            "Privileged access workflow tickets or JIT elevation logs",
            "Access review sign-off (audit artifact)",
        ],
    ),
    (
        "[VERIFY] Claim: We monitor email only; endpoint telemetry is optional.",
        "Incorrect — endpoint visibility is typically required for malware/IR coverage; scope must match AU/SI/IR controls.",
        [
            "Control ID: AU-2/AU-6 coverage matrix vs asset classes",
            "EDR/agent deployment inventory vs endpoint asset list",
            "IR plan excerpt requiring host-level artifacts",
            "Sample host timeline logs with timestamps for incident rehearsal",
        ],
    ),
    (
        "[VERIFY] Claim: Asset inventory is the CMDB export from last year; no quarterly refresh needed.",
        "Incorrect — stale inventory breaks CM-8 / risk decisions; refresh cadence must be evidenced.",
        [
            "Control ID: CM-8 (system inventory), CM-2 (baseline as applicable)",
            "Current inventory extract with last_updated timestamps per CI",
            "Diff vs live discovery scan within SLA window",
            "Audit artifact: inventory reconciliation record",
        ],
    ),
    (
        "[VERIFY] Claim: Contractor laptops do not need IR tabletop exercises documented.",
        "Incorrect — IR preparedness is IR-family controlled; contractor scope still maps to IR-4/IR-8 expectations where applicable.",
        [
            "Control ID: IR-4 (handling), IR-8 (plan), CP references if continuity invoked",
            "IR playbook version and last tabletop date with attendees list",
            "Lessons learned / corrective actions logged",
            "Audit artifact: exercise report stored in controlled repository",
        ],
    ),
    (
        "[VERIFY] Claim: Flat network with VLAN tagging is the same as segmentation for CMMC.",
        "Incorrect — tagging alone does not prove enforcement; segmentation requires AC-4 / SC-7 style boundaries evidenced.",
        [
            "Control ID: SC-7 (boundary protection), AC-4 (information flow)",
            "Firewall/NACL rulesets with deny-by-default posture excerpts",
            "East-west traffic logs between zones with timestamps",
            "Architecture diagram revision hash vs deployed configs",
            "Audit artifact: segmentation test (pen test / rule validation) results",
        ],
    ),
    (
        "[VERIFY] Claim: Identity lifecycle: we never disable accounts within 24h of termination.",
        "Incorrect — delayed deprovisioning violates IA-4 / AC-2 timely disable expectations absent documented compensating monitoring.",
        [
            "Control ID: AC-2 (disable), IA-4 (identifier mgmt)",
            "HR termination feed timestamps vs IdP disable timestamps",
            "Privileged account revocation audit trail",
            "Exceptions register with approvals",
            "Audit artifact: quarterly access review sample",
        ],
    ),
    (
        "[VERIFY] Claim: MFA prompts annoy executives; exempt VIP mailboxes.",
        "Incorrect — MFA exemptions for high-value identities increase risk; IA-2(1)/IA-5 controls still apply unless formally risk-accepted with evidence.",
        [
            "Control ID: IA-2(1), IA-5",
            "Conditional access policies showing exempt groups (should be empty or justified)",
            "Sign-in risk logs for exempted accounts",
            "Risk acceptance memo with expiry date",
            "Audit artifact: assessor observation response",
        ],
    ),
]

# Additional rotating adversarial claims per theme (short inputs)
EXTRA_ADV_INPUTS = [
    ("[VERIFY] Claim: Default deny on firewalls is optional if we trust staff.", "Incorrect — implicit trust contradicts SC-7 boundary expectations without documented exceptions."),
    ("[VERIFY] Claim: Backup encryption can wait until next fiscal year.", "Incorrect — backup confidentiality timelines must align with SC-28 / CP expectations when CUI may be present."),
    ("[VERIFY] Claim: We rotate passwords yearly; that satisfies IA-5.", "Incorrect — IA-5 expects authenticator strength per policy; annual rotation alone is not sufficient evidence."),
    ("[VERIFY] Claim: Container images pulled from public registries need no scan gates.", "Incorrect — SI-2 / RA-5 align supply-chain scanning; unsupported without CI/CD gates."),
    ("[VERIFY] Claim: SOC watches dashboards daily; formal AU-6 review is redundant.", "Incorrect — dashboards do not replace documented review of audit records under AU-6."),
]


def _standard_data_suffix(theme_extra: str) -> list[str]:
    """Ensure each row touches control IDs, logs, IAM, patching/CVE, audit themes."""
    return [
        theme_extra,
        "Control ID crosswalk column (e.g., AC-2, AU-2, IA-5, SC-8, SI-2, IR-4)",
        "Logs: UTC timestamps, source system (DC, IdP, firewall, EDR)",
        "IAM config evidence: roles, groups, MFA method/state per user class",
        "Patch levels / vuln scan export with CVE IDs mapped to hosts",
        "Audit artifacts: assessor request responses, POA&M excerpts, or formal reviews",
    ]


def main() -> None:
    rng = random.Random(SEED)
    n_adv = int(round(TARGET_N * ADV_FRAC))
    n_clean = TARGET_N - n_adv

    rows: list[dict] = []

    adv_rows: list[tuple[str, str, list[str]]] = []
    for t in ADV_TEMPLATES:
        inp, ver, data = t
        adv_rows.append((inp, ver, data))
    for inp_short, ver_short in EXTRA_ADV_INPUTS:
        adv_rows.append(
            (
                inp_short,
                ver_short,
                _standard_data_suffix("Supplemental adversarial theme"),
            )
        )

    rng.shuffle(adv_rows)
    for i in range(n_adv):
        inp, verdict, data_lines = adv_rows[i % len(adv_rows)]
        inp_v = inp.rstrip(".") + f" Variant {i + 1}.\n"
        out = four_section(
            claim_summary=inp_v.strip(),
            verdict=verdict,
            data_lines=data_lines,
            final_status="FAIL",
        )
        rows.append(
            {
                "instruction": INSTR,
                "input": inp_v,
                "output": out,
                "source_ids": ["secops_cmmc_synth", f"adv_{i + 1:04d}"],
                "category": "secops_cmmc",
                "adversarial": True,
                "quality_flags": [FLAG, "adversarial_trap", hashlib.sha256(inp_v.encode()).hexdigest()[:8]],
            }
        )

    CLEAN = [
        (
            "[VERIFY] Policy states MFA is enforced for all remote privileged access via IdP conditional access.",
            "Correct — aligns with IA-2(1) intent when evidenced by configuration and logs.",
            [
                "Control ID: IA-2(1), IA-5",
                "Conditional access policy JSON/export + MFA registration reports",
                "Sign-in logs with MFA claim results (UTC)",
                "Patch posture unrelated but attach SI-2 compliance excerpt if CUI systems touched",
                "Audit artifact: annual policy acknowledgment",
            ],
            "PASS",
        ),
        (
            "[VERIFY] Centralized logging aggregates auth, admin, and boundary device logs with 12-month retention.",
            "Correct — supports AU-2/AU-6 when reviews are evidenced.",
            [
                "Control ID: AU-2, AU-6, AU-12",
                "Log source list with ingestion timestamps",
                "Sample normalized events with UTC timestamps",
                "Retention policy doc + technical enforcement screenshot",
                "Audit artifact: periodic review minutes",
            ],
            "PASS",
        ),
        (
            "[VERIFY] Critical CVEs remediated within vendor SLA with emergency change records.",
            "Correct — consistent with SI-2 when tied to vuln scans.",
            [
                "Control ID: SI-2, RA-5",
                "CVE ID → ticket → deployment timestamp chain",
                "Scan showing cleared vs open findings",
                "Audit artifact: POA&M closure or scan attestation",
            ],
            "PASS",
        ),
        (
            "[VERIFY] TLS 1.2+ enforced for app-tier connections; weak ciphers disabled.",
            "Correct — supports SC-8 when configs match diagrams.",
            [
                "Control ID: SC-8, SC-13",
                "Load balancer / API gateway cipher suite export",
                "Certificate inventory with expiry alerts",
                "Audit artifact: configuration assessment screenshot",
            ],
            "PASS",
        ),
        (
            "[VERIFY] IR plan exercised annually; improvements tracked in ticketing.",
            "Correct — aligns with IR-4/IR-8 when documentation exists.",
            [
                "Control ID: IR-4, IR-8",
                "Tabletop agenda, attendees, scenarios",
                "Tickets opened/closed from lessons learned",
                "Audit artifact: signed IR plan revision",
            ],
            "PASS",
        ),
        (
            "[VERIFY] Asset inventory reconciled monthly against discovery scans.",
            "Correct — supports CM-8 when deltas are managed.",
            [
                "Control ID: CM-8",
                "Inventory export vs discovery mismatch report",
                "Logs from discovery tool runs with timestamps",
                "Audit artifact: reconciliation sign-off",
            ],
            "PASS",
        ),
        (
            "[VERIFY] Network zones enforce deny-by-default between prod and dev with rule reviews quarterly.",
            "Correct — aligns with SC-7 when tests prove enforcement.",
            [
                "Control ID: SC-7, AC-4",
                "Firewall ruleset version hash + change tickets",
                "Segmentation test logs",
                "Audit artifact: quarterly review record",
            ],
            "PASS",
        ),
    ]

    for j in range(n_clean):
        inp, mv, data_lines, st = CLEAN[j % len(CLEAN)]
        inp_v = inp + f" Case ref {j + 1}.\n"
        out = four_section(
            claim_summary=inp_v.strip(),
            verdict=mv,
            data_lines=data_lines,
            final_status=st,
        )
        rows.append(
            {
                "instruction": INSTR,
                "input": inp_v,
                "output": out,
                "source_ids": ["secops_cmmc_synth", f"clean_{j + 1:04d}"],
                "category": "secops_cmmc",
                "adversarial": False,
                "quality_flags": [FLAG, "reference_alignment"],
            }
        )

    rng.shuffle(rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    adv_n = sum(1 for r in rows if r.get("adversarial"))
    print(json.dumps({"path": str(OUT_JSONL), "total": len(rows), "adversarial": adv_n, "pct": round(100 * adv_n / len(rows), 2)}, indent=2))


if __name__ == "__main__":
    main()
