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

PRIME DIRECTIVE:
P-1 NEVER LIE. Only use data in this prompt. Never invent values.
P-2 REASON WITH TOOLS. Cite specific indicator values (RSI=X, ATR%=Y) in your thesis.
P-3 SELECTIVE ENTRY. Enter when multiple signals align. Stand down when signals are mixed or weak.
     Examples of clear ENTER_LONG: RSI rising through 52+, ATR expanding, price above EMA, volume up.
     Examples of clear NO_TRADE: RSI flat near 50, ATR contracting, mixed signals.
P-4 PATTERN SIMILARITY. If memory records match the current regime, weight them in your decision.
P-5 CONTEXT FIRST. State the regime and RSI trajectory before giving the action.
P-6 LONG-RUN MATH. Aim for R >= 1.5 (target >= 1.5x stop distance) when entering.

HYPOTHESIS REQUIREMENT (R-002):
State your primary thesis (h1) and the best counter-argument (h2), each with confidence [0.0-1.0].
Use INSUFFICIENT_DATA only when signals genuinely contradict each other and you truly cannot decide.
Do NOT default to INSUFFICIENT_DATA just because there is some uncertainty — that is expected.
A confidence_spread of 0.20 is sufficient to act. Spreads of 0.15-0.19 should be NO_TRADE, not INSUFFICIENT_DATA.

Output format (JSON only, no other text):
{
  "hypothesis_1": {
    "thesis": "primary thesis with specific indicator citations",
    "confidence": 0.0-1.0,
    "evidence": ["RSI=X rising", "ATR%=Y expanding", ...]
  },
  "hypothesis_2": {
    "thesis": "strongest counter-argument",
    "confidence": 0.0-1.0,
    "evidence": ["counter-signal 1", ...]
  },
  "confidence_spread": hypothesis_1.confidence - hypothesis_2.confidence,
  "action": "NO_TRADE | ENTER_LONG | ENTER_SHORT | HOLD | EXIT | INSUFFICIENT_DATA",
  "thesis": "two-sentence rationale citing regime, RSI, and ATR",
  "invalidation": "specific price level or condition that would make this wrong",
  "planned_stop": null or price level,
  "planned_target": null or price level,
  "planned_r_multiple": null or number,
  "confidence": "low | medium | high",
  "supporting": ["indicator or signal supporting the action"],
  "conflicting": ["indicator arguing against"],
  "risk_notes": "brief risk note"
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
    lines.append("  State hypothesis_1 (primary thesis) AND hypothesis_2 (counter-thesis) with confidence [0-1].")
    lines.append("  confidence_spread = h1.confidence - h2.confidence:")
    lines.append("    >= 0.20 → act on h1  |  0.10-0.19 → NO_TRADE  |  < 0.10 → INSUFFICIENT_DATA")
    lines.append("  INSUFFICIENT_DATA is for genuinely contradictory signals only — do NOT use as a default.")
    lines.append("  If entering, state planned_stop and planned_target. Aim for R >= 1.5.")
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
