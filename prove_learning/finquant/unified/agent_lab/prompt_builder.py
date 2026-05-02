"""
FinQuant Unified Agent Lab — Prompt Builder.

Builds structured prompts from the causal input packet for Ollama inference.

Governance rules:
  - Only causally available data appears in the prompt.
  - Future candles are never included.
  - Memory context is included only when retrieval is enabled and matched.
  - The model is asked to produce a single JSON object — no freeform narrative.
"""

from __future__ import annotations

from typing import Any


SYSTEM_PROMPT = """\
You are FinQuant, a disciplined crypto-perps trader agent.

You reason about market context step by step, then produce a single JSON decision.

Rules you must follow:
- Only use data provided in this prompt. Never invent indicator values or price data.
- You may choose: NO_TRADE, ENTER_LONG, ENTER_SHORT, HOLD, or EXIT.
- Choose NO_TRADE when evidence is weak, conflicting, or insufficient.
- Restraint is a first-class outcome — no forced trades.
- If in a position, evaluate whether to HOLD or EXIT.
- Your output must be a single valid JSON object — no other text after it.

Output format (JSON only):
{
  "action": "NO_TRADE | ENTER_LONG | ENTER_SHORT | HOLD | EXIT",
  "thesis": "one or two sentences explaining your reasoning",
  "invalidation": "specific condition that would invalidate this decision",
  "confidence": "low | medium | high",
  "supporting": ["indicator or context that supports the action"],
  "conflicting": ["indicator or context that argues against the action"],
  "risk_notes": "position sizing or risk management note"
}"""


def build_prompt(
    input_packet: dict[str, Any],
    position_open: bool = False,
    entry_price: float | None = None,
    entry_volume: float | None = None,
) -> str:
    """Build a prompt string from the input packet for a single lifecycle step."""
    lines: list[str] = []

    lines.append(f"Symbol: {input_packet.get('symbol')} | Timeframe: {input_packet.get('timeframe_minutes')}m | Step: {input_packet.get('step_index')}")
    lines.append(f"Candles visible: {input_packet.get('candles_visible_v1', 0)}")

    if input_packet.get("runtime_data_window_months_v1"):
        lines.append(f"Data window: {input_packet['runtime_data_window_months_v1']} months | Interval: {input_packet.get('runtime_interval_v1', 'N/A')}")

    lines.append("")
    lines.append("--- Market Math ---")
    math = input_packet.get("market_math_v1", {})
    if math:
        lines.append(f"Close: {math.get('close_v1')}  Prev close: {math.get('prev_close_v1')}")
        lines.append(f"Price delta: {math.get('price_delta_v1')}  Pct change: {_fmt_pct(math.get('pct_change_v1'))}")
        lines.append(f"EMA gap: {math.get('ema_gap_v1')}  ATR(14): {math.get('atr_14_v1')}  RSI(14): {math.get('rsi_14_v1')}")
        lines.append(f"Volume delta: {math.get('volume_delta_v1')}")

    ctx = input_packet.get("market_context_v1", {})
    if ctx:
        lines.append("")
        lines.append("--- Market Context ---")
        lines.append(f"Price above EMA: {ctx.get('price_above_ema_v1')}  Price up: {ctx.get('price_up_v1')}")
        lines.append(f"Volume expanding: {ctx.get('volume_expand_v1')}  ATR expanded: {ctx.get('atr_expanded_v1')}")
        lines.append(f"RSI state: {ctx.get('rsi_state_v1')}  Volatility: {ctx.get('volatility_state_v1')}")

    hypotheses = input_packet.get("strategy_hypotheses_v1", [])
    if hypotheses:
        lines.append("")
        lines.append("--- Strategy Hypotheses (reference only — do not blindly follow) ---")
        for h in sorted(hypotheses, key=lambda x: x.get("score_v1", 0), reverse=True):
            lines.append(
                f"  {h.get('strategy_family_v1', '?'):35} action={h.get('action_v1', '?'):12} score={h.get('score_v1', 0):.2f}"
            )

    memory = input_packet.get("memory_context_v1", {})
    if memory and memory.get("memory_influence_available_v1"):
        lines.append("")
        lines.append("--- Prior Memory Context ---")
        lines.append(f"Matched prior records: {memory.get('matched_record_count_v1', 0)}")
        lines.append(f"Long bias: {memory.get('long_bias_count_v1', 0)}  Short bias: {memory.get('short_bias_count_v1', 0)}  No-trade bias: {memory.get('no_trade_bias_count_v1', 0)}")
        lines.append(f"Best prior grade: {memory.get('best_grade_v1', 'UNKNOWN')}")
        lines.append("Note: prior memory shows validated patterns from similar past setups.")
    else:
        lines.append("")
        lines.append("--- Prior Memory Context ---")
        lines.append("No eligible prior memory available for this step.")

    lines.append("")
    lines.append("--- Position State ---")
    if position_open and entry_price is not None:
        lines.append(f"Position: OPEN  Entry price: {entry_price}")
        if entry_volume is not None:
            lines.append(f"Entry volume: {entry_volume}")
        lines.append("You must decide: HOLD or EXIT.")
    else:
        lines.append("Position: FLAT")
        lines.append("You must decide: NO_TRADE, ENTER_LONG, or ENTER_SHORT.")

    lines.append("")
    lines.append("Produce your decision now as a single JSON object:")

    return "\n".join(lines)


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.3f}%"
