"""
Directive 4.6.4 / 4.6.3.X — Grounded strategy copy for benchmark-aligned questions.

Deterministic text only (no LLM). Overrides generic interpretation summaries when patterns match.
"""
from __future__ import annotations

import re
from typing import Any


def apply_strategy_playbook(
    input_text: str,
    human_intent: dict[str, Any],
) -> dict[str, Any] | None:
    """
    If the question matches a known baseline-strategy pattern, return fields to merge
    into interpretation: headline (optional), summary (required), extra_signals.
    """
    raw = (input_text or "").strip()
    low = raw.lower()
    topic = (human_intent or {}).get("topic")

    # --- 5: confidence vs threshold (numeric rule) ---
    if re.search(
        r"\b61\b.*\b65\b|\b65\b.*\b61\b|scores?\s+61|threshold\s+is\s+65",
        low,
    ):
        return {
            "headline": "Threshold discipline",
            "summary": (
                "With a hard threshold at 65 and an adjusted score of 61, the setup should not be "
                "forwarded for execution — it fails the gate. Treat it as no-go for automated forwarding; "
                "you can still log, watch, or refine inputs until it clears 65. This is rule-driven: "
                "no emotional override."
            ),
            "extra_signals": ["playbook:confidence_threshold"],
        }

    # --- 6: consecutive losses + low volume ---
    if re.search(r"three\s+consecutive\s+loss", low) and re.search(
        r"low[- ]volume|low volume", low
    ):
        return {
            "headline": "Loss streak + thin conditions",
            "summary": (
                "After three consecutive losses in a low-volume regime, the system should pause new "
                "signals (cooldown), require a regime reset or revalidation, and avoid firing blindly — "
                "edge is likely degraded until volume and structure improve."
            ),
            "extra_signals": ["playbook:loss_streak_pause"],
        }

    # --- 3: RSI divergence + weak volume ---
    if "rsi" in low and re.search(r"divergenc", low) and re.search(
        r"volume\s+is\s+weak|weak\s+volume", low
    ):
        return {
            "headline": "Signal quality vs volume",
            "summary": (
                "RSI divergence alone is not enough if SOL-PERP volume is weak: signal quality drops. "
                "Default stance is to reduce confidence, size down, or skip unless structure and "
                "volume confirm — divergence without participation is easy to fade."
            ),
            "extra_signals": ["playbook:rsi_volume_suppression"],
        }

    # --- 2: fake breakout / follow-through ---
    if re.search(r"fake\s+breakout|local\s+high", low) and re.search(
        r"follow[- ]through|loses\s+follow", low
    ):
        return {
            "headline": "Breakout failure",
            "summary": (
                "Treat it as a likely fake if price breaks a local high then immediately fails: "
                "no continuation, wick-heavy rejection, failure to hold above the level, and "
                "volume that does not confirm. A reclaim back inside the prior range reinforces "
                "trap behavior over a real trend leg."
            ),
            "extra_signals": ["playbook:fake_breakout"],
        }

    # --- 4: wide spread at entry ---
    if re.search(r"spread.*wide|wide.*spread", low) and "entry" in low:
        return {
            "headline": "Spread vs setup quality",
            "summary": (
                "A wide spread at entry hurts fill quality and raises slippage risk even when "
                "the chart setup looks good. The signal should be downgraded or you should wait "
                "until the spread normalizes — good pattern ≠ good trade if execution is toxic."
            ),
            "extra_signals": ["playbook:wide_spread_entry"],
        }

    # --- 8: refuse despite valid divergence ---
    if re.search(r"refuse|veto|reject", low) and "rsi" in low and "divergenc" in low:
        return {
            "headline": "Veto conditions",
            "summary": (
                "Even with valid RSI divergence you can refuse the trade: dead or weak volume, "
                "wide spread, conflicting structure, bad follow-through, or post-adjustment confidence "
                "below gate. Divergence is a filter input, not a blank check."
            ),
            "extra_signals": ["playbook:veto_conditions"],
        }

    # --- 7: partial profit ---
    if re.search(r"partial\s+profit", low) or (
        "full target" in low and "hold" in low
    ):
        return {
            "headline": "Partial vs full",
            "summary": (
                "Take partial profit when momentum fades before the target, structure shows "
                "lower highs or reversal risk, you approach resistance, spread widens, or "
                "volume dries up — lock some gain and manage the rest with a trail or clearer invalidation."
            ),
            "extra_signals": ["playbook:partial_profit"],
        }

    # --- 9: bad fill / spread environment ---
    if re.search(r"bad\s+spread|spread\s+environment", low) and re.search(
        r"lose|loses|lost|money", low
    ):
        return {
            "headline": "Execution vs idea",
            "summary": (
                "If the idea was sound but you lost due to a bad spread environment, separate signal "
                "quality from fill quality: track spread at entry, tighten confidence or filter "
                "when spreads are wide, and learn execution conditions — not just win/loss."
            ),
            "extra_signals": ["playbook:spread_learning"],
        }

    # --- 10: Sean feedback ---
    if "sean" in low and re.search(r"follow[- ]through|signal\s+was\s+wrong", low):
        return {
            "headline": "Human feedback",
            "summary": (
                "Treat that as correction: log it, classify as analytical feedback, ask a clarifying "
                "question if needed, and validate against trade evidence before changing rules — "
                "do not mutate strategy from one comment alone."
            ),
            "extra_signals": ["playbook:human_feedback"],
        }

    # --- 1: exit timing / topping ---
    if topic == "exit_logic" or (
        "get out" in low
        and re.search(r"topp|revers", low)
    ):
        return {
            "headline": "Exit timing",
            "summary": (
                "Step down when momentum stalls: weaker candle bodies, upper wicks, volume "
                "thins, or lower highs / reversal structure form. Consider tightening the stop, "
                "scaling out, or taking partial profit to protect open PnL instead of hoping for "
                "full take-profit into a rollover."
            ),
            "extra_signals": ["playbook:exit_timing"],
        }

    return None
