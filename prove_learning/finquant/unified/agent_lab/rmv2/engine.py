"""
FinQuant — Reasoning Module v2 (RMv2)

Self-contained, pluggable reasoning module built on LangGraph + Tree of Thought.

Architecture:
  LangGraph StateGraph drives the decision pipeline:
    START
      → feature_extraction    (deterministic — RSI/EMA/ATR/regime, no decisions)
      → quality_retrieval     (quality-gated memory — win_rate >= 0.55, obs >= 5)
      → tot_reasoning         (Tree of Thought — 3 parallel branches, best selected)
      → guard_rails           (deterministic vetoes — chop/RSI/confidence gates)
    END

Tree of Thought (ToT):
  Standard technique (Yao et al. 2023). Three reasoning branches:
    Branch A: Bullish thesis — what conditions support ENTER_LONG?
    Branch B: Bearish/neutral thesis — what conditions support NO_TRADE?
    Branch C: Memory-informed thesis — what do prior validated patterns say?
  Each branch scores itself 0–10 on evidence strength.
  The branch with the highest evidence score drives the final proposal.
  Qwen 7B via Ollama generates each branch. Falls back to rule-based if LLM fails.

Quality-gated memory (industry best practice):
  Records retrieved only if:
    - pattern_total_obs_v1 >= MIN_OBS (default 5)
    - pattern_win_rate_v1 >= MIN_WIN_RATE (default 0.55)
    - pattern_status_v1 not in {candidate, retired}
    - regime matches case regime (when both are tagged)

Risk management (per guidance):
  Losses can exceed wins in count IF wins are financially larger.
  Positive expectancy = (avg_win * win_rate) - (avg_loss * loss_rate) > 0
  Guard rails enforce this by blocking low-confidence and chop entries.

Execution server: jmiller@172.20.2.230 (LLM and code co-located)
Data: jmiller@clawbot.a51.corp SQLite market_data.db

Package layout (RMv2 container): ``agent_lab/rmv2/`` — ``engine.py`` (this file),
``memory_index.py`` (SQLite learning index + optional context snapshots).

Usage:
  from rmv2 import ReasoningModule, RMConfig

  rm = ReasoningModule(config_path="configs/default_lab_config.json")
  decision = rm.decide(bars=last_20_bars, symbol="SOL-PERP", timeframe_minutes=15)

Self-test (no LLM):
  python3 rmv2/engine.py --self-test

LLM test (Ollama at 172.20.2.230:11434):
  python3 rmv2/engine.py --llm-test
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

_LAB_ROOT = Path(__file__).parent
sys.path.insert(0, str(_LAB_ROOT))

# Quality gate defaults
DEFAULT_MIN_OBS = 5
DEFAULT_MIN_WIN_RATE = 0.55

# ATR% thresholds calibrated to real 15m SOL-PERP (median 0.40%)
_ATR_EXPAND_PCT  = 0.0060   # > 0.60% — strong trend, full entry
_ATR_NEAR_PCT    = 0.0030   # > 0.30% — near-threshold, memory-backed OK
_ATR_CHOP_PCT    = 0.0020   # < 0.20% — genuine chop, block all entries
_RSI_LONG_MIN    = 50.0
_RSI_LONG_MAX    = 70.0
_MIN_CONFIDENCE  = 0.30

# R-003 CORE OVERRIDE — non-negotiable risk geometry
# Stop = STOP_ATR_MULT × ATR14 from entry
# Target = TARGET_ATR_MULT × ATR14 from entry
# R-multiple = TARGET / STOP = 2.5
# Breakeven win rate = 1 / (1 + 2.5) = 28.57%
# Any entry with R < MIN_R_MULTIPLE is blocked — no exceptions.
STOP_ATR_MULT   = 1.6
TARGET_ATR_MULT = 4.0
_MIN_R_MULTIPLE = 1.5   # hard floor — block if R < 1.5


# ---------------------------------------------------------------------------
# LangGraph state schema
# ---------------------------------------------------------------------------

class RMState(TypedDict):
    """State that flows through the LangGraph pipeline."""
    bars: list[dict[str, Any]]
    symbol: str
    timeframe_minutes: int
    position_open: bool
    entry_price: float | None
    config: dict[str, Any]

    # Populated by feature_extraction
    features: dict[str, Any]
    regime: str
    current_bar: dict[str, Any]

    # Populated by quality_retrieval
    prior_records: list[dict[str, Any]]
    retrieval_trace: list[dict[str, Any]]

    # Populated by tot_reasoning
    tot_branches: list[dict[str, Any]]
    tot_winner: dict[str, Any]

    # Populated by guard_rails
    final_action: str
    final_confidence: float
    final_thesis: str
    final_invalidation: str
    final_source: str
    guard_reason: str

    # Narrative query for vector pattern memory (STM/LTM similarity)
    context_narrative_v1: str

    # Metadata
    latency_ms: int
    error: str


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------

@dataclass
class RMDecision:
    action: str
    confidence: float
    thesis: str
    invalidation: str
    source: str
    regime: str
    memory_used: list[str] = field(default_factory=list)
    memory_quality: dict[str, Any] = field(default_factory=dict)
    tot_branches: list[dict[str, Any]] = field(default_factory=list)
    guard_reason: str = ""
    latency_ms: int = 0
    # Risk context — context IS risk management
    risk_pct: float = 0.0          # final recommended risk % of wallet
    risk_context: dict[str, Any] = field(default_factory=dict)  # factor breakdown
    context_narrative_v1: str = ""  # fed into tiered pattern-memory retrieval

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rm_decision_v2",
            "action": self.action,
            "confidence": self.confidence,
            "thesis": self.thesis,
            "invalidation": self.invalidation,
            "source": self.source,
            "regime": self.regime,
            "memory_used": self.memory_used,
            "memory_quality": self.memory_quality,
            "tot_branches": self.tot_branches,
            "guard_reason": self.guard_reason,
            "latency_ms": self.latency_ms,
            "risk_pct": self.risk_pct,
            "risk_context": self.risk_context,
            "context_narrative_v1": self.context_narrative_v1,
        }


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class RMConfig:
    use_llm: bool = False
    llm_model: str = "qwen2.5:7b"
    ollama_base_url: str = "http://172.20.2.230:11434"
    llm_timeout_seconds: int = 30
    llm_max_tokens: int = 500
    memory_store_path: str = ""  # JSONL spine; companion DB is same stem + .db
    retrieval_enabled: bool = False
    retrieval_max_records: int = 5
    retrieval_min_obs: int = DEFAULT_MIN_OBS
    retrieval_min_win_rate: float = DEFAULT_MIN_WIN_RATE
    retrieval_allow_candidate: bool = False
    horizon_bars: int = 5
    # Tiered vector pattern memory (STM/LTM in companion SQLite)
    memory_vector_enabled: bool = False
    memory_vector_k_stm: int = 2
    memory_vector_k_ltm: int = 2
    memory_vector_min_sim: float = 0.22
    memory_vector_max_extra: int = 4
    memory_embedding_backend: str = "deterministic"
    memory_embedding_dim: int = 256
    ollama_embeddings_model: str = "nomic-embed-text"
    stm_ttl_hours: int = 72

    @classmethod
    def from_file(cls, config_path: str) -> "RMConfig":
        with open(config_path) as f:
            raw = json.load(f)
        return cls(
            use_llm=bool(raw.get("use_llm_v1", False)),
            llm_model=str(raw.get("llm_model_v1") or "qwen2.5:7b"),
            ollama_base_url=str(raw.get("ollama_base_url_v1") or "http://172.20.2.230:11434"),
            llm_timeout_seconds=int(raw.get("llm_timeout_seconds_v1") or 30),
            llm_max_tokens=int(raw.get("llm_max_tokens_v1") or 500),
            memory_store_path=str(raw.get("memory_store_path") or ""),
            retrieval_enabled=bool(raw.get("retrieval_enabled_default_v1", False)),
            retrieval_max_records=int(raw.get("retrieval_max_records_v1") or 5),
            retrieval_min_obs=int(raw.get("retrieval_min_obs_v1") or DEFAULT_MIN_OBS),
            retrieval_min_win_rate=float(raw.get("retrieval_min_win_rate_v1") or DEFAULT_MIN_WIN_RATE),
            retrieval_allow_candidate=bool(raw.get("retrieval_allow_candidate_v1", False)),
            horizon_bars=int(raw.get("horizon_bars_v1") or 5),
            memory_vector_enabled=bool(raw.get("memory_vector_enabled_v1", False)),
            memory_vector_k_stm=int(raw.get("memory_vector_k_stm_v1") or 2),
            memory_vector_k_ltm=int(raw.get("memory_vector_k_ltm_v1") or 2),
            memory_vector_min_sim=float(raw.get("memory_vector_min_sim_v1") or 0.22),
            memory_vector_max_extra=int(raw.get("memory_vector_max_extra_v1") or 4),
            memory_embedding_backend=str(raw.get("memory_embedding_backend_v1") or "deterministic"),
            memory_embedding_dim=int(raw.get("memory_embedding_dim_v1") or 256),
            ollama_embeddings_model=str(raw.get("ollama_embeddings_model_v1") or "nomic-embed-text"),
            stm_ttl_hours=int(raw.get("stm_ttl_hours_v1") or 72),
        )

    def to_execution_config(self) -> dict[str, Any]:
        return {
            "schema": "finquant_agent_lab_config_v1",
            "agent_id": "finquant",
            "mode": "llm_v1" if self.use_llm else "deterministic_stub_v1",
            "use_llm_v1": self.use_llm,
            "llm_model_v1": self.llm_model,
            "ollama_base_url_v1": self.ollama_base_url,
            "llm_timeout_seconds_v1": self.llm_timeout_seconds,
            "llm_max_tokens_v1": self.llm_max_tokens,
            "memory_store_path": self.memory_store_path,
            "retrieval_enabled_default_v1": self.retrieval_enabled,
            "retrieval_max_records_v1": self.retrieval_max_records,
            "retrieval_min_obs_v1": self.retrieval_min_obs,
            "retrieval_min_win_rate_v1": self.retrieval_min_win_rate,
            "retrieval_allow_candidate_v1": self.retrieval_allow_candidate,
            "memory_vector_enabled_v1": self.memory_vector_enabled,
            "memory_vector_k_stm_v1": self.memory_vector_k_stm,
            "memory_vector_k_ltm_v1": self.memory_vector_k_ltm,
            "memory_vector_min_sim_v1": self.memory_vector_min_sim,
            "memory_vector_max_extra_v1": self.memory_vector_max_extra,
            "memory_embedding_backend_v1": self.memory_embedding_backend,
            "memory_embedding_dim_v1": self.memory_embedding_dim,
            "ollama_embeddings_model_v1": self.ollama_embeddings_model,
            "stm_ttl_hours_v1": self.stm_ttl_hours,
            "write_outputs_v1": False,
            "auto_promote_learning_v1": True,
        }


# ---------------------------------------------------------------------------
# Node: feature_extraction
# ---------------------------------------------------------------------------

def node_feature_extraction(state: RMState) -> dict[str, Any]:
    """Layer 1: Deterministic feature computation. No decisions."""
    from data_contracts import build_input_packet, detect_regime

    bars = state["bars"]
    if not bars:
        return {
            "features": {},
            "regime": "unknown",
            "current_bar": {},
            "error": "no_bars",
        }

    case = {
        "case_id": f"rm_{state['symbol']}_{int(time.time())}",
        "symbol": state["symbol"],
        "timeframe_minutes": state["timeframe_minutes"],
        "candles": bars,
        "decision_start_index": len(bars) - 1,
        "decision_end_index": len(bars) - 1,
        "hidden_future_start_index": len(bars),
    }

    cfg = state["config"]
    packet = build_input_packet(
        case=case,
        step_index=len(bars) - 1,
        visible_bars=bars,
        config=cfg,
        prior_records=[],
    )

    current_bar = bars[-1]
    close = float(current_bar.get("close", 0.0) or 0.0)
    atr = current_bar.get("atr_14")
    rsi = current_bar.get("rsi_14")
    atr_pct = (float(atr) / close) if (atr is not None and close > 0) else None

    regime = detect_regime(
        bars=bars,
        atr_pct=atr_pct,
        rsi=rsi,
        price_up=close > float((bars[-2] if len(bars) >= 2 else bars[-1]).get("close", close) or close),
    )

    return {
        "features": packet,
        "regime": regime,
        "current_bar": current_bar,
        "error": "",
    }


# ---------------------------------------------------------------------------
# Node: quality_retrieval
# ---------------------------------------------------------------------------

def node_quality_retrieval(state: RMState) -> dict[str, Any]:
    """Layer 1b: Quality-gated memory + optional STM/LTM vector similarity."""
    from context_builder import build_rich_context
    from retrieval import retrieve_eligible

    cfg = state["config"]
    store_path = cfg.get("memory_store_path")

    ctx_pkg = build_rich_context(
        bars=state["bars"],
        symbol=state["symbol"],
        timeframe_minutes=state["timeframe_minutes"],
        regime=state.get("regime") or "unknown",
        prior_records=[],
        n_trajectory=5,
    )
    narrative = str(ctx_pkg.get("narrative") or "")

    case = {
        "symbol": state["symbol"],
        "regime_v1": state.get("regime", "unknown"),
        "context_narrative_v1": narrative,
    }

    records, trace = retrieve_eligible(
        shared_store_path=store_path,
        case=case,
        config=cfg,
    )

    return {
        "prior_records": records,
        "retrieval_trace": trace,
        "context_narrative_v1": narrative,
    }


# ---------------------------------------------------------------------------
# Prime directive system prompt — embedded in every Qwen call
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are FinQuant, a disciplined quantitative crypto trading analyst.

PRIME DIRECTIVE (non-negotiable):
P-1 NEVER LIE. If you do not know, say INSUFFICIENT_DATA and stop. Fabricated confidence is worse than no answer.
P-2 REASON WITH TOOLS. Use the indicators, regime, and retrieved memory provided. Do not vibe-decide.
P-3 RISK-AVERSE DEFAULT. Default is NO_TRADE. Entries require confluence across multiple independent signals.
P-4 PATTERN SIMILARITY. Anchor judgment in retrieved prior cases that match the current regime signature.
P-5 CONTEXT FIRST. RSI=58 in bar 3 of a fresh uptrend is different from RSI=58 in bar 18 of an exhausted trend. Read trajectory before applying rules.
P-6 LONG-RUN MATH. Optimize dollars won minus dollars lost. Many small losses are acceptable if wins carry asymmetric R (target >= 2x stop).

RISK RULES:
R-001: Bounded risk — entries require a defined stop level. If you cannot define a stop, output NO_TRADE.
R-002: Two hypotheses required. State hypothesis_1 (your primary thesis) and hypothesis_2 (the counter-thesis) with numeric confidence [0,1]. If confidence_spread = confidence_1 - confidence_2 < 0.20, output INSUFFICIENT_DATA.
R-003: Every trade decision must include planned_r_multiple (target distance / stop distance). If R < 1.5, prefer NO_TRADE.

OUTPUT FORMAT (JSON only, no other text):
{
  "hypothesis_1": {"thesis": "<primary thesis>", "confidence": <0.0-1.0>, "evidence": ["<signal1>", "<signal2>"]},
  "hypothesis_2": {"thesis": "<counter thesis>", "confidence": <0.0-1.0>, "evidence": ["<counter1>", "<counter2>"]},
  "confidence_spread": <h1.confidence - h2.confidence>,
  "action": "ENTER_LONG" | "NO_TRADE" | "INSUFFICIENT_DATA",
  "thesis": "<2-sentence decision rationale>",
  "invalidation": "<what would make this wrong>",
  "planned_r_multiple": <target_distance / stop_distance or null>,
  "evidence_score": <0-10>,
  "memory_match": true | false
}"""


# ---------------------------------------------------------------------------
# Node: tot_reasoning (Tree of Thought)
# ---------------------------------------------------------------------------

_TOT_BRANCH_PROMPTS = {
    "bullish": """BRANCH: BULLISH — test the case for ENTER_LONG.

{context}

Instructions (follow P-1 through R-003):
1. Read the TRAJECTORY section first (P-5 — context first).
2. Identify all signals that support a long entry with confluence (P-3).
3. Define a stop level (R-001). If you cannot, action must be NO_TRADE.
4. Form hypothesis_1 (bullish case) and hypothesis_2 (counter — why this might fail).
5. If confidence_spread < 0.20, action = INSUFFICIENT_DATA (R-002).
6. Calculate planned_r_multiple = distance to target / distance to stop (R-003). If < 1.5, prefer NO_TRADE.
7. Score evidence_score 0-10 (10 = strong multi-signal confluence).

Respond in JSON only, no other text.""",

    "neutral": """BRANCH: NEUTRAL — test the case for NO_TRADE.

{context}

Instructions (follow P-1 through R-003):
1. Read the TRAJECTORY section first (P-5 — context first).
2. Identify all signals that argue for standing down (P-3 — default is NO_TRADE).
3. What confluence is missing that would be required for an entry?
4. Form hypothesis_1 (no-trade case) and hypothesis_2 (counter — why conditions might actually be good).
5. If confidence_spread < 0.20, action = INSUFFICIENT_DATA (R-002).
6. Score evidence_score 0-10 (10 = very clear case to stand down).

Respond in JSON only, no other text.""",

    "memory": """BRANCH: MEMORY-INFORMED — test whether retrieved validated patterns match current structure.

{context}

Instructions (follow P-1 through R-003, especially P-4):
1. Read the MEMORY section. Note regime match vs mismatch for each pattern.
2. Compare current TRAJECTORY with the trajectory described in retrieved patterns.
3. A memory match requires: same regime + similar RSI zone + similar ATR direction.
4. Form hypothesis_1 (memory supports entry) and hypothesis_2 (memory does not match or is insufficient).
5. If no memory retrieved, or regime mismatches dominate, action = NO_TRADE (P-4 requires evidence anchor).
6. If confidence_spread < 0.20, action = INSUFFICIENT_DATA (R-002).
7. Score evidence_score 0-10 based on quality and relevance of memory match.

Respond in JSON only, no other text.""",
}


def _build_prompt_context(state: RMState) -> str:
    """Build rich market context narrative using context_builder."""
    from context_builder import build_rich_context
    ctx = build_rich_context(
        bars=state["bars"],
        symbol=state["symbol"],
        timeframe_minutes=state["timeframe_minutes"],
        regime=state.get("regime") or "unknown",
        prior_records=state.get("prior_records") or [],
        n_trajectory=5,
    )
    return ctx["narrative"]


def _call_ollama_tot(
    base_url: str,
    model: str,
    prompt: str,
    timeout: int,
) -> dict[str, Any] | None:
    """Call Ollama for one ToT branch. Returns parsed dict or None on failure."""
    try:
        from llm_adapter import call_ollama
        result = call_ollama(
            base_url=base_url,
            model=model,
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            timeout_seconds=timeout,
            max_tokens=500,
        )
        if not result.success:
            return None
        raw = result.raw_output.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(raw[start:end])
            # Enforce R-002: if confidence_spread < 0.20 or missing, set INSUFFICIENT_DATA
            h1_conf = float((parsed.get("hypothesis_1") or {}).get("confidence") or 0.0)
            h2_conf = float((parsed.get("hypothesis_2") or {}).get("confidence") or 0.0)
            spread = h1_conf - h2_conf
            parsed["confidence_spread"] = round(spread, 4)
            if spread < 0.20 and parsed.get("action") not in ("NO_TRADE", "INSUFFICIENT_DATA"):
                parsed["action"] = "INSUFFICIENT_DATA"
                parsed["thesis"] = f"[R-002] Confidence spread {spread:.2f} < 0.20 — insufficient evidence to decide. {parsed.get('thesis','')}"
            return parsed
        return None
    except Exception:
        return None


def _rule_branch_bullish(state: RMState) -> dict[str, Any]:
    """Rule-based bullish branch (fallback when no LLM)."""
    bar = state.get("current_bar") or {}
    bars = state["bars"]
    prev = bars[-2] if len(bars) >= 2 else bar
    close = float(bar.get("close", 0.0) or 0.0)
    rsi = bar.get("rsi_14")
    atr = bar.get("atr_14")
    ema = bar.get("ema_20")
    ref = close if close > 0 else 1.0
    atr_pct = float(atr) / ref if atr is not None else 0.0
    price_up = close > float(prev.get("close", close) or close)
    rsi_ok = rsi is not None and 50 < rsi < 70
    vol_expand = float(bar.get("volume", 0) or 0) > float(prev.get("volume", 0) or 0)
    atr_expand = atr_pct > _ATR_EXPAND_PCT
    price_above_ema = ema is not None and close > float(ema)

    score = 0
    supports = []
    if price_up:
        score += 2; supports.append("price_rising")
    if rsi_ok:
        score += 2; supports.append(f"RSI={rsi:.1f} in 50-70")
    if vol_expand:
        score += 2; supports.append("volume_expanding")
    if atr_expand:
        score += 2; supports.append(f"ATR%={atr_pct*100:.2f}>0.60%")
    if price_above_ema:
        score += 2; supports.append("price_above_EMA")

    action = "ENTER_LONG" if score >= 6 else "NO_TRADE"
    return {
        "branch": "bullish",
        "action": action,
        "thesis": f"Rule analysis: {len(supports)} bullish signals present. {'Strong entry conditions.' if score >= 6 else 'Insufficient signals for entry.'}",
        "invalidation": f"Exit if price drops below {close * 0.995:.4f} or RSI falls under 45.",
        "evidence_score": score,
        "key_supports": supports,
        "source": "rule",
    }


def _rule_branch_neutral(state: RMState) -> dict[str, Any]:
    """Rule-based neutral branch."""
    bar = state.get("current_bar") or {}
    bars = state["bars"]
    prev = bars[-2] if len(bars) >= 2 else bar
    close = float(bar.get("close", 0.0) or 0.0)
    rsi = bar.get("rsi_14")
    atr = bar.get("atr_14")
    ref = close if close > 0 else 1.0
    atr_pct = float(atr) / ref if atr is not None else 0.0
    price_up = close > float(prev.get("close", close) or close)
    rsi_ok = rsi is not None and 50 < rsi < 70

    missing = []
    if not price_up: missing.append("price_not_rising")
    if not rsi_ok: missing.append(f"RSI={rsi:.1f} outside 50-70" if rsi else "RSI_unknown")
    if atr_pct < _ATR_EXPAND_PCT: missing.append(f"ATR%={atr_pct*100:.2f} below threshold")

    score = min(10, len(missing) * 3)
    return {
        "branch": "neutral",
        "action": "NO_TRADE",
        "thesis": f"Standing down: {len(missing)} conditions not met. Edge not sufficient.",
        "invalidation": "Entry valid when price rises, RSI 50–70, ATR% > 0.60%.",
        "evidence_score": score,
        "key_supports": missing,
        "source": "rule",
    }


def _rule_branch_memory(state: RMState) -> dict[str, Any]:
    """Rule-based memory branch."""
    prior = state.get("prior_records") or []
    if not prior:
        return {
            "branch": "memory",
            "action": "NO_TRADE",
            "thesis": "No validated patterns available. Memory branch abstains.",
            "invalidation": "Build pattern history first.",
            "evidence_score": 0,
            "memory_match": False,
            "source": "rule",
        }

    bar = state.get("current_bar") or {}
    bars = state["bars"]
    prev = bars[-2] if len(bars) >= 2 else bar
    close = float(bar.get("close", 0.0) or 0.0)
    rsi = bar.get("rsi_14")
    atr = bar.get("atr_14")
    ema = bar.get("ema_20")
    ref = close if close > 0 else 1.0
    atr_pct = float(atr) / ref if atr is not None else 0.0
    price_up = close > float(prev.get("close", close) or close)
    price_above_ema = ema is not None and close > float(ema)

    long_records = [r for r in prior if r.get("entry_action_v1") == "ENTER_LONG"]
    avg_wr = (sum(float(r.get("pattern_win_rate_v1") or 0) for r in long_records) / len(long_records)) if long_records else 0.0

    near_threshold = (
        price_up and price_above_ema
        and rsi is not None and rsi >= 52
        and atr_pct >= _ATR_NEAR_PCT
        and float(bar.get("volume", 0) or 0) >= float(prev.get("volume", 0) or 0) * 1.01
    )

    if long_records and near_threshold and avg_wr >= 0.55:
        score = min(10, int(avg_wr * 8) + 2)
        return {
            "branch": "memory",
            "action": "ENTER_LONG",
            "thesis": f"Memory: {len(long_records)} validated long pattern(s) with avg win_rate={avg_wr:.0%}. Near-threshold conditions met.",
            "invalidation": f"Exit if close < {close * 0.995:.4f} or memory thesis contradicted.",
            "evidence_score": score,
            "memory_match": True,
            "source": "rule",
        }

    return {
        "branch": "memory",
        "action": "NO_TRADE",
        "thesis": f"Memory: {len(long_records)} long pattern(s) available but near-threshold conditions not fully met.",
        "invalidation": "Wait for price_up + RSI >= 52 + ATR >= 0.30% + volume >= prior.",
        "evidence_score": 2,
        "memory_match": False,
        "source": "rule",
    }


def node_tot_reasoning(state: RMState) -> dict[str, Any]:
    """
    Layer 2: Tree of Thought reasoning.

    Generates 3 branches (bullish, neutral, memory-informed).
    Uses Qwen if available; falls back to deterministic rules.
    Selects winning branch by evidence_score.
    """
    cfg = state["config"]
    use_llm = bool(cfg.get("use_llm_v1", False))
    base_url = str(cfg.get("ollama_base_url_v1") or "http://172.20.2.230:11434")
    model = str(cfg.get("llm_model_v1") or "qwen2.5:7b")
    timeout = int(cfg.get("llm_timeout_seconds_v1") or 30)

    branches = []

    if use_llm:
        context = _build_prompt_context(state)
        for branch_name, prompt_tpl in _TOT_BRANCH_PROMPTS.items():
            prompt = prompt_tpl.format(context=context)
            result = _call_ollama_tot(base_url, model, prompt, timeout)
            if result:
                result["branch"] = branch_name
                result["source"] = "llm"
                branches.append(result)

    # Fill missing branches with rule-based fallback
    branch_names_got = {b.get("branch") for b in branches}
    if "bullish" not in branch_names_got:
        branches.append(_rule_branch_bullish(state))
    if "neutral" not in branch_names_got:
        branches.append(_rule_branch_neutral(state))
    if "memory" not in branch_names_got:
        branches.append(_rule_branch_memory(state))

    # Select winner: highest evidence_score; tie-break favors memory then bullish
    priority = {"memory": 0, "bullish": 1, "neutral": 2}
    winner = max(
        branches,
        key=lambda b: (float(b.get("evidence_score") or 0), -priority.get(b.get("branch", "neutral"), 9))
    )

    # Determine overall source
    any_llm = any(b.get("source") == "llm" for b in branches)
    winner_src = winner.get("source", "rule")
    if any_llm and winner_src == "llm":
        overall_source = "llm_tot"
    elif any_llm:
        overall_source = "hybrid"
    elif (state.get("prior_records") or []) and winner.get("branch") == "memory":
        overall_source = "hybrid"
    else:
        overall_source = "rule"

    # Map evidence_score to confidence (0–10 → 0–1)
    raw_score = float(winner.get("evidence_score") or 0)
    confidence = round(min(1.0, raw_score / 10.0), 4)

    return {
        "tot_branches": branches,
        "tot_winner": winner,
        "final_action": str(winner.get("action") or "NO_TRADE"),
        "final_confidence": confidence,
        "final_thesis": str(winner.get("thesis") or ""),
        "final_invalidation": str(winner.get("invalidation") or ""),
        "final_source": overall_source,
        "guard_reason": "",
    }


# ---------------------------------------------------------------------------
# Node: guard_rails
# ---------------------------------------------------------------------------

def node_guard_rails(state: RMState) -> dict[str, Any]:
    """
    Layer 3: Deterministic guard rails — veto unsafe proposals.

    Risk management: block entries that violate ATR/RSI/confidence thresholds.
    Per guidance: losses can exceed win count IF wins are financially larger.
    These guards protect the expectancy calculation.
    """
    bar = state.get("current_bar") or {}
    proposed = state.get("final_action") or "NO_TRADE"
    confidence = float(state.get("final_confidence") or 0.0)
    regime = state.get("regime") or "unknown"

    rsi = bar.get("rsi_14")
    atr = bar.get("atr_14")
    close = float(bar.get("close", 0.0) or 0.0)
    ref = close if close > 0 else 1.0
    atr_pct = float(atr) / ref if atr is not None else None

    guard_reason = ""

    if proposed in ("ENTER_LONG", "ENTER_SHORT"):
        # Block genuine chop
        if atr_pct is not None and atr_pct < _ATR_CHOP_PCT:
            guard_reason = f"guard:chop ATR%={atr_pct*100:.3f}% < {_ATR_CHOP_PCT*100:.2f}%"

        # Block long in bad RSI
        elif proposed == "ENTER_LONG":
            if rsi is not None and rsi < _RSI_LONG_MIN:
                guard_reason = f"guard:rsi_too_low RSI={rsi:.1f} < {_RSI_LONG_MIN}"
            elif rsi is not None and rsi > _RSI_LONG_MAX:
                guard_reason = f"guard:rsi_overbought RSI={rsi:.1f} > {_RSI_LONG_MAX}"

        # Block short in uptrend
        elif proposed == "ENTER_SHORT" and regime == "trending_up":
            guard_reason = f"guard:short_in_uptrend regime={regime}"

        # Block low confidence entries — protects positive expectancy
        if not guard_reason and confidence < _MIN_CONFIDENCE:
            guard_reason = f"guard:low_confidence {confidence:.2f} < {_MIN_CONFIDENCE}"

        # R-003 CORE OVERRIDE: block entries without valid R-multiple >= MIN_R
        # This is non-negotiable — if risk geometry cannot be computed, no entry.
        if not guard_reason:
            tot_winner = state.get("tot_winner") or {}
            r_mult = tot_winner.get("planned_r_multiple")
            # Also check from final fields if tot_winner not set
            if r_mult is None:
                r_mult = state.get("planned_r_multiple_v1")
            if r_mult is not None:
                try:
                    if float(r_mult) < _MIN_R_MULTIPLE:
                        guard_reason = f"guard:r_too_low R={float(r_mult):.2f} < {_MIN_R_MULTIPLE} (stop={STOP_ATR_MULT}xATR, target={TARGET_ATR_MULT}xATR required)"
                except (TypeError, ValueError):
                    pass

    if guard_reason:
        return {
            "final_action": "NO_TRADE",
            "final_source": "guard_vetoed",
            "final_thesis": f"[VETOED: {guard_reason}] {state.get('final_thesis', '')}",
            "guard_reason": guard_reason,
        }

    return {"guard_reason": ""}


# ---------------------------------------------------------------------------
# Build LangGraph pipeline
# ---------------------------------------------------------------------------

def _build_graph():
    """Build and compile the LangGraph StateGraph for RMv2."""
    from langgraph.graph import StateGraph, END

    graph = StateGraph(RMState)

    graph.add_node("feature_extraction", node_feature_extraction)
    graph.add_node("quality_retrieval", node_quality_retrieval)
    graph.add_node("tot_reasoning", node_tot_reasoning)
    graph.add_node("guard_rails", node_guard_rails)

    graph.set_entry_point("feature_extraction")
    graph.add_edge("feature_extraction", "quality_retrieval")
    graph.add_edge("quality_retrieval", "tot_reasoning")
    graph.add_edge("tot_reasoning", "guard_rails")
    graph.add_edge("guard_rails", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Reasoning Module — public interface
# ---------------------------------------------------------------------------

class ReasoningModule:
    """
    RMv2 — self-contained pluggable reasoning module.

    Built on LangGraph + Tree of Thought.
    Instantiate once; call decide() for each market observation.
    """

    def __init__(
        self,
        config: RMConfig | None = None,
        config_path: str | None = None,
    ) -> None:
        if config is not None:
            self.config = config
        elif config_path is not None:
            self.config = RMConfig.from_file(config_path)
        else:
            self.config = RMConfig()

        self._graph = _build_graph()

    def decide(
        self,
        bars: list[dict[str, Any]],
        symbol: str,
        timeframe_minutes: int = 15,
        position_open: bool = False,
        entry_price: float | None = None,
    ) -> RMDecision:
        """
        Main decision entry point.

        bars: list of OHLCV dicts with rsi_14, ema_20, atr_14 pre-computed.
              Minimum 2 bars required; 20+ recommended for full context.
        """
        t0 = time.monotonic()

        if not bars:
            return RMDecision(
                action="NO_TRADE", confidence=0.0,
                thesis="No bars provided.", invalidation="N/A",
                source="rule", regime="unknown", latency_ms=0,
                context_narrative_v1="",
            )

        initial_state: RMState = {
            "bars": bars,
            "symbol": symbol,
            "timeframe_minutes": timeframe_minutes,
            "position_open": position_open,
            "entry_price": entry_price,
            "config": self.config.to_execution_config(),
            "features": {},
            "regime": "unknown",
            "current_bar": {},
            "prior_records": [],
            "retrieval_trace": [],
            "tot_branches": [],
            "tot_winner": {},
            "final_action": "NO_TRADE",
            "final_confidence": 0.0,
            "final_thesis": "",
            "final_invalidation": "",
            "final_source": "rule",
            "guard_reason": "",
            "latency_ms": 0,
            "error": "",
            "context_narrative_v1": "",
        }

        try:
            final_state = self._graph.invoke(initial_state)
        except Exception as exc:
            return RMDecision(
                action="NO_TRADE", confidence=0.0,
                thesis=f"Graph error: {exc}", invalidation="N/A",
                source="rule", regime="unknown", latency_ms=0,
                context_narrative_v1="",
            )

        latency_ms = int((time.monotonic() - t0) * 1000)

        prior = final_state.get("prior_records") or []
        mem_quality = {
            "records_retrieved": len(prior),
            "min_obs_required": self.config.retrieval_min_obs,
            "min_win_rate_required": self.config.retrieval_min_win_rate,
            "avg_win_rate": round(
                sum(float(r.get("pattern_win_rate_v1") or 0) for r in prior) / max(len(prior), 1), 4
            ) if prior else 0.0,
        }

        action = str(final_state.get("final_action") or "NO_TRADE")
        regime = str(final_state.get("regime") or "unknown")
        current_bar = final_state.get("current_bar") or {}

        # ── Compute risk context from the same context already built ─────
        from risk_context import compute_risk_context, risk_context_summary
        import datetime as _dt
        ctx_mctx = (final_state.get("features") or {}).get("market_context_v1") or {}
        risk_ctx = compute_risk_context(
            atr_pct=ctx_mctx.get("atr_pct_v1"),
            regime=regime,
            swing_structure=None,  # will be added when swing detector is built
            confidence_spread=float(final_state.get("final_confidence") or 0.0) * 2,  # proxy
            utc_hour=_dt.datetime.now(_dt.timezone.utc).hour,
            pattern_win_rate=mem_quality["avg_win_rate"] if mem_quality["avg_win_rate"] > 0 else None,
            recent_losses=0,   # updated by live loop after falsification
            recent_wins=0,
            action=action,
        )

        return RMDecision(
            action=action,
            confidence=float(final_state.get("final_confidence") or 0.0),
            thesis=str(final_state.get("final_thesis") or ""),
            invalidation=str(final_state.get("final_invalidation") or ""),
            source=str(final_state.get("final_source") or "rule"),
            regime=regime,
            memory_used=[str(r.get("record_id") or "") for r in prior],
            memory_quality=mem_quality,
            tot_branches=final_state.get("tot_branches") or [],
            guard_reason=str(final_state.get("guard_reason") or ""),
            latency_ms=latency_ms,
            risk_pct=risk_ctx["final_risk_pct"],
            risk_context=risk_ctx,
            context_narrative_v1=str(final_state.get("context_narrative_v1") or ""),
        )


# ---------------------------------------------------------------------------
# Guard rails standalone (used by tests)
# ---------------------------------------------------------------------------

def apply_guard_rails(
    proposed: str,
    confidence: float,
    bar: dict[str, Any],
    regime: str,
) -> tuple[str, str]:
    """Standalone guard rail check for testing."""
    rsi = bar.get("rsi_14")
    atr = bar.get("atr_14")
    close = float(bar.get("close", 0.0) or 0.0)
    ref = close if close > 0 else 1.0
    atr_pct = float(atr) / ref if atr is not None else None

    if proposed in ("ENTER_LONG", "ENTER_SHORT"):
        if atr_pct is not None and atr_pct < _ATR_CHOP_PCT:
            return "NO_TRADE", f"guard:chop ATR%={atr_pct*100:.3f}% < {_ATR_CHOP_PCT*100:.2f}%"
        if proposed == "ENTER_LONG":
            if rsi is not None and rsi < _RSI_LONG_MIN:
                return "NO_TRADE", f"guard:rsi_too_low RSI={rsi:.1f} < {_RSI_LONG_MIN}"
            if rsi is not None and rsi > _RSI_LONG_MAX:
                return "NO_TRADE", f"guard:rsi_overbought RSI={rsi:.1f} > {_RSI_LONG_MAX}"
        if proposed == "ENTER_SHORT" and regime == "trending_up":
            return "NO_TRADE", f"guard:short_in_uptrend regime={regime}"
        if confidence < _MIN_CONFIDENCE:
            return "NO_TRADE", f"guard:low_confidence {confidence:.2f} < {_MIN_CONFIDENCE}"

    return proposed, ""


def compute_r_multiple(close: float, atr: float | None, action: str) -> float | None:
    """R-003 CORE: compute R-multiple. Returns 2.5 at policy multiples, None if ATR missing."""
    if atr is None or float(atr) <= 0 or float(close) <= 0:
        return None
    return round(TARGET_ATR_MULT / STOP_ATR_MULT, 4)


def compute_stop_target(close: float, atr: float, action: str) -> tuple[float, float]:
    """Compute (stop_price, target_price) for R-003 compliance."""
    atr_f = float(atr)
    close_f = float(close)
    if action == "ENTER_LONG":
        return round(close_f - STOP_ATR_MULT * atr_f, 6), round(close_f + TARGET_ATR_MULT * atr_f, 6)
    return round(close_f + STOP_ATR_MULT * atr_f, 6), round(close_f - TARGET_ATR_MULT * atr_f, 6)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _trend_bars(n: int = 22, atr_pct: float = 0.012) -> list[dict]:
    bars = []
    price = 100.0
    for i in range(n):
        price += 0.8 + i * 0.02
        bars.append({
            "timestamp": f"2024-01-01T{i:02d}:00:00Z",
            "open": price - 0.3, "high": price + 1.2,
            "low": price - 1.0, "close": price,
            "volume": 1200 + i * 80,
            "rsi_14": min(68.0, 52.0 + i * 0.7),
            "ema_20": price * 0.98,
            "atr_14": price * atr_pct,
        })
    return bars


def run_self_test() -> None:
    print("=" * 60)
    print("RMv2 Self-Test (LangGraph + Tree of Thought, no LLM)")
    print("=" * 60)

    rm = ReasoningModule(config=RMConfig(use_llm=False, retrieval_enabled=False))

    # Test 1: trending bars
    d = rm.decide(bars=_trend_bars(22), symbol="SOL-PERP")
    print(f"\nTest 1 (trending, ATR=1.2%):  action={d.action}  confidence={d.confidence:.2f}  regime={d.regime}  source={d.source}")
    assert d.action in ("ENTER_LONG", "NO_TRADE")
    assert d.regime in ("trending_up", "trending_down", "ranging", "volatile", "unknown")
    assert isinstance(d.tot_branches, list) and len(d.tot_branches) == 3
    print(f"  ToT branches: {[b['branch'] + '→' + b['action'] + '(' + str(b['evidence_score']) + ')' for b in d.tot_branches]}")
    print(f"  Winner: {d.tot_branches and max(d.tot_branches, key=lambda b: b.get('evidence_score', 0)).get('branch')}")
    print(f"  thesis: {d.thesis[:80]}")

    # Test 2: chop (ATR 0.08%) → guard veto → NO_TRADE
    bars_chop = []
    price = 100.0
    for i in range(22):
        price += 0.02 if i % 2 == 0 else -0.02
        bars_chop.append({
            "open": price, "high": price + 0.02, "low": price - 0.02, "close": price,
            "volume": 200 + i, "rsi_14": 50.0, "ema_20": 100.0,
            "atr_14": price * 0.0008, "timestamp": f"2024-01-02T{i:02d}:00:00Z",
        })
    d2 = rm.decide(bars=bars_chop, symbol="SOL-PERP")
    print(f"\nTest 2 (chop, ATR=0.08%):  action={d2.action}  guard={d2.guard_reason}")
    assert d2.action == "NO_TRADE", f"Expected NO_TRADE got {d2.action}"

    # Test 3: overbought RSI guard
    bars_ob = _trend_bars(22)
    for b in bars_ob:
        b["rsi_14"] = 78.0
    d3 = rm.decide(bars=bars_ob, symbol="SOL-PERP")
    print(f"\nTest 3 (overbought RSI=78):  action={d3.action}  guard={d3.guard_reason}")
    assert d3.action == "NO_TRADE"
    assert "overbought" in d3.guard_reason

    # Test 4: empty bars → graceful NO_TRADE
    d4 = rm.decide(bars=[], symbol="SOL-PERP")
    print(f"\nTest 4 (empty bars):  action={d4.action}")
    assert d4.action == "NO_TRADE"

    # Test 5: decision is a valid RMDecision
    assert d.to_dict()["schema"] == "rm_decision_v2"
    print(f"\nTest 5 (output contract):  schema=rm_decision_v2 ✓")

    print(f"\n{'='*60}")
    print("All self-tests PASSED")
    print(f"{'='*60}")


def run_llm_test() -> None:
    """Test with real Qwen via Ollama at 172.20.2.230:11434."""
    print("=" * 60)
    print("RMv2 LLM Test (Qwen 7B via Ollama)")
    print("=" * 60)

    rm = ReasoningModule(config=RMConfig(
        use_llm=True,
        ollama_base_url="http://172.20.2.230:11434",
        llm_model="qwen2.5:7b",
        retrieval_enabled=False,
    ))

    bars = _trend_bars(22)
    print("\nRunning decide() with LLM...")
    d = rm.decide(bars=bars, symbol="SOL-PERP")

    print(f"  action={d.action}  confidence={d.confidence:.2f}  source={d.source}")
    print(f"  regime={d.regime}  latency={d.latency_ms}ms")
    print(f"  ToT branches ({len(d.tot_branches)}):")
    for b in d.tot_branches:
        print(f"    [{b.get('branch')}] action={b.get('action')} score={b.get('evidence_score')} source={b.get('source')}")
    print(f"  thesis: {d.thesis[:120]}")
    if d.guard_reason:
        print(f"  guard: {d.guard_reason}")

    assert d.action in ("ENTER_LONG", "NO_TRADE", "HOLD", "EXIT")
    print("\nLLM test PASSED")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RMv2 — FinQuant Reasoning Module v2")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--llm-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
    elif args.llm_test:
        run_llm_test()
    else:
        print("RMv2 ready. Use --self-test or --llm-test, or import ReasoningModule.")


if __name__ == "__main__":
    main()
