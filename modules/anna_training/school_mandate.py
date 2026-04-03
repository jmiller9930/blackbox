"""School mandate — forces explicit 'keep doing harness work' FACTs into Anna's analyst path.

Canon: learning through repeated measured attempts until gates pass; a single lucky trade does not
satisfy graduation. These lines merge into ``facts_for_prompt`` (see ``carryforward_fact_lines``).
"""

from __future__ import annotations

from typing import Any, Mapping


def build_school_mandate_fact_lines(
    *,
    g12: Mapping[str, Any],
    st: Mapping[str, Any] | None = None,
) -> list[str]:
    """
    Short strings, no Rich markup. Safe to inject as FACT (school mandate): …
    """
    st = st or {}
    n = st.get("karpathy_loop_iteration")
    it_note = f" (supervisor iteration {n})" if n is not None else ""

    if bool(g12.get("pass")):
        return [
            f"Grade-12 overall gate PASS{it_note} — continue disciplined measurement; promotion remains human-governed."
        ]

    ct = bool(g12.get("curriculum_tools_pass"))
    ng = bool(g12.get("numeric_gate_pass"))

    if not ct:
        cf = g12.get("grade_12_current_focus") or "first missing curriculum tool in deck order"
        return [
            "School requires sequential curriculum work until all four tools pass — supervisor ticks alone do not complete tools.",
            f"Current required focus only: {cf}",
            "After evidence, use operator `anna tool-pass <id>` when policy requires manual attestation.",
        ]

    if not ng:
        dec = int(g12.get("decisive_trades") or 0)
        mind = int(g12.get("min_decisive_trades") or 30)
        wr = g12.get("win_rate")
        min_wr = float(g12.get("min_win_rate") or 0.6)
        wr_s = f"{float(wr):.0%}" if wr is not None else "n/a"
        lines = [
            "School mandate: numeric paper cohort gate NOT satisfied — continue the paper harness until decisive count and win-rate floor meet policy.",
            "One winning trade does not complete learning; the program scores a distribution over many decisive outcomes, not a single event.",
            f"Cohort evidence now: decisive {dec}/{mind}; win rate {wr_s} vs floor {min_wr:.0%}.",
        ]
        nb = g12.get("numeric_blockers") or []
        if nb:
            lines.append("Gate blockers: " + " | ".join(str(x) for x in nb[:5]))
        lines.append(
            "Required work: produce more logged paper outcomes (harness / execution path / operator log-trade) until the gate clears."
        )
        return lines

    return [
        f"School mandate: unexpected gate state (tools PASS, numeric PASS, overall NOT PASS){it_note} — run `anna gates` and inspect blockers."
    ]


def compute_school_mandate_payload(st: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persisted snapshot for status.json / heartbeats (daemon). Analyst path uses fresh gates via FACT merge."""
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.store import load_state

    raw = load_state() if st is None else st
    g12 = evaluate_grade12_gates(training_state=raw)
    fact_lines = build_school_mandate_fact_lines(g12=g12, st=raw)
    return {
        "version": 1,
        "gate_pass": bool(g12.get("pass")),
        "curriculum_tools_pass": bool(g12.get("curriculum_tools_pass")),
        "numeric_gate_pass": bool(g12.get("numeric_gate_pass")),
        "karpathy_loop_iteration": raw.get("karpathy_loop_iteration"),
        "fact_lines": fact_lines,
    }
