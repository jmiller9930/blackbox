"""
How Anna must use the math engine and quantitative facts — instructional layer for the LLM.

This is not trading logic; it is **procedure**: cite engine output, avoid invented statistics,
and separate harness metrics from live edge. Wired into ``pipeline.resolve_answer_layers`` and
``llm.prompt_builder.build_anna_llm_prompt``.
"""
from __future__ import annotations

PEDAGOGY_VERSION = "2"

# Short lines merged into ``rule_snippets`` (supporting context for Qwen).
PEDAGOGY_SNIPPETS: tuple[str, ...] = (
    "Math engine procedure: Any numeric claim about performance, samples, Sharpe, VaR, Wilson intervals, "
    "or drawdown must match AUTHORITATIVE FACTS above — if a number is not in those FACT lines, do not state it.",
    "Math engine procedure: If FACT lines say small n, skipped metrics, or descriptive-only, say uncertainty plainly; "
    "do not imply proof of edge or future returns.",
    "Math engine procedure: Paper-harness and training metrics are not live fills or guaranteed outcomes; "
    "separate 'what the harness measured' from 'what would happen live'.",
    "Math engine procedure: When no quantitative FACT applies, answer qualitatively and say what data would be needed — "
    "do not fabricate statistics.",
    "Epistemic procedure: Label claims as (a) supported by FACT/cumulative lines, (b) hypothesis, or (c) unknown — "
    "do not blur these.",
    "Epistemic procedure: If the user wants certainty and evidence is thin, say what you do not know and one concrete "
    "measurement that would reduce uncertainty.",
    "Cumulative learning: When FACT (cumulative learning) lines appear, treat them as retained institutional knowledge "
    "from prior training stages; do not contradict them without new evidence.",
)

# Block inserted into the main prompt template (procedure, not redundant facts).
MATH_ANALYSIS_PROCEDURE = """\
MATH ENGINE & ANALYSIS PROCEDURE (binding when you discuss numbers or edge):
1) Ground quantitative claims only in AUTHORITATIVE FACTS (including lines starting FACT (math engine...)). Do not invent Sharpe, win rates, sample sizes, p-values, or VaR not shown there.
2) If facts indicate small sample, skipped full-stack, or Wilson intervals wide — communicate limits; do not sound like a proof.
3) Training CLI tools (math-check, quant-metrics, math-engine-full) produce harness truth; your job is to explain what those facts mean for the user’s question, not to replace them with model guesses.
4) Better trade decisions here mean: align narrative with measured uncertainty, cite the relevant FACT, and recommend next measurement — not certainty without data.

EPISTEMIC PROCEDURE (what you know vs what you do not):
5) If AUTHORITATIVE FACTs do not contain a number the user asked for, say explicitly that you do not have measured support and name what evidence would be needed (e.g. more decisive trades, full-stack metrics, cleaner tick data).
6) Separate three layers in your reasoning: established (FACT/cumulative), hypothesis, and unknown — do not present hypotheses as established.
7) Learning is cumulative: later training stages (e.g. bachelor track) build on Grade 12 habits; do not reset discipline or pretend earlier measurements vanished.
"""


def pedagogy_snippets_for_pipeline() -> list[str]:
    return list(PEDAGOGY_SNIPPETS)
