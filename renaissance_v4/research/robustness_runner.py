"""
Orchestrate: deterministic replay → trade export → Monte Carlo → baseline comparison → reports.

Does not modify locked baseline code paths; uses the same silent replay as diagnostic_quality_pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from subprocess import run as subprocess_run
from typing import Any

from renaissance_v4.core.performance_metrics import compute_summary_metrics
from renaissance_v4.research.baseline_comparator import compare_summaries
from renaissance_v4.research.diagnostic_quality_pipeline import run_silent_replay
from renaissance_v4.research.experiment_tracker import ExperimentRecord, append_experiment
from renaissance_v4.research.monte_carlo import MonteCarloConfig, run_monte_carlo
from renaissance_v4.research.promotion_recommender import recommend
from renaissance_v4.research.trade_export import (
    export_trades_json,
    load_trades_json,
    outcomes_from_trade_dicts,
    pnl_series_from_trade_dicts,
)

RV4_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = RV4_ROOT / "state"
REPORTS_MC = RV4_ROOT / "reports" / "monte_carlo"
REPORTS_ROB = RV4_ROOT / "reports" / "robustness"
REPORTS_EXP = RV4_ROOT / "reports" / "experiments"
CONFIGS = RV4_ROOT / "configs" / "experiment_configs"

BASELINE_TAG = "RenaissanceV4_baseline_v1"
BASELINE_DET_JSON = STATE_DIR / "baseline_deterministic.json"
BASELINE_MC_JSON = STATE_DIR / "baseline_monte_carlo_summary.json"
BASELINE_TRADES_JSON = REPORTS_EXP / "baseline_v1_trades.json"


def _git_head() -> str:
    try:
        r = subprocess_run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(RV4_ROOT.parent),
            capture_output=True,
            text=True,
            check=False,
        )
        return (r.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


def _git_branch() -> str:
    try:
        r = subprocess_run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(RV4_ROOT.parent),
            capture_output=True,
            text=True,
            check=False,
        )
        return (r.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


def cmd_export_trades(args: argparse.Namespace) -> int:
    out = Path(args.output)
    outcomes, bars = run_silent_replay()
    export_trades_json(outcomes, out, dataset_bars=bars)
    det = compute_summary_metrics(sorted(outcomes, key=lambda o: o.exit_time))
    side = out.with_suffix(out.suffix + ".deterministic.json")
    side.write_text(json.dumps({"dataset_bars": bars, "deterministic": det}, indent=2), encoding="utf-8")
    print(f"[robustness] exported {len(outcomes)} trades to {out.resolve()}")
    print(f"[robustness] deterministic summary -> {side.resolve()}")
    return 0


def cmd_baseline_mc(args: argparse.Namespace) -> int:
    REPORTS_MC.mkdir(parents=True, exist_ok=True)
    REPORTS_EXP.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    outcomes, bars = run_silent_replay()
    ordered = sorted(outcomes, key=lambda o: o.exit_time)
    det = compute_summary_metrics(ordered)
    export_trades_json(outcomes, BASELINE_TRADES_JSON, dataset_bars=bars)

    pnls = [o.pnl for o in ordered]
    cfg = MonteCarloConfig(
        n_simulations=int(args.n_sims),
        seed=int(args.seed),
        modes=tuple(args.modes.split(",")),
        path_length=int(args.path_length) if args.path_length else None,
    )
    mc = run_monte_carlo(pnls, cfg)

    baseline_payload = {
        "baseline_tag": BASELINE_TAG,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_head": _git_head(),
        "git_branch": _git_branch(),
        "dataset_bars": bars,
        "deterministic": det,
        "monte_carlo_config": {
            "n_simulations": cfg.n_simulations,
            "seed": cfg.seed,
            "modes": list(cfg.modes),
            "path_length": cfg.path_length,
        },
        "monte_carlo": {m: mc.by_mode[m].to_summary_dict() for m in mc.by_mode},
    }
    BASELINE_DET_JSON.write_text(
        json.dumps(
            {"baseline_tag": BASELINE_TAG, "dataset_bars": bars, "deterministic": det},
            indent=2,
        ),
        encoding="utf-8",
    )
    BASELINE_MC_JSON.write_text(json.dumps(baseline_payload, indent=2), encoding="utf-8")

    report_path = REPORTS_MC / "monte_carlo_baseline_v1_reference.md"
    report_path.write_text(_render_mc_report("Baseline Monte Carlo reference", cfg, mc, det, bars), encoding="utf-8")
    print(f"[robustness] baseline deterministic -> {BASELINE_DET_JSON.resolve()}")
    print(f"[robustness] baseline Monte Carlo summary -> {BASELINE_MC_JSON.resolve()}")
    print(f"[robustness] baseline trades -> {BASELINE_TRADES_JSON.resolve()}")
    print(f"[robustness] report -> {report_path.resolve()}")
    return 0


def _render_mc_report(title: str, cfg: MonteCarloConfig, mc: Any, det: dict, bars: int) -> str:
    lines = [
        f"# {title}",
        "",
        f"Generated: **{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}**",
        "",
        "## Simulation settings",
        "",
        f"- **Modes:** {', '.join(cfg.modes)}",
        f"- **Simulations per mode:** {cfg.n_simulations}",
        f"- **RNG seed:** {cfg.seed}",
        f"- **Path length:** {cfg.path_length or 'len(trades)'}",
        f"- **Dataset bars (replay):** {bars}",
        "",
        "## Deterministic replay (authoritative first pass)",
        "",
        f"- **Trade count:** {det.get('total_trades', 0)}",
        f"- **Expectancy:** {det.get('expectancy', 0):.8f}",
        f"- **Max drawdown:** {det.get('max_drawdown', 0):.8f}",
        "",
        "## Monte Carlo by mode",
        "",
    ]
    for mode, mr in mc.by_mode.items():
        s = mr.to_summary_dict()
        lines.extend(
            [
                f"### `{mode}`",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Trade count (source) | {s['trade_count_source']} |",
                f"| Path length | {s['path_length']} |",
                f"| Median terminal PnL | {s['median_terminal_pnl']:.8f} |",
                f"| Mean terminal PnL | {s['mean_terminal_pnl']:.8f} |",
                f"| Worst / best terminal PnL | {s['worst_terminal_pnl']:.8f} / {s['best_terminal_pnl']:.8f} |",
                f"| p5 / p25 / p50 / p75 / p95 terminal | {s['p5_terminal']:.8f} / {s['p25_terminal']:.8f} / {s['p50_terminal']:.8f} / {s['p75_terminal']:.8f} / {s['p95_terminal']:.8f} |",
                f"| Mean / median max DD | {s['mean_max_drawdown']:.8f} / {s['median_max_drawdown']:.8f} |",
                f"| Worst max DD | {s['worst_max_drawdown']:.8f} |",
                f"| p95 max DD | {s['p95_max_drawdown']:.8f} |",
                f"| Simulations finishing negative | {s['simulations_terminal_negative']} ({100 * s['fraction_terminal_negative']:.2f}%) |",
                f"| Risk-of-ruin proxy (P(terminal<0)) | {s['risk_of_ruin_proxy']:.6f} |",
                "",
            ]
        )
    lines.append(
        "*Monte Carlo does not replace deterministic replay — it stress-tests sequence / resampling of the same closed-trade PnL set.*"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def cmd_compare(args: argparse.Namespace) -> int:
    if not BASELINE_MC_JSON.exists() or not BASELINE_DET_JSON.exists():
        print(
            "[robustness] ERROR: Baseline reference missing. Run first:\n"
            "  python -m renaissance_v4.research.robustness_runner baseline-mc --seed 42",
            file=sys.stderr,
        )
        return 1

    baseline_full = json.loads(BASELINE_MC_JSON.read_text(encoding="utf-8"))
    det_b = baseline_full["deterministic"]
    mc_b = baseline_full["monte_carlo"]

    cpath = Path(args.candidate_trades)
    trades, _bars = load_trades_json(cpath)
    outs = outcomes_from_trade_dicts(trades)
    det_c = compute_summary_metrics(outs)
    pnls = pnl_series_from_trade_dicts(trades)

    cfg = MonteCarloConfig(
        n_simulations=int(args.n_sims),
        seed=int(args.seed),
        modes=tuple(args.modes.split(",")),
        path_length=int(args.path_length) if args.path_length else None,
    )
    mc_run = run_monte_carlo(pnls, cfg)
    mc_c = {m: mc_run.by_mode[m].to_summary_dict() for m in mc_run.by_mode}

    primary_mode = args.primary_mode
    if primary_mode not in mc_c:
        primary_mode = list(mc_c.keys())[0]

    comp = compare_summaries(
        baseline_tag=BASELINE_TAG,
        candidate_label=args.experiment_id,
        det_baseline=det_b,
        det_candidate=det_c,
        mc_baseline_by_mode=mc_b,
        mc_candidate_by_mode=mc_c,
    )

    rec = recommend(
        det_baseline=det_b,
        det_candidate=det_c,
        mc_mode=primary_mode,
        mc_baseline=mc_b[primary_mode],
        mc_candidate=mc_c[primary_mode],
    )

    REPORTS_ROB.mkdir(parents=True, exist_ok=True)
    REPORTS_EXP.mkdir(parents=True, exist_ok=True)
    REPORTS_MC.mkdir(parents=True, exist_ok=True)

    rob_path = REPORTS_ROB / f"robustness_{args.experiment_id}.md"
    mc_path = REPORTS_MC / f"monte_carlo_{args.experiment_id}.md"
    exp_path = REPORTS_EXP / f"experiment_{args.experiment_id}.md"

    mc_path.write_text(
        _render_mc_report(
            f"Monte Carlo — {args.experiment_id}",
            cfg,
            mc_run,
            det_c,
            int(baseline_full.get("dataset_bars", 0)),
        ),
        encoding="utf-8",
    )

    summary_json = STATE_DIR / f"monte_carlo_{args.experiment_id}_summary.json"
    summary_json.write_text(
        json.dumps(
            {
                "experiment_id": args.experiment_id,
                "candidate_trades": str(cpath.resolve()),
                "deterministic": det_c,
                "monte_carlo": mc_c,
                "recommendation": rec.label,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    rob_path.write_text(
        _render_robustness_report(comp, rec, det_b, det_c, comp.monte_carlo_baseline_by_mode, comp.monte_carlo_candidate_by_mode, primary_mode),
        encoding="utf-8",
    )
    exp_path.write_text(
        _render_experiment_markdown(
            args,
            det_c,
            mc_c,
            rec,
            str(mc_path.relative_to(RV4_ROOT)),
            str(rob_path.relative_to(RV4_ROOT)),
        ),
        encoding="utf-8",
    )

    _now = datetime.now(timezone.utc).isoformat()
    append_experiment(
        ExperimentRecord(
            experiment_id=args.experiment_id,
            branch=args.branch or _git_branch(),
            commit_hash=args.commit or _git_head(),
            baseline_tag=BASELINE_TAG,
            description=args.description or "",
            subsystem=args.subsystem or "unspecified",
            status="complete",
            deterministic_summary_path=str((RV4_ROOT / "state" / f"deterministic_{args.experiment_id}.json").resolve()),
            monte_carlo_summary_path=str(summary_json.resolve()),
            comparison_report_path=str(rob_path.resolve()),
            recommendation=rec.label,
            created_at=_now,
            completed_at=_now,
            files_changed=list(args.files_changed or []),
            extra={
                "experiment_type": "robustness_compare",
                "candidate_trades": str(cpath),
            },
        )
    )
    (STATE_DIR / f"deterministic_{args.experiment_id}.json").write_text(
        json.dumps({"deterministic": det_c}, indent=2),
        encoding="utf-8",
    )

    print(f"[robustness] recommendation: **{rec.label}** — {('; '.join(rec.reasons))}")
    print(f"[robustness] comparison report -> {rob_path.resolve()}")
    return 0


def _render_robustness_report(comp: Any, rec: Any, det_b: dict, det_c: dict, mc_b: dict, mc_c: dict, mode: str) -> str:
    d = comp.deterministic
    return "\n".join(
        [
            "# Robustness comparison",
            "",
            f"**Candidate:** {comp.candidate_label}",
            f"**Baseline tag:** {comp.baseline_tag}",
            "",
            "## Deterministic (authoritative)",
            "",
            "| Metric | Baseline | Candidate | Delta |",
            "|--------|----------|-----------|-------|",
            f"| Trades | {det_b.get('total_trades')} | {det_c.get('total_trades')} | {d['delta_total_trades']:+d} |",
            f"| Expectancy | {det_b.get('expectancy'):.8f} | {det_c.get('expectancy'):.8f} | {d['delta_expectancy']:.8f} |",
            f"| Max drawdown | {det_b.get('max_drawdown'):.8f} | {det_c.get('max_drawdown'):.8f} | {d['delta_max_drawdown']:.8f} |",
            "",
            f"## Monte Carlo (mode: `{mode}`)",
            "",
            "| Metric | Baseline | Candidate |",
            "|--------|----------|-------------|",
            f"| Median terminal PnL | {mc_b[mode]['median_terminal_pnl']:.8f} | {mc_c[mode]['median_terminal_pnl']:.8f} |",
            f"| Median max DD | {mc_b[mode]['median_max_drawdown']:.8f} | {mc_c[mode]['median_max_drawdown']:.8f} |",
            f"| Fraction terminal negative | {mc_b[mode]['fraction_terminal_negative']:.4f} | {mc_c[mode]['fraction_terminal_negative']:.4f} |",
            "",
            "## Recommendation (advisory — not auto-promotion)",
            "",
            f"**{rec.label}**",
            "",
            "### Reasons",
            "",
            *[f"- {r}" for r in rec.reasons],
            "",
            "### Risk notes",
            "",
            "- Monte Carlo stress-tests the **same** closed-trade PnL set; it does not invent trades.",
            "- If candidate and baseline trades differ, differences reflect **deterministic replay** on different code/config — compare branches explicitly.",
            "",
        ]
    ) + "\n"


def _render_experiment_markdown(
    args: argparse.Namespace,
    det_c: dict,
    mc_c: dict,
    rec: Any,
    mc_rel: str,
    rob_rel: str,
) -> str:
    return "\n".join(
        [
            f"# Experiment `{args.experiment_id}`",
            "",
            "## Lineage",
            "",
            f"- **Baseline tag:** {BASELINE_TAG}",
            f"- **Branch:** {args.branch or _git_branch()}",
            f"- **Commit:** {args.commit or _git_head()}",
            f"- **Subsystem:** {args.subsystem or 'unspecified'}",
            "",
            "## Change description",
            "",
            args.description or "_No description provided._",
            "",
            "## Files / constants (declared)",
            "",
            *[f"- {f}" for f in (args.files_changed or ["_see branch diff_"])],
            "",
            "## Deterministic summary (candidate)",
            "",
            "```json",
            json.dumps(det_c, indent=2),
            "```",
            "",
            "## Monte Carlo modes (candidate)",
            "",
            "```json",
            json.dumps(mc_c, indent=2),
            "```",
            "",
            "## Reports",
            "",
            f"- Monte Carlo: `{mc_rel}`",
            f"- Robustness: `{rob_rel}`",
            "",
            "## Status",
            "",
            f"- **Recommendation:** {rec.label}",
            "- **Architect approval:** pending (governed loop)",
            "",
        ]
    ) + "\n"


def cmd_example_flow(args: argparse.Namespace) -> int:
    """Run compare using baseline trade file as candidate (sanity: should be inconclusive or improve)."""
    if not BASELINE_TRADES_JSON.exists():
        print("[robustness] Run baseline-mc first to create baseline trades.", file=sys.stderr)
        return 1
    c = argparse.Namespace(
        experiment_id=getattr(args, "experiment_id", None) or "example_shadow",
        candidate_trades=str(BASELINE_TRADES_JSON),
        n_sims=args.n_sims,
        seed=args.seed,
        modes=args.modes,
        path_length=args.path_length,
        primary_mode=args.primary_mode,
        description="Example: candidate trade list == baseline export (sanity check).",
        subsystem="none",
        branch=_git_branch(),
        commit=_git_head(),
        files_changed=[],
    )
    return cmd_compare(c)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RenaissanceV4 robustness & Monte Carlo runner")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_exp = sub.add_parser("export-trades", help="Deterministic replay only — export normalized trades JSON")
    p_exp.add_argument("--output", type=str, required=True, help="Output JSON path")
    p_exp.set_defaults(func=cmd_export_trades)

    p_bl = sub.add_parser("baseline-mc", help="Replay + export baseline trades + Monte Carlo reference artifacts")
    p_bl.add_argument("--n-sims", type=int, default=10_000)
    p_bl.add_argument("--seed", type=int, default=42)
    p_bl.add_argument("--modes", type=str, default="shuffle,bootstrap")
    p_bl.add_argument("--path-length", type=int, default=None)
    p_bl.set_defaults(func=cmd_baseline_mc)

    p_cmp = sub.add_parser("compare", help="Candidate trades vs frozen baseline reference")
    p_cmp.add_argument("--experiment-id", type=str, required=True)
    p_cmp.add_argument("--candidate-trades", type=str, required=True)
    p_cmp.add_argument("--n-sims", type=int, default=10_000)
    p_cmp.add_argument("--seed", type=int, default=42)
    p_cmp.add_argument("--modes", type=str, default="shuffle,bootstrap")
    p_cmp.add_argument("--path-length", type=int, default=None)
    p_cmp.add_argument("--primary-mode", type=str, default="shuffle")
    p_cmp.add_argument("--description", type=str, default="")
    p_cmp.add_argument("--subsystem", type=str, default="")
    p_cmp.add_argument("--branch", type=str, default="")
    p_cmp.add_argument("--commit", type=str, default="")
    p_cmp.add_argument("--files-changed", nargs="*", default=[])
    p_cmp.set_defaults(func=cmd_compare)

    p_ex = sub.add_parser("example-flow", help="Compare baseline trades to themselves (pipeline check)")
    p_ex.add_argument("--n-sims", type=int, default=2000)
    p_ex.add_argument("--seed", type=int, default=42)
    p_ex.add_argument("--modes", type=str, default="shuffle,bootstrap")
    p_ex.add_argument("--path-length", type=int, default=None, dest="path_length")
    p_ex.add_argument("--primary-mode", type=str, default="shuffle")
    p_ex.add_argument("--experiment-id", type=str, default="example_shadow")
    p_ex.set_defaults(func=cmd_example_flow)

    return p


def main() -> int:
    parser = build_parser()
    ns = parser.parse_args()
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())
