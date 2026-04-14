"""
diagnostic_risk_pipeline.py — read-only risk choke-point analysis (DV risk diagnostic).

Same replay loop as replay_runner; records fusion directional inputs vs risk outcomes only.
Does not modify risk, fusion, or signals.
"""

from __future__ import annotations

import io
import statistics
import sys
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from renaissance_v4.core.feature_engine import build_feature_set
from renaissance_v4.core.fusion_engine import fuse_signal_results
from renaissance_v4.core.market_state_builder import build_market_state
from renaissance_v4.core.regime_classifier import classify_regime
from renaissance_v4.core.risk_governor import (
    PROBE_SIZE_FUSION_MIN,
    evaluate_risk,
)
from renaissance_v4.signals.breakout_expansion import BreakoutExpansionSignal
from renaissance_v4.signals.mean_reversion_fade import MeanReversionFadeSignal
from renaissance_v4.signals.pullback_continuation import PullbackContinuationSignal
from renaissance_v4.signals.trend_continuation import TrendContinuationSignal
from renaissance_v4.utils.db import get_connection

MIN_ROWS_REQUIRED = 50
_REPORT_DEFAULT = Path(__file__).resolve().parent.parent / "reports" / "diagnostic_risk_v1.md"


def _signal_family(signal_name: str) -> str:
    if signal_name in {"trend_continuation", "pullback_continuation"}:
        return "trend_family"
    if signal_name == "breakout_expansion":
        return "breakout_family"
    if signal_name == "mean_reversion_fade":
        return "mean_reversion_family"
    return "other"


def _families_from_fusion(fr) -> list[str]:
    """contributing_signals entries look like 'mean_reversion_fade:long:0.1234'."""
    out: list[str] = []
    for entry in fr.contributing_signals or []:
        name = str(entry).split(":")[0].strip()
        if name:
            out.append(_signal_family(name))
    return out if out else ["(none)"]


def _eff_bucket(es: float) -> str:
    """Ordered buckets; probe floor may be < 0.25 — avoid inverted ranges."""
    p = float(PROBE_SIZE_FUSION_MIN)
    if es < 0:
        return "<0"
    if es < p:
        return f"[0, {p})"
    if es < 0.25:
        return f"[{p}, 0.25)"
    if es < 0.45:
        return "[0.25, 0.45)"
    if es < 0.55:
        return "[0.45, 0.55)"
    return ">=0.55"


def run_risk_diagnostic() -> dict:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT symbol, open_time, open, high, low, close, volume
        FROM market_bars_5m
        ORDER BY open_time ASC
        """
    ).fetchall()
    if len(rows) < MIN_ROWS_REQUIRED:
        raise RuntimeError(f"need >= {MIN_ROWS_REQUIRED} bars")

    signals = [
        TrendContinuationSignal(),
        PullbackContinuationSignal(),
        BreakoutExpansionSignal(),
        MeanReversionFadeSignal(),
    ]
    buf = io.StringIO()

    fusion_long = fusion_short = 0
    directional_allowed = 0
    directional_blocked = 0

    veto_counts: Counter[str] = Counter()
    regime_blocked: Counter[str] = Counter()
    family_blocked: Counter[str] = Counter()

    fusion_scores_dir: list[float] = []
    compression_dir: list[float] = []
    effective_dir: list[float] = []

    eff_blocked: list[float] = []
    eff_allowed: list[float] = []

    eff_hist_all: Counter[str] = Counter()

    steps = 0
    expected = max(0, len(rows) - MIN_ROWS_REQUIRED + 1)

    for _index in range(MIN_ROWS_REQUIRED, len(rows) + 1):
        window = rows[:_index]
        with redirect_stdout(buf):
            state = build_market_state(window)
            features = build_feature_set(state)
            regime = classify_regime(features)
            srs = [s.evaluate(state, features, regime) for s in signals]
            fusion_result = fuse_signal_results(srs)

        active_signal_names = [r.signal_name for r in srs if r.active]

        if fusion_result.direction == "long":
            fusion_long += 1
        elif fusion_result.direction == "short":
            fusion_short += 1
        else:
            steps += 1
            if steps % 25000 == 0:
                print(f"[diagnostic_risk] progress steps={steps}/{expected}", file=sys.stderr)
            continue

        with redirect_stdout(buf):
            risk_decision = evaluate_risk(
                fusion_result=fusion_result,
                features=features,
                regime=regime,
                drawdown_proxy=0.0,
                active_signal_names=active_signal_names,
            )

        fs = float(fusion_result.fusion_score)
        cf = float(risk_decision.compression_factor)
        es = float(risk_decision.debug_trace.get("effective_score", fs * cf))

        fusion_scores_dir.append(fs)
        compression_dir.append(cf)
        effective_dir.append(es)
        eff_hist_all[_eff_bucket(es)] += 1

        if risk_decision.allowed:
            directional_allowed += 1
            eff_allowed.append(es)
        else:
            directional_blocked += 1
            eff_blocked.append(es)
            regime_blocked[regime] += 1
            for fam in set(_families_from_fusion(fusion_result)):
                family_blocked[fam] += 1
            for vr in risk_decision.veto_reasons or []:
                veto_counts[str(vr)] += 1

        steps += 1
        if steps % 25000 == 0:
            print(f"[diagnostic_risk] progress steps={steps}/{expected}", file=sys.stderr)

    directional_total = fusion_long + fusion_short

    def _avg(xs: list[float]) -> float:
        return float(statistics.mean(xs)) if xs else 0.0

    dominant_veto = veto_counts.most_common(1)
    dom_reason = dominant_veto[0][0] if dominant_veto else "n/a"
    dom_n = dominant_veto[0][1] if dominant_veto else 0
    pct_dom = 100.0 * float(dom_n) / float(sum(veto_counts.values())) if veto_counts else 0.0

    return {
        "dataset_bars": len(rows),
        "decision_steps": expected,
        "fusion_long": fusion_long,
        "fusion_short": fusion_short,
        "directional_total": directional_total,
        "directional_allowed": directional_allowed,
        "directional_blocked": directional_blocked,
        "veto_ranked": veto_counts.most_common(),
        "regime_blocked": dict(regime_blocked.most_common()),
        "family_blocked": dict(family_blocked.most_common()),
        "avg_fusion_score_directional": _avg(fusion_scores_dir),
        "avg_compression_directional": _avg(compression_dir),
        "avg_effective_directional": _avg(effective_dir),
        "avg_effective_blocked": _avg(eff_blocked),
        "avg_effective_allowed": _avg(eff_allowed),
        "effective_hist_directional": dict(eff_hist_all),
        "probe_floor": PROBE_SIZE_FUSION_MIN,
        "dominant_veto": dom_reason,
        "dominant_veto_count": dom_n,
        "dominant_veto_pct_of_veto_events": pct_dom,
        "total_veto_events": sum(veto_counts.values()),
    }


def write_report(path: Path | None = None) -> Path:
    stats = run_risk_diagnostic()
    out = path or _REPORT_DEFAULT
    out.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    dtot = stats["directional_total"]
    allowed = stats["directional_allowed"]
    blocked = stats["directional_blocked"]
    dom = stats["dominant_veto"]
    dom_n = stats["dominant_veto_count"]
    pct_v = stats["dominant_veto_pct_of_veto_events"]
    tv = stats["total_veto_events"]

    pct_blk = 100.0 * float(blocked) / float(dtot) if dtot else 0.0
    pct_allow = 100.0 * float(allowed) / float(dtot) if dtot else 0.0

    # Root cause sentence (explicit)
    root = (
        f"The system is alive at fusion, but risk blocks **{blocked}** of **{dtot}** directional fused bars "
        f"(`{pct_blk:.2f}%`). The dominant veto tag (counted per veto line when multiple apply) is "
        f"**`{dom}`** ({dom_n} occurrences, **{pct_v:.1f}%** of {tv} total veto line events). "
        f"Average effective score on blocked directional bars is **{stats['avg_effective_blocked']:.6f}** vs probe floor **{stats['probe_floor']}**."
    )

    lines = [
        "# RenaissanceV4 — Risk governor diagnostic v1 (read-only)",
        "",
        f"Generated: **{now}** · `renaissance_v4/research/diagnostic_risk_pipeline.py`",
        "",
        "No risk thresholds, compression constants, or other logic were modified. This pass only observes ",
        "`fuse_signal_results` → `evaluate_risk` on the full bar history.",
        "",
        "## 7.1 Directional fusion population (input to risk)",
        "",
        f"- **Fusion `long`:** {stats['fusion_long']}",
        f"- **Fusion `short`:** {stats['fusion_short']}",
        f"- **Total directional (`long` + `short`):** {dtot}",
        "",
        "## 7.2 Risk allow vs block (directional inputs only)",
        "",
        f"- **Allowed:** {allowed} (`{pct_allow:.4f}%` of directional bars)",
        f"- **Blocked:** {blocked} (`{pct_blk:.4f}%` of directional bars)",
        "",
        "### Blocked — veto reason frequency",
        "",
        "Each veto string from `RiskDecision.veto_reasons` is counted (a single bar may contribute multiple reasons).",
        "",
        "| Rank | Veto reason | Count |",
        "|------|-------------|-------|",
    ]

    for i, (reason, cnt) in enumerate(stats["veto_ranked"], start=1):
        lines.append(f"| {i} | `{reason}` | {cnt} |")

    lines.extend(
        [
            "",
            "## 7.3 Compression path (directional fused outcomes only)",
            "",
            f"- **Probe / minimum tier floor (`effective_score`):** `{stats['probe_floor']}` (see `risk_governor.PROBE_SIZE_FUSION_MIN`)",
            f"- **Average raw `fusion_score` (pre-risk):** {stats['avg_fusion_score_directional']:.8f}",
            f"- **Average `compression_factor` (post-regime/vol/persistence chain):** {stats['avg_compression_directional']:.8f}",
            f"- **Average `effective_score` (`fusion_score × compression_factor`):** {stats['avg_effective_directional']:.8f}",
            f"- **Average effective score when blocked:** {stats['avg_effective_blocked']:.8f}",
            f"- **Average effective score when allowed:** {stats['avg_effective_allowed']:.8f}",
            "",
            "### Distribution of `effective_score` (directional bars)",
            "",
            "| Bucket | Count |",
            "|--------|-------|",
        ]
    )

    pf = stats["probe_floor"]
    bucket_order = [
        "<0",
        f"[0, {pf})",
        f"[{pf}, 0.25)",
        "[0.25, 0.45)",
        "[0.45, 0.55)",
        ">=0.55",
    ]
    for bucket in bucket_order:
        c = stats["effective_hist_directional"].get(bucket, 0)
        lines.append(f"| {bucket} | {c} |")

    lines.extend(
        [
            "",
            "## 7.4 Regime interaction (blocked directional only)",
            "",
            "| Regime | Blocked count |",
            "|--------|----------------|",
        ]
    )
    for reg, cnt in sorted(stats["regime_blocked"].items(), key=lambda x: -x[1]):
        lines.append(f"| `{reg}` | {cnt} |")

    lines.extend(
        [
            "",
            "## 7.5 Signal-family interaction (blocked directional only)",
            "",
            "Counts by coarse family derived from `FusionResult.contributing_signals` (a bar may increment multiple families).",
            "",
            "| Family | Count |",
            "|--------|-------|",
        ]
    )
    for fam, cnt in sorted(stats["family_blocked"].items(), key=lambda x: -x[1]):
        lines.append(f"| `{fam}` | {cnt} |")

    lines.extend(
        [
            "",
            "## Dominant root cause (explicit)",
            "",
            f"> {root}",
            "",
            "## Reproduce",
            "",
            "```bash",
            "cd /path/to/blackbox",
            "export PYTHONPATH=.",
            "python3 -m renaissance_v4.research.diagnostic_risk_pipeline",
            "```",
            "",
            "Default output: `renaissance_v4/reports/diagnostic_risk_v1.md`",
            "",
        ]
    )

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[diagnostic_risk_pipeline] Wrote {out.resolve()}")
    return out


def main() -> None:
    write_report()


if __name__ == "__main__":
    main()
