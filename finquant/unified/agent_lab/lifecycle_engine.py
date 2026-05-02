"""
FinQuant Unified Agent Lab — Lifecycle Engine.

Core FinQuant trader loop for the lab.
Processes candles in order; produces one decision event per step.
Future candles (>= hidden_future_start_index) are never visible during decisions.

Phase 0: deterministic stub logic. LLM wiring is a later directive.
"""

from __future__ import annotations
from typing import Any

from data_contracts import build_input_packet
from decision_contracts import make_decision
from learning.pattern_signature import build_signature_from_packet
from learning.pattern_competition import resolve_competition
from learning.decision_explainer import build_decision_explanation


class LifecycleEngine:
    def __init__(self, config: dict[str, Any], learning_store=None) -> None:
        self.config = config
        self.mode = config.get("mode", "deterministic_stub_v1")
        self._rule_source = (
            "deterministic_stub_v1" if self.mode == "deterministic_stub_v1" else "rule"
        )
        self._use_llm = bool(config.get("use_llm_v1", False))
        self._llm_model = str(config.get("llm_model_v1") or "qwen2.5:7b")
        self._ollama_url = str(config.get("ollama_base_url_v1") or "http://172.20.2.230:11434")
        self._llm_timeout = int(config.get("llm_timeout_seconds_v1") or 30)
        self._llm_max_tokens = int(config.get("llm_max_tokens_v1") or 400)
        self._learning_store = learning_store

    def run_case(
        self,
        case: dict[str, Any],
        prior_records: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Process all decision steps in a case.

        Returns one decision dict per step in [decision_start_index, decision_end_index].
        Candles at or after hidden_future_start_index are never passed to the decision logic.
        """
        case_id = case["case_id"]
        symbol = case["symbol"]
        candles = case["candles"]
        start = case["decision_start_index"]
        end = case["decision_end_index"]
        hide_from = case["hidden_future_start_index"]

        decisions: list[dict[str, Any]] = []
        position_open = False
        entry_price: float | None = None
        entry_volume: float | None = None
        prior_rsi: float | None = None

        for step_index in range(start, end + 1):
            # Only candles up to (and including) step_index, capped at hide_from
            visible_end = min(step_index + 1, hide_from)
            visible_bars = candles[:visible_end]
            input_packet = build_input_packet(
                case=case,
                step_index=step_index,
                visible_bars=visible_bars,
                config=self.config,
                prior_records=prior_records or [],
            )

            # -- Pattern signature for this step (always computed) --
            signature = build_signature_from_packet(input_packet, position_open=position_open)
            pattern_id = signature["pattern_id_v1"]
            human_label = signature["human_label_v1"]

            # -- Pattern competition over the learning store (if any) --
            competition = self._resolve_pattern_competition(pattern_id)

            # -- Try LLM path first; fall back to stub on any failure --
            llm_fields: dict[str, Any] = {}
            llm_used = False

            if self._use_llm:
                llm_fields, llm_used = self._decide_with_llm(
                    input_packet=input_packet,
                    position_open=position_open,
                    entry_price=entry_price,
                    entry_volume=entry_volume,
                )

            if not llm_used:
                (
                    action,
                    thesis,
                    invalidation,
                    risk_state,
                    decision_source,
                    confidence_band,
                    supporting_indicators,
                    conflicting_indicators,
                    risk_notes,
                ) = self._decide(
                    step_index=step_index,
                    visible_bars=visible_bars,
                    position_open=position_open,
                    entry_price=entry_price,
                    entry_volume=entry_volume,
                    prior_rsi=prior_rsi,
                    prior_records=prior_records or [],
                    input_packet=input_packet,
                )
                raw_output = ""
                llm_latency = 0
            else:
                action = llm_fields["action"]
                thesis = llm_fields["thesis_v1"]
                invalidation = llm_fields["invalidation_v1"]
                risk_state = llm_fields["risk_state_v1"]
                decision_source = "llm"
                confidence_band = llm_fields["confidence_band_v1"]
                supporting_indicators = llm_fields["supporting_indicators_v1"]
                conflicting_indicators = llm_fields["conflicting_indicators_v1"]
                risk_notes = llm_fields["risk_notes_v1"]
                raw_output = llm_fields.get("raw_model_output_v1", "")
                llm_latency = llm_fields.get("llm_latency_ms_v1", 0)

            decision = make_decision(
                case_id=case_id,
                step_index=step_index,
                symbol=symbol,
                action=action,
                thesis_v1=thesis,
                invalidation_v1=invalidation,
                risk_state_v1=risk_state,
                observed_context_v1=self._summarize_context(visible_bars),
                input_packet_v1=input_packet,
                confidence_band_v1=confidence_band,
                supporting_indicators_v1=supporting_indicators,
                conflicting_indicators_v1=conflicting_indicators,
                risk_notes_v1=risk_notes,
                memory_used_v1=[r["record_id"] for r in (prior_records or [])],
                llm_used_v1=llm_used,
                decision_source_v1=decision_source,
            )
            # Attach raw model output outside the contract for audit (not authoritative)
            if llm_used:
                decision["raw_model_output_v1"] = raw_output
                decision["llm_latency_ms_v1"] = llm_latency

            # Attach pattern signature + decision explanation
            decision["pattern_signature_v1"] = signature
            decision["decision_explanation_v1"] = build_decision_explanation(
                pattern_id=pattern_id,
                human_label=human_label,
                competition=competition,
                final_action=action,
                final_decision_source=decision_source,
            )
            decisions.append(decision)

            # Update position state
            if action in ("ENTER_LONG", "ENTER_SHORT"):
                position_open = True
                entry_price = visible_bars[-1]["close"] if visible_bars else None
                entry_volume = visible_bars[-1].get("volume") if visible_bars else None
            elif action == "EXIT":
                position_open = False
                entry_price = None
                entry_volume = None

            if visible_bars:
                prior_rsi = visible_bars[-1].get("rsi_14")

        return decisions

    # ------------------------------------------------------------------
    # Learning-unit competition (queries the learning store, if attached)
    # ------------------------------------------------------------------

    def _resolve_pattern_competition(self, pattern_id: str) -> dict[str, Any]:
        if not self._learning_store:
            return {
                "primary_unit_v1": None,
                "challengers_v1": [],
                "observers_v1": [],
                "suppressors_v1": [],
                "reason_v1": "no learning store attached",
            }
        try:
            units = self._learning_store.units_by_pattern(pattern_id)
        except Exception as exc:
            return {
                "primary_unit_v1": None,
                "challengers_v1": [],
                "observers_v1": [],
                "suppressors_v1": [],
                "reason_v1": f"store query failed: {exc}",
            }
        return resolve_competition(units)

    # ------------------------------------------------------------------
    # LLM decision path (Ollama)
    # ------------------------------------------------------------------

    def _decide_with_llm(
        self,
        *,
        input_packet: dict[str, Any],
        position_open: bool,
        entry_price: float | None,
        entry_volume: float | None,
    ) -> tuple[dict[str, Any], bool]:
        """
        Call Ollama and parse a governed decision.
        Returns (fields_dict, success).
        On any failure returns ({}, False) so caller falls back to stub.
        """
        from llm_adapter import call_ollama, normalize_llm_decision
        from prompt_builder import build_prompt, SYSTEM_PROMPT

        prompt = build_prompt(
            input_packet,
            position_open=position_open,
            entry_price=entry_price,
            entry_volume=entry_volume,
        )

        result = call_ollama(
            base_url=self._ollama_url,
            model=self._llm_model,
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            timeout_seconds=self._llm_timeout,
            max_tokens=self._llm_max_tokens,
        )

        if not result.success:
            return {}, False

        fields = normalize_llm_decision(
            result.parsed,
            case_id=str(input_packet.get("case_id", "")),
            step_index=int(input_packet.get("step_index", 0)),
            symbol=str(input_packet.get("symbol", "")),
            raw_output=result.raw_output,
            latency_ms=result.latency_ms,
        )
        return fields, True

    # ------------------------------------------------------------------
    # Deterministic stub decision logic
    # ------------------------------------------------------------------

    def _decide(
        self,
        step_index: int,
        visible_bars: list[dict],
        position_open: bool,
        entry_price: float | None,
        entry_volume: float | None,
        prior_rsi: float | None,
        prior_records: list,
        input_packet: dict[str, Any],
    ) -> tuple[str, str, str, str, str, str, list[str], list[str], str]:
        """Return decision fields for the governed contract."""

        if not visible_bars:
            return (
                "NO_TRADE",
                "No candles visible at this step.",
                "Insufficient data — cannot form a thesis.",
                "no_data",
                self._rule_source,
                "low",
                [],
                ["no_visible_bars"],
                "No risk can be defined without visible data.",
            )

        current = visible_bars[-1]
        rsi = current.get("rsi_14")
        atr = current.get("atr_14")
        close = current.get("close", 0.0)
        ema = current.get("ema_20")

        rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
        support: list[str] = []
        conflicts: list[str] = []

        # -- If in a position, evaluate hold vs exit --
        if position_open and entry_price is not None:
            # Hard exit conditions
            rsi_low = rsi is not None and rsi < 45.0
            price_retreat = close < entry_price * 0.995          # 0.5% below entry
            # Momentum decay: RSI dropped 5+ pts from prior step
            rsi_decay = (
                rsi is not None and prior_rsi is not None
                and (prior_rsi - rsi) >= 5.0
            )
            # Volume collapse vs entry volume
            vol_collapse = (
                entry_volume is not None
                and current.get("volume", 0) < entry_volume * 0.60
            )
            # Resistance level invalidation: close fell back below resistance
            res = current.get("resistance_level")
            resistance_break_fail = res is not None and close < res

            if rsi_low or price_retreat or resistance_break_fail or (rsi_decay and vol_collapse):
                reasons = []
                if rsi_low:
                    reasons.append(f"RSI={rsi_str}<45")
                if price_retreat:
                    reasons.append(f"close={close:.2f}<entry*0.995={entry_price*0.995:.2f}")
                if resistance_break_fail:
                    reasons.append(f"close={close:.2f} fell back below resistance={res}")
                if rsi_decay and vol_collapse:
                    reasons.append(f"RSI decayed {prior_rsi:.1f}→{rsi_str}, volume collapsed")
                return (
                    "EXIT",
                    f"Thesis invalidated: {'; '.join(reasons)}.",
                    "RSI reclaims prior level or price clears resistance.",
                    f"exit_triggered {' '.join(reasons)}",
                    self._rule_source,
                    "high",
                    reasons,
                    [],
                    "Exit was triggered by explicit invalidation rules.",
                )
            return (
                "HOLD",
                f"Position open. RSI={rsi_str}, close={close:.2f}. No exit signal.",
                "Exit if RSI < 45, price retreats 0.5%, or resistance recaptured.",
                f"holding entry={entry_price:.2f}",
                self._rule_source,
                "medium",
                [f"RSI={rsi_str}", f"close={close:.2f}"],
                [],
                "Hold while thesis remains intact.",
            )

        # -- No position — evaluate entry --

        # Single-candle breakout detection (resistance level case)
        res = current.get("resistance_level")
        if res is not None and close > res and rsi is not None and rsi > 58 and atr is not None and atr > 1.5:
            vol_ok = current.get("volume", 0) > 3000
            if vol_ok:
                return (
                    "ENTER_LONG",
                    f"Breakout above resistance={res}: close={close:.2f}, RSI={rsi_str}, ATR={atr:.2f}, vol={current.get('volume')}.",
                    f"Exit if close falls back below resistance {res} on next candle.",
                    f"breakout_long res={res} rsi={rsi_str}",
                    self._rule_source,
                    "high",
                    [f"breakout_above_resistance={res}", f"RSI={rsi_str}", f"ATR={atr:.2f}"],
                    [],
                    "ATR-based risk geometry should be applied if opened.",
                )

        if len(visible_bars) < 2:
            return (
                "NO_TRADE",
                "Only one candle visible; insufficient context for trend entry.",
                "Need at least 2 candles to form a thesis.",
                "insufficient_context",
                self._rule_source,
                "low",
                [],
                ["insufficient_context"],
                "Do not size risk from a one-candle view.",
            )

        prev = visible_bars[-2]
        price_up = close > prev["close"]
        rsi_ok = rsi is not None and 50 < rsi < 70
        volume_expand = current.get("volume", 0) > prev.get("volume", 0)
        atr_expand = atr is not None and atr > 1.5
        price_above_ema = ema is not None and close > ema
        memory = input_packet.get("memory_context_v1") or {}
        memory_long = int(memory.get("long_bias_count_v1", 0))
        memory_available = bool(memory.get("memory_influence_available_v1"))
        near_threshold_long = (
            price_up
            and price_above_ema
            and rsi is not None and rsi >= 52
            and atr is not None and atr >= 1.2
            and current.get("volume", 0) >= prev.get("volume", 0) * 1.05
        )

        # Trend entry: price rising, RSI mid-range, volume expanding
        if price_up and rsi_ok and volume_expand and atr_expand:
            return (
                "ENTER_LONG",
                f"Uptrend: close {prev['close']:.2f}→{close:.2f}, RSI={rsi_str}, volume expanding, ATR={atr:.2f}.",
                f"Exit if close drops below {close * 0.995:.2f} or RSI decays with volume collapse.",
                f"entry_long rsi={rsi_str} atr={atr:.2f}",
                self._rule_source,
                "high",
                [f"close_up={price_up}", f"rsi_midrange={rsi_ok}", f"volume_expand={volume_expand}", f"atr_expand={atr_expand}"],
                [],
                "Strong trend-continuation evidence.",
            )

        if memory_available and memory_long > 0 and near_threshold_long:
            return (
                "ENTER_LONG",
                f"Memory-backed long: similar promoted long pattern(s)={memory_long}; close={close:.2f}, RSI={rsi_str}, ATR={atr:.2f}.",
                f"Exit if close drops below {close * 0.995:.2f} or memory thesis is contradicted by RSI < 45.",
                f"memory_backed_entry long_bias={memory_long}",
                "hybrid",
                "medium",
                [f"memory_long_bias={memory_long}", f"close_above_ema={price_above_ema}", f"rsi={rsi_str}"],
                ["direct_rule_threshold_not_fully_met"],
                "Memory/context promoted a near-threshold trend setup into an allowed entry.",
            )

        # Chop / ranging: price not moving decisively
        avg_move = abs(close - prev["close"])
        is_chop = avg_move < 0.5 or (atr is not None and atr < 1.0)
        if is_chop:
            return (
                "NO_TRADE",
                f"Market choppy: avg_move={avg_move:.2f}, ATR={atr}. No edge.",
                "Stand down until ATR > 1.0 and directional conviction appears.",
                "chop_no_edge",
                self._rule_source,
                "medium",
                [],
                [f"avg_move={avg_move:.2f}", f"atr={atr}"],
                "No-trade is the best bounded action under chop.",
            )

        return (
            "NO_TRADE",
            f"Conditions not met: price_up={price_up}, rsi_ok={rsi_ok}, volume_expand={volume_expand}.",
            "Require price uptick, RSI 50-70, expanding volume.",
            "wait",
                self._rule_source,
                "low",
            [],
            [f"price_up={price_up}", f"rsi_ok={rsi_ok}", f"volume_expand={volume_expand}"],
            "Wait for a stronger bounded setup.",
        )

    def _summarize_context(self, visible_bars: list[dict]) -> dict[str, Any]:
        if not visible_bars:
            return {}
        bar = visible_bars[-1]
        return {
            "candles_visible": len(visible_bars),
            "last_close": bar.get("close"),
            "last_rsi_14": bar.get("rsi_14"),
            "last_ema_20": bar.get("ema_20"),
            "last_atr_14": bar.get("atr_14"),
            "last_volume": bar.get("volume"),
        }
