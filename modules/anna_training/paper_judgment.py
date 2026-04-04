"""Paper ledger vs live settlement — training judgment contract.

Grade 12 and bachelor **paper** tracks do **not** move venue capital. Settlement is still **off**.

**Judgment is on.** Rows in ``paper_trades.jsonl`` (from Jack paper, manual log-trade, or the bundled lab executor)
are the **authoritative performance surface** for curriculum gates, wallet goals, cohort metrics, and report cards.
“Monopoly money” means **no bank transfer** — not that outcomes are ignored. Anna is expected to play with full
discipline; wins and losses in the log **count** for pass/fail the same way they would if the digits were wired
to a broker after policy graduation.
"""

from __future__ import annotations

# Single importable flag for UI, tests, and docs that need a binary contract.
PAPER_LEDGER_AUTHORITATIVE_FOR_TRAINING: bool = True

PAPER_JUDGMENT_BLURB: str = (
    "Paper rows are what Grade 12 gates and the scorecard judge: no live settlement, but logged "
    "results and P&L are the real training record until policy allows venue execution."
)
