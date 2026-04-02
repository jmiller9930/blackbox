"""
Chris Coinbase paper dataset + score surfaces (12th-grade paper-only contract, CANONICAL #137 draft).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ChrisPaperDecisionRecordV1:
    decision_id: str
    intent_id: str
    candidate_id: str
    signal_id: str
    participant_id: str
    account_id: str
    risk_tier: str
    decision_at_utc: str
    decision_summary: str


@dataclass(frozen=True)
class ChrisPaperOutcomeRecordV1:
    outcome_id: str
    intent_id: str
    decision_id: str
    venue_status: str
    recorded_at_utc: str
    filled_quantity: str
    avg_fill_price: str
    fees_total: str
    realized_pnl: str
    baseline_pnl: str


@dataclass(frozen=True)
class ChrisPaperRcsReflectionLinkV1:
    reflection_id: str
    decision_id: str
    outcome_id: str
    linked_at_utc: str


@dataclass(frozen=True)
class ChrisPaperArtifactBundleV1:
    decision: ChrisPaperDecisionRecordV1
    outcome: ChrisPaperOutcomeRecordV1
    rcs_link: ChrisPaperRcsReflectionLinkV1


@dataclass(frozen=True)
class ChrisScoreSurfacesV1:
    win_rate: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    baseline_delta: float


def _to_f(v: str) -> float:
    return float(v.strip())


def _bundle_to_dict(bundle: ChrisPaperArtifactBundleV1) -> dict[str, dict[str, str]]:
    return {
        "decision": bundle.decision.__dict__,
        "outcome": bundle.outcome.__dict__,
        "rcs_link": bundle.rcs_link.__dict__,
    }


def _bundle_canonical_json(bundle: ChrisPaperArtifactBundleV1) -> str:
    return json.dumps(_bundle_to_dict(bundle), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def ensure_chris_paper_artifact_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chris_paper_artifacts_v1 (
            participant_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            decision_id TEXT NOT NULL,
            outcome_id TEXT NOT NULL,
            reflection_id TEXT NOT NULL,
            recorded_at_utc TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            canonical_hash TEXT NOT NULL,
            PRIMARY KEY (participant_id, account_id, decision_id, outcome_id)
        )
        """
    )
    conn.commit()


def write_chris_paper_artifact_bundle(
    conn: sqlite3.Connection,
    bundle: ChrisPaperArtifactBundleV1,
) -> tuple[bool, str]:
    ok, reason = validate_chris_artifact_bundle(bundle)
    if not ok:
        return False, reason
    payload = _bundle_canonical_json(bundle)
    chash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    pid = bundle.decision.participant_id
    aid = bundle.decision.account_id
    did = bundle.decision.decision_id
    oid = bundle.outcome.outcome_id
    rid = bundle.rcs_link.reflection_id
    rat = bundle.outcome.recorded_at_utc
    row = conn.execute(
        """
        SELECT payload_json, canonical_hash
        FROM chris_paper_artifacts_v1
        WHERE participant_id=? AND account_id=? AND decision_id=? AND outcome_id=?
        """,
        (pid, aid, did, oid),
    ).fetchone()
    if row is not None:
        stored_payload, stored_hash = row
        cur_hash = hashlib.sha256(stored_payload.encode("utf-8")).hexdigest()
        if cur_hash != stored_hash:
            return False, "stored payload/hash mismatch"
        if stored_hash == chash:
            return True, ""
        return False, "existing bundle key has different canonical payload"
    try:
        conn.execute(
            """
            INSERT INTO chris_paper_artifacts_v1 (
              participant_id, account_id, decision_id, outcome_id, reflection_id,
              recorded_at_utc, payload_json, canonical_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pid, aid, did, oid, rid, rat, payload, chash),
        )
        conn.commit()
    except sqlite3.Error as e:
        return False, f"sqlite write error: {e}"
    return True, ""


def read_chris_paper_bundles(
    conn: sqlite3.Connection,
    *,
    participant_id: str,
    account_id: str,
) -> list[ChrisPaperArtifactBundleV1]:
    rows = conn.execute(
        """
        SELECT payload_json FROM chris_paper_artifacts_v1
        WHERE participant_id=? AND account_id=?
        ORDER BY recorded_at_utc ASC, decision_id ASC
        """,
        (participant_id, account_id),
    ).fetchall()
    out: list[ChrisPaperArtifactBundleV1] = []
    for (payload_json,) in rows:
        raw = json.loads(payload_json)
        d = ChrisPaperDecisionRecordV1(**raw["decision"])
        o = ChrisPaperOutcomeRecordV1(**raw["outcome"])
        r = ChrisPaperRcsReflectionLinkV1(**raw["rcs_link"])
        out.append(ChrisPaperArtifactBundleV1(decision=d, outcome=o, rcs_link=r))
    return out


def validate_chris_artifact_bundle(bundle: ChrisPaperArtifactBundleV1) -> tuple[bool, str]:
    if bundle.decision.decision_id != bundle.outcome.decision_id:
        return False, "decision_id mismatch between decision and outcome records"
    if bundle.decision.intent_id != bundle.outcome.intent_id:
        return False, "intent_id mismatch between decision and outcome records"
    if bundle.rcs_link.decision_id != bundle.decision.decision_id:
        return False, "RCS decision_id does not link to decision record"
    if bundle.rcs_link.outcome_id != bundle.outcome.outcome_id:
        return False, "RCS outcome_id does not link to outcome record"
    return True, ""


def compute_chris_score_surfaces(bundles: Iterable[ChrisPaperArtifactBundleV1]) -> ChrisScoreSurfacesV1:
    rows = list(bundles)
    if not rows:
        return ChrisScoreSurfacesV1(0.0, 0.0, 0.0, 0.0, 0.0)

    pnl: list[float] = []
    baseline_delta = 0.0
    for b in rows:
        ok, reason = validate_chris_artifact_bundle(b)
        if not ok:
            raise ValueError(f"invalid artifact bundle: {reason}")
        p = _to_f(b.outcome.realized_pnl)
        bl = _to_f(b.outcome.baseline_pnl)
        pnl.append(p)
        baseline_delta += p - bl

    n = len(pnl)
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]
    win_rate = float(len(wins)) / float(n)
    expectancy = sum(pnl) / float(n)
    if losses:
        profit_factor = sum(wins) / abs(sum(losses)) if wins else 0.0
    else:
        profit_factor = float("inf") if wins else 0.0

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in pnl:
        equity += x
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    return ChrisScoreSurfacesV1(
        win_rate=win_rate,
        expectancy=expectancy,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        baseline_delta=baseline_delta,
    )

