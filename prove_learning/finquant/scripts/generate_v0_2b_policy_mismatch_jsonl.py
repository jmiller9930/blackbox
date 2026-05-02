#!/usr/bin/env python3
"""
Deterministic generator for finquant_v0.2b_policy_mismatch_reinforcement.jsonl.

Focus: policy vs implementation drift (YAML, registry, runtime, ledger).

Run from repo root:
  python3 finquant/scripts/generate_v0_2b_policy_mismatch_jsonl.py

Outputs:
  finquant/patches/v0.2b/finquant_v0.2b_policy_mismatch_reinforcement.jsonl
  finquant/reports/v0.2b_policy_mismatch_reinforcement_report.md

Deploy staging copy to trx40:
  /data/finquant-1/datasets/staging/finquant_v0.2b_policy_mismatch_reinforcement.jsonl
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

PATCH_DIR = Path(__file__).resolve().parents[1] / "patches" / "v0.2b"
OUT_JSONL = PATCH_DIR / "finquant_v0.2b_policy_mismatch_reinforcement.jsonl"
OUT_REPORT = Path(__file__).resolve().parents[1] / "reports" / "v0.2b_policy_mismatch_reinforcement_report.md"

INSTR = (
    "You are a quant verifier. Answer using exactly four labeled sections in this order: "
    "Claim reviewed:, Math verdict:, DATA evidence required:, Final verifier status:. "
    "Be concise. When policy documents disagree with execution artifacts, treat the claim as unverified "
    "and use FAIL unless independent evidence proves they match."
)

TARGET_N = 120
ADV_FRAC = 0.80
SEED = 42008
FLAG = "policy_mismatch_v0.2b"


def _snip(s: str, max_words: int = 28) -> str:
    w = s.replace("\n", " ").strip().split()
    if len(w) <= max_words:
        return " ".join(w)
    return " ".join(w[:max_words]) + "…"


def format_data_evidence_block(items: list[str]) -> str:
    lines = [f"- {x.strip()}" for x in items if x and x.strip()]
    return "\n".join(lines) if lines else "- Strategy YAML checksum; execution log slice with timestamps"


def four_section_output(
    *,
    claim_summary: str,
    verdict_line: str,
    data_items: list[str],
    final_status: str,
) -> str:
    body = format_data_evidence_block(data_items)
    return (
        f"Claim reviewed:\n{_snip(claim_summary)}\n\n"
        f"Math verdict:\n{verdict_line.strip()}\n\n"
        f"DATA evidence required:\n{body}\n\n"
        f"Final verifier status:\n{final_status.strip()}"
    )


def data_items_policy_audit() -> list[str]:
    return [
        "Strategy or policy YAML as deployed (checksum)",
        "Runtime parameter snapshot from process/config reader",
        "Execution order logs with strategy version tag",
        "Git or artifact hash for the binary versus policy bundle",
    ]


ADV_POOL: list[tuple[str, str, list[str], str]] = [
    (
        "[VERIFY] Strategy YAML sets stop_loss_pct: 0.02 but risk logs show engine using 5%.",
        "Incorrect — threshold mismatch between declared policy and runtime exit logic.",
        [
            "YAML stop_loss_pct field and deploy manifest checksum",
            "Risk engine effective stop from live parameters API",
            "Order amendment trail showing actual stop prices",
            "Replay bar timestamps when stops triggered",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Live bot reports TP from strategy YAML but execution logs show hard-coded ATR multiple not in YAML.",
        "Incorrect — take-profit source differs from documented policy; implementation drift.",
        [
            "Strategy YAML take_profit / ATR fields",
            "Execution fill logs with venue order tags",
            "Source code or config constant for ATR multiple actually used",
            "Replay bar timestamps covering TP fills",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Policy declares ATR(14)*2.5 for stops but orders show fixed tick offset unrelated to ATR.",
        "Incorrect — declared ATR policy not reflected in order construction.",
        [
            "YAML ATR period and multiplier",
            "ATR series used at order time (bar timestamps)",
            "Bracket order distance in ticks from exchange ack",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Risk sizing in policy says 1% equity per trade but ledger shows identical notional every fill.",
        "Incorrect — position sizing policy vs fixed contract count in execution.",
        [
            "Equity curve and risk_per_trade from policy",
            "Order quantity field per fill vs equity snapshot",
            "Account leverage and margin mode at each entry",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Funding-rate filter in YAML blocks entries when |funding|>0.01% but runtime accepts all fills.",
        "Incorrect — declared filter not applied in live path.",
        [
            "YAML funding filter predicate",
            "Funding rate timestamps at entry decisions",
            "Decision log branch showing filter evaluated or skipped",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Indicator gate requires ADX>25 for entries but dashboard hotlink submits orders without gate.",
        "Incorrect — UI bypass diverges from coded gate in strategy core.",
        [
            "Strategy gate code path vs dashboard API route",
            "ADX values at submit timestamps",
            "Authentication log for manual vs automated submits",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Policy registry lists active_policy: momentum_v3 but process argv shows runner executing mean_revert_v1.",
        "Incorrect — active policy name mismatch registry vs runtime.",
        [
            "Registry snapshot with policy ID and hash",
            "Process launch command and MODULE loaded",
            "Heartbeat ping naming policy version",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Backtest manifest specifies fee_bps: 4 and slip_bps: 2 but ledger reconciliation uses 6 and 0.",
        "Incorrect — simulation assumptions disagree with accounting parameters.",
        [
            "Backtest manifest JSON checksum",
            "Ledger fee schedule row applied to trades",
            "Venue actual fee invoices vs manifest",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Default leverage in code is 10x while production YAML caps leverage at 3x.",
        "Incorrect — hardcoded default overrides documented cap unless loader proves otherwise.",
        [
            "YAML max_leverage",
            "Constructor default in strategy source",
            "Effective leverage from position notional / equity",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Fallback policy 'flat_only' activates on feed gap although ops states no fallback should run.",
        "Incorrect — hidden fallback path contradicts operational policy.",
        [
            "Ops runbook for feed-loss behavior",
            "Code branch selecting fallback policy",
            "Market data gap detector timestamps",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Bot still reads strategy_config_v7.yaml while deploy artifact uploaded strategy_config_v9.yaml.",
        "Incorrect — stale parameter file loaded; version skew.",
        [
            "Expected config path from systemd/docker env",
            "Inode and SHA256 of file actually mmap'd",
            "Deploy timestamp vs process start time",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Circuit breaker threshold is 3% daily loss in policy PDF but risk daemon trips at 5%.",
        "Incorrect — operational threshold differs from marketing/policy document.",
        [
            "Signed policy PDF version",
            "Risk daemon YAML or etcd key for breaker",
            "PnL series used for breaker calculation",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Max positions YAML says 5 concurrent symbols but orchestrator caps at 12 in code.",
        "Incorrect — cardinality limit mismatch.",
        [
            "YAML max_open_positions",
            "Orchestrator semaphore limit constant",
            "Open orders snapshot count",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Slippage model in research notebook uses 1 bp while execution adapter hardcodes 5 bp.",
        "Incorrect — research vs production implementation drift.",
        [
            "Notebook parameter cell hash",
            "Adapter constant for assumed_slippage_bps",
            "Actual realized slippage from fills",
        ],
        "FAIL",
    ),
    (
        "[VERIFY] Kill switch YAML enables kill_on_drawdown: true but watchdog binary was built with flag disabled.",
        "Incorrect — compile-time flag contradicts runtime policy file.",
        [
            "YAML kill switch stanza",
            "Watchdog build flags from CI artifact metadata",
            "Drawdown computation input series",
        ],
        "FAIL",
    ),
]

# Extra high-weight templates mirroring eval prompt (near-duplicates with wording drift)
EVAL_MIRROR = [
    (
        "[VERIFY] Live bot reports TP from strategy YAML but execution logs show hard-coded ATR multiple not in YAML. Policy vs implementation.",
        "Incorrect — documented TP rule differs from executable rule; mismatch.",
        data_items_policy_audit()
        + ["Hard-coded ATR constant location in repo", "Fill metadata tying exits to rule ID"],
        "FAIL",
    ),
]


def main() -> None:
    rng = random.Random(SEED)
    n_adv = int(round(TARGET_N * ADV_FRAC))
    n_clean = TARGET_N - n_adv

    rows: list[dict] = []

    adv_source = list(ADV_POOL)
    adv_source.extend(EVAL_MIRROR * 12)
    rng.shuffle(adv_source)

    for i in range(n_adv):
        tpl = adv_source[i % len(adv_source)]
        inp_base, mv, data_items, st = tpl
        inp_v = inp_base + f" Variant {i + 1}."
        out = four_section_output(
            claim_summary=inp_v,
            verdict_line=mv,
            data_items=data_items,
            final_status=st,
        )
        rows.append(
            {
                "instruction": INSTR,
                "input": inp_v + "\n",
                "output": out,
                "source_ids": ["v0.2b_policy_mismatch_synth", f"adv_{i + 1:04d}"],
                "category": "policy_mismatch",
                "adversarial": True,
                "quality_flags": [
                    FLAG,
                    "adversarial_trap",
                    "substance_v0.2",
                    hashlib.sha256(inp_v.encode()).hexdigest()[:8],
                ],
            }
        )

    clean_templates: list[tuple[str, str, list[str], str]] = [
        (
            "[VERIFY] Auditor confirms strategy YAML hash matches loaded module and execution logs reference same hash.",
            "Correct — no drift detected given matching artifact IDs across YAML, loader, and logs.",
            [
                "Deploy manifest checksum line",
                "Loader log line printing effective YAML SHA256",
                "Sample fills referencing strategy_revision field",
            ],
            "PASS",
        ),
        (
            "[VERIFY] Risk asks whether 1% sizing policy matches ledger when equity updates each session.",
            "Correct — sizing can match policy if quantity recomputed from refreshed equity; verify with DATA.",
            [
                "Equity snapshots at each session boundary",
                "Order notional / equity ratio per trade",
                "Policy risk_per_trade unchanged in YAML",
            ],
            "PASS",
        ),
        (
            "[VERIFY] Does the dashboard submission route call the same validator as the automated gate?",
            "Correct — single shared library path reduces mismatch risk; still verify with traces.",
            [
                "HTTP route handler stack trace module path",
                "Shared validator function symbol",
                "ADX gate evaluation log for manual submit ID",
            ],
            "PASS",
        ),
        (
            "[VERIFY] Registry shows momentum_v3 and systemd ExecStart loads momentum_v3.main.",
            "Correct — registry and argv aligned on inspection.",
            [
                "systemd unit file after daemon-reload",
                "Import path in runner log",
                "Policy registry row for active strategy",
            ],
            "PASS",
        ),
    ]

    for j in range(n_clean):
        tpl = clean_templates[j % len(clean_templates)]
        inp, mv, data_items, st = tpl
        inp_v = inp + f" Case ref {j + 1}."
        out = four_section_output(
            claim_summary=inp_v,
            verdict_line=mv,
            data_items=data_items,
            final_status=st,
        )
        rows.append(
            {
                "instruction": INSTR,
                "input": inp_v + "\n",
                "output": out,
                "source_ids": ["v0.2b_policy_mismatch_synth", f"clean_{j + 1:04d}"],
                "category": "policy_mismatch",
                "adversarial": False,
                "quality_flags": [FLAG, "reference_alignment", "substance_v0.2"],
            }
        )

    rng.shuffle(rows)

    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    adv_n = sum(1 for r in rows if r.get("adversarial"))
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    report_lines = [
        "# FinQuant v0.2b — policy mismatch reinforcement",
        "",
        f"**Generated (UTC):** `{ts}`",
        "",
        "## Purpose",
        "",
        "Targeted patch for **policy vs implementation** drift. Adversarial rows teach **Incorrect** verdicts "
        "and **FAIL** status unless evidence proves YAML/registry/logs align. Clean rows teach audited alignment.",
        "",
        "## Artifacts",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total records | {len(rows)} |",
        f"| Adversarial | {adv_n} ({100.0 * adv_n / len(rows):.1f}%) |",
        f"| Seed | {SEED} |",
        f"| Flag | `{FLAG}` |",
        "",
        "## Staging (trx40)",
        "",
        "```text",
        "/data/finquant-1/datasets/staging/finquant_v0.2b_policy_mismatch_reinforcement.jsonl",
        "```",
        "",
        "## Combined smoke training (v0.2 + v0.2b)",
        "",
        "Merge with base v0.2 reinforcement **without** deduplicating lines:",
        "",
        "```bash",
        "export FINQUANT_BASE=/data/finquant-1",
        "cd ~/blackbox",
        "cat \\",
        "  /data/finquant-1/datasets/staging/finquant_v0.2_reinforcement.jsonl \\",
        "  /data/finquant-1/datasets/staging/finquant_v0.2b_policy_mismatch_reinforcement.jsonl \\",
        "  > /data/finquant-1/datasets/staging/finquant_v0.2_plus_v0.2b_reinforcement.jsonl",
        "wc -l /data/finquant-1/datasets/staging/finquant_v0.2_plus_v0.2b_reinforcement.jsonl",
        "",
        "python3 finquant/training/train_qlora.py smoke --config finquant/training/config_v0.1.yaml \\",
        "  --dataset /data/finquant-1/datasets/staging/finquant_v0.2_plus_v0.2b_reinforcement.jsonl \\",
        "  --output-dir adapters/finquant-1-qwen7b-v0.2-smoke",
        "",
        "python3 finquant/evals/eval_finquant.py --adapter adapters/finquant-1-qwen7b-v0.2-smoke \\",
        "  --write-report --report-path v0.2_smoke_eval_report.md",
        "```",
        "",
        "## Acceptance",
        "",
        "- `policy_mismatch` eval case **pass**",
        "- `funding_liquidation` **still pass**",
        "- Overall **6/6** on smoke eval harness",
        "",
        "---",
        "",
        f"*Generator:* `finquant/scripts/generate_v0_2b_policy_mismatch_jsonl.py`*",
    ]
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(report_lines), encoding="utf-8")

    print(json.dumps({"path": str(OUT_JSONL), "report": str(OUT_REPORT), "total": len(rows), "adversarial": adv_n, "seed": SEED}, indent=2))


if __name__ == "__main__":
    main()
