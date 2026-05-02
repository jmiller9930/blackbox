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
You are FinQuant, a disciplined quantitative crypto-perps trading agent.

PRIME DIRECTIVE — non-negotiable:
P-1 NEVER LIE. Only use data in this prompt. Never invent values or fabricate confidence.
P-2 REASON WITH TOOLS. Use the indicators, regime, and memory provided. Do not guess.
P-3 RISK-AVERSE DEFAULT. Default is NO_TRADE. Entries require confluence across multiple independent signals.
P-4 PATTERN SIMILARITY. If memory records are provided, anchor your judgment in them.
P-5 CONTEXT FIRST. Read the trajectory (how indicators have been moving) before deciding.
P-6 LONG-RUN MATH. Target must be at least 1.5x the stop distance. If R < 1.5, prefer NO_TRADE.

REQUIRED OUTPUT — two competing hypotheses, then a decision:
You must state BOTH a primary thesis AND a counter-thesis with numeric confidence [0.0-1.0].
If (primary_confidence - counter_confidence) < 0.20, you MUST output INSUFFICIENT_DATA — do not force a trade.

Output format (JSON only, no other text):
{
  "hypothesis_1": {
    "thesis": "primary thesis — the case FOR the proposed action",
    "confidence": 0.0-1.0,
    "evidence": ["signal supporting this thesis"]
  },
  "hypothesis_2": {
    "thesis": "counter-thesis — the strongest argument AGAINST",
    "confidence": 0.0-1.0,
    "evidence": ["signal supporting the counter"]
  },
  "confidence_spread": hypothesis_1.confidence - hypothesis_2.confidence,
  "action": "NO_TRADE | ENTER_LONG | ENTER_SHORT | HOLD | EXIT | INSUFFICIENT_DATA",
  "thesis": "two-sentence decision rationale referencing the winning hypothesis",
  "invalidation": "specific price level or condition that would make this decision wrong",
  "planned_stop": null or price level,
  "planned_target": null or price level,
  "planned_r_multiple": null or (target_distance / stop_distance),
  "confidence": "low | medium | high",
  "supporting": ["signals that support the action"],
  "conflicting": ["signals that argue against"],
  "risk_notes": "risk management note"
}"""


def build_prompt(
    input_packet: dict[str, Any],
    position_open: bool = False,
    entry_price: float | None = None,
    entry_volume: float | None = None,
) -> str:
    """
    Build a structured prompt from the input packet.
    Includes prime directive context, trajectory, memory, and R-002 output requirement.
    """
    lines: list[str] = []

    symbol = input_packet.get("symbol", "?")
    tf = input_packet.get("timeframe_minutes", "?")
    regime = input_packet.get("regime_v1") or "unknown"
    lines.append(f"MARKET: {symbol} | {tf}m candles | Regime: {regime.upper()}")
    lines.append(f"Candles of context visible: {input_packet.get('candles_visible_v1', 0)}")
    lines.append("")

    # --- Current bar (P-5 context first) ---
    math = input_packet.get("market_math_v1") or {}
    ctx = input_packet.get("market_context_v1") or {}
    close = math.get("close_v1")
    prev_close = math.get("prev_close_v1")
    atr = math.get("atr_14_v1")
    rsi = math.get("rsi_14_v1")
    atr_pct = None
    if atr is not None and close and float(close) > 0:
        atr_pct = float(atr) / float(close) * 100

    lines.append("=== CURRENT BAR (P-5: read context before indicators) ===")
    lines.append(f"  Close: {close}  Prev close: {prev_close}  Change: {_fmt_pct(math.get('pct_change_v1'))}")
    lines.append(f"  RSI(14): {rsi}  [{ctx.get('rsi_state_v1', 'unknown')}]")
    lines.append(f"  ATR(14): {atr}  [{f'{atr_pct:.3f}% of price' if atr_pct else 'N/A'}]  [{ctx.get('volatility_state_v1', 'unknown')} volatility]")
    lines.append(f"  EMA(20) gap: {math.get('ema_gap_v1')}  Price above EMA: {ctx.get('price_above_ema_v1')}")
    lines.append(f"  Volume: {_fmt_vol(math.get('volume_delta_v1'))} vs prior bar  Expanding: {ctx.get('volume_expand_v1')}")
    lines.append(f"  ATR expanded (>0.60% of price): {ctx.get('atr_expanded_v1')}")
    lines.append("")

    # --- Memory context (P-4) ---
    memory = input_packet.get("memory_context_v1") or {}
    lines.append("=== MEMORY CONTEXT (P-4: anchor judgment in prior validated patterns) ===")
    if memory.get("memory_influence_available_v1"):
        lines.append(f"  Retrieved records: {memory.get('matched_record_count_v1', 0)}")
        lines.append(f"  Long-bias patterns: {memory.get('long_bias_count_v1', 0)}  Short-bias: {memory.get('short_bias_count_v1', 0)}  No-trade: {memory.get('no_trade_bias_count_v1', 0)}")
        lines.append(f"  Best prior grade: {memory.get('best_grade_v1', 'UNKNOWN')}")
        lines.append("  These patterns are from VALIDATED prior decisions on similar market structures.")
        lines.append("  Check whether current regime matches the pattern's regime before applying.")
    else:
        lines.append("  No validated patterns available. Reason from indicators only (P-2).")
        lines.append("  Be more conservative without memory support (P-3).")
    lines.append("")

    # --- Strategy hypotheses (deterministic scoring for reference) ---
    hypotheses = input_packet.get("strategy_hypotheses_v1") or []
    if hypotheses:
        lines.append("=== DETERMINISTIC SCORING (reference — do NOT blindly follow) ===")
        for h in sorted(hypotheses, key=lambda x: x.get("score_v1", 0), reverse=True)[:3]:
            lines.append(
                f"  {h.get('strategy_family_v1', '?'):30} → {h.get('action_v1', '?'):12} score={h.get('score_v1', 0):.2f}"
            )
        lines.append("")

    # --- Position state ---
    lines.append("=== POSITION STATE ===")
    if position_open and entry_price is not None:
        lines.append(f"  OPEN position. Entry price: {entry_price}")
        if entry_volume:
            lines.append(f"  Entry volume: {entry_volume}")
        lines.append("  Decide: HOLD or EXIT.")
    else:
        lines.append("  FLAT — no open position.")
        lines.append("  Decide: NO_TRADE, ENTER_LONG, or ENTER_SHORT.")
    lines.append("")

    # --- R-002 reminder ---
    lines.append("=== DECISION REQUIREMENT (R-002) ===")
    lines.append("  State hypothesis_1 (primary thesis) AND hypothesis_2 (counter-thesis).")
    lines.append("  If confidence_spread = h1.confidence - h2.confidence < 0.20 → action MUST be INSUFFICIENT_DATA.")
    lines.append("  If entering, state planned_stop and planned_target. R = target_dist / stop_dist must be >= 1.5.")
    lines.append("  P-3: when in doubt, NO_TRADE. Restraint is a first-class outcome.")
    lines.append("")
    lines.append("Produce your JSON decision now:")

    return "\n".join(lines)


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.3f}%"


def _fmt_vol(delta: float | None) -> str:
    if delta is None:
        return "N/A"
    return f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"
